# ============================================
#   Lexyo — Command Handler (2026 PRO EDITION)
#   Supports: /help /me /code /mp(admin) /kick /ban /kill /unban
#   MESSAGE TYPES: text / action / code
# ============================================

import os
import time
from flask_socketio import emit, disconnect

from py.state import users, rooms, rooms_meta, admins, banned_until, used_pseudos
from py.users import get_users_in_room
from py.storage import append_message, save_channels
from py.rooms import get_room_counts
from py.logger import log_info, log_warning, log_exception
from py.config import (
    ADMIN_RATE_WINDOW_SECONDS,
    ADMIN_RATE_MAX_ATTEMPTS,
    ADMIN_LOCK_SECONDS,
)

# =====================================================
#   /ADMIN BRUTE-FORCE GUARD (S2C)
# =====================================================
# _ADMIN_GUARD[key] = {
#   "fails": [ts, ts, ...],
#   "locked_until": ts
# }
_ADMIN_GUARD = {}


def _admin_guard_key(user, sid):
    return str(user.get("user_id") or sid)


def _admin_is_locked(key, now):
    entry = _ADMIN_GUARD.get(key)
    return bool(entry and entry.get("locked_until", 0) > now)


def _admin_register_fail(key, now):
    entry = _ADMIN_GUARD.get(key, {"fails": [], "locked_until": 0})

    cutoff = now - ADMIN_RATE_WINDOW_SECONDS
    fails = [t for t in entry["fails"] if t >= cutoff]
    fails.append(now)

    if len(fails) >= ADMIN_RATE_MAX_ATTEMPTS:
        entry["locked_until"] = now + ADMIN_LOCK_SECONDS
        entry["fails"] = []
    else:
        entry["fails"] = fails

    _ADMIN_GUARD[key] = entry


def _admin_register_success(key):
    _ADMIN_GUARD.pop(key, None)


# =====================================================
#   ADMIN CHECK
# =====================================================

def is_admin(sid) -> bool:
    return sid in admins


# =====================================================
#   ROOM MODERATION HELPERS (LOCAL PER ROOM)
# =====================================================

def is_room_creator(sid, room) -> bool:
    user = users.get(sid)
    if not user:
        return False
    meta = rooms_meta.get(room)
    if not meta:
        return False
    return str(meta.get("creator_id") or "") == str(user.get("user_id") or "")


def is_room_mod(sid, room) -> bool:
    """
    A room moderator is:
    - the creator of the room
    - OR a delegated moderator in rooms_meta[room]["mods"]
    """
    user = users.get(sid)
    if not user:
        return False

    meta = rooms_meta.get(room)
    if not meta:
        return False

    uid = str(user.get("user_id") or "")
    if not uid:
        return False

    if str(meta.get("creator_id") or "") == uid:
        return True

    mods = meta.get("mods", set())
    try:
        return uid in mods
    except Exception:
        return False


# =====================================================
#   DURATION PARSER
# =====================================================

def parse_duration(arg):
    if not arg:
        return None

    try:
        if arg.endswith("m"):
            return int(arg[:-1]) * 60
        if arg.endswith("h"):
            return int(arg[:-1]) * 3600
        if arg.endswith("d"):
            return int(arg[:-1]) * 86400
        if arg.endswith("y"):
            return int(arg[:-1]) * 31536000
    except:
        return None

    return None


# =====================================================
#   /HELP (dynamic)
# =====================================================

