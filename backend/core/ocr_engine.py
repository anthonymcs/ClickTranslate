"""
Módulo OCR Multi-idioma de Alta Velocidad (RapidOCR + Manga-OCR).
- RapidOCR (ONNX Runtime): Inferencia ultra-rápida (5-30 ms), soporte para inglés, coreano, chino, japonés y alfabetos latinos.
- Manga-OCR: Especializado en transcripción de japonés vertical y kanji complejo.
- Agrupador de globos de diálogo: fusiona líneas adyacentes en bloques de texto coherentes.
"""

import os
import logging
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import cv2
from PIL import Image

# Configurar HuggingFace / PaddleX en modo Offline para evitar llamadas de red lentas en cada inferencia
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["FLAGS_use_mkldnn"] = "0"

import unicodedata

logger = logging.getLogger("ClickTranslate.OCR")

_rapid_ocr_instance = None
_manga_ocr_instance = None
_paddle_jp_instance = None


def get_paddle_jp_ocr():
    """Carga perezosa del motor PaddleOCR PP-OCRv6 especializado en japonés."""
    global _paddle_jp_instance
    if _paddle_jp_instance is None:
        try:
            from paddleocr import PaddleOCR
            _paddle_jp_instance = PaddleOCR(
                lang="japan",
                enable_mkldnn=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_det_box_thresh=0.32,
                text_det_thresh=0.20,
            )
            logger.info("PaddleOCR (PP-OCRv6 Japonés) inicializado exitosamente.")
        except Exception as e:
            logger.warning(f"PaddleOCR japonés no disponible: {e}")
            _paddle_jp_instance = None
    return _paddle_jp_instance


def get_rapid_ocr():
    """Carga perezosa del motor RapidOCR basado en ONNX Runtime."""
    global _rapid_ocr_instance
    if _rapid_ocr_instance is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _rapid_ocr_instance = RapidOCR()
            logger.info("RapidOCR (ONNX Runtime) inicializado exitosamente.")
        except Exception as e:
            logger.error(f"Error al inicializar RapidOCR: {e}")
            _rapid_ocr_instance = None
    return _rapid_ocr_instance


def get_manga_ocr():
    """Carga perezosa de Manga-OCR para japonés."""
    global _manga_ocr_instance
    if _manga_ocr_instance is None:
        try:
            from manga_ocr import MangaOcr
            _manga_ocr_instance = MangaOcr()
            logger.info("Manga-OCR inicializado exitosamente.")
        except Exception as e:
            logger.warning(f"Manga-OCR no disponible: {e}")
            _manga_ocr_instance = None
    return _manga_ocr_instance


