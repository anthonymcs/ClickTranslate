"""
Módulo de Re-tipografía Inteligente con Pillow (Calidad Scanlation Profesional).
- Carga de fuentes en backend/assets/fonts/ con Fallback automático (incluyendo fuentes CJK si el destino es asiático).
- Escalado dinámico de fuente adaptable a cualquier resolución (SD, HD, 2K, 4K).
- Soporte de saltos de línea explícitos (fechas, títulos y subtítulos).
- Preservación automática del color de texto original y su contorno (stroke/glow).
"""

import os
import glob
import textwrap
import logging
import unicodedata
from typing import List, Tuple, Optional
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .detector import TextBlock

logger = logging.getLogger("ClickTranslate.Typesetter")

# Rutas de búsqueda de fuentes
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "assets", "fonts")

# Fuentes estándar de respaldo para alfabeto latino
SYSTEM_FONTS = [
    "C:/Windows/Fonts/comicbd.ttf",
    "C:/Windows/Fonts/comic.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf"
]

# Fuentes del sistema con soporte completo para CJK (Japonés, Coreano, Chino)
CJK_SYSTEM_FONTS = [
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]


def contains_cjk_glyphs(text: str) -> bool:
    """Detecta si la cadena a renderizar contiene glifos CJK que requieren fuente asiática."""
    for c in text:
        code = ord(c)
        if (0x3000 <= code <= 0x30FF) or (0x4E00 <= code <= 0x9FFF) or (0xAC00 <= code <= 0xD7AF):
            return True
    return False


def resolve_font_path(preferred_names: List[str], need_cjk: bool = False) -> Optional[str]:
    """Busca primero en backend/assets/fonts/ y luego en el sistema."""
    if need_cjk:
        for cf in CJK_SYSTEM_FONTS:
            if os.path.isfile(cf):
                return cf

    if os.path.isdir(FONTS_DIR):
        for name in preferred_names:
            candidate = os.path.join(FONTS_DIR, name)
            if os.path.isfile(candidate):
                return candidate
            for f in os.listdir(FONTS_DIR):
                if f.lower() == name.lower():
                    return os.path.join(FONTS_DIR, f)

        ttf_files = glob.glob(os.path.join(FONTS_DIR, "*.ttf"))
        if ttf_files:
            return ttf_files[0]

    for sf in SYSTEM_FONTS:
        if os.path.isfile(sf):
            return sf

    return None


def get_font(size: int, is_sfx: bool = False, need_cjk: bool = False, clean_sans: bool = False) -> ImageFont.FreeTypeFont:
    """Carga la fuente apropiada con el tamaño deseado."""
    if clean_sans:
        preferred = ["segoeuib.ttf", "arialbd.ttf", "ComicBold.ttf"]
        for sf in ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
            if not need_cjk and os.path.isfile(sf):
                try:
                    return ImageFont.truetype(sf, size=size)
                except Exception:
                    pass
    else:
        preferred = ["ComicBold.ttf", "WildWords.ttf", "AnimeAce.ttf", "animeace.ttf", "Comic.ttf", "comic.ttf"]
    font_path = resolve_font_path(preferred, need_cjk=need_cjk)

    if font_path:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception as e:
            logger.warning(f"No se pudo cargar la fuente '{font_path}': {e}")

    try:
        return ImageFont.load_default()
    except Exception:
        return None


def calculate_text_dimensions(
    draw: ImageDraw.ImageDraw,
    lines: List[str],
    font: ImageFont.ImageFont,
    line_spacing: int = 4,
    stroke_w: int = 0
) -> Tuple[int, int]:
    """Calcula el ancho máximo y alto total de un bloque multilínea."""
    max_w = 0
    total_h = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_w)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        max_w = max(max_w, w)
        total_h += h + line_spacing
    if lines:
        total_h -= line_spacing
    return max_w, max(0, total_h)


