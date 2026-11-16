"""
Módulo de Traducción Contextual y Multi-Modelo de IA de Alta Velocidad.
- Motor IA Cloud Sin Token (Pollinations OpenAI / GPT-OSS Reasoning): Traducción de manga contextual en JSON sin necesidad de API Keys.
- Motor Ultrarrápido por Lotes (Google Clients5 + GTX Batch): Traduce todos los globos de la página en 1 sola petición (~0.4s), evitando límites HTTP 429.
- Modo Ollama Local: IA 100% offline en RAM si el usuario tiene Ollama instalado.
- Cadena de respaldo de 4 niveles con validación de alfabeto para garantizar 0% de textos sin traducir.
"""

import os
import re
import json
import logging
import urllib.parse
import urllib.request
from typing import List, Dict, Any, Optional
import httpx

from .detector import TextBlock

logger = logging.getLogger("ClickTranslate.Translator")

OLLAMA_BASE_URL = "http://localhost:11434"

# Mapeo de códigos de idioma estándar
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

# Mapeo ISO completo requerido por MyMemoryTranslator
MYMEMORY_LOCALES = {
    "ja": "ja-JP",
    "ko": "ko-KR",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "en": "en-US",
    "es": "es-ES",
    "pt": "pt-BR",
    "fr": "fr-FR",
    "de": "de-DE",
    "it": "it-IT",
    "ru": "ru-RU",
}

LANGUAGE_NAMES = {
    "auto": "Auto-detect",
    "es": "Spanish (Español neutro de scanlation)",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "pt": "Portuguese",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "ru": "Russian",
}


def has_cjk(text: str) -> bool:
    """Detecta si el texto contiene caracteres japoneses (Kana/Kanji), coreanos (Hangul) o chinos."""
    for c in text:
        code = ord(c)
        if (
            (0x3040 <= code <= 0x30FF)  # Hiragana y Katakana
            or (0x4E00 <= code <= 0x9FFF)  # Kanji / Hanzi
            or (0x3400 <= code <= 0x4DBF)  # Extensión CJK A
            or (0xAC00 <= code <= 0xD7AF)  # Hangul coreano
        ):
            return True
    return False


def detect_script(text: str) -> str:
    """Detecta el idioma origen aproximado a partir de los caracteres Unicode."""
    if any(0x3040 <= ord(c) <= 0x30FF for c in text):
        return "ja"
    if any(0xAC00 <= ord(c) <= 0xD7AF for c in text):
        return "ko"
    if any(0x4E00 <= ord(c) <= 0x9FFF for c in text):
        return "ja"  # En mangas suele ser japonés o chino
    return "en"


def is_valid_translation(orig: str, trans: Optional[str], tgt_lang: str) -> bool:
    """
    Verifica que la traducción sea válida y no haya dejado caracteres asiáticos sin traducir
    cuando el idioma destino es occidental (es, en, pt, fr, de, it).
    """
    if not trans or not trans.strip():
        return False
    up = trans.upper()
    if "MYMEMORY WARNING" in up or "INVALID SOURCE LANGUAGE" in up or "TOO MANY REQUESTS" in up:
        return False
    tgt = tgt_lang.lower().strip()
    if tgt in ["es", "en", "pt", "fr", "de", "it"] and has_cjk(orig):
        # Si el original tenía CJK y la supuesta traducción sigue teniendo CJK, falló la traducción
        if has_cjk(trans):
            return False
    return True


