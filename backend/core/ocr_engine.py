"""
Módulo OCR Multi-idioma de Alta Velocidad (RapidOCR + Manga-OCR).
- RapidOCR (ONNX Runtime): Inferencia ultra-rápida (5-30 ms), soporte para inglés, coreano, chino, japonés y alfabetos latinos.
- Manga-OCR: Especializado en transcripción de japonés vertical y kanji complejo.
- Agrupador de globos de diálogo: fusiona líneas adyacentes en bloques de texto coherentes.
"""

import os
import logging
from typing import List, Tuple, Dict, Any
import numpy as np
import cv2
from PIL import Image

logger = logging.getLogger("ClickTranslate.OCR")

_rapid_ocr_instance = None
_manga_ocr_instance = None


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
    max_v_dist: int = 40,
    max_h_dist: int = 50
) -> List[Tuple[Tuple[int, int, int, int], str]]:
    """
    Agrupa líneas de texto cercanas que pertenecen al mismo globo de diálogo o viñeta.
    Retorna lista de: [((x1, y1, x2, y2), texto_combinado)]
    """
    if not raw_detections:
        return []

    h_img, w_img = img_shape[:2]

    # Filtrar detecciones con confianza razonable (>= 0.40) y texto no vacío
    valid = []
    for d in raw_detections:
        box = d["box"]
        text = d["text"].strip()
        score = d.get("score", 1.0)
        # Ignorar caracteres sueltos de ruido o muy baja confianza
        if len(text) >= 1 and score >= 0.40:
            valid.append(d)

    if not valid:
        return []

    # Ordenar verticalmente de arriba hacia abajo
    valid.sort(key=lambda item: (item["box"][1], item["box"][0]))

    groups: List[Dict[str, Any]] = []

    for item in valid:
        x1, y1, x2, y2 = item["box"]
        text = item["text"]
        merged = False

        for g in groups:
            gx1, gy1, gx2, gy2 = g["box"]

            # Verificar proximidad vertical (líneas consecutivas en el mismo globo)
            v_close = (y1 >= gy1 - 15) and (y1 <= gy2 + max_v_dist)
            # Verificar solapamiento o cercanía horizontal
            h_overlap = not (x2 < gx1 - max_h_dist or x1 > gx2 + max_h_dist)

            if v_close and h_overlap:
                g["box"] = (min(gx1, x1), min(gy1, y1), max(gx2, x2), max(gy2, y2))
                g["texts"].append(text)
                merged = True
                break

        if not merged:
            groups.append({
                "box": (x1, y1, x2, y2),
                "texts": [text]
            })

    results: List[Tuple[Tuple[int, int, int, int], str]] = []
    for g in groups:
        box = g["box"]
        # Añadir un pequeño margen (padding) al cuadro agrupado para abarcar todo el globo
        pad_x = max(4, int((box[2] - box[0]) * 0.08))
        pad_y = max(4, int((box[3] - box[1]) * 0.08))
        expanded_box = (
            max(0, box[0] - pad_x),
            max(0, box[1] - pad_y),
            min(w_img, box[2] + pad_x),
            min(h_img, box[3] + pad_y),
        )
        combined_text = " ".join(g["texts"]).strip()
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

    raw_detections = []
    try:
        ocr_result, elapse = rapid_engine(img_bgr)
        if ocr_result:
            for item in ocr_result:
                pts = np.array(item[0], dtype=np.int32)
                text = item[1].strip()
                score = float(item[2])

                x1 = max(0, int(pts[:, 0].min()))
                y1 = max(0, int(pts[:, 1].min()))
                x2 = min(w, int(pts[:, 0].max()))
                y2 = min(h, int(pts[:, 1].max()))

                if x2 - x1 < 6 or y2 - y1 < 6:
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

    def contains_cjk_or_japanese(txt: str) -> bool:
        for ch in txt:
            code = ord(ch)
            if (0x3040 <= code <= 0x309F) or (0x30A0 <= code <= 0x30FF) or (0x4E00 <= code <= 0x9FFF):
                return True
        return False

    # Determinar si debemos refinar con Manga-OCR:
    # 1. Si el usuario seleccionó japonés explícitamente.
    # 2. Si está en 'auto' y se detectaron caracteres CJK / japoneses preliminares.
    detected_asian = any(contains_cjk_or_japanese(item["text"]) for item in raw_detections)
    should_use_manga_ocr = is_japanese or (lang_code == "auto" and detected_asian)

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
