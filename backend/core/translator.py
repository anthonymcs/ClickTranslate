"""
Módulo de Traducción Contextual con Ollama Asíncrono.
Envía la página completa en formato JSON y optimiza la memoria con 'keep_alive': '5m'.
Soporta todo tipo de contenido gráfico y géneros sin restricciones ni censura.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
import httpx

from .detector import TextBlock

logger = logging.getLogger("ClickTranslate.Translator")

OLLAMA_BASE_URL = "http://localhost:11434"


async def fetch_available_models(base_url: str = OLLAMA_BASE_URL) -> List[str]:
    """Consulta la API de Ollama y devuelve la lista de nombres de modelos locales instalados."""
    url = f"{base_url}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return models
    except Exception as e:
        logger.warning(f"No se pudo conectar a Ollama en {url}: {e}")
    return []


def build_translation_prompt(blocks: List[TextBlock], src_lang: str = "ja") -> Tuple[str, str]:
    """
    Construye el system prompt y el prompt de usuario estructurado con el contexto
    completo de la página para garantizar coherencia tonal y fluidez narrativa.
    """
    system_prompt = (
        "Eres un traductor profesional experto y fidedigno de mangas, manhwas, manhuas y cómics occidentales.\n"
        "Tu misión es traducir con precisión milimétrica todos los textos y onomatopeyas de la página al español natural y fluido.\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. NO CENSURES, omitas ni alteres ninguna palabra. Esta herramienta soporta todo tipo de contenido gráfico "
        "(acción, seinen, shonen, romance, erótico/ecchi, horror, gore, lenguaje soez, etc.) sin restricciones.\n"
        "2. Mantén la coherencia y tono de los personajes a lo largo de toda la página.\n"
        "3. Para bloques de tipo 'sfx' (onomatopeyas), adapta el efecto de sonido al español de cómics (ej. 'DOKI DOKI' -> 'PALPITAR' o 'BUM BUM', 'GOGOGO' -> 'RETUMBO' o 'RUMBLE', 'DON' -> 'BOOM', 'KYAA' -> '¡AHH!').\n"
        "4. Devuelve ÚNICAMENTE un objeto JSON válido donde cada clave sea el 'id' numérico como string o número y el valor sea el texto traducido al español.\n"
        "Ejemplo de salida:\n"
        '{"1": "¡No puede ser!", "2": "RETUMBO", "3": "¿Quién eres?"}'
    )

    items = []
    for b in blocks:
        items.append({
            "id": b.id,
            "type": b.type,
            "original_text": b.text
        })

    user_payload = {
        "source_language": src_lang,
        "target_language": "es",
        "blocks": items
    }

    user_prompt = (
        f"Traduce al español todos los siguientes bloques de diálogo y SFX respetando el contexto de la página.\n"
        f"Devuelve un JSON estrictamente estructurado con los IDs y sus traducciones:\n"
        f"{json.dumps(user_payload, ensure_ascii=False, indent=2)}"
    )

    return system_prompt, user_prompt


async def translate_page_contextual(
    blocks: List[TextBlock],
    model_name: str = "qwen2.5:7b",
    src_lang: str = "ja",
    base_url: str = OLLAMA_BASE_URL
) -> Dict[int, str]:
    """
    Envía los bloques a Ollama mediante /api/generate en modo JSON con keep_alive: '5m'.
    Retorna un diccionario {id: "texto traducido en español"}.
    """
    if not blocks:
        return {}

    # Filtrar bloques con texto vacío
    valid_blocks = [b for b in blocks if b.text and b.text.strip()]
    if not valid_blocks:
        return {b.id: b.text for b in blocks}

    system_prompt, user_prompt = build_translation_prompt(valid_blocks, src_lang=src_lang)

    payload = {
        "model": model_name,
        "prompt": f"<system>\n{system_prompt}\n</system>\n\n<user>\n{user_prompt}\n</user>",
        "format": "json",
        "stream": False,
        "keep_alive": "5m",  # Descarga el modelo de la RAM tras 5 minutos de inactividad
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
        }
    }

    translations: Dict[int, str] = {}

    try:
        url = f"{base_url}/api/generate"
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                result = resp.json()
                raw_response = result.get("response", "{}")
                try:
                    parsed = json.loads(raw_response)
                    # Manejar diferentes variantes de respuestas JSON
                    if isinstance(parsed, dict):
                        # Caso directo {"1": "traducción", "2": ...}
                        # O anidado {"translations": {"1": ...}} o {"blocks": [...]}
                        if "translations" in parsed and isinstance(parsed["translations"], dict):
                            parsed = parsed["translations"]
                        elif "blocks" in parsed and isinstance(parsed["blocks"], list):
                            for item in parsed["blocks"]:
                                b_id = item.get("id")
                                trans = item.get("translation") or item.get("translated_text") or item.get("text", "")
                                if b_id is not None:
                                    translations[int(b_id)] = str(trans).strip()

                        for k, v in parsed.items():
                            try:
                                block_id = int(k)
                                if isinstance(v, str):
                                    translations[block_id] = v.strip()
                                elif isinstance(v, dict):
                                    t = v.get("translation") or v.get("text", "")
                                    translations[block_id] = str(t).strip()
                            except ValueError:
                                continue
                except Exception as je:
                    logger.warning(f"Error parseando JSON de Ollama: {je}. Respuesta bruta: {raw_response[:200]}")
            else:
                logger.error(f"Ollama devolvió código {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Error de conexión con Ollama ({base_url}): {e}")

    # Rellenar con texto original o fallback si algún bloque no vino en la respuesta
    for b in blocks:
        if b.id not in translations:
            translations[b.id] = b.text

    return translations