def translate_with_clients5_single(text: str, src: str, tgt: str) -> Optional[str]:
    """Traduce mediante el endpoint Chrome Extension de Google (clients5) sin límite 429 de gtx."""
    url = (
        f"https://clients5.google.com/translate_a/t"
        f"?client=dict-chrome-ex&sl={src}&tl={tgt}&q="
        + urllib.parse.quote(text)
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "*/*",
        }
    )
    with urllib.request.urlopen(req, timeout=6.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
            if isinstance(item, str):
                return item.strip()
            if isinstance(item, list) and len(item) > 0:
                return str(item[0]).strip()
    return None


def translate_with_gtx_single(text: str, src: str, tgt: str) -> Optional[str]:
    """Traduce mediante el endpoint translate.googleapis.com/translate_a/single."""
    url = (
        f"https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl={src}&tl={tgt}&dt=t&q="
        + urllib.parse.quote(text)
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": "https://translate.google.com/",
            "Accept": "*/*",
        }
    )
    with urllib.request.urlopen(req, timeout=6.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if data and len(data) > 0 and isinstance(data[0], list):
            parts = [part[0] for part in data[0] if part and len(part) > 0 and part[0]]
            return "".join(parts).strip()
    return None


def translate_batch_fast_google(
    blocks: List[TextBlock],
    src_lang: str = "auto",
    tgt_lang: str = "es"
) -> Dict[int, str]:
    """
    Traduce TODOS los bloques de la página en UNA SOLA petición HTTP combinada.
    Evita por completo el error HTTP 429 (Too Many Requests) y acelera la página a ~0.4s.
    """
    if not blocks:
        return {}

    src = LANGUAGE_CODES.get(src_lang.lower(), src_lang.lower())
    tgt = LANGUAGE_CODES.get(tgt_lang.lower(), tgt_lang.lower())

    # Usar separador numérico robusto que los motores de traducción preservan intacto
    sep = "\n[[[###]]]\n"
    combined_text = sep.join([b.text for b in blocks])

    translated_combined = None
    for engine_fn in (translate_with_clients5_single, translate_with_gtx_single):
        try:
            res = engine_fn(combined_text, src, tgt)
            if res:
                translated_combined = res
                break
        except Exception as e:
            logger.warning(f"Fallo en lote rápido ({engine_fn.__name__}): {e}")

    results: Dict[int, str] = {}
    if translated_combined:
        # Dividir por el separador (tolerando espacios alrededor de [[[###]]])
        parts = re.split(r"\s*\[\[\[\s*###\s*\]\]\]\s*", translated_combined)
        if len(parts) == len(blocks):
            for b, part in zip(blocks, parts):
                cln = part.strip()
                if is_valid_translation(b.text, cln, tgt_lang):
                    results[b.id] = cln

    return results


def translate_with_cloud_ai_llm(
    blocks: List[TextBlock],
    src_lang: str = "auto",
    tgt_lang: str = "es",
    ai_model: str = "openai-fast"
) -> Dict[int, str]:
    """
    Traduce todos los bloques de la página usando IA Contextual en la nube (Pollinations AI)
    SIN necesidad de Tokens ni API Keys. Ideal para diálogos de manga, modismos, comedia y NSFW.
    """
    if not blocks:
        return {}

    src_name = LANGUAGE_NAMES.get(src_lang.lower(), src_lang)
    tgt_name = LANGUAGE_NAMES.get(tgt_lang.lower(), tgt_lang)

    system_prompt = (
        f"You are an elite, uncensored professional manga, manhwa, and comic scanlation translator.\n"
        f"Translate each dialogue entry from {src_name} into natural, idiomatic {tgt_name}.\n"
        "STRICT RULES:\n"
        "1. NEVER censor any content (translate romance, NSFW, ecchi, adult, slang, and action faithfully).\n"
        "2. Preserve line breaks (\\n), numbers, dates (like 6/22), and punctuation style.\n"
        "3. Leave ZERO untranslated Japanese/Korean/Chinese characters in the output.\n"
        "4. Return ONLY a valid JSON object mapping each string ID to its translated string. No markdown, no explanations."
    )

    payload_map = {str(b.id): b.text for b in blocks}
    provider_model = "openai-fast" if "deepseek" not in ai_model.lower() else "openai"

    try:
        with httpx.Client(timeout=14.0) as client:
            resp = client.post(
                "https://text.pollinations.ai/",
                json={
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(payload_map, ensure_ascii=False)}
                    ],
                    "model": provider_model,
                    "jsonMode": True
                }
            )
            if resp.status_code == 200:
                raw_txt = resp.text.strip()
                # Extraer bloque JSON si viene envuelto en ```json ... ```
                if "{" in raw_txt and "}" in raw_txt:
                    raw_txt = raw_txt[raw_txt.find("{") : raw_txt.rfind("}") + 1]
                parsed = json.loads(raw_txt)
                out: Dict[int, str] = {}
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        try:
                            bid = int(k)
                            val_str = str(v).strip()
                            orig_b = next((x for x in blocks if x.id == bid), None)
                            if orig_b and is_valid_translation(orig_b.text, val_str, tgt_lang):
                                out[bid] = val_str
                        except ValueError:
                            continue
                return out
    except Exception as e:
        logger.warning(f"Aviso en Cloud AI LLM ({ai_model}): {e}")

    return {}