def cmd_help(socketio, sid, room, args):
    base = (
        "Available commands:\n"
        "/help — show this help\n"
        "/me <action> — express an action\n"
        "/code [lang]\\n<your code> — send code blocks\n"
        "/mp <user> <msg> — private message\n"
    )

    # Admin sees everything
    if is_admin(sid):
        admin = (
            "\nAdmin commands:\n"
            "/kick <user>\n"
            "/ban <user> [duration]\n"
            "/unban <user>\n"
            "/kill <room>\n"
        )
        text = base + admin
        emit("system_message", {"room": room, "msg": text}, to=sid)
        return

    # Local room moderation help (public channels only, not MP)
    # Creator sees /mod + /kick; delegated mod sees /kick only
    if room and not room.startswith("@"):
        if is_room_creator(sid, room):
            text = base + (
                "\nChannel moderation:\n"
                "/mod <user>\n"
                "/kick <user> [duration]\n"
            )
            emit("system_message", {"room": room, "msg": text}, to=sid)
            return

        if is_room_mod(sid, room):
            text = base + (
                "\nChannel moderation:\n"
                "/kick <user> [duration]\n"
            )
            emit("system_message", {"room": room, "msg": text}, to=sid)
            return

    # Default
    emit("system_message", {"room": room, "msg": base}, to=sid)


# =====================================================
#   /ME
# =====================================================

def cmd_me(socketio, sid, room, args):
    user = users.get(sid)
    if not user:
        return

    if not args:
        emit("system_message", {"room": room, "msg": "Usage: /me <action>"}, to=sid)
        return

    content = args.strip()
    now = time.time()

    msg_record = {
        "type": "action",
        "pseudo": user["pseudo"],
        "content": content,
        "timestamp": now,
    }
    append_message(room, msg_record)

    emit(
        "action_message",
        {
            "room": room,
            "author": user["pseudo"],
            "content": content,
            "timestamp": now,
        },
        broadcast=True,
    )


# =====================================================
#   /CODE
# =====================================================

KNOWN_LANG = {
    "js", "javascript", "ts", "typescript",
    "py", "python",
    "html", "css", "json",
    "java", "c", "cpp", "c++",
    "go", "rust", "php", "sql",
    "bash", "sh", "lua",
}


def cmd_code(socketio, sid, room, args):
    user = users.get(sid)
    if not user:
        return

    raw = args.strip()
    if not raw:
        emit(
            "system_message",
            {"room": room, "msg": "Usage:\n/code [lang]\n<your code>"},
            to=sid,
        )
        return

    lines = raw.split("\n")
    first = lines[0].strip()

    if first.lower() in KNOWN_LANG:
        lang = first.lower()
        code = "\n".join(lines[1:]).strip()
    else:
        lang = "txt"
        code = raw

    if not code:
        emit("system_message", {"room": room, "msg": "No code detected."}, to=sid)
        return

    now = time.time()

    msg_record = {
        "type": "code",
        "pseudo": user["pseudo"],
        "lang": lang,
        "content": code,
        "timestamp": now,
    }

    append_message(room, msg_record)

    emit(
        "code_message",
        {
            "room": room,
            "pseudo": user["pseudo"],
            "lang": lang,
            "content": code,
            "timestamp": now,
        },
        broadcast=True,
    )

    log_info("commands", f"/code by {user['pseudo']} ({lang}, {len(code)} chars)")


# =====================================================
#   /ADMIN (HARDENED)
# =====================================================

