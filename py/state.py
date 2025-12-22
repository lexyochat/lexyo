# ============================================
#     Lexyo — Runtime Global State (CLEAN PROD)
#     + Secure MP Architecture (MP-02A)
# ============================================

# Connected users:
# { sid: {"pseudo": str, "lang": str, "room": str, "user_id": str, "color": str, ...} }
users = {}

# Set of all active nicknames (case-insensitive check done elsewhere)
used_pseudos = set()

# List of existing public rooms (e.g. #general, #music)
# MP rooms are NOT listed here anymore
rooms = []

# Metadata for each room:
# rooms_meta = {
#   room_name: {
#       "official": bool,
#       "last_activity": float,
#       "last_empty": float|None,
#       "creator_id": str|None,
#       "mods": set(user_id)   # delegated moderators (session-only, per-room)
#   }
# }
rooms_meta = {}

# =====================================================
#   PRIVATE MESSAGE ROOMS (SECURE, USER_ID BASED)
# =====================================================
# mp_rooms = {
#   frozenset({user_id_A, user_id_B}): {
#       "room": "@mp_<hash>",
#       "participants": {user_id_A, user_id_B},
#       "connected": set(user_ids_currently_connected),
#       "created_at": float,
#       "last_activity": float,
#   }
# }
#
# IMPORTANT:
# - NOT based on pseudo
# - NOT guessable
# - Single source of truth
# - Safe against pseudo reuse
#
mp_rooms = {}

# =====================================================
#   ADMIN & MODERATION
# =====================================================

# Set of administrator SIDs (granted with /admin <key>)
admins = set()

# Ban system:
# banned_until = {
#     user_id: timestamp_of_expiration,
#     (float("inf") → permanent ban)
# }
banned_until = {}


# =====================================================
#   MP CLEANUP HELPERS (DETERMINISTIC)
# =====================================================

def get_connected_user_ids():
    """
    Return the set of user_id values currently connected to the server.
    This is used to deterministically cleanup MP rooms.
    """
    ids = set()
    for u in users.values():
        try:
            uid = u.get("user_id")
            if uid:
                ids.add(str(uid))
        except Exception:
            continue
    return ids


def is_user_id_connected(user_id: str) -> bool:
    """
    True if the given user_id is currently connected.
    """
    if not user_id:
        return False
    return str(user_id) in get_connected_user_ids()