def group_text_boxes(
    raw_detections: List[Dict[str, Any]],
    img_shape: Tuple[int, int],
    max_v_dist: int = 24,
    max_h_dist: int = 30
) -> List[Tuple[Tuple[int, int, int, int], str]]:
    """
    Agrupa líneas de texto cercanas que pertenecen al mismo globo de diálogo o viñeta.
    Respeta el sentido de lectura:
    - Vertical (manga/manhua): Columnas de derecha a izquierda.
    - Horizontal (cómics/webtoons): Líneas de arriba hacia abajo.
    """
    if not raw_detections:
        return []

    h_img, w_img = img_shape[:2]

    # Filtrar detecciones con confianza razonable (>= 0.28)
    valid = []
    for d in raw_detections:
        text = d["text"].strip()
        score = d.get("score", 1.0)
        if len(text) >= 1 and score >= 0.28:
            valid.append(d)

    if not valid:
        return []

    # Ordenar preliminarmente
    valid.sort(key=lambda item: (item["box"][1], item["box"][0]))

    groups: List[Dict[str, Any]] = []

    for item in valid:
        x1, y1, x2, y2 = item["box"]
        text = item["text"]
        merged = False

        for g in groups:
            gx1, gy1, gx2, gy2 = g["box"]

            # Comprobar si pertenecen al mismo globo de diálogo
            # 1. Proximidad vertical para líneas horizontales apiladas
            v_close = (y1 >= gy1 - 18) and (y1 <= gy2 + max_v_dist)
            h_overlap = not (x2 < gx1 - max_h_dist or x1 > gx2 + max_h_dist)

            # 2. Columnas paralelas en texto vertical (similar Y, X contiguo)
            v_overlap = not (y2 < gy1 - 10 or y1 > gy2 + 10)
            h_close = (abs(x1 - gx2) <= max_h_dist) or (abs(gx1 - x2) <= max_h_dist)

            if (v_close and h_overlap) or (v_overlap and h_close):
                g["box"] = (min(gx1, x1), min(gy1, y1), max(gx2, x2), max(gy2, y2))
                g["items"].append(item)
                merged = True
                break

        if not merged:
            groups.append({
                "box": (x1, y1, x2, y2),
                "items": [item]
            })

    results: List[Tuple[Tuple[int, int, int, int], str]] = []
    for g in groups:
        box = g["box"]
        gw = box[2] - box[0]
        gh = box[3] - box[1]

        # Si el bloque es predominantemente vertical, ordenar columnas de derecha a izquierda
        if gh > gw * 1.15:
            sorted_items = sorted(g["items"], key=lambda it: (-it["box"][0], it["box"][1]))
        else:
            sorted_items = sorted(g["items"], key=lambda it: (it["box"][1], it["box"][0]))

        combined_text = " ".join([it["text"] for it in sorted_items]).strip()

        # Margen adaptativo alrededor del globo
        pad_x = max(5, int(gw * 0.10))
        pad_y = max(5, int(gh * 0.10))
        expanded_box = (
            max(0, box[0] - pad_x),
            max(0, box[1] - pad_y),
            min(w_img, box[2] + pad_x),
            min(h_img, box[3] + pad_y),
        )

        if combined_text:
            results.append((expanded_box, combined_text))

    return results


