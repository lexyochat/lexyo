# ============================================
#   Lexyo — Public Socket.IO Handlers (2026 Clean + Turnstile + Anti-Spam Option B)
# ============================================

import time
import requests
from flask import request
from flask_socketio import emit

import py.state as state
from py.state import users, used_pseudos, banned_until
from py.users import get_users_in_room, init_user_struct, is_valid_pseudo, is_reserved_pseudo
from py.rooms import (
    touch_room,
    update_room_empty_state,
    get_room_counts,
    create_public_room,  # PATCH 02
)
from py.config import (
    MIN_DELAY,
    MAX_MESSAGE_LENGTH,
    TURNSTILE_SECRET_KEY,
    REQUIRE_TURNSTILE,
    RATE_LIMIT_WINDOW_SECONDS,
    RATE_LIMIT_MAX_IP,
    RATE_LIMIT_MAX_USER,
)
from py.history import send_room_history
from py.storage import append_message, schedule_save_channels, remove_room_file
from py.translate import translate_text
from py.commands import handle_command
from py.logger import log_info, log_warning, log_exception


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
#   TURNSTILE CAPTCHA VALIDATION (PATCHED)
#   - remoteip REMOVED (proxy-safe)
#   - explicit missing-token handling (better logs)
# =====================================================
def verify_turnstile(token):
    # Normalize token defensively (prod can sometimes send non-str or whitespace)
    token = str(token or "").strip()

    if not TURNSTILE_SECRET_KEY:
        # In production, Turnstile MUST be enforced.
        if REQUIRE_TURNSTILE:
            log_warning("captcha", "TURNSTILE_SECRET_KEY missing — captcha REQUIRED in prod.")
            return False
        log_warning("captcha", "TURNSTILE_SECRET_KEY missing — bypassing captcha (dev mode).")
        return True

    if not token:
        log_warning("captcha", "Turnstile token missing.")
        return False

    url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    data = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": token,
        # IMPORTANT: do NOT send remoteip behind proxies (Render/Cloudflare/etc.)
    }

    try:
        r = requests.post(url, data=data, timeout=8)

        if r.status_code != 200:
            log_warning("captcha", f"Turnstile HTTP {r.status_code}: {r.text[:300]}")
            return False

        try:
            resp = r.json()
        except Exception:
            log_warning("captcha", f"Turnstile non-JSON response: {r.text[:300]}")
            return False

        ok = bool(resp.get("success", False))
        if not ok:
            codes = resp.get("error-codes") or resp.get("error_codes") or []
            log_warning("captcha", f"Turnstile failed: codes={codes} full={resp}")

        return ok

    except Exception as e:
        log_exception("captcha", f"Turnstile verify error: {e}")
        return False


# =====================================================
#   ANTI-SPAM — OPTION B (adoucie, recommandée)
# =====================================================
def check_spam(user, msg, now):
    """
    Anti-spam intelligent, version adoucie :
      - message identique → +1
      - message très court (<3 chars) → +0
      - burst (3 msg < 2 sec) → +1
      - mentions abusives (3+) → +2
    """

    score = user.get("spam_score", 0)

    # 1) Répétition exacte
    if msg == user.get("last_msg_text", ""):
        score += 1

    # 2) Messages ultra courts → moins sévère
    if len(msg) < 3:
        score += 0

    # 3) Burst spam (3 msg < 2 sec)
    timestamps = user.get("msg_timestamps", [])
    timestamps.append(now)
    user["msg_timestamps"] = timestamps[-5:]

    if len(user["msg_timestamps"]) >= 3:
        if user["msg_timestamps"][-1] - user["msg_timestamps"][-3] < 2:
            score += 1

    # 4) Mentions abusives
    if msg.count("@") >= 3:
        score += 2

    # Save fields
    user["spam_score"] = score
    user["last_msg_text"] = msg

    return score


