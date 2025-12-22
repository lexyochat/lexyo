# ============================================
#     Lexyo — Private Socket.IO Handlers
#     CLEAN PROD 2026 — MP (SECURE USER_ID ROOMS)
# ============================================

import time
import hashlib
from flask_socketio import emit
from flask import request

import py.state as state
from py.state import users
from py.users import get_sid_by_pseudo, get_users_in_room
from py.rooms import (
    touch_room,
    update_room_empty_state,
    get_room_counts,
)
from py.storage import append_message, remove_room_file
from py.config import (
    MAX_MESSAGE_LENGTH,
    MIN_DELAY,
    RATE_LIMIT_WINDOW_SECONDS,
    RATE_LIMIT_MAX_IP,
    RATE_LIMIT_MAX_USER,
)
from py.translate import translate_text
from py.logger import log_warning, log_info, log_exception


# =====================================================
#   GLOBAL RATE LIMIT — S3-B (IP + USER_ID)
# =====================================================
# _RATE_LIMIT["ip:1.2.3.4"] = [timestamps]
# _RATE_LIMIT["uid:abc123"] = [timestamps]
_RATE_LIMIT = {}


def _rate_limit_hit(key: str, limit: int, now: float) -> bool:
    window = RATE_LIMIT_WINDOW_SECONDS
    timestamps = _RATE_LIMIT.get(key, [])
    cutoff = now - window
    timestamps = [t for t in timestamps if t >= cutoff]
    timestamps.append(now)
    _RATE_LIMIT[key] = timestamps
    return len(timestamps) > limit


def _rate_limit_check(user_id: str, ip: str) -> bool:
    now = time.time()
    if ip and _rate_limit_hit(f"ip:{ip}", RATE_LIMIT_MAX_IP, now):
        return True
    if user_id and _rate_limit_hit(f"uid:{user_id}", RATE_LIMIT_MAX_USER, now):
        return True
    return False


# =====================================================
#   MP COMMAND POLICY (OPTION A)
# =====================================================
MP_ALLOWED_COMMANDS = {"code", "me", "help"}


def _parse_mp_code_command(raw: str):
    """
    Parses /code command in MP.

    Accepted forms:
      /code python <inline>
      /code python\n<block>
      /code\n<block>              (lang defaults to txt)
    """
    rest = raw[len("/code"):].lstrip()
    if not rest:
        return ("txt", "")

    # If block form:
    if "\n" in rest:
        first, body = rest.split("\n", 1)
        first = first.strip()
        body = body.rstrip("\n")
        if not first:
            return ("txt", body)
        return (first, body)

    # Inline form:
    parts = rest.split(" ", 1)
    if len(parts) == 1:
        # only one token after /code -> treat it as content, lang=txt
        return ("txt", parts[0].strip())
    lang = parts[0].strip()
    body = parts[1].strip()
    return (lang or "txt", body)


