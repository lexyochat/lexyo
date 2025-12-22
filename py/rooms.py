# ============================================
#     Lexyo — Room Logic (PRO VERSION V3)
#     (Ajout Sécurité : validation room name)
#     MP-03: MP lifecycle based on users[*]["room"]
# ============================================

import time
import re

from py.config import OFFICIAL_ROOMS, ROOM_TTL_SECONDS
from py.state import users, rooms, rooms_meta
from py.storage import (
    get_all_room_files,
    remove_room_file,
    schedule_save_channels,
)
from py.logger import log_info, log_warning, log_error, log_exception


# =====================================================
#   VALIDATION SÉCURISÉE DU NOM DE SALON
# =====================================================

ROOM_NAME_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,16}$")

def is_valid_room_name(name: str) -> bool:
    """Interdit tout caractère dangereux (XSS, HTML, injection).
       Autorise : lettres, chiffres, underscore, tiret.
    """
    if not isinstance(name, str):
        return False
    return bool(ROOM_NAME_REGEX.fullmatch(name))


# =====================================================
#   TOUCH ROOM (inchangé)
# =====================================================

def touch_room(room, message=False, user_join=False):
    now = time.time()
    meta = rooms_meta.get(room)

    if not meta:
        meta = {
            "official": room in OFFICIAL_ROOMS,
            "last_activity": now,
            "creator_id": None,
            "mods": set(),
        }
        rooms_meta[room] = meta

        if room not in rooms and not room.startswith("@"):
            rooms.append(room)
            log_info("rooms", f"Room metadata created for {room}")

    if message or user_join:
        meta["last_activity"] = now
        schedule_save_channels()
        log_info("rooms", f"Activity update {room} (message={message}, join={user_join})")


# =====================================================
#   UPDATE EMPTY STATE (MP-03)
#   - Public rooms: log empty state (no delete here)
#   - Private rooms (@...): delete ONLY when truly empty
# =====================================================

def update_room_empty_state(room):
    meta = rooms_meta.get(room)
    if not meta:
        return

    # OFFICIAL rooms: never deleted
    if meta.get("official"):
        return

    # Check emptiness from the real source of truth:
    # a room is empty iff no user currently has user["room"] == room
    is_empty = True
    for u in users.values():
        if u.get("room") == room:
            is_empty = False
            break

    # PUBLIC rooms: we only log empty state (TTL deletion handled by cleanup_rooms)
    if not room.startswith("@"):
        schedule_save_channels()
        log_info("rooms", f"update_room_empty_state({room}) → empty={is_empty}")
        return

    # PRIVATE rooms (@...):
    # MP-03: delete only when truly empty (no user inside)
    if not is_empty:
        return

    try:
        remove_room_file(room)
    except Exception:
        log_exception("rooms", f"Error removing private room file for {room}")

    rooms_meta.pop(room, None)

    schedule_save_channels()
    log_info("rooms", f"Private room deleted (empty): {room}")


# =====================================================
#   ROOM HAS USERS ? (inchangé)
# =====================================================

def room_has_users(room):
    return any(u.get("room") == room for u in users.values())


# =====================================================
#   PRIVATE ROOM NAME (inchangé)
#   (legacy helper; MP rooms are now @mp_<hash>, but keep it)
# =====================================================

def get_private_room_name(pseudo1, pseudo2):
    a = pseudo1.lower()
    b = pseudo2.lower()
    x, y = sorted([a, b])
    return f"@{x}_{y}"


# =====================================================
#   ROOM COUNTS (inchangé)
# =====================================================

def get_room_counts():
    counts = {}
    for _, u in users.items():
        r = u.get("room")
        if r:
            counts[r] = counts.get(r, 0) + 1
    return counts


# =====================================================
#   CREATE PUBLIC ROOM (PATCH SÉCURITÉ + LOGIC FIX)
# =====================================================

def create_public_room(name, creator_id):
    """Crée une room publique validée et sécurisée."""

    # 1) Validation XSS / caractères interdits
    if not is_valid_room_name(name):
        log_warning("rooms", f"Rejected invalid room name: {name!r}")
        return {"error": "invalid_name"}

    # 2) Vérifier si un utilisateur a déjà une room
    # (anti-spam : une seule création possible)
    for r, meta in rooms_meta.items():
        if meta.get("creator_id") == creator_id:
            return {"error": "already_created"}

    now = time.time()

    # 3) Créer la room si elle n'existe pas déjà
    if name not in rooms:
        rooms.append(name)

    # 4) Créer les métadonnées
    rooms_meta[name] = {
        "official": False,
        "creator_id": creator_id,
        "created_at": now,
        "last_activity": now,
        "message_count": 0,
        "mods": set(),
    }

    # 5) Save
    schedule_save_channels()

    log_info("rooms", f"Public room created: {name} (creator_id={creator_id})")

    return {"success": True, "room": name}


# =====================================================
#   CLEANUP ROOMS (MP-03)
#   - Public TTL: unchanged
#   - Private rooms: DO NOT delete here (handled by update_room_empty_state)
# =====================================================

def cleanup_rooms(socketio=None):
    now = time.time()
    to_delete = []

    try:
        online_pseudos = {u["pseudo"] for u in users.values()}
    except Exception:
        online_pseudos = set()
        log_exception("rooms", "Failed reading online pseudos.")

    # 1) PUBLIC TTL
    for room, meta in list(rooms_meta.items()):
        if room.startswith("@"):
            continue

        if not meta.get("official"):
            if not room_has_users(room):
                last = meta.get("last_activity") or 0
                idle = now - last

                if idle > ROOM_TTL_SECONDS:
                    to_delete.append(room)
                    log_info("rooms",
                             f"Delete public inactive room {room} (idle={idle:.1f}s)")

    # 2) PRIVATE ROOMS BOTH USERS OFFLINE  (DISABLED — MP-03)
    # This logic breaks @mp_<hash> rooms because the room name no longer contains pseudos.
    # MP rooms are deleted deterministically when they are truly empty (no user inside),
    # via update_room_empty_state(room).
    #
    # for room in list(rooms_meta.keys()):
    #     if room.startswith("@"):
    #         parts = room[1:].split("_", 2)
    #         if len(parts) != 2:
    #             continue
    #
    #         p1, p2 = parts
    #         if p1 not in online_pseudos and p2 not in online_pseudos:
    #             to_delete.append(room)
    #             log_info("rooms",
    #                      f"Delete private room {room} (both offline)")

    # 3) ORPHANED FILES (PUBLIC ONLY)
    try:
        existing_files = set(get_all_room_files())
    except Exception:
        existing_files = set()
        log_exception("rooms", "Error fetching existing room files.")

    for room, meta in list(rooms_meta.items()):
        if room in OFFICIAL_ROOMS:
            continue
        if room.startswith("@"):
            continue

        if room not in existing_files:
            last = meta.get("last_activity") or 0
            idle = now - last

            if idle > ROOM_TTL_SECONDS:
                to_delete.append(room)
                log_warning("rooms",
                            f"Delete orphan room after inactivity: {room} (idle={idle:.1f}s)")
            continue

    # APPLY DELETE (PUBLIC)
    for room in set(to_delete):
        try:
            remove_room_file(room)
        except Exception:
            log_exception("rooms", f"Error removing file for {room}")

        rooms_meta.pop(room, None)

        if room in rooms:
            rooms.remove(room)

        if socketio is not None:
            socketio.emit("room_deleted", {"room": room}, namespace="/")

        log_info("rooms", f"Room deleted: {room}")

    schedule_save_channels()