def cmd_admin(socketio, sid, room, args):
    user = users.get(sid)
    if not user:
        return

    now = time.time()
    guard_key = _admin_guard_key(user, sid)

    if _admin_is_locked(guard_key, now):
        emit(
            "system_message",
            {"room": room, "msg": "Too many /admin attempts. Try again later."},
            to=sid,
        )
        log_warning("commands", f"/admin locked for key={guard_key}")
        return

    if sid in admins or user.get("is_admin"):
        emit("system_message", {"room": room, "msg": "You are already admin."}, to=sid)
        return

    if not args:
        emit("system_message", {"room": room, "msg": "Usage: /admin <key>"}, to=sid)
        return

    key = os.getenv("ADMIN_KEY", "")
    if not key or args != key:
        emit("system_message", {"room": room, "msg": "Invalid admin key."}, to=sid)
        log_warning("commands", f"SID={sid} attempted invalid admin key.")
        _admin_register_fail(guard_key, now)
        return

    for other_sid, u in users.items():
        if other_sid != sid and str(u.get("pseudo", "")).lower() == "lexyo":
            emit(
                "system_message",
                {"room": room, "msg": "Admin identity is currently in use."},
                to=sid,
            )
            return

    old_pseudo = user.get("pseudo") or ""

    if old_pseudo:
        for p in list(used_pseudos):
            if str(p).lower() == old_pseudo.lower():
                used_pseudos.discard(p)
                break

    for p in list(used_pseudos):
        if str(p).lower() == "lexyo":
            used_pseudos.discard(p)

    user["is_admin"] = True
    user["pseudo"] = "Lexyo"
    admins.add(sid)
    used_pseudos.add("Lexyo")

    _admin_register_success(guard_key)

    emit(
        "identity_update",
        {
            "pseudo": user["pseudo"],
            "color": user.get("color"),
            "is_admin": True,
        },
        to=sid,
    )

    emit(
        "system_message",
        {"room": room, "msg": f"{old_pseudo} is now logged in as admin."},
        broadcast=True,
    )

    emit(
        "room_users",
        {"room": room, "users": get_users_in_room(room)},
        broadcast=True,
    )

    emit("system_message", {"room": room, "msg": "Admin mode enabled."}, to=sid)
    log_info("commands", f"SID={sid} elevated to admin (Lexyo).")


# =====================================================
#   /MOD (delegate moderator — creator only)
# =====================================================

def cmd_mod(socketio, sid, room, args):
    user = users.get(sid)
    if not user:
        return

    if not room or room.startswith("@"):
        emit("system_message", {"room": room, "msg": "Moderation is only available in public channels."}, to=sid)
        return

    if not is_room_creator(sid, room):
        emit("system_message", {"room": room, "msg": "Creator only."}, to=sid)
        return

    if not args:
        emit("system_message", {"room": room, "msg": "Usage: /mod <user>"}, to=sid)
        return

    target_name = args.strip().lower()
    if not target_name:
        emit("system_message", {"room": room, "msg": "Usage: /mod <user>"}, to=sid)
        return

    # Find target in the same room
    target_sid = None
    target_user = None
    for s, u in users.items():
        if u.get("room") == room and str(u.get("pseudo", "")).lower() == target_name:
            target_sid = s
            target_user = u
            break

    if not target_sid or not target_user:
        emit("system_message", {"room": room, "msg": f"User '{args}' not found in this channel."}, to=sid)
        return

    # Do not assign moderators to admins (they already have higher power)
    if is_admin(target_sid) or target_user.get("is_admin"):
        emit("system_message", {"room": room, "msg": "That user is an admin."}, to=sid)
        return

    meta = rooms_meta.get(room)
    if not meta:
        emit("system_message", {"room": room, "msg": "Channel metadata missing."}, to=sid)
        return

    meta.setdefault("mods", set())
    try:
        meta["mods"].add(str(target_user.get("user_id") or ""))
    except Exception:
        meta["mods"] = set(meta.get("mods", set()))
        meta["mods"].add(str(target_user.get("user_id") or ""))

    emit(
        "system_message",
        {"room": room, "msg": f"{target_user.get('pseudo')} is now a moderator ⭐"},
        broadcast=True,
    )

    # Refresh users list so frontend can show ⭐ later (we will add is_mod in users list payload in next patch)
    emit(
        "room_users",
        {"room": room, "users": get_users_in_room(room)},
        broadcast=True,
    )

    log_info("commands", f"Delegated mod in {room}: {target_user.get('pseudo')} (by creator_id={user.get('user_id')})")


# =====================================================
#   /KICK
# =====================================================