def run_ocr(img_bgr: np.ndarray, raw_lang: str = "auto") -> List[Tuple[Tuple[int, int, int, int], str]]:
    """
    Ejecuta el OCR en memoria RAM de forma ultra-rápida.
    Retorna lista de tuplas: [((x1, y1, x2, y2), texto_extraido)]
    """
    h, w = img_bgr.shape[:2]
    rapid_engine = get_rapid_ocr()
    if rapid_engine is None:
        logger.error("RapidOCR no disponible.")
        return []

    lang_code = (raw_lang or "auto").lower().strip()
    is_japanese = lang_code in ["ja", "jp", "japanese", "japonés", "japones"]

    # Escalado adaptativo si la imagen es de baja resolución (< 1100px) para máxima precisión en viñetas
    scale_factor = 1.0
    max_dim = max(h, w)
    if max_dim < 1100:
        scale_factor = min(3.0, 1200.0 / max(1, max_dim))
        detect_img = cv2.resize(img_bgr, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
    else:
        detect_img = img_bgr

    dh, dw = detect_img.shape[:2]
    raw_detections = []
    try:
        ocr_result, elapse = rapid_engine(detect_img)
        if ocr_result:
            for item in ocr_result:
                pts = np.array(item[0], dtype=np.float32)
                text = item[1].strip()
                score = float(item[2])

                # Mapear coordenadas de vuelta a la resolución original
                x1 = max(0, int(pts[:, 0].min() / scale_factor))
                y1 = max(0, int(pts[:, 1].min() / scale_factor))
                x2 = min(w, int(pts[:, 0].max() / scale_factor))
                y2 = min(h, int(pts[:, 1].max() / scale_factor))

                if x2 - x1 < 5 or y2 - y1 < 5:
                    continue

                raw_detections.append({
                    "box": (x1, y1, x2, y2),
                    "text": text,
                    "score": score
                })
    except Exception as e:
        logger.error(f"Error en RapidOCR: {e}")

    # Agrupar líneas en globos de diálogo coherentes
    grouped_results = group_text_boxes(raw_detections, img_shape=(h, w))

    def contains_japanese_kana(txt: str) -> bool:
        """Comprueba si el texto contiene Hiragana o Katakana, caracteres exclusivos del idioma japonés."""
        for ch in txt:
            code = ord(ch)
            if (0x3040 <= code <= 0x309F) or (0x30A0 <= code <= 0x30FF):
                return True
        return False

    # Activar Manga-OCR EXCLUSIVAMENTE si:
    # 1. El usuario seleccionó explícitamente Japonés (ja/jp/manga).
    # 2. O si en modo 'auto' se detectaron caracteres Kana (Hiragana o Katakana) exclusivos del japonés.
    # En caso de chino (manhua), inglés o coreano, RapidOCR es el motor óptimo.
    has_kana = any(contains_japanese_kana(item["text"]) for item in raw_detections)
    should_use_manga_ocr = is_japanese or (lang_code == "auto" and has_kana)

    if should_use_manga_ocr:
        manga_engine = get_manga_ocr()
        if manga_engine is not None:
            refined_results = []
            for box, current_text in grouped_results:
                x1, y1, x2, y2 = box
                crop_bgr = img_bgr[y1:y2, x1:x2]
                if crop_bgr.size > 0:
                    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
                    pil_crop = Image.fromarray(crop_rgb)
                    try:
                        manga_text = manga_engine(pil_crop).strip()
                        if manga_text:
                            refined_results.append((box, manga_text))
                        else:
                            refined_results.append((box, current_text))
                    except Exception:
                        refined_results.append((box, current_text))
            if refined_results:
                return refined_results

    return grouped_results


def _has_jp_or_cjk(txt: str) -> bool:
    for c in txt:
        code = ord(c)
        if (0x3040 <= code <= 0x30FF) or (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF):
            return True
    return False


def _has_kana(txt: str) -> bool:
    return any((0x3040 <= ord(c) <= 0x309F) or (0x30A0 <= ord(c) <= 0x30FF) for c in txt)


def _extract_paddle_items(res_list) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not res_list:
        return items
    for r in res_list:
        polys = r.get("dt_polys") or r.get("rec_polys") or []
        texts = r.get("rec_texts") or []
        scores = r.get("rec_scores") or []
        for poly, txt, sc in zip(polys, texts, scores):
            txt_clean = unicodedata.normalize("NFKC", str(txt)).strip()
            if not txt_clean:
                continue
            sc_val = float(sc)
            if sc_val < 0.48:
                continue
            if not _has_jp_or_cjk(txt_clean):
                # Descartar ruido corto de puntuación/ASCII con baja confianza
                alnum = sum(c.isalnum() for c in txt_clean)
                if alnum == 0 or (len(txt_clean) <= 2 and sc_val < 0.78):
                    continue
            items.append({
                "poly": np.array(poly, dtype=np.float32),
                "text": txt_clean,
                "score": sc_val,
            })
    return items


def detect_and_read_japanese_paddle(
    img_bgr: np.ndarray,
    comic_blocks: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Motor de detección y lectura japonés de alta precisión (PP-OCRv6 Dual-Orientation):
    1. Rota 90° en sentido antihorario para leer TODAS las columnas verticales japonesas
       (incluyendo texto blanco con contorno de color sobre fondos ilustrados sin globo).
    2. Procesa también líneas horizontales detectadas por ComicDetector (fechas, títulos, subtítulos).
    3. Agrupa columnas verticales contiguas de derecha a izquierda en globos/diálogos completos.
    """
    ocr = get_paddle_jp_ocr()
    if ocr is None or img_bgr is None or img_bgr.size == 0:
        return []

    im_h, im_w = img_bgr.shape[:2]
    max_dim = max(im_h, im_w)
    scale = 1.0
    if max_dim < 750:
        scale = min(1.8, 800.0 / max(1, max_dim))
        work_img = cv2.resize(img_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    elif max_dim > 1800:
        scale = 1600.0 / max_dim
        work_img = cv2.resize(img_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        work_img = img_bgr

    w_h, w_w = work_img.shape[:2]

    # Pasada 1: 90° antihorario (todas las columnas verticales quedan horizontales de izq. a der.)
    rot_ccw = cv2.rotate(work_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    v_items = _extract_paddle_items(ocr.predict(rot_ccw))

    vertical_cols: List[Dict[str, Any]] = []
    for it in v_items:
        pts = it["poly"]
        # Mapear (rx, ry) en imagen rotada 90° CCW de vuelta a work_img: ox = w_w - 1 - ry, oy = rx
        ox = (w_w - 1.0 - pts[:, 1]) / scale
        oy = pts[:, 0] / scale
        x1 = max(0, int(np.floor(ox.min())))
        y1 = max(0, int(np.floor(oy.min())))
        x2 = min(im_w, int(np.ceil(ox.max())))
        y2 = min(im_h, int(np.ceil(oy.max())))
        bw, bh = x2 - x1, y2 - y1
        if bw < 6 or bh < 6:
            continue
        # Verificar que en coordenadas originales sea vertical o al menos un carácter cuadrado/kana
        if bh >= bw * 0.65 or _has_kana(it["text"]):
            vertical_cols.append({
                "box": (x1, y1, x2, y2),
                "text": it["text"],
                "score": it["score"],
                "vertical": True,
            })

    # Pasada 2: Líneas horizontales detectadas por ComicDetector que no estén cubiertas por Pasada 1
    horizontal_lines: List[Dict[str, Any]] = []
    uncovered_h_crops = []
    if comic_blocks:
        for cb in comic_blocks:
            bx1, by1, bx2, by2 = cb["box"]
            bw_c, bh_c = max(1, bx2 - bx1), max(1, by2 - by1)
            if cb.get("vertical", False) and bh_c >= bw_c * 1.1:
                continue
            # Comprobar si ya fue cubierto por columnas verticales
            area_cb = bw_c * bh_c
            covered = 0
            for vc in vertical_cols:
                vx1, vy1, vx2, vy2 = vc["box"]
                ix1, iy1 = max(bx1, vx1), max(by1, vy1)
                ix2, iy2 = min(bx2, vx2), min(by2, vy2)
                if ix2 > ix1 and iy2 > iy1:
                    covered += (ix2 - ix1) * (iy2 - iy1)
            if (covered / area_cb) < 0.35:
                uncovered_h_crops.append((bx1, by1, bx2, by2))

    if uncovered_h_crops:
        for (bx1, by1, bx2, by2) in uncovered_h_crops:
            pad = 14
            cx1, cy1 = max(0, bx1 - pad), max(0, by1 - pad)
            cx2, cy2 = min(im_w, bx2 + pad), min(im_h, by2 + pad)
            crop = img_bgr[cy1:cy2, cx1:cx2]
            if crop.size == 0:
                continue
            c_scale = 1.8 if max(crop.shape[:2]) < 260 else 1.0
            c_in = cv2.resize(crop, None, fx=c_scale, fy=c_scale, interpolation=cv2.INTER_CUBIC) if c_scale != 1.0 else crop
            h_items = _extract_paddle_items(ocr.predict(c_in))
            if h_items:
                # Ordenar líneas de arriba hacia abajo y unir con \n
                line_entries = []
                for it in h_items:
                    pts = it["poly"] / c_scale
                    lx1 = max(0, int(cx1 + pts[:, 0].min()))
                    ly1 = max(0, int(cy1 + pts[:, 1].min()))
                    lx2 = min(im_w, int(cx1 + pts[:, 0].max()))
                    ly2 = min(im_h, int(cy1 + pts[:, 1].max()))
                    line_entries.append(((lx1, ly1, lx2, ly2), it["text"], it["score"]))
                line_entries.sort(key=lambda e: (e[0][1] + e[0][3]) / 2.0)
                ux1 = min(e[0][0] for e in line_entries)
                uy1 = min(e[0][1] for e in line_entries)
                ux2 = max(e[0][2] for e in line_entries)
                uy2 = max(e[0][3] for e in line_entries)
                joined = "\n".join(e[1] for e in line_entries)
                avg_sc = float(np.mean([e[2] for e in line_entries]))
                horizontal_lines.append({
                    "box": (ux1, uy1, ux2, uy2),
                    "poly_boxes": [e[0] for e in line_entries],
                    "text": joined,
                    "vertical": False,
                    "score": avg_sc,
                })
    elif not vertical_cols:
        # Fallback 0° en página completa si no se detectó nada en vertical
        h_items = _extract_paddle_items(ocr.predict(work_img))
        for it in h_items:
            pts = it["poly"] / scale
            x1 = max(0, int(pts[:, 0].min()))
            y1 = max(0, int(pts[:, 1].min()))
            x2 = min(im_w, int(pts[:, 0].max()))
            y2 = min(im_h, int(pts[:, 1].max()))
            horizontal_lines.append({
                "box": (x1, y1, x2, y2),
                "poly_boxes": [(x1, y1, x2, y2)],
                "text": it["text"],
                "vertical": False,
                "score": it["score"],
            })

    # Agrupar columnas verticales contiguas en bloques de diálogo coherentes (de derecha a izquierda)
    # Ordenar primero por centro X descendente (derecha a izquierda)
    vertical_cols.sort(key=lambda c: -((c["box"][0] + c["box"][2]) / 2.0))
    v_groups: List[List[Dict[str, Any]]] = []
    for col in vertical_cols:
        cx1, cy1, cx2, cy2 = col["box"]
        cw, ch = max(1, cx2 - cx1), max(1, cy2 - cy1)
        cy_mid = (cy1 + cy2) / 2.0
        placed = False

        for grp in v_groups:
            # Comparar contra la columna más cercana del grupo (normalmente la última añadida)
            gx1 = min(g["box"][0] for g in grp)
            gy1 = min(g["box"][1] for g in grp)
            gx2 = max(g["box"][2] for g in grp)
            gy2 = max(g["box"][3] for g in grp)
            avg_cw = float(np.mean([g["box"][2] - g["box"][0] for g in grp]))
            gy_mid = (gy1 + gy2) / 2.0

            ov_y = max(0, min(gy2, cy2) - max(gy1, cy1))
            min_h = min(gy2 - gy1, ch)
            v_match = (min_h > 0 and ov_y >= 0.20 * min_h) or (abs(cy_mid - gy_mid) <= max(gy2 - gy1, ch) * 0.45)

            h_gap = max(0, max(gx1, cx1) - min(gx2, cx2))
            max_gap = max(avg_cw * 0.85, cw * 0.85, 10.0)
            size_ok = max(cw, avg_cw) <= min(cw, avg_cw) * 2.2

            if v_match and h_gap <= max_gap and size_ok:
                grp.append(col)
                placed = True
                break

        if not placed:
            v_groups.append([col])

    merged_blocks: List[Dict[str, Any]] = []
    for grp in v_groups:
        # Ordenar columnas dentro del globo de derecha a izquierda (-center_x)
        grp.sort(key=lambda c: -((c["box"][0] + c["box"][2]) / 2.0))
        ux1 = min(c["box"][0] for c in grp)
        uy1 = min(c["box"][1] for c in grp)
        ux2 = max(c["box"][2] for c in grp)
        uy2 = max(c["box"][3] for c in grp)
        joined_text = "".join(c["text"] for c in grp).strip()
        avg_sc = float(np.mean([c["score"] for c in grp]))
        merged_blocks.append({
            "box": (ux1, uy1, ux2, uy2),
            "poly_boxes": [c["box"] for c in grp],
            "text": joined_text,
            "vertical": True,
            "score": avg_sc,
        })

    merged_blocks.extend(horizontal_lines)
    return merged_blocks
