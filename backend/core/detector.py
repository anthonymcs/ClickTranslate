"""
Módulo de detección y clasificación de globos y onomatopeyas (SFX).
Genera máscaras binarias para inpainting y ordena los bloques según el sentido de lectura.
"""

from dataclasses import dataclass
from typing import List, Tuple, Literal, Optional
import cv2
import numpy as np


@dataclass
class TextBlock:
    """Representa un bloque de texto detectado en una página."""
    id: int
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    type: Literal["dialog", "sfx"]
    text: str = ""
    translated_text: str = ""
    bg_color: Tuple[int, int, int] = (255, 255, 255)
    text_color: Tuple[int, int, int] = (0, 0, 0)
    stroke_color: Optional[Tuple[int, int, int]] = None
    is_uniform_bg: bool = True
    contour: np.ndarray = None
    render_box: Optional[Tuple[int, int, int, int]] = None
    draw_backdrop: bool = False


def calculate_region_variance(img_gray: np.ndarray, box: Tuple[int, int, int, int]) -> float:
    """Calcula la varianza de escala de grises en la región para determinar uniformidad de fondo."""
    x1, y1, x2, y2 = box
    h, w = img_gray.shape
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    if x2 <= x1 or y2 <= y1:
        return 0.0

    crop = img_gray[y1:y2, x1:x2]
    # Extraer el borde o periferia del bloque para analizar el fondo y no las letras negras
    h_c, w_c = crop.shape
    border_pixels = []
    if h_c > 4 and w_c > 4:
        border_pixels.extend(crop[0:2, :].flatten())
        border_pixels.extend(crop[-2:, :].flatten())
        border_pixels.extend(crop[:, 0:2].flatten())
        border_pixels.extend(crop[:, -2:].flatten())
        return float(np.var(border_pixels)) if border_pixels else float(np.var(crop))
    return float(np.var(crop))


def get_dominant_bg_color(img_bgr: np.ndarray, box: Tuple[int, int, int, int]) -> Tuple[Tuple[int, int, int], bool]:
    """
    Obtiene el color de fondo dominante de un bloque y determina si es uniforme.
    Retorna ((B, G, R), is_uniform)
    """
    x1, y1, x2, y2 = box
    h, w, _ = img_bgr.shape
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    if x2 <= x1 or y2 <= y1:
        return ((255, 255, 255), True)

    crop = img_bgr[y1:y2, x1:x2]
    # Muestrear el contorno exterior del recorte
    h_c, w_c, _ = crop.shape
    if h_c > 6 and w_c > 6:
        border = np.concatenate([
            crop[0:3, :, :].reshape(-1, 3),
            crop[-3:, :, :].reshape(-1, 3),
            crop[:, 0:3, :].reshape(-1, 3),
            crop[:, -3:, :].reshape(-1, 3),
        ], axis=0)
    else:
        border = crop.reshape(-1, 3)

    var = np.mean(np.var(border, axis=0))
    median_color = np.median(border, axis=0).astype(int)
    # En cómics y mangas, si el fondo es claro (> 175) o la varianza es baja, es un globo uniforme
    is_bright = float(np.mean(median_color)) > 175.0
    is_uniform = is_bright or (var < 450.0)
    return (int(median_color[0]), int(median_color[1]), int(median_color[2])), is_uniform