def register_private_handlers(socketio):
    """
    Private events:
    - open_private      → open UI tab only (no room switch)
    - switch_private    → user clicks MP tab (room switch)
    - private_message   → sending PM (also ensures room switch)

    MP-02:
    - MP rooms are NOT based on pseudo anymore
    - MP rooms are based on user_id, via @mp_<hash>
    - Prevents pseudo reuse from accessing old MP history
    """

    # --------------------------------------------------
    # MP-02 Helpers
    # --------------------------------------------------
    def _mp_key(user_id_a: str, user_id_b: str):
        return frozenset({str(user_id_a), str(user_id_b)})

    def _mp_room_name(user_id_a: str, user_id_b: str) -> str:
        # Deterministic + non-guessable enough for casual probing:
        # hash(sorted_ids.join("|")) truncated
        a = str(user_id_a)
        b = str(user_id_b)
        ids = sorted([a, b])
        digest = hashlib.sha256(("|".join(ids)).encode("utf-8")).hexdigest()[:16]
        return f"@mp_{digest}"

    def get_or_create_private_room(user_a: dict, user_b: dict) -> str:
        """
        Returns the secure MP room name for two connected users.
        Creates state.mp_rooms entry if missing.
        """
        uid_a = str(user_a.get("user_id") or "")
        uid_b = str(user_b.get("user_id") or "")

        if not uid_a or not uid_b:
            # Fallback (should not happen in normal flow)
            # but we refuse MP rather than creating pseudo-based room.
            return ""

        key = _mp_key(uid_a, uid_b)

        entry = state.mp_rooms.get(key)
        if entry:
            return entry["room"]

        room = _mp_room_name(uid_a, uid_b)
        now = time.time()

        state.mp_rooms[key] = {
            "room": room,
            "participants": {uid_a, uid_b},
            "connected": set(),          # updated on switch/send
            "created_at": now,
            "last_activity": now,
        }

        return room

    def _find_mp_entry_by_room(room: str):
        for key, entry in state.mp_rooms.items():
            if entry.get("room") == room:
                return key, entry
        return None, None

    def _mark_mp_connected(entry: dict, user_id: str):
        try:
            entry["connected"].add(str(user_id))
        except Exception:
            entry["connected"] = {str(user_id)}
        entry["last_activity"] = time.time()

    def _mark_mp_disconnected_by_uid(user_id: str):
        """
        Remove a user_id from all MP rooms' connected sets.
        (Used by disconnect logic, wired in PATCH 04C.)
        """
        if not user_id:
            return
        uid = str(user_id)
        for _, entry in state.mp_rooms.items():
            try:
                entry.get("connected", set()).discard(uid)
            except Exception:
                continue

    def _cleanup_dead_mp_rooms():
        """
        Deterministic MP cleanup:
        - recompute "connected" from actual connected user_ids
        - delete mp_rooms entries with no connected participants
        - remove associated encrypted JSON file
        """
        try:
            connected_ids = state.get_connected_user_ids()
        except Exception:
            # Fallback: if helper missing for any reason, skip cleanup safely
            return

        to_delete = []
        for key, entry in state.mp_rooms.items():
            try:
                participants = set(entry.get("participants", set()))
                still_connected = participants.intersection(connected_ids)
                entry["connected"] = still_connected
                if not still_connected:
                    to_delete.append(key)
            except Exception:
                continue

        for key in to_delete:
            try:
                room = state.mp_rooms.get(key, {}).get("room")
                if room:
                    remove_room_file(room)
                state.mp_rooms.pop(key, None)
                if room:
                    log_info("sockets_private", f"Cleaned dead MP room: {room}")
            except Exception:
                log_exception("sockets_private", "Failed cleaning dead MP room")

    # --------------------------------------------------
    # Helper: switch user room server-side (with counts)
    # --------------------------------------------------
    def _switch_user_room(user, new_room):
        old_room = user.get("room")
        if not old_room or old_room == new_room:
            return

        user["room"] = new_room

        # Meta / cleanup
        touch_room(new_room, user_join=True)
        update_room_empty_state(old_room)

        # Update users in old & new rooms
        socketio.emit("room_users", {
            "room": old_room,
            "users": get_users_in_room(old_room),
        })

        socketio.emit("room_users", {
            "room": new_room,
            "users": get_users_in_room(new_room),
        })

        # Update global room counts
        socketio.emit("room_counts", get_room_counts())

    # =====================================================
    #   OPEN PRIVATE TAB (UI ONLY — NO ROOM SWITCH)
    # =====================================================
    @socketio.on("open_private")
    def open_private(data):
        user = users.get(request.sid)
        if not user:
            return

        # GLOBAL RATE LIMIT (S3-B)
        if _rate_limit_check(str(user.get("user_id") or request.sid), request.remote_addr or ""):
            log_warning("rate_limit", f"open_private blocked (ip={request.remote_addr})")
            return

        target_pseudo = (data.get("with") or "").strip()
        if not target_pseudo or target_pseudo.lower() == user["pseudo"].lower():
            return

        target_sid, target_user = get_sid_by_pseudo(target_pseudo)
        if not target_sid:
            emit("system_message", {
                "room": user["room"],
                "msg": f"{target_pseudo} is not connected."
            }, to=request.sid)
            return

        # MP-02: secure room based on user_id
        room = get_or_create_private_room(user, target_user)
        if not room:
            emit("system_message", {
                "room": user["room"],
                "msg": "Private messaging is unavailable (missing user_id)."
            }, to=request.sid)
            return

        # Track as connected (tab opened, not necessarily switched, but safe)
        key, entry = _find_mp_entry_by_room(room)
        if entry:
            _mark_mp_connected(entry, user.get("user_id") or request.sid)

        _cleanup_dead_mp_rooms()

        emit("open_private_room", {
            "room": room,
            "with": target_user["pseudo"],
        }, to=request.sid)

        log_info(
            "sockets_private",
            f'Open MP tab: {room} ({user["pseudo"]} -> {target_user["pseudo"]})'
        )

    # =====================================================
    #   SWITCH PRIVATE ROOM (user clicks MP tab)
    # =====================================================
    @socketio.on("switch_private")
    def switch_private(data):
        user = users.get(request.sid)
        if not user:
            return

        # GLOBAL RATE LIMIT (S3-B)
        if _rate_limit_check(str(user.get("user_id") or request.sid), request.remote_addr or ""):
            log_warning("rate_limit", f"switch_private blocked (ip={request.remote_addr})")
            return

        room = (data.get("room") or "").strip()
        if not room or not room.startswith("@"):
            return

        # MP-02: user can only switch to a MP room they are a participant of
        key, entry = _find_mp_entry_by_room(room)
        if not entry:
            emit("system_message", {
                "room": user.get("room"),
                "msg": "This private room no longer exists."
            }, to=request.sid)
            return

        uid = str(user.get("user_id") or "")
        if not uid or uid not in entry.get("participants", set()):
            emit("system_message", {
                "room": user.get("room"),
                "msg": "Access denied to this private room."
            }, to=request.sid)
            return

        _mark_mp_connected(entry, uid)
        _switch_user_room(user, room)

        _cleanup_dead_mp_rooms()

    # =====================================================
    #   PRIVATE MESSAGE — ensure room switch + send
    # =====================================================
    @socketio.on("private_message")
    def private_message(data):
        user = users.get(request.sid)
        if not user:
            return

        # GLOBAL RATE LIMIT (S3-B)
        if _rate_limit_check(str(user.get("user_id") or request.sid), request.remote_addr or ""):
            log_warning("rate_limit", f"private_message blocked (ip={request.remote_addr})")
            return

        now = time.time()
        last = user.get("last_message_time", 0)

        # Anti spam
        if now - last < MIN_DELAY:
            log_warning(
                "sockets_private",
                f'Rate limited PM from "{user["pseudo"]}".'
            )
            return
        user["last_message_time"] = now

        msg = (data.get("msg") or "").strip()
        target_pseudo = (data.get("to") or "").strip()
        contains_link = "http://" in msg or "https://" in msg

        if not msg or not target_pseudo:
            return

        if len(msg) > MAX_MESSAGE_LENGTH:
            emit("system_message", {
                "room": user["room"],
                "msg": f"Private message too long ({len(msg)} chars)."
            }, to=request.sid)
            return

        target_sid, target_user = get_sid_by_pseudo(target_pseudo)
        if not target_sid:
            emit("system_message", {
                "room": user["room"],
                "msg": f"{target_pseudo} is not connected."
            }, to=request.sid)
            return

        # MP-02: secure room based on user_id (prevents pseudo reuse leaks)
        room = get_or_create_private_room(user, target_user)
        if not room:
            emit("system_message", {
                "room": user["room"],
                "msg": "Private messaging is unavailable (missing user_id)."
            }, to=request.sid)
            return

        # Track connected participants
        key, entry = _find_mp_entry_by_room(room)
        if entry:
            _mark_mp_connected(entry, user.get("user_id") or request.sid)
            _mark_mp_connected(entry, target_user.get("user_id") or target_sid)

        # IMPORTANT: ensure server knows we are in the MP room
        _switch_user_room(user, room)

        # MP-02F: matérialise la room MP avant stockage
        # (garantit création du fichier dans data/private)
        touch_room(room, user_join=True)

        # =====================================================
        #   COMMANDS IN MP (OPTION A)
        # =====================================================
        if msg.startswith("/"):
            cmd = msg.split(" ", 1)[0][1:].lower()

            if cmd not in MP_ALLOWED_COMMANDS:
                emit("system_message", {
                    "room": room,
                    "msg": f"Command /{cmd} is not available in private messages."
                }, to=request.sid)
                return

            if cmd == "help":
                emit("system_message", {
                    "room": room,
                    "msg": "Available in private messages: /code, /me, /help"
                }, to=request.sid)
                return

            if cmd == "me":
                content = msg[len("/me"):].strip()
                if not content:
                    emit("system_message", {
                        "room": room,
                        "msg": "Usage: /me action"
                    }, to=request.sid)
                    return

                # Save as action
                action_record = {
                    "pseudo": user["pseudo"],
                    "content": content,
                    "timestamp": now,
                    "color": user.get("color"),
                    "type": "action",
                }
                try:
                    append_message(room, action_record)
                except Exception:
                    log_exception("sockets_private", f"Failed saving MP action in {room}")

                # Emit to both
                emit("action_message", {
                    "room": room,
                    "author": user["pseudo"],
                    "content": content,
                }, to=request.sid)

                emit("action_message", {
                    "room": room,
                    "author": user["pseudo"],
                    "content": content,
                }, to=target_sid)

                _cleanup_dead_mp_rooms()
                return

            if cmd == "code":
                lang, content = _parse_mp_code_command(msg)
                if not content:
                    emit("system_message", {
                        "room": room,
                        "msg": "Usage: /code <lang> <code>  (or /code <lang>\\n<code>)"
                    }, to=request.sid)
                    return

                # Save as code
                code_record = {
                    "pseudo": user["pseudo"],
                    "lang": lang,
                    "content": content,
                    "timestamp": now,
                    "color": user.get("color"),
                    "type": "code",
                }
                try:
                    append_message(room, code_record)
                except Exception:
                    log_exception("sockets_private", f"Failed saving MP code in {room}")

                # Emit to both
                emit("code_message", {
                    "room": room,
                    "pseudo": user["pseudo"],
                    "lang": lang,
                    "content": content,
                    "timestamp": now,
                }, to=request.sid)

                emit("code_message", {
                    "room": room,
                    "pseudo": user["pseudo"],
                    "lang": lang,
                    "content": content,
                    "timestamp": now,
                }, to=target_sid)

                _cleanup_dead_mp_rooms()
                return

        # =====================================================
        #   SAVE MESSAGE (MP-01 will encrypt because room startswith "@")
        # =====================================================
        msg_record = {
            "pseudo": user["pseudo"],
            "original": msg,
            "source_lang": user["lang"],
            "timestamp": now,
            "color": user.get("color"),
            "type": "text",
        }

        try:
            append_message(room, msg_record)
        except Exception:
            log_exception(
                "sockets_private",
                f"Failed saving PM in {room}"
            )

        # =====================================================
        #   SENDER
        # =====================================================
        emit("receive_message", {
            "pseudo": user["pseudo"],
            "original": msg,
            "translated": msg,
            "source_lang": user["lang"],
            "target_lang": user["lang"],
            "room": room,
            "is_private": True,
            "with": target_user["pseudo"],
            "color": user.get("color"),
            "timestamp": now,
        }, to=request.sid)

        # =====================================================
        #   RECEIVER (with translation)
        # =====================================================
        if contains_link or user["lang"] == target_user["lang"]:
            translated = msg
        else:
            try:
                translated = translate_text(
                    msg, user["lang"], target_user["lang"]
                )
            except Exception:
                translated = msg
                log_exception(
                    "sockets_private",
                    f"Translation error {user['lang']} -> {target_user['lang']}"
                )

        emit("receive_message", {
            "pseudo": user["pseudo"],
            "original": msg,
            "translated": translated,
            "source_lang": user["lang"],
            "target_lang": target_user["lang"],
            "room": room,
            "is_private": True,
            "with": user["pseudo"],
            "color": user.get("color"),
            "timestamp": now,
        }, to=target_sid)

        log_info(
            "sockets_private",
            f'PM {user["pseudo"]} -> {target_user["pseudo"]}: {msg[:60]!r}'
        )

        _cleanup_dead_mp_rooms()
