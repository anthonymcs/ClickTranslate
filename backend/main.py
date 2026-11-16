"""
Servidor FastAPI para ClickTranslate.
Procesamiento 100% en memoria RAM (Zero Persistence).
Optimizado para traducción instantánea multi-idioma (esquema Google Translate + Ollama local).
"""

import io
import os
import sys

# Configurar salida estándar en UTF-8 en Windows para evitar UnicodeEncodeError con kanjis/acentos
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Evitar consultas de red lentas a Hugging Face en cada llamada de OCR
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import gc
import uuid
import json
import base64
import asyncio
import zipfile
import logging
import unicodedata
from typing import Dict, Any, Optional, Tuple

import cv2
import numpy as np
from natsort import natsorted
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from PIL import Image
from core.comic_detector import detect_comic_text
from core.detector import detect_balloons_and_sfx, get_dominant_bg_color, sort_blocks, TextBlock
from core.ocr_engine import run_ocr, get_manga_ocr, get_rapid_ocr
from core.inpainter import clean_page
from core.translator import translate_page_contextual, fetch_available_models
from core.typesetter import render_typesetting

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("ClickTranslate.Server")

app = FastAPI(
    title="ClickTranslate Backend",
    version="1.1.0",
    description="Motor de traducción visual para cómics, mangas y manhwas sin persistencia en disco"
)

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BATCH_JOBS: Dict[str, Dict[str, Any]] = {}
VALID_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def process_single_image_in_memory(
    image_bytes: bytes,
    src_lang: str = "auto",
    tgt_lang: str = "es",
    model_name: str = "fast"
) -> Tuple[bytes, bytes]:
    """
    Ejecuta el pipeline de traducción completo sobre los bytes de una imagen en memoria RAM.
    Integra Comic-Text-Detector (IA especializada en mangas/cómics) + Manga-OCR / RapidOCR.
    Retorna: (imagen_traducida_png_bytes, miniatura_jpeg_bytes)
    """
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if img_bgr is None:
        raise ValueError("No se pudo decodificar la imagen proporcionada.")

    im_h, im_w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    lang_code = (src_lang or "auto").lower().strip()
    is_japanese = lang_code in ["ja", "jp", "japanese", "japonés", "japones"]

    # 1. Detección neuronal especializada con Comic-Text-Detector (ONNX)
    comic_blocks, text_mask = detect_comic_text(img_bgr)

    if comic_blocks:
        logger.info(f"ComicDetector identificó {len(comic_blocks)} regiones en la página.")
        manga_engine = get_manga_ocr() if is_japanese else None
        rapid_engine = get_rapid_ocr()

        reading_dir = "rtl" if lang_code in ["ja", "jp", "auto"] else "ltr"
        raw_blocks = []
        cleaned_img = img_bgr.copy()

        # Detección de contornos reales de globos de diálogo para ajuste scanlation
        _, thresh = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        balloon_contours = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            bx, by, bw, bh = cv2.boundingRect(cnt)
            if area > 800 and (bw < im_w * 0.90 and bh < im_h * 0.90):
                balloon_contours.append((cnt, (bx, by, bx + bw, by + bh)))

        for idx, cb in enumerate(comic_blocks):
            x1, y1, x2, y2 = cb["box"]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(im_w, x2), min(im_h, y2)
            bw, bh = x2 - x1, y2 - y1
            if bw < 10 or bh < 10:
                continue

            crop_bgr = img_bgr[y1:y2, x1:x2]
            is_vertical = bool(cb.get("vertical", False))
            cb_lines = cb.get("lines", [])

            center_pt = ((x1 + x2) // 2, (y1 + y2) // 2)
            matching_balloon = None
            matching_cnt = None
            for cnt, bbox in balloon_contours:
                bx_c, by_c, bx2_c, by2_c = bbox
                bw_c, bh_c = bx2_c - bx_c, by2_c - by_c
                if cv2.pointPolygonTest(cnt, center_pt, False) >= 0:
                    if (bw_c * bh_c) <= (bw * bh * 5.5):
                        matching_balloon = bbox
                        matching_cnt = cnt
                        break

            # OCR Inteligente Multi-idioma con soporte por línea en bloques horizontales
            def contains_kana(txt: str) -> bool:
                return any((0x3040 <= ord(c) <= 0x309F) or (0x30A0 <= ord(c) <= 0x30FF) for c in txt)

            def ocr_japanese_crop(c_bgr: np.ndarray) -> str:
                nonlocal manga_engine
                if c_bgr.size == 0:
                    return ""
                if manga_engine is None:
                    manga_engine = get_manga_ocr()
                if manga_engine is not None:
                    try:
                        c_rgb = cv2.cvtColor(c_bgr, cv2.COLOR_BGR2RGB)
                        return manga_engine(Image.fromarray(c_rgb)).strip()
                    except Exception as e:
                        logger.warning(f"Error Manga-OCR: {e}")
                return ""

            extracted_text = ""
            if is_japanese:
                # Si es un bloque horizontal con múltiples líneas (ej. fecha + subtítulo), leer línea por línea sin duplicados
                if not is_vertical and len(cb_lines) > 1:
                    raw_lboxes = []
                    for poly in cb_lines:
                        pts = np.array(poly)
                        lx1, ly1 = max(0, int(pts[:, 0].min()) - 4), max(0, int(pts[:, 1].min()) - 4)
                        lx2, ly2 = min(im_w, int(pts[:, 0].max()) + 4), min(im_h, int(pts[:, 1].max()) + 4)
                        if lx2 - lx1 >= 12 and ly2 - ly1 >= 12:
                            raw_lboxes.append([ly1, lx1, lx2, ly2])
                    raw_lboxes.sort(key=lambda b: b[0])
                    # Fusionar líneas que se solapen verticalmente (> 45% de su altura)
                    dedup_lboxes = []
                    for lb in raw_lboxes:
                        if not dedup_lboxes:
                            dedup_lboxes.append(lb)
                        else:
                            prev = dedup_lboxes[-1]
                            ov_y = max(0, min(prev[3], lb[3]) - max(prev[0], lb[0]))
                            min_h = min(prev[3] - prev[0], lb[3] - lb[0])
                            if min_h > 0 and (ov_y / min_h) >= 0.45:
                                prev[0] = min(prev[0], lb[0])
                                prev[1] = min(prev[1], lb[1])
                                prev[2] = max(prev[2], lb[2])
                                prev[3] = max(prev[3], lb[3])
                            else:
                                dedup_lboxes.append(lb)
                    line_texts = []
                    for (ly1, lx1, lx2, ly2) in dedup_lboxes:
                        lt = ocr_japanese_crop(img_bgr[ly1:ly2, lx1:lx2])
                        if lt:
                            line_texts.append(unicodedata.normalize("NFKC", lt).strip())
                    extracted_text = "\n".join(line_texts).strip()

                if not extracted_text:
                    extracted_text = ocr_japanese_crop(crop_bgr)

                if not extracted_text and rapid_engine is not None and crop_bgr.size > 0:
                    r_res, _ = rapid_engine(crop_bgr)
                    if r_res:
                        extracted_text = " ".join([item[1] for item in r_res]).strip()
            else:
                # Inglés, coreano, chino o modo 'auto': RapidOCR procesa primero con orden vertical y horizontal
                if rapid_engine is not None and crop_bgr.size > 0:
                    try:
                        r_res, _ = rapid_engine(crop_bgr)
                        if r_res:
                            lines_grouped = []
                            for item in r_res:
                                iy = item[0][0][1]
                                ix = item[0][0][0]
                                itxt = item[1]
                                placed = False
                                for lg in lines_grouped:
                                    if abs(lg["y"] - iy) <= 7:
                                        lg["items"].append((ix, itxt))
                                        placed = True
                                        break
                                if not placed:
                                    lines_grouped.append({"y": iy, "items": [(ix, itxt)]})
                            lines_grouped.sort(key=lambda l: l["y"])
                            full_lines = []
                            for lg in lines_grouped:
                                lg["items"].sort(key=lambda w: w[0])
                                full_lines.append(" ".join([w[1] for w in lg["items"]]))
                            extracted_text = " ".join(full_lines).strip()
                    except Exception as e:
                        logger.warning(f"Error RapidOCR: {e}")

                # Si en modo 'auto' el texto extraído contiene Kana japonés, usar Manga-OCR
                if lang_code == "auto" and contains_kana(extracted_text):
                    if not is_vertical and len(cb_lines) > 1:
                        line_boxes = []
                        for poly in cb_lines:
                            pts = np.array(poly)
                            lx1, ly1 = max(0, int(pts[:, 0].min()) - 4), max(0, int(pts[:, 1].min()) - 4)
                            lx2, ly2 = min(im_w, int(pts[:, 0].max()) + 4), min(im_h, int(pts[:, 1].max()) + 4)
                            if lx2 - lx1 >= 8 and ly2 - ly1 >= 8:
                                line_boxes.append((ly1, lx1, lx2, ly2))
                        line_boxes.sort(key=lambda b: b[0])
                        line_texts = [ocr_japanese_crop(img_bgr[ly1:ly2, lx1:lx2]) for (ly1, lx1, lx2, ly2) in line_boxes]
                        m_txt = "\n".join([t for t in line_texts if t]).strip()
                    else:
                        m_txt = ocr_japanese_crop(crop_bgr)
                    if m_txt and contains_kana(m_txt):
                        extracted_text = m_txt

            # Normalizar NFKC estrictamente para eliminar fullwidth characters (evita cuadrados/tofu)
            extracted_text = unicodedata.normalize("NFKC", extracted_text).strip()

            if not extracted_text:
                continue

            # Análisis cromático de precisión: separar núcleo de letra, contorno (stroke/glow) y fondo real
            pad = max(8, int(min(bw, bh) * 0.10))
            px1, py1 = max(0, x1 - pad), max(0, y1 - pad)
            px2, py2 = min(im_w, x2 + pad), min(im_h, y2 + pad)

            sub_orig = img_bgr[py1:py2, px1:px2]
            sub_mask = text_mask[py1:py2, px1:px2]

            r_stroke = max(6, min(24, int(min(bw, bh) * 0.14)))
            k_search = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_stroke + 1, 2 * r_stroke + 1))
            search_zone = cv2.dilate(sub_mask, k_search, iterations=1) if np.count_nonzero(sub_mask) > 0 else np.zeros_like(sub_mask)

            bg_pixels = sub_orig[search_zone == 0]
            if len(bg_pixels) > 10:
                bg_median = np.median(bg_pixels, axis=0).astype(np.uint8)
                bg_dists = np.linalg.norm(bg_pixels.astype(np.float32) - bg_median.astype(np.float32), axis=1)
                uniform_ratio = float(np.mean(bg_dists < 16.0))
            else:
                dom_c, unif_c = get_dominant_bg_color(img_bgr, (x1, y1, x2, y2))
                bg_median = np.array(dom_c, dtype=np.uint8)
                uniform_ratio = 0.90 if unif_c else 0.30

            bg_bright = float(np.mean(bg_median))
            dom_color = (int(bg_median[0]), int(bg_median[1]), int(bg_median[2]))
            is_uniform = uniform_ratio >= 0.80

            # Extraer color de letra y color de contorno antes de limpiar
            core_px = sub_orig[sub_mask > 127]
            fg_bgr = np.median(core_px, axis=0).astype(int) if len(core_px) > 5 else (np.array([0, 0, 0]) if bg_bright > 160 else np.array([255, 255, 255]))

            k_in = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            k_mid = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(9, r_stroke | 1), max(9, r_stroke | 1)))
            ring_zone = (cv2.dilate(sub_mask, k_mid) > 0) & (cv2.dilate(sub_mask, k_in) == 0)
            ring_px = sub_orig[ring_zone]
            stroke_bgr = None
            if len(ring_px) > 10:
                ring_diff = np.linalg.norm(ring_px.astype(np.float32) - bg_median.astype(np.float32), axis=1)
                stroke_candidates = ring_px[ring_diff > 35.0]
                if len(stroke_candidates) > 8:
                    stroke_bgr = np.percentile(stroke_candidates, 75, axis=0).astype(int)

            # Verificar color de fondo interior inmediato dentro de la caja (para distinguir mini-globos blancos de fondos crema)
            inner_tmask = text_mask[y1:y2, x1:x2]
            k_inner_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            inner_free = cv2.dilate(inner_tmask, k_inner_dil, iterations=1) == 0
            inner_bg_px = img_bgr[y1:y2, x1:x2][inner_free]
            if len(inner_bg_px) > 12:
                local_bg_median = np.median(inner_bg_px, axis=0).astype(np.uint8)
            else:
                local_bg_median = bg_median

            fg_sat = int(np.max(fg_bgr)) - int(np.min(fg_bgr))

            # Clasificación de bloque y limpieza visual impecable
            is_dark_neutral_text = (float(np.mean(fg_bgr)) < 115.0) and (fg_sat < 45)
            if matching_balloon or (is_uniform and bg_bright > 195 and is_dark_neutral_text):
                block_type = "dialog"
                if matching_balloon:
                    bx1, by1, bx2, by2 = matching_balloon
                    eff_box = (bx1 + 6, max(y1, by1 + 6), bx2 - 6, min(y2, by2 - 6))
                else:
                    eff_box = (x1, y1, x2, y2)

                text_color = (0, 0, 0)
                stroke_color = None
                fill_c = (255, 255, 255) if bg_bright > 210 else dom_color

                # Si tenemos el contorno exacto del globo, rellenar su interior erosionado 2px (borra 100% del texto sin tocar el borde negro)
                if matching_cnt is not None:
                    b_mask = np.zeros_like(gray)
                    cv2.drawContours(b_mask, [matching_cnt], -1, 255, cv2.FILLED)
                    k_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                    b_eroded = cv2.erode(b_mask, k_erode, iterations=1)
                    cleaned_img[b_eroded > 0] = fill_c
                else:
                    p_gray = gray[y1:y2, x1:x2]
                    if np.count_nonzero(inner_tmask) > 0:
                        k_guide = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
                        guide_zone = cv2.dilate(inner_tmask, k_guide, iterations=1)
                        erase_m = (guide_zone > 0) & (p_gray < 235)
                    else:
                        erase_m = p_gray < 220
                    cleaned_img[y1:y2, x1:x2][erase_m] = fill_c
            else:
                block_type = "sfx"
                eff_box = (x1, y1, x2, y2)

                if float(np.mean(fg_bgr)) > 175:
                    text_color = (255, 255, 255)
                    stroke_color = (int(stroke_bgr[2]), int(stroke_bgr[1]), int(stroke_bgr[0])) if stroke_bgr is not None else (0, 0, 0)
                else:
                    text_color = (int(fg_bgr[2]), int(fg_bgr[1]), int(fg_bgr[0]))
                    stroke_color = (int(stroke_bgr[2]), int(stroke_bgr[1]), int(stroke_bgr[0])) if stroke_bgr is not None else (255, 255, 255)

                if bg_bright > 180 and (fg_sat > 25 or (stroke_bgr is not None and (int(np.max(stroke_bgr)) - int(np.min(stroke_bgr))) > 25)):
                    # Texto o SFX a color sobre fondo claro o dentro de mini-globo blanco:
                    sub_clean = cleaned_img[py1:py2, px1:px2]
                    sub_g = gray[py1:py2, px1:px2]
                    sub_sat = np.max(sub_clean, axis=2).astype(int) - np.min(sub_clean, axis=2).astype(int)
                    is_black_lineart = (sub_g < 232) & (sub_sat < 18)
                    has_balloon_border = float(np.mean((sub_g < 180) & (sub_sat < 18))) >= 0.02
                    target_fill = np.array([255, 255, 255], dtype=np.uint8) if has_balloon_border else bg_median
                    diff_target = np.linalg.norm(sub_clean.astype(np.float32) - target_fill.astype(np.float32), axis=2)
                    if has_balloon_border:
                        # Dentro de mini-globo con borde negro: borrar solo píxeles saturados (texto rosa/rojo) dentro del globo
                        erase_m = (search_zone > 0) & (~is_black_lineart) & (sub_sat >= 18)
                    else:
                        # SFX libre sobre fondo crema/claro: borrar tanto el color como su halo blanco hacia el color exacto del fondo
                        erase_m = (search_zone > 0) & (~is_black_lineart) & ((sub_sat >= 16) | (diff_target > 6.0))
                    sub_clean[erase_m] = target_fill
                    cleaned_img[py1:py2, px1:px2] = sub_clean
                elif is_uniform:
                    # Fondo uniforme (oscuro, negro o sólido): reemplazar núcleo + contorno con el color exacto del fondo (bg_median)
                    sub_clean = cleaned_img[py1:py2, px1:px2]
                    diff_all = np.linalg.norm(sub_clean.astype(np.float32) - bg_median.astype(np.float32), axis=2)
                    erase_m = (search_zone > 0) & (diff_all > 6.0)
                    sub_clean[erase_m] = bg_median
                    cleaned_img[py1:py2, px1:px2] = sub_clean
                else:
                    # Fondo con dibujo artístico complejo: dilatar máscara para cubrir todo el stroke antes de Telea
                    if np.count_nonzero(sub_mask) > 0:
                        r_inp = max(5, min(16, int(min(bw, bh) * 0.12)))
                        k_inp = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_inp + 1, 2 * r_inp + 1))
                        dilated = cv2.dilate(sub_mask, k_inp, iterations=1)
                        inpainted = cv2.inpaint(cleaned_img[py1:py2, px1:px2], dilated, 5, cv2.INPAINT_TELEA)
                        cleaned_img[py1:py2, px1:px2] = inpainted

            tb = TextBlock(
                id=idx + 1,
                box=eff_box,
                type=block_type,
                text=extracted_text,
                bg_color=dom_color,
                text_color=text_color,
                stroke_color=stroke_color,
                is_uniform_bg=is_uniform
            )
            raw_blocks.append(tb)

        blocks = sort_blocks(raw_blocks, reading_direction=reading_dir)
        for i, b in enumerate(blocks):
            b.id = i + 1

    else:
        # Fallback para imágenes generales donde no aplique modelo de cómic
        logger.info("Fallback a detección RapidOCR general.")
        ocr_results = run_ocr(img_bgr, raw_lang=src_lang)
        raw_boxes = [box for box, _ in ocr_results]
        blocks, balloon_mask, sfx_mask = detect_balloons_and_sfx(img_bgr, raw_boxes, lang=src_lang)
        for block in blocks:
            for (box, text) in ocr_results:
                if box == block.box:
                    block.text = text
                    break
        cleaned_img = clean_page(img_bgr, blocks, balloon_mask, sfx_mask)

    # 4. Traducción multi-idioma contextual
    translations = translate_page_contextual(
        blocks,
        model_name=model_name,
        src_lang=src_lang,
        tgt_lang=tgt_lang
    )

    for block in blocks:
        if block.id in translations:
            block.translated_text = unicodedata.normalize("NFKC", translations[block.id]).strip()

    # 5. Re-tipografía Scanlation profesional (Mayúsculas, centrado, ajuste en globo)
    final_bgr = render_typesetting(cleaned_img, blocks)

    # Codificar a PNG en memoria RAM
    success, png_buf = cv2.imencode(".png", final_bgr)
    if not success:
        raise RuntimeError("Error al codificar imagen traducida a PNG.")

    # Generar miniatura JPEG ligera para preview
    h, w = final_bgr.shape[:2]
    thumb_w = 400
    thumb_h = int(h * (thumb_w / max(1, w)))
    resized_thumb = cv2.resize(final_bgr, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
    _, thumb_buf = cv2.imencode(".jpg", resized_thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 75])

    # Liberar referencias para garbage collection
    del np_arr, img_bgr, cleaned_img, final_bgr, resized_thumb
    gc.collect()

    return png_buf.tobytes(), thumb_buf.tobytes()


