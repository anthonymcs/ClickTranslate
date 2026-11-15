"""
Módulo OCR Multi-idioma con Carga Perezosa (Lazy Loading).
Utiliza Manga-OCR para Japonés y PaddleOCR para Coreano, Chino e Inglés.
"""

import logging
from typing import List, Tuple, Optional
import numpy as np
from PIL import Image
import cv2

logger = logging.getLogger("ClickTranslate.OCR")

# Instancias cacheadas para Lazy Loading
_manga_ocr_model = None
_paddle_ocr_instances = {}


def get_manga_ocr():
    """Carga diferida del modelo Manga-OCR para japonés."""
    global _manga_ocr_model
    if _manga_ocr_model is None:
        try:
            logger.info("Cargando modelo Manga-OCR para japonés en memoria...")
            from manga_ocr import MangaOcr
            _manga_ocr_model = MangaOcr()
            logger.info("Modelo Manga-OCR cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error al inicializar Manga-OCR: {e}")
            _manga_ocr_model = None
    return _manga_ocr_model


def get_paddle_ocr(lang: str = "korean"):
    """Carga diferida del modelo PaddleOCR según el idioma (korean, ch, en)."""
    global _paddle_ocr_instances
    if lang not in _paddle_ocr_instances:
        try:
            logger.info(f"Cargando modelo PaddleOCR para idioma '{lang}'...")
            from paddleocr import PaddleOCR
            # use_angle_cls=True para detectar rotación de texto
            ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
            _paddle_ocr_instances[lang] = ocr
            logger.info(f"PaddleOCR para '{lang}' cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error al inicializar PaddleOCR ({lang}): {e}")
            _paddle_ocr_instances[lang] = None
    return _paddle_ocr_instances[lang]


def detect_text_regions_morphology(img_bgr: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """
    Detector morfológico de respaldo rápido para encontrar posibles regiones de texto y globos
    si el detector de PaddleOCR no está disponible o para enriquecer la segmentación.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Gradiente morfológico para resaltar bordes de caracteres
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)

    # Binarización
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Conectar letras cercanas en bloques de texto
    connect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3))
    connected = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, connect_kernel)

    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for cnt in contours:
        x, y, bw_box, bh_box = cv2.boundingRect(cnt)
        area = bw_box * bh_box
        if 200 < area < (h * w * 0.4) and bw_box > 12 and bh_box > 12:
            boxes.append((x, y, x + bw_box, y + bh_box))
    return boxes


def normalize_lang_code(raw_lang: str) -> Tuple[str, str]:
    """
    Normaliza el idioma origen ingresado por el usuario:
    Retorna (engine_type, paddle_lang_code)
    engine_type: 'manga_ocr' o 'paddle'
    """
    code = (raw_lang or "auto").lower().strip()
    if code in ["ja", "jp", "japanese", "manga", "japonés", "japones"]:
        return ("manga_ocr", "japan")
    elif code in ["ko", "kr", "korean", "manhwa", "coreano"]:
        return ("paddle", "korean")
    elif code in ["zh", "cn", "chinese", "manhua", "chino"]:
        return ("paddle", "ch")
    elif code in ["en", "english", "inglés", "ingles"]:
        return ("paddle", "en")
    else:
        # Default / auto: se asume manga japonés o detección automática
        return ("manga_ocr", "japan")


def run_ocr(img_bgr: np.ndarray, raw_lang: str = "ja") -> List[Tuple[Tuple[int, int, int, int], str]]:
    """
    Ejecuta el OCR sobre la imagen en memoria y retorna lista de tuplas:
    [((x1, y1, x2, y2), texto_extraido)]
    """
    engine_type, paddle_code = normalize_lang_code(raw_lang)
    h, w, _ = img_bgr.shape
    results: List[Tuple[Tuple[int, int, int, int], str]] = []

    # 1. Intentar con PaddleOCR para detección de cuadros y reconocimiento
    paddle_engine = get_paddle_ocr(paddle_code)
    manga_engine = get_manga_ocr() if engine_type == "manga_ocr" else None

    if paddle_engine is not None:
        try:
            # PaddleOCR acepta imagen numpy BGR directamente
            ocr_output = paddle_engine.ocr(img_bgr, cls=True)
            if ocr_output and len(ocr_output) > 0 and ocr_output[0]:
                for line in ocr_output[0]:
                    polygon = line[0]  # 4 puntos del polígono [[x1, y1], [x2, y2], ...]
                    text_info = line[1]  # (texto, confianza)
                    text = text_info[0].strip() if text_info else ""

                    pts = np.array(polygon, dtype=np.int32)
                    x1 = max(0, int(np.min(pts[:, 0])))
                    y1 = max(0, int(np.min(pts[:, 1])))
                    x2 = min(w, int(np.max(pts[:, 0])))
                    y2 = min(h, int(np.max(pts[:, 1])))

                    if x2 - x1 < 6 or y2 - y1 < 6:
                        continue

                    # Si es japonés y tenemos Manga-OCR, usamos Manga-OCR para transcribir el crop
                    # ya que maneja furigana y caracteres verticales con mucha mayor precisión que PaddleOCR
                    if engine_type == "manga_ocr" and manga_engine is not None:
                        crop_bgr = img_bgr[y1:y2, x1:x2]
                        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
                        pil_crop = Image.fromarray(crop_rgb)
                        try:
                            manga_text = manga_engine(pil_crop).strip()
                            if manga_text:
                                text = manga_text
                        except Exception as me:
                            logger.warning(f"Error parcial en Manga-OCR crop: {me}")

                    if text:
                        results.append(((x1, y1, x2, y2), text))
                return results
        except Exception as pe:
            logger.error(f"Error ejecutando PaddleOCR: {pe}")

    # 2. Si PaddleOCR falló o no está instalado, pero tenemos Manga-OCR (para Japonés)
    if engine_type == "manga_ocr" and manga_engine is not None:
        logger.info("Usando detección morfológica combinada con Manga-OCR...")
        candidate_boxes = detect_text_regions_morphology(img_bgr)
        for box in candidate_boxes:
            x1, y1, x2, y2 = box
            crop_bgr = img_bgr[y1:y2, x1:x2]
            crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            pil_crop = Image.fromarray(crop_rgb)
            try:
                text = manga_engine(pil_crop).strip()
                if len(text) >= 1:
                    results.append((box, text))
            except Exception as me:
                continue
        if results:
            return results

    # 3. Fallback de detección morfológica para no dejar la página sin procesar
    if not results:
        logger.warning("No se pudo extraer texto con los modelos instalados. Buscando regiones por morfología...")
        fallback_boxes = detect_text_regions_morphology(img_bgr)
        for box in fallback_boxes[:10]:
            results.append((box, "Texto a traducir"))

    return results
