"""
Servidor FastAPI para ClickTranslate.
Procesamiento 100% en memoria RAM (Zero Persistence).
Optimizado para entornos con 8 GB de RAM mediante Lazy Loading y Garbage Collection.
"""

import io
import os
import gc
import uuid
import json
import base64
import asyncio
import zipfile
import logging
from typing import Dict, Any, Optional, Tuple

import cv2
import numpy as np
from natsort import natsorted
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from core.detector import detect_balloons_and_sfx
from core.ocr_engine import run_ocr
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
    version="1.0.0",
    description="Motor de traducción visual para cómics, mangas y manhwas sin persistencia en disco"
)

# Habilitar CORS para Tauri y clientes web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Diccionario de trabajos en memoria RAM
# job_id -> { "status": str, "page": int, "total": int, "percent": int, "thumbnail": str, "buffer": io.BytesIO, ... }
BATCH_JOBS: Dict[str, Dict[str, Any]] = {}

VALID_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def process_single_image_in_memory(image_bytes: bytes, src_lang: str, model_name: str) -> Tuple[bytes, bytes]:
    """
    Ejecuta el pipeline de traducción completo sobre los bytes de una imagen en memoria RAM.
    Retorna: (imagen_traducida_png_bytes, miniatura_jpeg_bytes)
    """
    # Decodificar imagen desde memoria
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if img_bgr is None:
        raise ValueError("No se pudo decodificar la imagen proporcionada.")

    # 1. OCR (detección de texto y extracción)
    ocr_results = run_ocr(img_bgr, raw_lang=src_lang)
    raw_boxes = [box for box, _ in ocr_results]

    # 2. Detección y clasificación de globos vs SFX
    blocks, balloon_mask, sfx_mask = detect_balloons_and_sfx(img_bgr, raw_boxes, lang=src_lang)

    # Asignar texto de OCR al bloque correspondiente
    for block in blocks:
        for (box, text) in ocr_results:
            if box == block.box:
                block.text = text
                break

    # 3. Limpieza visual (Inpainting: OpenCV para globos, LaMa para SFX)
    cleaned_img = clean_page(img_bgr, blocks, balloon_mask, sfx_mask)

    # 4. Traducción contextual con Ollama
    # Ejecutamos en loop sincrónico para la función auxiliar
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                translations = pool.submit(
                    asyncio.run,
                    translate_page_contextual(blocks, model_name=model_name, src_lang=src_lang)
                ).result()
        else:
            translations = loop.run_until_complete(
                translate_page_contextual(blocks, model_name=model_name, src_lang=src_lang)
            )
    except Exception:
        # Fallback de llamada directa
        translations = asyncio.run(
            translate_page_contextual(blocks, model_name=model_name, src_lang=src_lang)
        )

    for block in blocks:
        if block.id in translations:
            block.translated_text = translations[block.id]

    # 5. Re-tipografía inteligente (Pillow)
    final_bgr = render_typesetting(cleaned_img, blocks)

    # Codificar a PNG en memoria
    success, png_buf = cv2.imencode(".png", final_bgr)
    if not success:
        raise RuntimeError("Error al codificar imagen traducida a PNG.")

    # Generar miniatura JPEG ligera para preview en vivo
    h, w = final_bgr.shape[:2]
    thumb_w = 400
    thumb_h = int(h * (thumb_w / max(1, w)))
    resized_thumb = cv2.resize(final_bgr, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
    _, thumb_buf = cv2.imencode(".jpg", resized_thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 75])

    # Forzar recolección de basura para optimización en 8GB de RAM
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
    model_name: str = Form("qwen2.5:7b")
):
    """
    Traduce una imagen individual del portapapeles o archivo.
    Procesa estrictamente en memoria y retorna bytes PNG.
    """
    try:
        content = await file.read()
        translated_png, _ = process_single_image_in_memory(content, src_lang, model_name)
        return Response(content=translated_png, media_type="image/png")
    except Exception as e:
        logger.error(f"Error procesando /translate-single: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        gc.collect()


async def run_batch_job_task(job_id: str, zip_bytes: bytes, src_lang: str, model_name: str, out_ext: str):
    """Tarea asíncrona de procesamiento de lote ZIP/CBZ página por página en RAM."""
    job_info = BATCH_JOBS.get(job_id)
    if not job_info:
        return

    try:
        in_memory_zip = zipfile.ZipFile(io.BytesIO(zip_bytes))
        all_entries = in_memory_zip.namelist()

        # Filtrar solo imágenes válidas ignorando directorios y metadatos del SO
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

        # Crear ZIP de salida completamente en memoria RAM
        out_memory_buffer = io.BytesIO()
        with zipfile.ZipFile(out_memory_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as out_zip:
            for idx, img_name in enumerate(sorted_images):
                if job_info.get("cancelled", False):
                    logger.info(f"Trabajo {job_id} cancelado por el usuario.")
                    return

                # Leer la página de forma secuencial
                raw_img_bytes = in_memory_zip.read(img_name)

                # Traducir página
                translated_png_bytes, thumb_jpeg_bytes = process_single_image_in_memory(
                    raw_img_bytes, src_lang, model_name
                )

                # Guardar en el zip de salida conservando la estructura de nombres
                base, _ = os.path.splitext(img_name)
                out_name = f"{base}.png"
                out_zip.writestr(out_name, translated_png_bytes)

                # Actualizar estado de progreso y miniatura para SSE
                thumb_b64 = f"data:image/jpeg;base64,{base64.b64encode(thumb_jpeg_bytes).decode('ascii')}"
                current_page = idx + 1
                percent = int((current_page / total_pages) * 100)

                job_info["page"] = current_page
                job_info["percent"] = percent
                job_info["thumbnail"] = thumb_b64

                # Limpieza estricta de memoria tras cada iteración
                del raw_img_bytes, translated_png_bytes, thumb_jpeg_bytes
                gc.collect()

        out_memory_buffer.seek(0)
        job_info["output_bytes"] = out_memory_buffer.getvalue()
        job_info["status"] = "completed"
        logger.info(f"Trabajo {job_id} completado exitosamente ({total_pages} páginas).")

    except Exception as e:
        logger.error(f"Error en trabajo de lote {job_id}: {e}", exc_info=True)
        job_info["status"] = "error"
        job_info["error"] = str(e)
    finally:
        gc.collect()


@app.post("/translate-batch")
async def translate_batch(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    src_lang: str = Form("auto"),
    model_name: str = Form("qwen2.5:7b"),
    output_format: str = Form("zip")
):
    """
    Recibe un archivo ZIP o CBZ y arranca el procesamiento por páginas en RAM.
    Retorna un job_id para seguimiento mediante Server-Sent Events.
    """
    content = await file.read()
    job_id = str(uuid.uuid4())

    orig_filename = file.filename or "manga_chapter"
    base_name, _ = os.path.splitext(orig_filename)
    out_ext = "cbz" if output_format.lower() == "cbz" else "zip"
    final_filename = f"{base_name}_ES.{out_ext}"

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

    # Despachar tarea en segundo plano
    background_tasks.add_task(
        run_batch_job_task, job_id, content, src_lang, model_name, out_ext
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

            import json
            yield {"event": "message", "data": json.dumps(data)}

            if job["status"] in ["completed", "error"] or job.get("cancelled"):
                break

            await asyncio.sleep(0.4)

    return EventSourceResponse(event_generator())


@app.get("/download/{job_id}")
def download_batch_result(job_id: str):
    """
    Descarga el ZIP o CBZ generado y purga inmediatamente el trabajo de la memoria RAM.
    """
    job = BATCH_JOBS.get(job_id)
    if not job or job["status"] != "completed" or not job["output_bytes"]:
        raise HTTPException(status_code=404, detail="El archivo aún no está listo o ya fue purgado.")

    data = job["output_bytes"]
    filename = job["filename"]
    media_type = "application/vnd.comicbook+zip" if filename.endswith(".cbz") else "application/zip"

    # Purgar inmediatamente el job de la memoria RAM (Principio de Cero Persistencia)
    del BATCH_JOBS[job_id]
    gc.collect()

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.post("/cancel/{job_id}")
def cancel_batch_job(job_id: str):
    """Cancela un trabajo en cola o ejecución y libera la memoria RAM."""
    job = BATCH_JOBS.get(job_id)
    if job:
        job["cancelled"] = True
        del BATCH_JOBS[job_id]
        gc.collect()
        return {"status": "cancelled", "job_id": job_id}
    return {"status": "not_found"}
