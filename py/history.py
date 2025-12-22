# ============================================
#     PolyTalk / Lexyo — History Manager
#     Support des types: text / action / code
#     + MP server-side decryption
# ============================================

from flask_socketio import emit

from py.state import users
from py.storage import get_room_history, decrypt_mp
from py.config import HISTORY_LIMIT
from py.logger import log_info, log_warning, log_error, log_exception


def send_room_history(room, sid):
    """
    Envoie l'historique complet d'un salon (public ou privé) à un user.
    - PATCH: AUCUNE traduction batch ici (aucun appel OpenAI pendant join/refresh).
    - Messages "text" → envoyés bruts (original indicates original; translated=None).
    - Messages "action" (/me) → renvoyés tels quels, sans traduction.
    - Messages "code" (/code) → renvoyés tels quels, sans traduction.
    - MP (@room) → messages stockés chiffrés, déchiffrés côté serveur avant envoi.
    """
    try:
        user = users.get(sid)
        if not user:
            log_warning("history", f"send_room_history aborted: sid={sid} not found.")
            return

        target_lang = user["lang"]

        # On récupère l'historique brut (liste de dicts)
        room_msgs = get_room_history(room, HISTORY_LIMIT)

        # ----------------------------------------------------
        # 0) Déchiffrement des MP (si room privée @...)
        #    IMPORTANT: on le fait AVANT payload.
        # ----------------------------------------------------
        if isinstance(room, str) and room.startswith("@"):
            for m in room_msgs:
                msg_type = m.get("type", "text")
                try:
                    if msg_type == "text" and "original" in m and isinstance(m.get("original"), str):
                        m["original"] = decrypt_mp(m["original"])
                    elif msg_type in ("action", "code") and "content" in m and isinstance(m.get("content"), str):
                        m["content"] = decrypt_mp(m["content"])
                except Exception:
                    # Ne pas casser l'envoi d'historique si un message est corrompu/ancienne version
                    log_exception("history", f"Failed to decrypt MP message in {room}")

        log_info(
            "history",
            f"Sending history of '{room}' to '{user.get('pseudo')}' "
            f"({len(room_msgs)} messages).",
        )

        # ----------------------------------------------------
        # 1) Construction du payload final (SANS traduction)
        # ----------------------------------------------------
        history_payload = []

        for msg in room_msgs:
            msg_type = msg.get("type", "text")

            # ---------- /me : action ----------
            if msg_type == "action":
                history_payload.append(
                    {
                        "type": "action",
                        "pseudo": msg.get("pseudo", ""),
                        "content": msg.get("content", ""),
                        "timestamp": msg.get("timestamp"),
                    }
                )
                continue

            # ---------- /code ----------
            if msg_type == "code":
                history_payload.append(
                    {
                        "type": "code",
                        "pseudo": msg.get("pseudo", ""),
                        "lang": msg.get("lang", "txt"),
                        "content": msg.get("content", ""),
                        "timestamp": msg.get("timestamp"),
                    }
                )
                continue

            # ---------- Message texte classique ----------
            original = msg.get("original", "")

            history_payload.append(
                {
                    "type": "text",
                    "pseudo": msg.get("pseudo", ""),
                    "text": original,              # PATCH: affichage immédiat (brut)
                    "original": original,
                    "translated": None,            # PATCH: aucune traduction dans l'historique
                    "source_lang": msg.get("source_lang"),
                    "target_lang": target_lang,
                    "timestamp": msg.get("timestamp"),
                    "color": msg.get("color"),
                }
            )

        # ----------------------------------------------------
        # 2) Envoi au client
        # ----------------------------------------------------
        emit("room_history", {"room": room, "messages": history_payload}, to=sid)

        log_info(
            "history",
            f"History for room '{room}' sent successfully to '{user.get('pseudo')}'.",
        )

    except Exception:
        log_exception(
            "history",
            f"Unexpected error while sending history of '{room}' to sid={sid}",
        )
