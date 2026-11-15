"""
Módulo de Limpieza Visual e Inpainting.
- Globos sólidos: Relleno ultrarrápido con OpenCV (< 5 ms).
- SFX sobre arte/ilustración: LaMa (simple-lama-inpainting) con fallback a Telea.
"""

import logging
from typing import List
import cv2
import numpy as np
from PIL import Image

from .detector import TextBlock

logger = logging.getLogger("ClickTranslate.Inpainter")

_lama_model = None


def get_lama_inpainter():
    """Carga perezosa del modelo SimpleLama para inpainting sobre arte."""
    global _lama_model
    if _lama_model is None:
        try:
            logger.info("Cargando modelo LaMa Inpainting en memoria RAM...")
            from simple_lama_inpainting import SimpleLama
            _lama_model = SimpleLama()
            logger.info("Modelo LaMa cargado exitosamente.")
        except Exception as e:
            logger.warning(f"simple-lama-inpainting no disponible o error al cargar ({e}). Se usará OpenCV Telea.")
            _lama_model = None
    return _lama_model


def inpaint_balloons_fast(img_bgr: np.ndarray, blocks: List[TextBlock], balloon_mask: np.ndarray) -> np.ndarray:
    """
    Limpia los globos sólidos directamente con OpenCV.
    Si el fondo del globo es de baja varianza, se rellena con su color dominante exacto,
    o se aplica cv2.inpaint de forma localizada para mantener suavizado.
    """
    clean_img = img_bgr.copy()

    for block in blocks:
        if block.type != "dialog":
            continue

        x1, y1, x2, y2 = block.box
        h, w = clean_img.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if block.is_uniform_bg:
            # Relleno sólido ultrarrápido con el color dominante del fondo
            # Rellenar la región del texto con un pequeño padding
            pad_x = max(2, int((x2 - x1) * 0.05))
            pad_y = max(2, int((y2 - y1) * 0.05))
            bx1, by1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
            bx2, by2 = min(w, x2 + pad_x), min(h, y2 + pad_y)

            cv2.rectangle(clean_img, (bx1, by1), (bx2, by2), block.bg_color, -1)
        else:
            # Si tiene un gradiente suave en el globo, inpainting rápido por parche
            patch_mask = balloon_mask[y1:y2, x1:x2]
            if np.count_nonzero(patch_mask) > 0:
                patch_img = clean_img[y1:y2, x1:x2]
                inpainted_patch = cv2.inpaint(patch_img, patch_mask, 3, cv2.INPAINT_TELEA)
                clean_img[y1:y2, x1:x2] = inpainted_patch

    return clean_img


def inpaint_sfx_lama(img_bgr: np.ndarray, sfx_mask: np.ndarray) -> np.ndarray:
    """
    Limpia onomatopeyas y texto flotante sobre el dibujo utilizando LaMa
    para reconstruir tramas, líneas y sombreados. Fallback a OpenCV Telea si LaMa no está disponible.
    """
    if np.count_nonzero(sfx_mask) == 0:
        return img_bgr

    lama = get_lama_inpainter()

    if lama is not None:
        try:
            # SimpleLama trabaja con PIL Images en RGB
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            pil_mask = Image.fromarray(sfx_mask)

            # Inpainting con red neuronal LaMa
            result_pil = lama(pil_img, pil_mask)
            result_rgb = np.array(result_pil)
            return cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"Fallo durante la inferencia con LaMa: {e}. Aplicando OpenCV Telea.")

    # Fallback OpenCV Telea de alta calidad
    dilated_mask = cv2.dilate(sfx_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    return cv2.inpaint(img_bgr, dilated_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)


def clean_page(img_bgr: np.ndarray, blocks: List[TextBlock], balloon_mask: np.ndarray, sfx_mask: np.ndarray) -> np.ndarray:
    """
    Pipeline completo de limpieza de página:
    1. Rellena globos sólidos con OpenCV (< 5 ms).
    2. Reconstruye arte de fondo para SFX con LaMa / Telea.
    """
    # 1. Limpieza de globos
    cleaned_balloons = inpaint_balloons_fast(img_bgr, blocks, balloon_mask)

    # 2. Limpieza de SFX sobre dibujo
    if np.count_nonzero(sfx_mask) > 0:
        final_clean = inpaint_sfx_lama(cleaned_balloons, sfx_mask)
    else:
        final_clean = cleaned_balloons

    return final_clean
