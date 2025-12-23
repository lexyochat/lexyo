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

from cryptography.fernet import Fernet

from py.config import (
    CHANNELS_FILE,
    PUBLIC_DIR,
    PRIVATE_DIR,
    HISTORY_LIMIT,
    OFFICIAL_ROOMS,
    MP_SECRET_KEY,
)
import py.state as state
from py.logger import log_info, log_warning, log_error, log_exception


# =====================================================
#   FILESYSTEM SAFETY (PERSISTENT DISK COMPAT)
# =====================================================

def _ensure_dirs():
    """
    Defensive directory creation.
    config.py already creates these directories at import-time,
    but we keep it here to protect against unexpected import order
    or missing mount in certain environments.
    """
    try:
        base = os.path.dirname(CHANNELS_FILE)
        if base:
            os.makedirs(base, exist_ok=True)
    except Exception:
        # Do not crash; reads/writes will log failures downstream
        pass

    try:
        os.makedirs(PUBLIC_DIR, exist_ok=True)
    except Exception:
        pass

    try:
        os.makedirs(PRIVATE_DIR, exist_ok=True)
    except Exception:
        pass


def _safe_read_json(path: str, default):
    """
    Safe JSON reader with fallback.
    Returns `default` on missing file or parse errors.
    """
    if not path:
        return default

    try:
        if not os.path.exists(path):
            return default

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default


def _atomic_write_json(path: str, payload):
    """
    Atomic JSON write to avoid corruption on crash/restart:
    write temp file then os.replace().
    """
    if not path:
        raise ValueError("Missing path")

    _ensure_dirs()

    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
        return True
    except Exception:
        # Try cleanup tmp, but never fail the original exception handling
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


# Ensure directories exist (defensive)
_ensure_dirs()


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
    """
    Normalize message structure before persistence.
    Guarantees a stable backend ↔ frontend contract.
    """
    m = dict(msg or {})

    m.setdefault("type", "text")
    m.setdefault("user", None)
    m.setdefault("ts", int(time.time()))

    if m["type"] == "text":
        m.setdefault("text", "")
        m.setdefault("original", m.get("text"))
        m.setdefault("translated", None)
        m.setdefault("lang", None)

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
    """
    Load public channels metadata from CHANNELS_FILE.
    Private rooms are intentionally ignored.
    """
    _ensure_dirs()

    try:
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        state.rooms_meta.clear()
        now = time.time()

        if not isinstance(data, dict):
            log_warning("storage", "channels.json invalid format (expected dict), resetting.")
            data = {}

        for r, meta in data.items():

            # skip private rooms
            if isinstance(r, str) and r.startswith("@"):
                log_warning("storage", f"Ignoring private room in channels.json: {r}")
                continue

            meta = meta if isinstance(meta, dict) else {}

            state.rooms_meta[r] = {
                "official": meta.get("official", r in OFFICIAL_ROOMS),
                "last_activity": meta.get("last_activity", now),
                "last_empty": meta.get("last_empty"),
                "creator_id": meta.get("creator_id"),
            }

        state.rooms[:] = [
            r for r in state.rooms_meta.keys() if not (isinstance(r, str) and r.startswith("@"))
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

    # Inject officials
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
    """
    Persist public channels metadata into CHANNELS_FILE.
    Uses atomic write to reduce risk of file corruption.
    """
    _ensure_dirs()

    now = time.time()

    # ensure official exist
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

    # strip private rooms
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
    """
    Return the JSON file path for a room.
    - Private rooms start with '@' and are stored under PRIVATE_DIR.
    - Public rooms are stored under PUBLIC_DIR.
    """
    _ensure_dirs()

    if isinstance(room, str) and room.startswith("@"):
        return os.path.join(PRIVATE_DIR, f"{room}.json")
    return os.path.join(PUBLIC_DIR, f"{room}.json")


def get_all_room_files():
    """
    Return list of room names that have JSON files, without extension.
    Includes both PUBLIC_DIR and PRIVATE_DIR.
    """
    _ensure_dirs()

    found = []
    for folder in (PUBLIC_DIR, PRIVATE_DIR):
        try:
            if os.path.exists(folder):
                for f in os.listdir(folder):
                    if f.endswith(".json"):
                        found.append(f[:-5])
        except Exception:
            continue
    return found


def load_room_messages(room):
    path = get_room_path(room)

    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        log_exception("storage", f"Error reading room file: {room}")
        return []


def save_room_messages(room, msgs):
    """
    Save the full list of messages for a room.
    Uses atomic write for robustness.
    """
    path = get_room_path(room)

    # Ensure list payload
    payload = msgs if isinstance(msgs, list) else []

    try:
        _atomic_write_json(path, payload)
    except Exception:
        log_exception("storage", f"Error writing room file: {room}")


def append_message(room, msg):
    """
    Append any message type (text, action, code)
    and ensure HISTORY_LIMIT is respected.
    MP rooms are encrypted server-side.
    """
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
    """
    Delete the persisted JSON history file for a room (public or private).
    """
    path = get_room_path(room)
    if os.path.exists(path):
        try:
            os.remove(path)
            log_info("storage", f"Removed room file: {room}")
        except Exception:
            log_exception("storage", f"Could not remove file for room: {room}")
