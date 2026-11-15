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
            if x2 - x1 < 5 or y2 - y1 < 5:
                continue

            crop_bgr = img_bgr[y1:y2, x1:x2]
            crop_gray = gray[y1:y2, x1:x2]
            dom_color, is_uniform = get_dominant_bg_color(img_bgr, (x1, y1, x2, y2))

            center_pt = ((x1 + x2) // 2, (y1 + y2) // 2)
            matching_balloon = None
            for cnt, bbox in balloon_contours:
                if cv2.pointPolygonTest(cnt, center_pt, False) >= 0:
                    matching_balloon = bbox
                    break

            if matching_balloon:
                block_type = "dialog"
                bx1, by1, bx2, by2 = matching_balloon
                eff_box = (bx1 + 4, max(y1, by1 + 4), bx2 - 4, min(y2, by2 - 4))
            else:
                if is_uniform and float(np.mean(dom_color)) > 210:
                    block_type = "dialog"
                else:
                    block_type = "sfx"
                eff_box = (x1, y1, x2, y2)

            # OCR Inteligente Multi-idioma con enrutamiento automático
            def contains_kana(txt: str) -> bool:
                return any((0x3040 <= ord(c) <= 0x309F) or (0x30A0 <= ord(c) <= 0x30FF) for c in txt)

            extracted_text = ""
            if is_japanese:
                # Si el usuario seleccionó explícitamente Japonés, priorizar Manga-OCR
                if manga_engine is not None and crop_bgr.size > 0:
                    try:
                        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
                        pil_crop = Image.fromarray(crop_rgb)
                        extracted_text = manga_engine(pil_crop).strip()
                    except Exception as e:
                        logger.warning(f"Error Manga-OCR: {e}")
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
                            # Agrupar en líneas por proximidad vertical Y (tolerancia 7px)
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

                # Si en modo 'auto' el texto extraído contiene Kana japonés, o si es japonés explícito, usar Manga-OCR
                if (is_japanese or (lang_code == "auto" and contains_kana(extracted_text))):
                    if manga_engine is None:
                        manga_engine = get_manga_ocr()
                    if manga_engine is not None and crop_bgr.size > 0:
                        try:
                            crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
                            pil_crop = Image.fromarray(crop_rgb)
                            m_txt = manga_engine(pil_crop).strip()
                            if m_txt and contains_kana(m_txt):
                                extracted_text = m_txt
                        except Exception as e:
                            logger.warning(f"Error Manga-OCR fallback: {e}")

            # Normalizar NFKC estrictamente para eliminar fullwidth characters (evita cuadrados/tofu)
            extracted_text = unicodedata.normalize("NFKC", extracted_text).strip()

            if not extracted_text:
                continue

            # Inpainting profesional TranslateManga: limpieza impecable de globos sin residuos de texto
            if block_type == "dialog":
                p_gray = gray[y1:y2, x1:x2]
                bg_bright = sum(dom_color) / 3.0
                if bg_bright > 175 or is_uniform:
                    # Rango ampliado a 215 y 2 iteraciones de dilatación para eliminar halos grises anti-alias
                    t_mask = (p_gray < 215).astype(np.uint8)
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                    dilated = cv2.dilate(t_mask, kernel, iterations=2)
                    target_color = (255, 255, 255) if bg_bright > 185 else dom_color
                    cleaned_img[y1:y2, x1:x2][dilated > 0] = target_color
                else:
                    sub_m = text_mask[y1:y2, x1:x2]
                    if np.count_nonzero(sub_m) > 0:
                        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                        dilated = cv2.dilate(sub_m, kernel, iterations=2)
                        inpainted = cv2.inpaint(cleaned_img[y1:y2, x1:x2], dilated, 3, cv2.INPAINT_TELEA)
                        cleaned_img[y1:y2, x1:x2] = inpainted
            else:
                sub_m = text_mask[y1:y2, x1:x2]
                if np.count_nonzero(sub_m) > 0:
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                    dilated = cv2.dilate(sub_m, kernel, iterations=2)
                    inpainted = cv2.inpaint(cleaned_img[y1:y2, x1:x2], dilated, 3, cv2.INPAINT_TELEA)
                    cleaned_img[y1:y2, x1:x2] = inpainted

            text_color = (0, 0, 0) if block_type == "dialog" else (255, 255, 255)

            tb = TextBlock(
                id=idx + 1,
                box=eff_box,
                type=block_type,
                text=extracted_text,
                bg_color=dom_color,
                text_color=text_color,
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