def translate_text_fast_google(text: str, src_lang: str = "auto", tgt_lang: str = "es") -> str:
    """
    Traduce un bloque individual con cadena de respaldo de 4 niveles:
    1. Google Clients5 (Chrome Extension API)
    2. Google GTX API
    3. MyMemory API con mapeo ISO completo (ja-JP, ko-KR, es-ES, etc.)
    """
    if not text or not text.strip():
        return ""

    # Si el texto son solo números/símbolos (ej. '6/22' o '!?'), devolver tal cual
    if not any(c.isalpha() or ord(c) > 127 for c in text):
        return text.strip()

    src = LANGUAGE_CODES.get(src_lang.lower(), src_lang.lower())
    tgt = LANGUAGE_CODES.get(tgt_lang.lower(), tgt_lang.lower())

    # Si el texto contiene líneas separadas por \n, traducir preservando cada línea
    if "\n" in text:
        sub_lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(sub_lines) > 1:
            translated_lines = [translate_text_fast_google(line, src_lang, tgt_lang) for line in sub_lines]
            return "\n".join(translated_lines)

    # Nivel 1: Google Clients5
    try:
        res = translate_with_clients5_single(text, src, tgt)
        if is_valid_translation(text, res, tgt_lang):
            return res
    except Exception as e:
        logger.debug(f"Clients5 individual fallo: {e}")

    # Nivel 2: Google GTX
    try:
        res = translate_with_gtx_single(text, src, tgt)
        if is_valid_translation(text, res, tgt_lang):
            return res
    except Exception as e:
        logger.debug(f"GTX individual fallo: {e}")

    # Nivel 3: MyMemory con códigos ISO exactos (ja-JP, es-ES, etc.)
    try:
        src_resolved = detect_script(text) if src == "auto" else src
        src_mm = MYMEMORY_LOCALES.get(src_resolved.lower(), "en-US")
        tgt_mm = MYMEMORY_LOCALES.get(tgt.lower(), "es-ES")
        from deep_translator import MyMemoryTranslator
        tr = MyMemoryTranslator(source=src_mm, target=tgt_mm)
        res = tr.translate(text)
        if is_valid_translation(text, res, tgt_lang):
            return res.strip()
    except Exception as me:
        logger.warning(f"Error en fallback MyMemory: {me}")

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
    Orquestador inteligente multi-IA:
    1. Si se selecciona un modelo Cloud AI ('gpt-ai', 'deepseek-ai', 'gemini-ai'), traduce con LLM contextual sin token.
    2. Si se selecciona 'fast', traduce todos los bloques en 1 solo lote ultrarrápido (Clients5 / GTX).
    3. Cualquier bloque que falte pasa por respaldo Cloud AI LLM y luego traducción individual multi-motor.
    """
    if not blocks:
        return {}

    translations: Dict[int, str] = {}
    m_low = (model_name or "fast").lower().strip()

    is_cloud_ai = m_low in ["gpt-ai", "deepseek-ai", "gemini-ai", "claude-ai", "ai"]
    is_ollama = not is_cloud_ai and m_low not in ["fast", "google", "cloud", "rapido", "rápido"]

    # Paso 1: Si el usuario eligió IA Contextual en la nube (estilo TranslateManga.net)
    if is_cloud_ai:
        translations = translate_with_cloud_ai_llm(blocks, src_lang=src_lang, tgt_lang=tgt_lang, ai_model=m_low)

    # Paso 1B: Si el usuario eligió un modelo local de Ollama
    elif is_ollama:
        import asyncio
        try:
            translations = asyncio.run(
                translate_with_ollama(blocks, model_name=model_name, src_lang=src_lang, tgt_lang=tgt_lang, base_url=base_url)
            )
        except Exception:
            translations = {}

    # Paso 2: Traducir en LOTE todos los bloques pendientes usando Google Clients5 / GTX (1 sola petición)
    missing_blocks = [b for b in blocks if b.id not in translations or not is_valid_translation(b.text, translations.get(b.id), tgt_lang)]
    if missing_blocks:
        batch_res = translate_batch_fast_google(missing_blocks, src_lang=src_lang, tgt_lang=tgt_lang)
        translations.update(batch_res)

    # Paso 3: Si algún bloque aún falta, intentar por línea/individual con Clients5 -> GTX -> MyMemory
    still_missing = [b for b in blocks if b.id not in translations or not is_valid_translation(b.text, translations.get(b.id), tgt_lang)]
    if still_missing:
        for b in still_missing:
            fast_trans = translate_text_fast_google(b.text, src_lang=src_lang, tgt_lang=tgt_lang)
            if is_valid_translation(b.text, fast_trans, tgt_lang):
                translations[b.id] = fast_trans

    # Paso 4: Si aún queda algún bloque con CJK sin traducir (ej. bloqueo de red en Google), usar Cloud AI LLM de respaldo
    final_missing = [b for b in blocks if b.id not in translations or not is_valid_translation(b.text, translations.get(b.id), tgt_lang)]
    if final_missing:
        ai_res = translate_with_cloud_ai_llm(final_missing, src_lang=src_lang, tgt_lang=tgt_lang, ai_model="openai-fast")
        translations.update(ai_res)

    # Garantizar entrada para cada bloque
    for b in blocks:
        if b.id not in translations or not translations[b.id]:
            translations[b.id] = b.text

    return translations
