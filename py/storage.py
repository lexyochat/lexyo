# ============================================
#   Lexyo — JSON Persistence (2026 EDITION)
#   Support: text / action / code
#   Includes debounced channel saving + safe history
#   + MP server-side encryption
# ============================================

import os
import json
import time
import threading
import base64
import tempfile

from cryptography.fernet import Fernet

from py.config import (
    CHANNELS_FILE, PUBLIC_DIR, PRIVATE_DIR,
    HISTORY_LIMIT, OFFICIAL_ROOMS, MP_SECRET_KEY
)
import py.state as state
from py.logger import log_info, log_warning, log_error, log_exception


# Ensure directories exist
os.makedirs(PUBLIC_DIR, exist_ok=True)
os.makedirs(PRIVATE_DIR, exist_ok=True)


# =====================================================
#   ATOMIC JSON WRITE (ROBUST PERSISTENCE)
# =====================================================

def _atomic_write_json(path: str, payload):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


# =====================================================
#   MP SERVER-SIDE ENCRYPTION HELPERS
# =====================================================

def _get_mp_cipher():
    if not MP_SECRET_KEY:
        raise RuntimeError("MP_SECRET_KEY is not set")

    key = base64.urlsafe_b64encode(
        MP_SECRET_KEY.encode("utf-8")[:32].ljust(32, b"0")
    )
    return Fernet(key)


def encrypt_mp(text: str) -> str:
    cipher = _get_mp_cipher()
    return cipher.encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_mp(token: str) -> str:
    cipher = _get_mp_cipher()
    return cipher.decrypt(token.encode("utf-8")).decode("utf-8")


# =====================================================
#   MESSAGE NORMALIZATION (CONTRACT LOCK)
# =====================================================

def normalize_message(msg: dict) -> dict:
    m = dict(msg or {})

    m.setdefault("type", "text")
    m.setdefault("user", None)
    m.setdefault("ts", int(time.time()))

    if m["type"] == "text":
        m.setdefault("text", "")
        m.setdefault("original", m.get("text"))
        m.setdefault("translated", None)
        m.setdefault("lang", None)
        # IMPORTANT:
        # - source_lang MUST be preserved if provided by the sender
        # - NEVER derive source_lang from user lang
        if "source_lang" not in m:
            m["source_lang"] = None

    elif m["type"] in ("action", "code"):
        m.setdefault("content", "")

    return m


# =====================================================
#   DEBOUNCE SAVE (CHANNELS)
# =====================================================

_last_save_request = 0
_save_scheduled = False
_DEBOUNCE_DELAY = 1.0


def schedule_save_channels():
    global _last_save_request, _save_scheduled
    _last_save_request = time.time()

    if _save_scheduled:
        return

    _save_scheduled = True

    def _delayed_save():
        global _save_scheduled
        now = time.time()

        if now - _last_save_request < _DEBOUNCE_DELAY:
            threading.Timer(_DEBOUNCE_DELAY, _delayed_save).start()
            return

        _save_scheduled = False
        save_channels()

    threading.Timer(_DEBOUNCE_DELAY, _delayed_save).start()


# =====================================================
#   LOAD CHANNELS
# =====================================================

def load_channels():
    try:
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        state.rooms_meta.clear()
        now = time.time()

        for r, meta in data.items():
            if isinstance(r, str) and r.startswith("@"):
                log_warning("storage", f"Ignoring private room in channels.json: {r}")
                continue

            state.rooms_meta[r] = {
                "official": meta.get("official", r in OFFICIAL_ROOMS),
                "last_activity": meta.get("last_activity", now),
                "last_empty": meta.get("last_empty"),
                "creator_id": meta.get("creator_id"),
            }

        state.rooms[:] = [
            r for r in state.rooms_meta.keys() if not r.startswith("@")
        ]

        log_info("storage", f"Loaded {len(state.rooms)} channels.")

    except FileNotFoundError:
        log_warning("storage", "channels.json missing, rebuilding...")
        state.rooms_meta.clear()
        state.rooms.clear()

    except Exception:
        log_exception("storage", "Error reading channels.json — resetting.")
        state.rooms_meta.clear()
        state.rooms.clear()

    now = time.time()
    for r in OFFICIAL_ROOMS:
        if r not in state.rooms_meta:
            state.rooms_meta[r] = {
                "official": True,
                "last_activity": now,
                "last_empty": None,
                "creator_id": None,
            }
        if r not in state.rooms:
            state.rooms.append(r)

    schedule_save_channels()


# =====================================================
#   SAVE CHANNELS
# =====================================================

def save_channels():
    now = time.time()

    for r in OFFICIAL_ROOMS:
        if r not in state.rooms_meta:
            state.rooms_meta[r] = {
                "official": True,
                "last_activity": now,
                "last_empty": None,
                "creator_id": None,
            }
        if r not in state.rooms:
            state.rooms.append(r)

    state.rooms[:] = [
        r for r in state.rooms
        if not (isinstance(r, str) and r.startswith("@"))
    ]

    serializable_meta = {}
    for r, meta in state.rooms_meta.items():
        if isinstance(r, str) and r.startswith("@"):
            continue
        serializable_meta[r] = meta

    try:
        _atomic_write_json(CHANNELS_FILE, serializable_meta)
        log_info("storage", f"Saved {len(serializable_meta)} channels.")
    except Exception:
        log_exception("storage", "Failed writing channels.json")


# =====================================================
#   MESSAGE HISTORY
# =====================================================

def get_room_path(room):
    if room.startswith("@"):
        return os.path.join(PRIVATE_DIR, f"{room}.json")
    return os.path.join(PUBLIC_DIR, f"{room}.json")


def get_all_room_files():
    rooms = []
    for folder in (PUBLIC_DIR, PRIVATE_DIR):
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.endswith(".json"):
                    rooms.append(f[:-5])
    return rooms


def load_room_messages(room):
    path = get_room_path(room)

    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        log_exception("storage", f"Error reading room file: {room}")
        return []


def save_room_messages(room, msgs):
    path = get_room_path(room)

    try:
        _atomic_write_json(path, msgs)
    except Exception:
        log_exception("storage", f"Error writing room file: {room}")


def append_message(room, msg):
    msgs = load_room_messages(room)
    msg = normalize_message(msg)

    if isinstance(room, str) and room.startswith("@"):
        msg = msg.copy()
        msg_type = msg.get("type", "text")

        try:
            if msg_type == "text":
                msg["original"] = encrypt_mp(msg.get("original", ""))
            elif msg_type in ("action", "code"):
                msg["content"] = encrypt_mp(msg.get("content", ""))
        except Exception:
            log_exception("storage", f"Failed to encrypt MP message in {room}")

    msgs.append(msg)

    if len(msgs) > HISTORY_LIMIT:
        msgs = msgs[-HISTORY_LIMIT:]

    save_room_messages(room, msgs)
    log_info("storage", f"Message appended in {room} (total={len(msgs)}).")


def get_room_history(room, limit=None):
    msgs = load_room_messages(room)
    if limit is None or limit >= len(msgs):
        return msgs
    return msgs[-limit:]


def remove_room_file(room):
    path = get_room_path(room)
    if os.path.exists(path):
        try:
            os.remove(path)
            log_info("storage", f"Removed room file: {room}")
        except Exception:
            log_exception("storage", f"Could not remove file for room: {room}")