def sort_blocks(blocks: List[TextBlock], reading_direction: str = "rtl") -> List[TextBlock]:
    """
    Ordena los bloques de texto según el sentido de lectura:
    - 'rtl' (Right-to-Left): Manga japonés (de derecha a izquierda, arriba a abajo).
    - 'ltr' (Left-to-Right): Manhwa coreano, manhua chino, cómics occidentales.
    """
    if not blocks:
        return []

    if reading_direction == "rtl":
        # Agrupamiento por franjas verticales o columnas de derecha a izquierda
        # Ordenar primero por posición X decreciente y luego por Y creciente
        def rtl_key(b: TextBlock):
            x1, y1, x2, y2 = b.box
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            # Cuantizar en franjas para dar prioridad a columnas de lectura de manga
            col = int(center_x // 120)
            return (-col, center_y)
        return sorted(blocks, key=rtl_key)
    else:
        # LTR: Lectura occidental estándar (izquierda a derecha, arriba a abajo)
        def ltr_key(b: TextBlock):
            x1, y1, x2, y2 = b.box
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            row = int(center_y // 100)
            return (row, center_x)
        return sorted(blocks, key=ltr_key)


def detect_balloons_and_sfx(img_bgr: np.ndarray, raw_text_boxes: List[Tuple[int, int, int, int]], lang: str = "ja") -> Tuple[List[TextBlock], np.ndarray, np.ndarray]:
    """
    A partir de la imagen y las cajas detectadas por el motor OCR (o por visión),
    clasifica cada bloque en diálogo en globo vs SFX/onomatopeya y construye:
    1. Lista de TextBlock ordenados
    2. balloon_mask (para OpenCV rápido)
    3. sfx_mask (para LaMa)
    """
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    balloon_mask = np.zeros((h, w), dtype=np.uint8)
    sfx_mask = np.zeros((h, w), dtype=np.uint8)

    reading_dir = "rtl" if lang in ["ja", "jp", "manga", "auto"] else "ltr"
    blocks: List[TextBlock] = []

    # Umbrales morfológicos para búsqueda de contornos de globos
    _, thresh = cv2.threshold(gray, 235, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    balloon_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 1200 and area < (h * w * 0.75):
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            balloon_contours.append(cnt)

    for idx, box in enumerate(raw_text_boxes):
        x1, y1, x2, y2 = box
        # Asegurar límites válidos
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(w, int(x2)), min(h, int(y2))
        if x2 - x1 < 5 or y2 - y1 < 5:
            continue

        dominant_color, is_uniform = get_dominant_bg_color(img_bgr, (x1, y1, x2, y2))
        center_pt = ((x1 + x2) // 2, (y1 + y2) // 2)

        # Determinar si el bloque cae dentro de un globo detectado
        inside_balloon = False
        matching_cnt = None
        for cnt in balloon_contours:
            if cv2.pointPolygonTest(cnt, center_pt, False) >= 0:
                inside_balloon = True
                matching_cnt = cnt
                break

        # Clasificación:
        # Si está dentro de un globo o el fondo tiene baja varianza (blanco/negro uniforme) -> "dialog"
        # Si el fondo tiene alta varianza (dibujo/tramas) -> "sfx"
        if inside_balloon or is_uniform:
            block_type = "dialog"
            # Dilatación ligera del cuadro de texto para la máscara
            pad_x = max(2, int((x2 - x1) * 0.06))
            pad_y = max(2, int((y2 - y1) * 0.06))
            bx1, by1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
            bx2, by2 = min(w, x2 + pad_x), min(h, y2 + pad_y)

            # Para globos con fondo uniforme, marcar la región
            balloon_mask[by1:by2, bx1:bx2] = 255
            # Determinar color de texto sugerido
            avg_brightness = (dominant_color[0] + dominant_color[1] + dominant_color[2]) / 3
            text_color = (0, 0, 0) if avg_brightness > 128 else (255, 255, 255)
        else:
            block_type = "sfx"
            pad = 6
            sx1, sy1 = max(0, x1 - pad), max(0, y1 - pad)
            sx2, sy2 = min(w, x2 + pad), min(h, y2 + pad)
            sfx_mask[sy1:sy2, sx1:sx2] = 255
            text_color = (255, 255, 255)

        block = TextBlock(
            id=idx + 1,
            box=(x1, y1, x2, y2),
            type=block_type,
            bg_color=dominant_color,
            text_color=text_color,
            is_uniform_bg=is_uniform,
            contour=matching_cnt
        )
        blocks.append(block)

    sorted_blocks = sort_blocks(blocks, reading_direction=reading_dir)
    # Re-asignar IDs secuenciales tras el orden de lectura
    for i, b in enumerate(sorted_blocks):
        b.id = i + 1

    return sorted_blocks, balloon_mask, sfx_mask