def apply_spam_penalty(user, sid, socketio):
    """
    OPTION B:
      Warning  = score ≥ 5
      Kick     = score ≥ 10
      Ban 10m  = score ≥ 20
      Perma    = score ≥ 35
    """

    score = user.get("spam_score", 0)
    pseudo = user.get("pseudo")
    room = user.get("room")
    user_id = user.get("user_id") or sid

    # WARNING
    if score >= 5 and score < 10 and not user.get("spam_warned", False):
        emit("system_message", {
            "room": room,
            "msg": f"{pseudo}, please slow down — spam detected."
        }, broadcast=True)

        emit("system_message", {
            "room": room,
            "msg": "Your message rate is too high."
        }, to=sid)

        user["spam_warned"] = True
        return None

    # KICK
    if score >= 10 and score < 20:
        emit("system_message", {
            "room": room,
            "msg": f"{pseudo} was kicked for spam."
        }, broadcast=True)

        emit("force_disconnect", {"reason": "spam_kick"}, to=sid)
        log_warning("spam", f"{pseudo} kicked for spam (score={score})")
        return "kick"

    # TEMP BAN — 10 minutes
    if score >= 20 and score < 35:
        banned_until[user_id] = time.time() + 600

        emit("system_message", {
            "room": room,
            "msg": f"🚫 {pseudo} was banned 10 minutes (spam)."
        }, broadcast=True)

        emit("force_disconnect", {"reason": "spam_ban"}, to=sid)
        log_warning("spam", f"{pseudo} banned 10m for spam (score={score})")
        return "ban"

    # PERMANENT BAN
    if score >= 35:
        banned_until[user_id] = float("inf")

        emit("system_message", {
            "room": room,
            "msg": f"💀 {pseudo} was permanently banned (spam)."
        }, broadcast=True)

        emit("force_disconnect", {"reason": "spam_perma"}, to=sid)
        log_warning("spam", f"{pseudo} permanently banned (score={score})")
        return "perma"

    return None


