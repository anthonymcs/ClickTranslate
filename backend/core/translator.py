"""
Módulo de Traducción Contextual y Multi-idioma de Alta Velocidad.
- Modo Rápido (Google Translate API con fallback a MyMemory): Inferencia en ~200 ms, soporte para 100+ idiomas.
- Modo Ollama Local: IA contextual sin censura para ejecución 100% privada en RAM.
- Soporte dinámico de idiomas origen y destino (estilo Google Translate).
"""

import os
import json
import logging
import urllib.parse
import urllib.request
from typing import List, Dict, Any, Optional, Tuple
import httpx

from .detector import TextBlock

logger = logging.getLogger("ClickTranslate.Translator")

OLLAMA_BASE_URL = "http://localhost:11434"

# Mapeo de códigos de idioma amigables
LANGUAGE_CODES = {
    "auto": "auto",
    "es": "es",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "zh": "zh-CN",
    "pt": "pt",
    "fr": "fr",
    "de": "de",
    "it": "it",
    "ru": "ru",
}


def translate_text_fast_google(text: str, src_lang: str = "auto", tgt_lang: str = "es") -> Optional[str]:
    """
    Traduce un texto usando la API de Google Translate con headers de navegador.
    Tiempo de respuesta: ~100-250 ms.
    """
    if not text or not text.strip():
        return ""

    src = LANGUAGE_CODES.get(src_lang.lower(), src_lang.lower())
    tgt = LANGUAGE_CODES.get(tgt_lang.lower(), tgt_lang.lower())

    url = (
        f"https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl={src}&tl={tgt}&dt=t&q="
        + urllib.parse.quote(text)
    )

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://translate.google.com/",
            "Accept": "*/*",
        }
    )

    # Intento 1 y 2 con Google Translate API
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and len(data) > 0 and isinstance(data[0], list):
                    translated_parts = [part[0] for part in data[0] if part and len(part) > 0 and part[0]]
                    res_str = "".join(translated_parts).strip()
                    if res_str:
                        return res_str
        except Exception as e:
            logger.warning(f"Intento {attempt + 1} Google Translate API fallo: {e}")

    # Fallback inteligente con detección de idioma para evitar error 'auto'
    try:
        def detect_script(t: str) -> str:
            if any(0x3040 <= ord(c) <= 0x30FF for c in t):
                return "ja"
            if any(0xAC00 <= ord(c) <= 0xD7AF for c in t):
                return "ko"
            if any(0x4E00 <= ord(c) <= 0x9FFF for c in t):
                return "zh-CN"
            return "en"

        src_resolved = detect_script(text) if src == "auto" else src
        from deep_translator import MyMemoryTranslator
        src_mm = "en-US" if src_resolved == "en" else src_resolved
        tgt_mm = "es-ES" if tgt == "es" else tgt
        tr = MyMemoryTranslator(source=src_mm, target=tgt_mm)
        res = tr.translate(text)
        if res and "INVALID" not in res.upper() and "MYMEMORY WARNING" not in res.upper():
            return res.strip()
    except Exception as me:
        logger.warning(f"Error en fallback MyMemory: {me}")

    # Si todo falla, mantener el texto original para no mostrar mensajes de error dentro del globo
    return text


async def fetch_available_models(base_url: str = OLLAMA_BASE_URL) -> List[str]:
    """Consulta la API de Ollama y devuelve la lista de nombres de modelos locales instalados."""
    url = f"{base_url}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return models
    except Exception:
        pass
    return []


async def translate_with_ollama(
    blocks: List[TextBlock],
    model_name: str = "qwen2.5:7b",
    src_lang: str = "auto",
    tgt_lang: str = "es",
    base_url: str = OLLAMA_BASE_URL
) -> Dict[int, str]:
    """Traduce bloques usando Ollama local con contexto y formato JSON."""
    system_prompt = (
        f"Eres un traductor experto de mangas, cómics y novelas gráficas.\n"
        f"Tu misión es traducir todos los textos del idioma '{src_lang}' al idioma destino '{tgt_lang}'.\n"
        "REGLAS:\n"
        "1. NO CENSURES ninguna palabra. Soporta contenido erótico, gore, romance y lenguaje soez.\n"
        "2. Devuelve ÚNICAMENTE un JSON con pares id: texto_traducido.\n"
        'Ejemplo: {"1": "¡Hola!", "2": "¡Vamos!"}'
    )

    items = [{"id": b.id, "text": b.text} for b in blocks]
    user_payload = {"source": src_lang, "target": tgt_lang, "dialogues": items}
    user_prompt = f"Traduce los siguientes diálogos:\n{json.dumps(user_payload, ensure_ascii=False)}"

    payload = {
        "model": model_name,
        "prompt": f"<system>\n{system_prompt}\n</system>\n\n<user>\n{user_prompt}\n</user>",
        "format": "json",
        "stream": False,
        "keep_alive": "5m",
        "options": {"temperature": 0.3}
    }

    translations: Dict[int, str] = {}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{base_url}/api/generate", json=payload)
            if resp.status_code == 200:
                result = resp.json()
                parsed = json.loads(result.get("response", "{}"))
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        try:
                            b_id = int(k)
                            translations[b_id] = str(v).strip()
                        except ValueError:
                            continue
    except Exception as e:
        logger.warning(f"Fallo en Ollama ({e}). Se usará motor rápido de traducción.")

    return translations


def translate_page_contextual(
    blocks: List[TextBlock],
    model_name: str = "fast",
    src_lang: str = "auto",
    tgt_lang: str = "es",
    base_url: str = OLLAMA_BASE_URL
) -> Dict[int, str]:
    """
    Función orquestadora de traducción:
    - Si model_name es 'fast' o Google, o si Ollama no está disponible, utiliza el motor ultrarrápido.
    - Si se especifica un modelo de Ollama (ej. 'qwen2.5:7b'), intenta Ollama y hace fallback inmediato si falla.
    """
    if not blocks:
        return {}

    translations: Dict[int, str] = {}
    use_ollama = model_name and model_name.lower() not in ["fast", "google", "cloud", "rapido", "rápido"]

    if use_ollama:
        import asyncio
        try:
            translations = asyncio.run(
                translate_with_ollama(blocks, model_name=model_name, src_lang=src_lang, tgt_lang=tgt_lang, base_url=base_url)
            )
        except Exception:
            translations = {}

    # Traducir los bloques que falten con el motor ultrarrápido (< 200ms cada uno)
    for b in blocks:
        if b.id not in translations or not translations[b.id] or translations[b.id] == b.text:
            fast_trans = translate_text_fast_google(b.text, src_lang=src_lang, tgt_lang=tgt_lang)
            if fast_trans:
                translations[b.id] = fast_trans
            else:
                translations[b.id] = b.text

    return translations