def cmd_kick(socketio, sid, room, args):
    # -------------------------------------------------
    # Local moderation kick (creator/mod) — before admin-only branch
    # -------------------------------------------------
    if not is_admin(sid) and room and not room.startswith("@") and is_room_mod(sid, room):
        if not args:
            emit("system_message", {"room": room, "msg": "Usage: /kick <user> [duration]"}, to=sid)
            return

        parts = args.split()
        nickname = parts[0].strip()
        duration_arg = parts[1] if len(parts) > 1 else None

        # Default duration for local kick (prevents instant rejoin)
        duration = parse_duration(duration_arg)
        if duration is None:
            duration = 300  # 5 minutes default

        actor_user = users.get(sid)
        if not actor_user:
            return

        # Find target in the same room
        target_sid = next(
            (s for s, u in users.items()
             if u.get("room") == room and str(u.get("pseudo", "")).lower() == nickname.lower()),
            None
        )

        if not target_sid:
            emit("system_message", {"room": room, "msg": f"User '{nickname}' not found."}, to=sid)
            return

        if target_sid == sid:
            emit("system_message", {"room": room, "msg": "You cannot kick yourself."}, to=sid)
            return

        target_user = users.get(target_sid)
        if not target_user:
            emit("system_message", {"room": room, "msg": f"User '{nickname}' not found."}, to=sid)
            return

        # Protect admins
        if is_admin(target_sid) or target_user.get("is_admin"):
            emit("system_message", {"room": room, "msg": "You cannot kick an admin."}, to=sid)
            return

        # Protect creator (mods cannot kick creator; creator can kick mods/users)
        if not is_room_creator(sid, room) and is_room_creator(target_sid, room):
            emit("system_message", {"room": room, "msg": "You cannot kick the creator."}, to=sid)
            return

        meta = rooms_meta.get(room)
        if not meta:
            emit("system_message", {"room": room, "msg": "Channel metadata missing."}, to=sid)
            return

        meta.setdefault("kicked_until", {})
        uid = str(target_user.get("user_id") or "")
        if uid:
            meta["kicked_until"][uid] = time.time() + duration

        emit(
            "system_message",
            {"room": room, "msg": f"{nickname} was kicked by a moderator ⭐."},
            broadcast=True,
        )

        emit(
            "user_kicked",
            {"room": room, "reason": "You were kicked by a moderator."},
            to=target_sid,
        )
        disconnect(sid=target_sid)
        log_info("commands", f"Local kick in {room}: '{nickname}' ({duration}s)")
        return

    # -------------------------------------------------
    # Admin kick (original behavior)
    # -------------------------------------------------
    if not is_admin(sid):
        emit("system_message", {"room": room, "msg": "Admin only."}, to=sid)
        return

    if not args:
        emit("system_message", {"room": room, "msg": "Usage: /kick <user>"}, to=sid)
        return

    target_sid = next(
        (s for s, u in users.items()
         if u["room"] == room and u["pseudo"].lower() == args.lower()),
        None
    )

    if not target_sid:
        emit("system_message", {"room": room, "msg": f"User '{args}' not found."}, to=sid)
        return

    emit(
        "system_message",
        {"room": room, "msg": f"{args} was kicked by an admin."},
        broadcast=True,
    )

    emit(
        "user_kicked",
        {"room": room, "reason": "You were kicked by an admin."},
        to=target_sid,
    )
    disconnect(sid=target_sid)
    log_info("commands", f"User '{args}' kicked from {room}")


# =====================================================
#   /BAN
# =====================================================

