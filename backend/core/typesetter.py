"""
Módulo de Re-tipografía Inteligente con Pillow.
- Carga de fuentes en backend/assets/fonts/ con Fallback automático al sistema.
- Auto-fit dinámico para globos de diálogo (word-wrap y centrado perfecto).
- Renderizado de SFX con stroke/contorno contrastante sobre el dibujo reconstruido.
"""

import os
import glob
import textwrap
import logging
from typing import List, Tuple, Optional
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .detector import TextBlock

logger = logging.getLogger("ClickTranslate.Typesetter")

# Rutas de búsqueda de fuentes
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "assets", "fonts")

# Fuentes estándar de Windows / Linux / macOS como respaldo
SYSTEM_FONTS = [
    "C:/Windows/Fonts/comic.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf"
]


def resolve_font_path(preferred_names: List[str]) -> Optional[str]:
    """Busca primero en backend/assets/fonts/ y luego en el sistema."""
    if os.path.isdir(FONTS_DIR):
        for name in preferred_names:
            candidate = os.path.join(FONTS_DIR, name)
            if os.path.isfile(candidate):
                return candidate
            # Búsqueda case-insensitive
            for f in os.listdir(FONTS_DIR):
                if f.lower() == name.lower():
                    return os.path.join(FONTS_DIR, f)

        # Si hay cualquier otra fuente .ttf en la carpeta, usar la primera
        ttf_files = glob.glob(os.path.join(FONTS_DIR, "*.ttf"))
        if ttf_files:
            return ttf_files[0]

    # Respaldo en fuentes del sistema
    for sf in SYSTEM_FONTS:
        if os.path.isfile(sf):
            return sf

    return None


def get_font(size: int, is_sfx: bool = False) -> ImageFont.FreeTypeFont:
    """Carga la fuente apropiada con el tamaño deseado o recurre al fallback de Pillow."""
    preferred = ["Impact.ttf", "impact.ttf", "Bangers.ttf"] if is_sfx else ["WildWords.ttf", "AnimeAce.ttf", "animeace.ttf", "comic.ttf"]
    font_path = resolve_font_path(preferred)

    if font_path:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception as e:
            logger.warning(f"No se pudo cargar la fuente '{font_path}': {e}")

    try:
        return ImageFont.load_default()
    except Exception:
        return None


def calculate_text_dimensions(draw: ImageDraw.ImageDraw, lines: List[str], font: ImageFont.ImageFont, line_spacing: int = 4) -> Tuple[int, int]:
    """Calcula el ancho máximo y alto total de un bloque multilínea."""
    max_w = 0
    total_h = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        max_w = max(max_w, w)
        total_h += h + line_spacing
    total_h -= line_spacing
    return max_w, max(0, total_h)


def fit_text_in_balloon(
    draw: ImageDraw.ImageDraw,
    text: str,
    box_w: int,
    box_h: int,
    min_size: int = 9,
    max_size: int = 28
) -> Tuple[List[str], ImageFont.ImageFont, int, int]:
    """
    Encuentra de forma adaptativa el tamaño de fuente óptimo y la división en líneas (word-wrap)
    para que el texto encaje perfectamente en el bounding box del globo.
    """
    best_font = None
    best_lines = [text]
    best_w, best_h = box_w, box_h

    # Margen de seguridad interior adaptativo (90% del espacio)
    usable_w = max(24, int(box_w * 0.90))
    usable_h = max(24, int(box_h * 0.90))

    # Búsqueda desde tamaño mayor hacia menor
    for size in range(max_size, min_size - 1, -1):
        font = get_font(size=size, is_sfx=False)
        avg_char_w = max(4, int(size * 0.52))
        chars_per_line = max(5, usable_w // avg_char_w)

        lines = textwrap.wrap(text, width=chars_per_line, break_long_words=False)
        if not lines:
            lines = [text]

        w_calc, h_calc = calculate_text_dimensions(draw, lines, font, line_spacing=2)
        if w_calc <= usable_w and h_calc <= usable_h:
            return lines, font, w_calc, h_calc

        best_font = font
        best_lines = lines
        best_w, best_h = w_calc, h_calc

    return best_lines, best_font, best_w, best_h


def render_typesetting(img_bgr: np.ndarray, blocks: List[TextBlock]) -> np.ndarray:
    """
    Dibuja los textos traducidos en la imagen limpia:
    - Diálogos: Centrados dentro del globo con auto-fit y color armónico estilo scanlation.
    - SFX: Tipografía destacada con trazo de borde (stroke) contrastante.
    """
    # Convertir a RGB para dibujar con Pillow
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)

    for block in blocks:
        text = block.translated_text or block.text
        if not text or not text.strip():
            continue

        x1, y1, x2, y2 = block.box
        bw = max(10, x2 - x1)
        bh = max(10, y2 - y1)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        if block.type == "dialog":
            # Si el cuadro de OCR original era vertical estrecho (mangas orientales),
            # expandir el ancho útil horizontalmente para que el texto occidental encaje con holgura
            if bw < bh * 0.75:
                target_w = max(bw, int(bh * 0.82))
                eff_bw = min(pil_img.width - 10, target_w)
            else:
                eff_bw = bw

            lines, font, text_w, text_h = fit_text_in_balloon(draw, text, eff_bw, bh)

            # Posición de inicio centrada verticalmente con respecto al centro del globo
            start_y = cy - text_h // 2
            curr_y = start_y

            for line in lines:
                l_bbox = draw.textbbox((0, 0), line, font=font)
                lw = l_bbox[2] - l_bbox[0]
                lh = l_bbox[3] - l_bbox[1]
                # Centrado horizontal exacto por línea respecto al eje central
                line_x = cx - lw // 2
                draw.text(
                    (line_x, curr_y),
                    line,
                    font=font,
                    fill=block.text_color
                )
                curr_y += lh + 2

        else:
            # SFX / Onomatopeyas: Dibujar grande con contorno contrastante
            sfx_size = min(42, max(14, int(bh * 0.7)))
            font = get_font(size=sfx_size, is_sfx=True)

            # Word wrap básico para SFX si es largo
            lines = textwrap.wrap(text, width=max(6, int(bw / (sfx_size * 0.6))))
            if not lines:
                lines = [text]

            _, text_h = calculate_text_dimensions(draw, lines, font)
            curr_y = y1 + (bh - text_h) // 2

            for line in lines:
                l_bbox = draw.textbbox((0, 0), line, font=font)
                lw = l_bbox[2] - l_bbox[0]
                lh = l_bbox[3] - l_bbox[1]
                line_x = x1 + (bw - lw) // 2

                # Trazo contrastante (stroke): texto blanco con borde negro, o viceversa
                fill_color = (255, 255, 255)
                stroke_color = (0, 0, 0)

                draw.text(
                    (line_x, curr_y),
                    line,
                    font=font,
                    fill=fill_color,
                    stroke_width=3,
                    stroke_fill=stroke_color
                )
                curr_y += lh + 3

    # Retornar BGR para OpenCV / codificación final
    out_rgb = np.array(pil_img)
    return cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)
