"""
Módulo de Detección de Texto y Globos de Cómic mediante IA Neuronal.
Utiliza 'comic-text-detector.onnx' (entrenado específicamente para manga, cómics y doujinshi).
Detecta globos de diálogo, onomatopeyas y genera máscaras precisas de trazos de texto.
"""

import os
import urllib.request
import logging
from typing import List, Tuple, Dict, Any, Optional
import cv2
import numpy as np
import torch
import onnxruntime as ort

from .ctd.utils.yolov5_utils import non_max_suppression
from .ctd.utils.db_utils import SegDetectorRepresenter
from .ctd.utils.imgproc_utils import letterbox
from .ctd.utils.textblock import group_output, TextBlock as CTDTextBlock
from .ctd.utils.textmask import refine_mask

logger = logging.getLogger("ClickTranslate.ComicDetector")

_comic_detector_session: Optional[ort.InferenceSession] = None
_seg_rep: Optional[SegDetectorRepresenter] = None

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "comic-text-detector.onnx"
)
MODEL_URL = "https://huggingface.co/mayocream/comic-text-detector-onnx/resolve/main/comictextdetector.pt.onnx"


def ensure_model_exists() -> bool:
    """Descarga automáticamente el modelo ONNX desde Hugging Face si no existe localmente."""
    if os.path.isfile(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 10_000_000:
        return True

    logger.info("Modelo comic-text-detector.onnx no encontrado. Iniciando descarga automática...")
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    temp_path = MODEL_PATH + ".tmp"
    try:
        req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=90) as response, open(temp_path, "wb") as out_file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out_file.write(chunk)
        if os.path.exists(MODEL_PATH):
            os.remove(MODEL_PATH)
        os.rename(temp_path, MODEL_PATH)
        logger.info(f"Modelo comic-text-detector.onnx descargado exitosamente ({os.path.getsize(MODEL_PATH)} bytes).")
        return True
    except Exception as e:
        logger.error(f"Error descargando modelo comic-text-detector: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


def get_detector_session() -> Optional[ort.InferenceSession]:
    """Carga perezosa del modelo ONNX de detección neuronal."""
    global _comic_detector_session, _seg_rep
    if _comic_detector_session is None:
        if not ensure_model_exists():
            logger.warning(f"No se pudo asegurar el modelo en {MODEL_PATH}")
            return None
        try:
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = 4
            sess_opts.inter_op_num_threads = 1
            sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            _comic_detector_session = ort.InferenceSession(
                MODEL_PATH,
                sess_options=sess_opts,
                providers=["CPUExecutionProvider"]
            )
            _seg_rep = SegDetectorRepresenter(thresh=0.3)
            logger.info("Comic-Text-Detector (ONNX) cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error cargando comic-text-detector.onnx: {e}")
            _comic_detector_session = None
    return _comic_detector_session


def postprocess_mask(img: np.ndarray, thresh: Optional[float] = None) -> np.ndarray:
    """Procesa la máscara de segmentación a uint8."""
    img = img.squeeze()
    if thresh is not None:
        img = img > thresh
    img = img * 255
    return img.astype(np.uint8)


def detect_comic_text(
    img_bgr: np.ndarray,
    conf_thresh: float = 0.22,
    nms_thresh: float = 0.35,
    input_size: Tuple[int, int] = (1024, 1024)
) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """
    Ejecuta el detector neuronal sobre la imagen:
    Retorna:
    - blocks: Lista de diccionarios con:
        'box': (x1, y1, x2, y2),
        'lines': lista de polígonos de líneas de texto,
        'conf': float,
        'is_balloon': bool
    - text_mask: Máscara binaria uint8 (255 para trazos de texto, 0 para fondo)
    """
    session = get_detector_session()
    im_h, im_w = img_bgr.shape[:2]

    if session is None:
        logger.warning("Detector neuronal no disponible, devolviendo vacío.")
        return [], np.zeros((im_h, im_w), dtype=np.uint8)

    try:
        # Preprocesamiento Letterbox manteniendo aspecto
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img_in, ratio, (dw, dh) = letterbox(img_rgb, new_shape=input_size, auto=False, stride=64)
        img_in = img_in.transpose((2, 0, 1))
        img_in = np.ascontiguousarray(img_in).astype(np.float32) / 255.0
        img_in = np.expand_dims(img_in, 0)

        # Inferencia ONNX
        blks_raw, seg_raw, det_raw = session.run(None, {"images": img_in})

        # Relación de aspecto para mapear a dimensiones originales
        resize_ratio = (im_w / (input_size[0] - dw), im_h / (input_size[1] - dh))

        # NMS para cuadros de texto
        det_tensor = torch.from_numpy(blks_raw)
        det_nms = non_max_suppression(det_tensor, conf_thres=conf_thresh, iou_thres=nms_thresh)[0].numpy()

        if len(det_nms) > 0:
            det_nms[..., [0, 2]] *= resize_ratio[0]
            det_nms[..., [1, 3]] *= resize_ratio[1]
            blines = det_nms[..., 0:4].astype(np.int32)
            confs = np.round(det_nms[..., 4], 3)
            cls = det_nms[..., 5].astype(np.int32)
            blks = (blines, cls, confs)
        else:
            blks = ([], [], [])

        # DBNet: mapa de líneas
        lines_map = torch.from_numpy(det_raw)
        lines, scores = _seg_rep(input_size, lines_map)
        idx = np.where(scores[0] > 0.35)
        lines, scores = lines[0][idx], scores[0][idx]

        # Máscara de segmentación
        mask = postprocess_mask(seg_raw)
        mask = mask[: mask.shape[0] - dh, : mask.shape[1] - dw]
        mask = cv2.resize(mask, (im_w, im_h), interpolation=cv2.INTER_LINEAR)

        if len(lines) > 0:
            lines = lines.astype(np.float64)
            lines[..., 0] *= resize_ratio[0]
            lines[..., 1] *= resize_ratio[1]
            lines = lines.astype(np.int32)
        else:
            lines = []

        # Agrupar bloques de texto
        ctd_blocks = group_output(blks, lines, im_w, im_h, mask)

        # Refinar máscara de texto y combinar con máscara neuronal base para cubrir contornos/strokes
        _, mask_bin = cv2.threshold(mask, 50, 255, cv2.THRESH_BINARY)
        try:
            mask_refined = refine_mask(img_bgr, mask, ctd_blocks)
            mask_refined = cv2.bitwise_or(mask_refined, mask_bin)
        except Exception as e:
            logger.warning(f"Error en refine_mask: {e}, usando máscara base")
            mask_refined = mask_bin

        raw_blocks = []
        for blk in ctd_blocks:
            x1, y1, x2, y2 = blk.xyxy
            x1 = max(0, int(x1))
            y1 = max(0, int(y1))
            x2 = min(im_w, int(x2))
            y2 = min(im_h, int(y2))
            bw, bh = x2 - x1, y2 - y1

            # Filtrar ruido microscópico
            if bw < 14 or bh < 14 or (bw * bh) < 220:
                continue

            raw_blocks.append({
                "box": (x1, y1, x2, y2),
                "lines": getattr(blk, "lines", []),
                "vertical": bool(getattr(blk, "vertical", False)),
                "conf": getattr(blk, "prob", 1.0),
                "is_balloon": True
            })

        # Fusionar bloques superpuestos o anidados (evita duplicados o recortes partidos)
        merged = True
        while merged and len(raw_blocks) > 1:
            merged = False
            new_list = []
            used = [False] * len(raw_blocks)
            for i in range(len(raw_blocks)):
                if used[i]:
                    continue
                b1 = raw_blocks[i]
                x1_a, y1_a, x2_a, y2_a = b1["box"]
                area_a = max(1, (x2_a - x1_a) * (y2_a - y1_a))

                for j in range(i + 1, len(raw_blocks)):
                    if used[j]:
                        continue
                    b2 = raw_blocks[j]
                    x1_b, y1_b, x2_b, y2_b = b2["box"]
                    area_b = max(1, (x2_b - x1_b) * (y2_b - y1_b))

                    ix1, iy1 = max(x1_a, x1_b), max(y1_a, y1_b)
                    ix2, iy2 = min(x2_a, x2_b), min(y2_a, y2_b)
                    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)

                    # También fusionar si están en la misma línea horizontal y se tocan (< 12px)
                    v_overlap = max(0, min(y2_a, y2_b) - max(y1_a, y1_b))
                    min_h = min(y2_a - y1_a, y2_b - y1_b)
                    h_gap = max(0, max(x1_a, x1_b) - min(x2_a, x2_b))
                    same_h_line = (not b1["vertical"] and not b2["vertical"]) and (v_overlap > 0.6 * min_h) and (h_gap <= 12)

                    if (inter / min(area_a, area_b)) >= 0.30 or same_h_line:
                        x1_a, y1_a = min(x1_a, x1_b), min(y1_a, y1_b)
                        x2_a, y2_a = max(x2_a, x2_b), max(y2_a, y2_b)
                        area_a = max(1, (x2_a - x1_a) * (y2_a - y1_a))
                        b1 = {
                            "box": (x1_a, y1_a, x2_a, y2_a),
                            "lines": b1["lines"] + b2["lines"],
                            "vertical": b1["vertical"] and b2["vertical"],
                            "conf": max(b1["conf"], b2["conf"]),
                            "is_balloon": True
                        }
                        used[j] = True
                        merged = True
                new_list.append(b1)
            raw_blocks = new_list

        return raw_blocks, mask_refined

    except Exception as e:
        logger.error(f"Error en detect_comic_text: {e}")
        return [], np.zeros((im_h, im_w), dtype=np.uint8)