def cmd_ban(socketio, sid, room, args):
    if not is_admin(sid):
        emit("system_message", {"room": room, "msg": "Admin only."}, to=sid)
        return

    if not args:
        emit(
            "system_message",
            {"room": room, "msg": "Usage: /ban <user> [duration]"},
            to=sid,
        )
        return

    parts = args.split()
    nickname = parts[0]
    duration_arg = parts[1] if len(parts) > 1 else None

    duration = parse_duration(duration_arg)
    expires_at = float("inf") if duration is None else time.time() + duration

    target_sid = None
    target_uid = None

    for s, u in users.items():
        if u["pseudo"].lower() == nickname.lower():
            target_sid = s
            target_uid = u["user_id"]
            break

    if not target_sid:
        emit("system_message", {"room": room, "msg": f"User '{nickname}' not found."}, to=sid)
        return

    banned_until[target_uid] = expires_at

    readable = (
        "permanently"
        if expires_at == float("inf")
        else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_at))
    )

    emit(
        "system_message",
        {"room": room, "msg": f"{nickname} was banned until {readable}."},
        broadcast=True,
    )

    emit(
        "user_kicked",
        {"room": room, "reason": f"You were banned until {readable}."},
        to=target_sid,
    )
    disconnect(sid=target_sid)

    log_info("commands", f"Banned '{nickname}' until {readable}")


# =====================================================
#   /UNBAN
# =====================================================

def cmd_unban(socketio, sid, room, args):
    if not is_admin(sid):
        emit("system_message", {"room": room, "msg": "Admin only."}, to=sid)
        return

    if not args:
        emit("system_message", {"room": room, "msg": "Usage: /unban <user>"}, to=sid)
        return

    nickname = args.lower()
    target_uid = None

    for u in users.values():
        if u["pseudo"].lower() == nickname:
            target_uid = u["user_id"]
            break

    removed = False
    to_remove = []

    for uid, exp in banned_until.items():
        if uid == target_uid:
            to_remove.append(uid)

    for uid in to_remove:
        banned_until.pop(uid, None)
        removed = True

    if removed:
        emit("system_message", {"room": room, "msg": f"User '{args}' is now unbanned."}, to=sid)
        log_info("commands", f"Unbanned '{args}'.")
    else:
        emit("system_message", {"room": room, "msg": f"No active ban for '{args}'."}, to=sid)


# =====================================================
#   /KILL
# =====================================================

def cmd_kill(socketio, sid, room, args):
    if not is_admin(sid):
        emit("system_message", {"room": room, "msg": "Admin only."}, to=sid)
        return

    target = args if args else room
    meta = rooms_meta.get(target)

    if not meta:
        emit("system_message", {"room": room, "msg": f"Channel {target} not found."}, to=sid)
        return

    if meta.get("official"):
        emit("system_message", {"room": room, "msg": "Cannot delete official channel."}, to=sid)
        return

    for s, u in users.items():
        if u["room"] == target:
            u["room"] = "#general"
            emit("switched_room", {"room": "#general"}, to=s)

    rooms.remove(target)
    rooms_meta.pop(target, None)
    save_channels()

    emit("channel_list", {"channels": rooms}, broadcast=True)
    emit(
        "system_message",
        {"room": "#general", "msg": f"{target} was deleted by an admin."},
        broadcast=True,
    )
    emit("room_counts", get_room_counts(), broadcast=True)


# =====================================================
#   ROUTER
# =====================================================

def handle_command(socketio, sid, room, msg):
    parts = msg.split(" ", 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    try:
        if cmd == "/help":
            cmd_help(socketio, sid, room, args)
            return True

        if cmd == "/me":
            cmd_me(socketio, sid, room, args)
            return True

        if cmd == "/code":
            cmd_code(socketio, sid, room, args)
            return True

        if cmd == "/admin":
            cmd_admin(socketio, sid, room, args)
            return True

        if cmd == "/mod":
            cmd_mod(socketio, sid, room, args)
            return True

        if cmd == "/kick":
            cmd_kick(socketio, sid, room, args)
            return True

        if cmd == "/ban":
            cmd_ban(socketio, sid, room, args)
            return True

        if cmd == "/unban":
            cmd_unban(socketio, sid, room, args)
            return True

        if cmd == "/kill":
            cmd_kill(socketio, sid, room, args)
            return True

    except Exception:
        log_exception("commands", f"Error executing command: {msg}")

    return False