# =====================================================
#   PUBLIC SOCKET HANDLERS
# =====================================================
def register_public_handlers(socketio):

    # -----------------------------------------
    # MP CLEANUP — deterministic (single source of truth)
    # -----------------------------------------
    def _cleanup_dead_mp_rooms():
        """
        Deterministic cleanup of MP rooms/files.
        A MP is alive if at least one participant user_id is still connected.
        """
        try:
            connected_ids = state.get_connected_user_ids()
        except Exception:
            return

        to_delete = []
        for key, entry in list(state.mp_rooms.items()):
            try:
                participants = set(entry.get("participants", set()))
                still_connected = participants.intersection(connected_ids)
                entry["connected"] = still_connected
                if not still_connected:
                    to_delete.append(key)
            except Exception:
                continue

        for key in to_delete:
            entry = state.mp_rooms.get(key)
            if not entry:
                continue

            room_name = entry.get("room")
            try:
                if room_name:
                    remove_room_file(room_name)
                    log_info("mp_cleanup", f"Deleted private room file: {room_name}")
            except Exception:
                log_exception("mp_cleanup", f"Failed deleting private room file: {room_name}")

            state.mp_rooms.pop(key, None)

    # -----------------------------------------
    # ROOM USER PAYLOAD (adds is_mod / is_admin)
    # -----------------------------------------
    def _is_user_mod_in_room(room_name, user_obj):
        meta = state.rooms_meta.get(room_name) if room_name else None
        if not meta:
            return False

        uid = str(user_obj.get("user_id") or "")
        if not uid:
            return False

        creator_id = str(meta.get("creator_id") or "")
        if uid == creator_id:
            return True

        mods = meta.get("mods", set())
        try:
            return uid in mods
        except Exception:
            return False


    def _build_room_users_payload(room_name):
        payload = []
        for sid, u in users.items():
            if u.get("room") != room_name:
                continue

            payload.append({
                "user_id": str(u.get("user_id") or sid),
                "pseudo": u.get("pseudo"),
                "lang": u.get("lang"),
                "color": u.get("color"),
                "is_admin": bool(u.get("is_admin") or sid in getattr(state, "admins", set())),
                "is_mod": _is_user_mod_in_room(room_name, u),
            })
        return payload


    def _emit_room_users(room_name):
        emit("room_users", {
            "room": room_name,
            "users": _build_room_users_payload(room_name),
        }, broadcast=True)


    # -----------------------------------------
    # CONNECT
    # -----------------------------------------
    @socketio.on("connect", namespace="/")
    def on_connect():
        from py.state import rooms
        emit("channel_list", {"channels": rooms})
        log_info("sockets_public", f"Client connected: sid={request.sid}")

    # -----------------------------------------
    # REGISTER + CAPTCHA
    # -----------------------------------------
    @socketio.on("register", namespace="/")
    def register(data):
        from py.state import rooms, rooms_meta

        pseudo = (data.get("pseudo") or "").strip()
        lang = data.get("lang", "en")
        user_id = data.get("user_id") or request.sid

        # PATCH: accept several token field names (front may have changed)
        captcha_token = (
            data.get("captcha_token")
            or data.get("cf-turnstile-response")
            or data.get("cf_turnstile_response")
            or data.get("turnstile_token")
            or data.get("token")
        )

        # GLOBAL RATE LIMIT (S3-B)
        if _rate_limit_check(str(user_id), request.remote_addr or ""):
            log_warning("rate_limit", f"Register blocked (ip={request.remote_addr}, uid={user_id})")
            return

        # CAPTCHA
        if not verify_turnstile(captcha_token):
            emit("pseudo_taken", {"msg": "Captcha failed. Try again."})
            return

        # BAN CHECK
        ban_exp = banned_until.get(user_id)
        if ban_exp:
            now = time.time()
            if ban_exp == float("inf") or ban_exp > now:
                emit("pseudo_taken", {"msg": "You are banned from this server."})
                return
            else:
                banned_until.pop(user_id, None)

        # LOCAL KICK CHECK (per-room, prevents immediate rejoin to #general)
        try:
            general_meta = rooms_meta.get("#general", {})
            kicked_until_map = general_meta.get("kicked_until", {})
            ku = kicked_until_map.get(str(user_id))
            if ku:
                now = time.time()
                if ku > now:
                    emit("pseudo_taken", {"msg": "You are temporarily blocked from #general."})
                    return
                else:
                    kicked_until_map.pop(str(user_id), None)
        except Exception:
            pass

        # PSEUDO VALIDATION (backend, 1–10 chars, A-Z a-z 0-9 _ -)
        if not is_valid_pseudo(pseudo):
            emit("pseudo_taken", {
                "msg": "Invalid nickname. Use 1–10 letters, numbers, - or _."
            })
            return

        # RESERVED SYSTEM PSEUDOS
        if is_reserved_pseudo(pseudo):
            emit("pseudo_taken", {
                "msg": f"Nickname '{pseudo}' is reserved."
            })
            return

        # Pseudo already used (case-insensitive)
        if pseudo.lower() in (p.lower() for p in used_pseudos):
            emit("pseudo_taken", {"msg": f"Nickname '{pseudo}' is already in use."})
            return

        # COLOR
        color = f"hsl({__import__('random').randint(0,360)}, 70%, 60%)"

        # CREATE USER
        users[request.sid] = init_user_struct({
            "pseudo": pseudo,
            "lang": lang,
            "room": "#general",
            "user_id": user_id,
            "color": color,
            "last_message_time": 0,
        })
        used_pseudos.add(pseudo)

        # ROOM INIT
        if "#general" not in rooms_meta:
            rooms_meta["#general"] = {
                "created_at": time.time(),
                "message_count": 0,
                "last_activity": time.time(),
            }

        touch_room("#general", user_join=True)

        emit("joined_room", {"room": "#general", "color": color})
        emit("system_message", {
            "room": "#general",
            "msg": f"{pseudo} joined #general."
        }, broadcast=True)

        _emit_room_users("#general")

        emit("channel_list", {"channels": rooms})
        emit("room_counts", get_room_counts(), broadcast=True)

        send_room_history("#general", request.sid)

        log_info("sockets_public", f'User "{pseudo}" registered (lang={lang}, id={user_id}).')

    # -----------------------------------------
    # DISCONNECT
    # -----------------------------------------
    @socketio.on("disconnect", namespace="/")
    def disconnect():
        user = users.get(request.sid)
        if not user:
            return

        pseudo = user["pseudo"]
        room = user["room"]
        user_id = str(user.get("user_id") or request.sid)

        # -------------------------------------------------
        # Normal disconnect flow (unchanged)
        # -------------------------------------------------
        used_pseudos.discard(pseudo)
        users.pop(request.sid, None)

        _cleanup_dead_mp_rooms()

        emit("system_message", {
            "room": room,
            "msg": f"{pseudo} left {room}."
        }, broadcast=True)

        _emit_room_users(room)

        update_room_empty_state(room)
        emit("room_counts", get_room_counts(), broadcast=True)

        log_info("sockets_public", f'Client "{pseudo}" disconnected from {room}.')

    # -----------------------------------------
    # JOIN ROOM
    # -----------------------------------------
    @socketio.on("join", namespace="/")
    def join_room_handler(data):
        from py.state import rooms, rooms_meta

        user = users.get(request.sid)
        if not user:
            return

        # GLOBAL RATE LIMIT (S3-B)
        if _rate_limit_check(str(user.get("user_id") or request.sid), request.remote_addr or ""):
            log_warning("rate_limit", f"Join blocked (ip={request.remote_addr}, uid={user.get('user_id')})")
            return

        room = data.get("room")
        old_room = user["room"]

        if not room:
            return

        if room.startswith("@"):
            return

        if room not in rooms:
            emit("system_message", {
                "room": old_room,
                "msg": f"Channel {room} does not exist."
            }, to=request.sid)
            return

        if room == old_room:
            return

        # Ensure metadata exists
        if room not in rooms_meta:
            rooms_meta[room] = {
                "created_at": time.time(),
                "message_count": 0,
                "last_activity": time.time(),
            }

        # LOCAL KICK CHECK (per-room, prevents rejoin for a duration)
        try:
            meta = rooms_meta.get(room, {})
            kicked_until_map = meta.get("kicked_until", {})
            uid = str(user.get("user_id") or request.sid)
            until = kicked_until_map.get(uid)
            if until:
                now = time.time()
                if until > now:
                    emit("system_message", {
                        "room": old_room,
                        "msg": f"You are temporarily blocked from {room}."
                    }, to=request.sid)
                    return
                else:
                    kicked_until_map.pop(uid, None)
        except Exception:
            pass

        user["room"] = room

        touch_room(room, user_join=True)
        update_room_empty_state(old_room)

        emit("switched_room", {"room": room}, to=request.sid)

        emit("system_message", {
            "room": room,
            "msg": f"{user['pseudo']} joined {room}."
        }, broadcast=True)

        _emit_room_users(room)

        send_room_history(room, request.sid)
        emit("room_counts", get_room_counts(), broadcast=True)

        log_info("sockets_public", f'"{user["pseudo"]}" joined room {room}.')

    # -----------------------------------------
    # CREATE ROOM (PATCH VALIDATION + RETOURS PROPRES)
    # -----------------------------------------
    @socketio.on("create_room", namespace="/")
    def create_room_handler(data):
        from py.state import rooms, rooms_meta
        from py.rooms import is_valid_room_name

        raw_name = (data.get("name") or "").strip()
        user_id = data.get("user_id") or request.sid

        # GLOBAL RATE LIMIT (S3-B)
        if _rate_limit_check(str(user_id), request.remote_addr or ""):
            log_warning("rate_limit", f"Create room blocked (ip={request.remote_addr}, uid={user_id})")
            return

        # nom vide
        if not raw_name:
            emit("room_create_error", {"error": "Room name cannot be empty"})
            return

        # Validation sécurisée : lettres, chiffres, _ et -
        if not is_valid_room_name(raw_name):
            emit("room_create_error", {
                "error": "Invalid channel name. Use only letters, numbers, - or _."
            })
            return

        name = raw_name.lower()

        # Un seul salon par créateur
        for r, meta in rooms_meta.items():
            if not r.startswith("@") and meta.get("creator_id") == user_id:
                emit("room_create_error", {
                    "error": "You have already created a room. You can create another one once your current room has been empty for 10 minutes."
                })
                return

        # Interdire nom privé
        if name.startswith("@"):
            emit("room_create_error", {"error": "Invalid room name"})
            return

        # Doublon
        if name in rooms:
            emit("room_create_error", {"error": "Room already exists"})
            return

        # Création réelle (patch sécurité dans rooms.py)
        resp = create_public_room(name, user_id)

        # Erreurs renvoyées par rooms.py
        if "error" in resp:
            err = resp["error"]

            if err == "invalid_name":
                emit("room_create_error", {
                    "error": "Invalid channel name. Use only letters, numbers, - or _."
                })
                return

            if err == "already_created":
                emit("room_create_error", {
                    "error": "You have already created a room. You can create another one once your current room has been empty for 10 minutes."
                })
                return

        # Succès — auto-switch du créateur dans sa room
        user = users.get(request.sid)
        if user:
            old_room = user.get("room")
            user["room"] = name

            emit("switched_room", {"room": name}, to=request.sid)

            # update users list
            if old_room:
                _emit_room_users(old_room)

            _emit_room_users(name)

            send_room_history(name, request.sid)

        # Mise à jour globale
        emit("channel_list", {"channels": rooms}, broadcast=True)
        emit("room_counts", get_room_counts(), broadcast=True)

        # Feedback client
        emit("room_created", {"room": name}, to=request.sid)

        log_info("sockets_public", f"Room created: {name} by {user_id}")

    # -----------------------------------------
    # SEND MESSAGE
    # -----------------------------------------
    @socketio.on("send_message", namespace="/")
    def handle_message(data):
        user = users.get(request.sid)
        if not user:
            return

        # GLOBAL RATE LIMIT (S3-B)
        if _rate_limit_check(str(user.get("user_id") or request.sid), request.remote_addr or ""):
            log_warning("rate_limit", f"Message blocked (ip={request.remote_addr}, uid={user.get('user_id')})")
            return

        now = time.time()
        last = user.get("last_message_time", 0)

        # Legacy anti-flood
        if now - last < MIN_DELAY:
            log_warning("sockets_public", f"Rate-limited message from '{user['pseudo']}'")
            return

        user["last_message_time"] = now

        msg = (data.get("msg") or "").strip()
        room = user["room"]

        if not msg:
            return

        if len(msg) > MAX_MESSAGE_LENGTH:
            emit("system_message", {
                "room": room,
                "msg": f"Message too long ({len(msg)} chars)."
            }, to=request.sid)
            return

        # ANTI-SPAM OPTION B
        spam_score = check_spam(user, msg, now)
        penalty = apply_spam_penalty(user, request.sid, socketio)
        if penalty:
            return

        # No MP room
        if room.startswith("@"):
            return

        # Commands
        if msg.startswith("/"):
            try:
                if handle_command(socketio, request.sid, room, msg):
                    return
            except Exception:
                log_exception("commands", f"Error executing command: {msg}")
                return

        # ROOM META SAFETY PATCH (prevent KeyError)
        from py.state import rooms_meta

        if room not in rooms_meta:
            rooms_meta[room] = {
                "created_at": time.time(),
                "message_count": 0,
                "last_activity": now,
            }

        # Guarantee no KeyError ever
        rooms_meta[room].setdefault("message_count", 0)
        rooms_meta[room].setdefault("last_activity", now)

        # Update counters
        rooms_meta[room]["message_count"] += 1
        rooms_meta[room]["last_activity"] = now

        touch_room(room, message=True)

        # Prepare record
        contains_link = "http://" in msg or "https://" in msg

        msg_record = {
            "type": "text",
            "pseudo": user["pseudo"],
            "original": msg,
            "source_lang": user["lang"],
            "timestamp": now,
            "color": user.get("color"),
        }

        try:
            append_message(room, msg_record)
            schedule_save_channels()
        except Exception:
            log_exception("storage", f"Error saving message in {room}")

        # SEND WITH TRANSLATION (S5-C-lite: de-dup by target language)
        # Build groups per target language to avoid repeated translations for the same lang.
        sids_by_lang = {}
        room_users = []

        for sid, u in users.items():
            if u["room"] != room:
                continue
            room_users.append((sid, u))
            lang_target = u.get("lang") or user["lang"]
            sids_by_lang.setdefault(lang_target, []).append(sid)

        translations = {}
        source_lang = user["lang"]

        # Always provide original for the source language and for link messages.
        if contains_link:
            for lang_target in sids_by_lang.keys():
                translations[lang_target] = msg
        else:
            translations[source_lang] = msg
            for lang_target in sids_by_lang.keys():
                if lang_target == source_lang:
                    continue
                try:
                    translations[lang_target] = translate_text(msg, source_lang, lang_target)
                except Exception:
                    translations[lang_target] = msg
                    log_exception("translate", f"Translation failed {source_lang}→{lang_target}")

        for sid, u in room_users:
            lang_target = u.get("lang") or source_lang
            translated = translations.get(lang_target, msg)

            emit("receive_message", {
                "pseudo": user["pseudo"],
                "original": msg,
                "translated": translated,
                "source_lang": source_lang,
                "target_lang": lang_target,
                "room": room,
                "color": user.get("color"),
                "timestamp": now,
            }, to=sid)

        log_info("sockets_public", f'Message in {room} from "{user["pseudo"]}": {msg[:80]}')