def wrap_preserving_newlines(text: str, chars_per_line: int, allow_break_words: bool = False) -> List[str]:
    """Envuelve el texto respetando los saltos de línea explícitos (\\n) sin cortar palabras a la mitad."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return [text]
    all_lines: List[str] = []
    for p in paragraphs:
        wrapped = textwrap.wrap(
            p,
            width=chars_per_line,
            break_long_words=allow_break_words,
            break_on_hyphens=False
        )
        if wrapped:
            all_lines.extend(wrapped)
        else:
            all_lines.append(p)
    return all_lines


def sanitize_for_comic_font(text: str, need_cjk: bool = False) -> str:
    """Normaliza puntuación asiática y símbolos especiales para evitar recuadros vacíos (tofu) en fuentes de cómic."""
    text = unicodedata.normalize("NFKC", text)
    replacements = {
        "〈": "(",
        "〉": ")",
        "《": "(",
        "》": ")",
        "【": "[",
        "】": "]",
        "「": '"',
        "」": '"',
        "『": '"',
        "』": '"',
        "〜": "~",
        "～": "~",
        "…": "...",
        "‥": "..",
        "—": "-",
        "―": "-",
        "ー": "-",
        "♥": "~",
        "♡": "~",
        "❤": "~",
        "♪": "~",
        "♫": "~",
        "★": "*",
        "☆": "*",
        "・": "-",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    if not need_cjk:
        # Filtrar cualquier carácter fuera de Latin-1 / puntuación extendida que no exista en ComicBold.ttf
        cleaned_chars = []
        for ch in text:
            code = ord(ch)
            if ch == "\n" or (32 <= code <= 0x024F) or ch in "¡¿«»—–…“”‘’•":
                cleaned_chars.append(ch)
        text = "".join(cleaned_chars)

    return text.strip()


def fit_text_in_balloon(
    draw: ImageDraw.ImageDraw,
    text: str,
    box_w: int,
    box_h: int,
    is_sfx: bool = False,
    has_stroke: bool = False,
    min_size: int = 8,
    max_size: Optional[int] = None,
    clean_sans: bool = False
) -> Tuple[List[str], ImageFont.ImageFont, int, int, int]:
    """
    Encuentra de forma adaptativa el tamaño de fuente óptimo y la división en líneas (word-wrap)
    para que el texto encaje perfectamente en el bounding box a cualquier resolución de imagen.
    """
    need_cjk = contains_cjk_glyphs(text)
    text = sanitize_for_comic_font(text, need_cjk=need_cjk)
    if not clean_sans:
        text = text.upper()

    if max_size is None:
        # Escalar el límite superior proporcionalmente a las dimensiones de la caja (soporta imágenes 2K/4K)
        max_size = max(26, min(100, int(min(box_w, box_h) * 0.54)))

    usable_w = max(20, int(box_w * (0.95 if is_sfx else 0.90)))
    usable_h = max(20, int(box_h * (0.94 if is_sfx else 0.90)))

    best_font = get_font(size=min_size, is_sfx=is_sfx, need_cjk=need_cjk, clean_sans=clean_sans)
    best_lines = [text]
    best_w, best_h = box_w, box_h
    best_spacing = 3

    for size in range(max_size, min_size - 1, -1):
        font = get_font(size=size, is_sfx=is_sfx, need_cjk=need_cjk, clean_sans=clean_sans)
        stroke_w = max(2, int(size * 0.09)) if (has_stroke and not clean_sans) else (1 if has_stroke else 0)
        line_spacing = max(2, int(size * 0.16))

        # Medir el ancho real promedio de un carácter con esta fuente
        sample_str = "abcdefghijklmnopqrs" if clean_sans else "ABCDEFGHIJKLMN"
        sample_bbox = draw.textbbox((0, 0), sample_str, font=font)
        avg_char_w = max(4.0, (sample_bbox[2] - sample_bbox[0]) / len(sample_str))
        chars_per_line = max(3, int(usable_w / avg_char_w))

        lines = wrap_preserving_newlines(text, chars_per_line, allow_break_words=(size <= min_size))
        w_calc, h_calc = calculate_text_dimensions(draw, lines, font, line_spacing=line_spacing, stroke_w=stroke_w)

        if w_calc <= usable_w and h_calc <= usable_h:
            return lines, font, w_calc, h_calc, line_spacing

        best_font = font
        best_lines = lines
        best_w, best_h = w_calc, h_calc
        best_spacing = line_spacing

    return best_lines, best_font, best_w, best_h, best_spacing


def render_typesetting(img_bgr: np.ndarray, blocks: List[TextBlock]) -> np.ndarray:
    """
    Dibuja los textos traducidos en la imagen:
    - Diálogos en globo claro: Centrados con auto-fit sobre globo limpio/difuminado.
    - Textos flotantes sobre ilustración: Tarjeta difuminada estilo Google Translate con tipografía nítida mixta de alto contraste.
    - Textos sobre fondo oscuro uniforme o SFX: Preservan el color de texto y el contorno (stroke) original.
    """
    im_h, im_w = img_bgr.shape[:2]
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb).convert("RGBA")

    for block in blocks:
        text = unicodedata.normalize("NFKC", block.translated_text or block.text).strip()
        if not text:
            continue

        x1, y1, x2, y2 = block.render_box if block.render_box is not None else block.box
        bw = max(16, x2 - x1)
        bh = max(16, y2 - y1)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        draw_tmp = ImageDraw.Draw(pil_img)
        use_clean_sans = bool(block.draw_backdrop)
        has_stroke = (block.stroke_color is not None or block.type == "sfx") and not block.draw_backdrop
        lines, font, text_w, text_h, line_spacing = fit_text_in_balloon(
            draw_tmp,
            text,
            bw,
            bh,
            is_sfx=(block.type == "sfx" and not block.draw_backdrop),
            has_stroke=has_stroke,
            clean_sans=use_clean_sans
        )

        font_size = getattr(font, "size", 16)
        stroke_w = max(2, int(font_size * 0.11)) if has_stroke else 0
        stroke_fill = block.stroke_color if block.stroke_color is not None else (0, 0, 0)

        # Ajustar centro para que el bloque entero nunca se salga de los bordes de la imagen
        curr_y = max(6, min(im_h - text_h - 6, cy - text_h // 2))
        eff_cx = max(text_w // 2 + 10, min(im_w - text_w // 2 - 10, cx))

        # Si el texto flota sobre ilustración (estilo Google Translate), dibujar tarjeta translúcida sobre el difuminado
        if block.draw_backdrop:
            pad_x = max(10, int(font_size * 0.55))
            pad_y = max(8, int(font_size * 0.45))
            rx1 = max(2, eff_cx - text_w // 2 - pad_x)
            ry1 = max(2, curr_y - pad_y)
            rx2 = min(im_w - 2, eff_cx + text_w // 2 + pad_x)
            ry2 = min(im_h - 2, curr_y + text_h + pad_y + max(5, int(font_size * 0.25)))

            overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            border_c = (*block.stroke_color, 210) if block.stroke_color is not None else (148, 163, 184, 190)
            radius = max(8, int(font_size * 0.45))
            ov_draw.rounded_rectangle(
                [rx1, ry1, rx2, ry2],
                radius=radius,
                fill=(15, 18, 28, 200),
                outline=border_c,
                width=max(2, int(font_size * 0.08))
            )
            pil_img = Image.alpha_composite(pil_img, overlay)
            text_fill = (255, 255, 255, 255)
            stroke_fill_rgba = (0, 0, 0, 255)
        else:
            text_fill = (*block.text_color, 255)
            stroke_fill_rgba = (*stroke_fill, 255)

        draw = ImageDraw.Draw(pil_img)
        for line in lines:
            l_bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_w)
            lw = l_bbox[2] - l_bbox[0]
            lh = l_bbox[3] - l_bbox[1]
            line_x = max(4, min(im_w - lw - 4, eff_cx - lw // 2))

            if stroke_w > 0:
                draw.text(
                    (line_x, curr_y),
                    line,
                    font=font,
                    fill=text_fill,
                    stroke_width=stroke_w,
                    stroke_fill=stroke_fill_rgba
                )
            else:
                draw.text(
                    (line_x, curr_y),
                    line,
                    font=font,
                    fill=text_fill
                )
            curr_y += lh + line_spacing

    out_rgb = np.array(pil_img.convert("RGB"))
    return cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)