@app.get("/health")
def health_check():
    """Verifica que el servicio esté activo y listo."""
    return {"status": "ok", "app": "ClickTranslate", "zero_persistence": True}


@app.get("/models")
async def list_models():
    """Obtiene los modelos disponibles en la instancia local de Ollama."""
    models = await fetch_available_models()
    return {"models": models}


@app.post("/translate-single")
async def translate_single(
    file: UploadFile = File(...),
    src_lang: str = Form("auto"),
    tgt_lang: str = Form("es"),
    model_name: str = Form("fast")
):
    """
    Traduce una imagen individual del portapapeles o archivo.
    Procesa estrictamente en memoria y retorna bytes PNG.
    """
    try:
        content = await file.read()
        translated_png, _ = process_single_image_in_memory(
            content,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            model_name=model_name
        )
        return Response(content=translated_png, media_type="image/png")
    except Exception as e:
        logger.error(f"Error procesando /translate-single: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        gc.collect()


async def run_batch_job_task(
    job_id: str,
    zip_bytes: bytes,
    src_lang: str,
    tgt_lang: str,
    model_name: str,
    out_ext: str
):
    """Tarea asíncrona de procesamiento de lote ZIP/CBZ página por página en RAM."""
    job_info = BATCH_JOBS.get(job_id)
    if not job_info:
        return

    try:
        in_memory_zip = zipfile.ZipFile(io.BytesIO(zip_bytes))
        all_entries = in_memory_zip.namelist()

        image_entries = [
            f for f in all_entries
            if not f.startswith("__MACOSX/")
            and not f.endswith("/")
            and not os.path.basename(f).startswith(".")
            and f.lower().endswith(VALID_IMAGE_EXTENSIONS)
        ]

        sorted_images = natsorted(image_entries)
        total_pages = len(sorted_images)

        if total_pages == 0:
            job_info["status"] = "error"
            job_info["error"] = "El archivo ZIP/CBZ no contiene imágenes válidas."
            return

        job_info["total"] = total_pages

        out_memory_buffer = io.BytesIO()
        with zipfile.ZipFile(out_memory_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as out_zip:
            for idx, img_name in enumerate(sorted_images):
                if job_info.get("cancelled", False):
                    return

                raw_img_bytes = in_memory_zip.read(img_name)
                translated_png_bytes, thumb_jpeg_bytes = process_single_image_in_memory(
                    raw_img_bytes,
                    src_lang=src_lang,
                    tgt_lang=tgt_lang,
                    model_name=model_name
                )

                base, _ = os.path.splitext(img_name)
                out_name = f"{base}.png"
                out_zip.writestr(out_name, translated_png_bytes)

                thumb_b64 = f"data:image/jpeg;base64,{base64.b64encode(thumb_jpeg_bytes).decode('ascii')}"
                current_page = idx + 1
                percent = int((current_page / total_pages) * 100)

                job_info["page"] = current_page
                job_info["percent"] = percent
                job_info["thumbnail"] = thumb_b64

                del raw_img_bytes, translated_png_bytes, thumb_jpeg_bytes
                gc.collect()

        out_memory_buffer.seek(0)
        job_info["output_bytes"] = out_memory_buffer.getvalue()
        job_info["status"] = "completed"
        logger.info(f"Trabajo {job_id} completado ({total_pages} páginas).")

    except Exception as e:
        logger.error(f"Error en trabajo {job_id}: {e}", exc_info=True)
        job_info["status"] = "error"
        job_info["error"] = str(e)
    finally:
        gc.collect()


@app.post("/translate-batch")
async def translate_batch(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    src_lang: str = Form("auto"),
    tgt_lang: str = Form("es"),
    model_name: str = Form("fast"),
    output_format: str = Form("zip")
):
    """Recibe archivo ZIP/CBZ y procesa en lote."""
    content = await file.read()
    job_id = str(uuid.uuid4())

    orig_filename = file.filename or "manga_chapter"
    base_name, _ = os.path.splitext(orig_filename)
    out_ext = "cbz" if output_format.lower() == "cbz" else "zip"
    final_filename = f"{base_name}_{tgt_lang.upper()}.{out_ext}"

    BATCH_JOBS[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "page": 0,
        "total": 0,
        "percent": 0,
        "thumbnail": "",
        "output_bytes": None,
        "filename": final_filename,
        "cancelled": False,
        "error": None
    }

    background_tasks.add_task(
        run_batch_job_task, job_id, content, src_lang, tgt_lang, model_name, out_ext
    )

    return {"job_id": job_id, "filename": final_filename}


@app.get("/progress/{job_id}")
async def stream_progress(job_id: str):
    """Transmite eventos SSE con el progreso en tiempo real y la miniatura actual."""
    if job_id not in BATCH_JOBS:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")

    async def event_generator():
        while True:
            job = BATCH_JOBS.get(job_id)
            if not job:
                yield {
                    "event": "message",
                    "data": json.dumps({"status": "error", "error": "Trabajo no disponible"})
                }
                break

            data = {
                "status": job["status"],
                "page": job["page"],
                "total": job["total"],
                "percent": job["percent"],
                "thumbnail": job["thumbnail"],
                "error": job["error"]
            }

            yield {"event": "message", "data": json.dumps(data)}

            if job["status"] in ["completed", "error"] or job.get("cancelled"):
                break

            await asyncio.sleep(0.4)

    return EventSourceResponse(event_generator())


@app.get("/download/{job_id}")
def download_batch_result(job_id: str):
    """Descarga el ZIP/CBZ y purga de la memoria RAM."""
    job = BATCH_JOBS.get(job_id)
    if not job or job["status"] != "completed" or not job["output_bytes"]:
        raise HTTPException(status_code=404, detail="Archivo no listo o purgado.")

    data = job["output_bytes"]
    filename = job["filename"]
    media_type = "application/vnd.comicbook+zip" if filename.endswith(".cbz") else "application/zip"

    del BATCH_JOBS[job_id]
    gc.collect()

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.post("/cancel/{job_id}")
def cancel_batch_job(job_id: str):
    """Cancela un trabajo en cola y libera RAM."""
    job = BATCH_JOBS.get(job_id)
    if job:
        job["cancelled"] = True
        del BATCH_JOBS[job_id]
        gc.collect()
        return {"status": "cancelled", "job_id": job_id}
    return {"status": "not_found"}
