"""
Módulo de Limpieza Visual e Inpainting.
- Globos sólidos: Relleno ultrarrápido con OpenCV (< 5 ms).
- SFX sobre arte/ilustración: Inpainting neuronal LaMa nativo en PyTorch TorchScript
  (compatible con Pillow 10+ y Python 3.12, eliminando conflictos de dependencia obsoletos)
  con fallback robusto a OpenCV Telea.
"""

import os
import logging
from typing import List, Optional
import cv2
import numpy as np
from PIL import Image
import torch

from .detector import TextBlock

logger = logging.getLogger("ClickTranslate.Inpainter")

_lama_model_instance = None
LAMA_MODEL_URL = "https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt"


class NativeLamaInpainter:
    """
    Implementación nativa y ligera de LaMa utilizando PyTorch TorchScript.
    Totalmente compatible con Pillow 10.x+ y Python 3.12, eliminando las
    restricciones de versiones incompatibles de paquetes de terceros.
    """
    def __init__(self, device: Optional[str] = None):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        self.model = self._load_or_download_model()

    def _load_or_download_model(self):
        models_dir = os.path.join(os.path.expanduser("~"), ".cache", "clicktranslate", "models")
        os.makedirs(models_dir, exist_ok=True)
        model_path = os.path.join(models_dir, "big-lama.pt")

        if not os.path.isfile(model_path):
            logger.info(f"Descargando checkpoint oficial de LaMa a {model_path}...")
            try:
                torch.hub.download_url_to_file(LAMA_MODEL_URL, model_path, progress=True)
            except Exception as e:
                logger.error(f"Error descargando pesos de LaMa: {e}")
                raise e

        logger.info(f"Cargando modelo LaMa TorchScript en dispositivo: {self.device}...")
        model = torch.jit.load(model_path, map_location=self.device)
        model.eval()
        return model

    @torch.no_grad()
    def __call__(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        """
        Ejecuta inpainting neuronal LaMa sobre la imagen y su máscara binaria.
        """
        orig_w, orig_h = image.size

        # Redondear dimensiones al múltiplo de 8 más cercano requerido por LaMa
        pad_w = (8 - orig_w % 8) % 8
        pad_h = (8 - orig_h % 8) % 8

        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        mask_np = np.array(mask.convert("L")).astype(np.float32) / 255.0
        mask_np = (mask_np > 0).astype(np.float32)

        if pad_w > 0 or pad_h > 0:
            img_np = np.pad(img_np, ((0, pad_h), (0, pad_w), (0, 0)), mode="reflect")
            mask_np = np.pad(mask_np, ((0, pad_h), (0, pad_w)), mode="reflect")

        # Convertir a tensores PyTorch [1, C, H, W]
        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).to(self.device)
        mask_tensor = torch.from_numpy(mask_np).unsqueeze(0).unsqueeze(0).to(self.device)

        # Inferencia
        pred = self.model(img_tensor, mask_tensor)

        # Post-procesamiento
        pred = pred[0].permute(1, 2, 0).detach().cpu().numpy()
        pred = np.clip(pred * 255.0, 0, 255).astype(np.uint8)

        # Quitar el padding
        pred = pred[:orig_h, :orig_w]
        return Image.fromarray(pred)


def get_lama_inpainter():
    """Carga perezosa del modelo LaMa nativo en memoria RAM."""
    global _lama_model_instance
    if _lama_model_instance is None:
        # 1. Intentar con cargador nativo
        try:
            _lama_model_instance = NativeLamaInpainter()
            logger.info("Motor nativo LaMa inicializado exitosamente.")
            return _lama_model_instance
        except Exception as ne:
            logger.warning(f"No se pudo inicializar LaMa nativo: {ne}. Buscando simple-lama-inpainting...")

        # 2. Intentar si simple-lama-inpainting estuviese instalado
        try:
            from simple_lama_inpainting import SimpleLama
            _lama_model_instance = SimpleLama()
            logger.info("simple-lama-inpainting cargado exitosamente.")
            return _lama_model_instance
        except Exception:
            _lama_model_instance = None
            logger.warning("LaMa no disponible. Se utilizará OpenCV Telea de alta precisión.")

    return _lama_model_instance


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
    cleaned_balloons = inpaint_balloons_fast(img_bgr, blocks, balloon_mask)

    if np.count_nonzero(sfx_mask) > 0:
        final_clean = inpaint_sfx_lama(cleaned_balloons, sfx_mask)
    else:
        final_clean = cleaned_balloons

    return final_clean
