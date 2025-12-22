# =========================================
#     Lexyo — Translation Engine (CLEAN PROD + Logging)
#     PATCH 12: allow batch translation even if src == tgt
# =========================================

import os
import re
import json
import time
from typing import List, Dict
from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI

from py.logger import log_info, log_warning, log_error, log_exception
from py.config import CACHE_DIR, TRANSLATIONS_CACHE_FILE

# =========================================
#   OPENAI CONFIG (SAFE / LAZY)
# =========================================
load_dotenv()
_openai_client = None
_openai_disabled = False
MODEL_NAME = "gpt-4o-mini"

# LRU in-memory cache (S5-B)
LRU_MAXSIZE = 5000


def _get_openai_client():
    """
    Lazy initialization of OpenAI client.
    The server must NEVER crash if OpenAI is unavailable.
    """
    global _openai_client, _openai_disabled

    if _openai_disabled:
        return None

    if _openai_client is not None:
        return _openai_client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log_warning("translate", "OPENAI_API_KEY missing — translation disabled.")
        _openai_disabled = True
        return None

    try:
        # IMPORTANT: project-based keys (sk-proj-*) must NOT be passed explicitly
        _openai_client = OpenAI()
        log_info("translate", "OpenAI client initialized.")
        return _openai_client
    except Exception:
        log_exception("translate", "Failed to initialize OpenAI client.")
        _openai_disabled = True
        return None


# =========================================
#   CACHE CONFIG (PERSISTENT)
# =========================================
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_FILE = TRANSLATIONS_CACHE_FILE

MAX_CACHE_SIZE = 50000
TRIM_TARGET_RATIO = 0.9
SAVE_EVERY_N_WRITES = 50  # kept for compatibility / future tuning

TRANSLATION_CACHE: Dict[str, Dict] = {}
_write_counter = 0
URL_REGEX = re.compile(r"https?://\S+", re.IGNORECASE)


# =========================================
#   HELPERS
# =========================================
def contains_url(text: str) -> bool:
    return bool(text and URL_REGEX.search(text))


def _make_key(text: str, src: str, tgt: str) -> str:
    return f"{src}|{tgt}|{text}"


# =========================================
#   CACHE — LOAD
# =========================================
def _load_cache():
    global TRANSLATION_CACHE

    if not os.path.exists(CACHE_FILE):
        TRANSLATION_CACHE = {}
        return

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            TRANSLATION_CACHE = data if isinstance(data, dict) else {}
        log_info("translate", f"Loaded translation cache ({len(TRANSLATION_CACHE)} entries).")
    except Exception:
        TRANSLATION_CACHE = {}
        log_error("translate", "Failed to load translation cache.")


# =========================================
#   CACHE — SAVE
# =========================================
def _save_cache(force=False):
    global _write_counter

    if not force and _write_counter < SAVE_EVERY_N_WRITES:
        return

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(TRANSLATION_CACHE, f, ensure_ascii=False)
        log_info("translate", "Cache saved successfully.")
    except Exception:
        log_error("translate", "Failed to save translation cache.")

    _write_counter = 0


def _touch_entry(key: str, entry: Dict):
    entry["last_used"] = time.time()
    entry["uses"] = entry.get("uses", 0) + 1


def _ensure_cache_limit():
    size = len(TRANSLATION_CACHE)
    if size <= MAX_CACHE_SIZE:
        return

    target = int(MAX_CACHE_SIZE * TRIM_TARGET_RATIO)

    try:
        items = list(TRANSLATION_CACHE.items())
        items.sort(key=lambda kv: kv[1].get("last_used", 0.0))
        to_remove = size - target

        for i in range(to_remove):
            TRANSLATION_CACHE.pop(items[i][0], None)

        log_warning("translate", f"Translation cache trimmed: {size} → {target}")
    except Exception:
        log_error("translate", "Failed to trim translation cache.")


def _add_to_cache(key: str, translated: str):
    """
    Add entry to cache AND persist immediately.
    This guarantees translation survives refresh / restart.
    """
    global _write_counter

    now = time.time()
    old_uses = TRANSLATION_CACHE.get(key, {}).get("uses", 0)

    TRANSLATION_CACHE[key] = {
        "translated": translated,
        "last_used": now,
        "uses": old_uses + 1,
    }

    _write_counter += 1
    _ensure_cache_limit()

    # Persist immediately so cache is not lost between messages
    _save_cache(force=True)


# Load cache on startup
_load_cache()


# =========================================
#   LRU HELPERS (S5-B)
# =========================================
def _build_prompt_single(text: str, src: str, tgt: str) -> str:
    return (
        f"Translate this message from {src} to {tgt}.\n"
        f"Respond ONLY with the translated text, nothing else:\n\n{text}"
    )


@lru_cache(maxsize=LRU_MAXSIZE)
def _translate_via_openai_lru(text: str, src: str, tgt: str) -> str:
    """
    In-memory LRU cache for OpenAI translations.
    Complements the persistent disk cache.
    """
    client = _get_openai_client()
    if not client:
        return text

    prompt = _build_prompt_single(text, src, tgt)

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        translated = (resp.choices[0].message.content or "").strip() or text
        log_info("translate", f"Translated: '{text[:30]}' → '{translated[:30]}'")
        return translated
    except Exception:
        log_exception("translate", f"Translation API failed for '{text[:30]}'")
        return text


# =========================================
#   SINGLE TRANSLATION
# =========================================
def translate_text(text: str, src: str, tgt: str) -> str:
    """Translate a single message safely (cached, failsafe, no URLs)."""

    if not text or contains_url(text):
        return text

    key = _make_key(text, src, tgt)
    entry = TRANSLATION_CACHE.get(key)

    if entry:
        _touch_entry(key, entry)
        return entry.get("translated", text)

    translated = _translate_via_openai_lru(text, src, tgt)
    _add_to_cache(key, translated)
    return translated


# =========================================
#   BATCH TRANSLATION
# =========================================
def translate_batch(texts: List[str], src: str, tgt: str) -> List[str]:
    """Translate a list of texts with caching, URL skipping and fallback."""

    if not texts:
        return []

    client = _get_openai_client()
    if not client:
        return texts

    results = [None] * len(texts)
    to_translate = []
    to_indices = []

    for i, txt in enumerate(texts):
        if not txt or contains_url(txt):
            results[i] = txt
            continue

        key = _make_key(txt, src, tgt)
        entry = TRANSLATION_CACHE.get(key)

        if entry:
            _touch_entry(key, entry)
            results[i] = entry.get("translated", txt)
        else:
            to_translate.append(txt)
            to_indices.append(i)

    if not to_translate:
        return [r if r is not None else texts[i] for i, r in enumerate(results)]

    prompt = (
        f"Translate ALL the following texts from {src} to {tgt}.\n"
        f"Return ONLY a JSON list of translated strings.\n\n"
        f"{json.dumps(to_translate, ensure_ascii=False)}"
    )

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )

        raw = (resp.choices[0].message.content or "").strip()
        batch = json.loads(raw)

        if not isinstance(batch, list) or len(batch) != len(to_translate):
            raise ValueError("Invalid batch response")

        for idx, original, translated in zip(to_indices, to_translate, batch):
            translated = translated or original
            results[idx] = translated
            _add_to_cache(_make_key(original, src, tgt), translated)

        log_info("translate", f"Batch translated {len(to_translate)} messages.")

    except Exception:
        log_exception("translate", "Batch translation failed — falling back to single requests.")

        for idx, original in zip(to_indices, to_translate):
            results[idx] = translate_text(original, src, tgt)

    return [r if r is not None else texts[i] for i, r in enumerate(results)]
