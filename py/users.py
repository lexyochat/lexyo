# ============================================
#     Lexyo — User Helpers (CLEAN PROD 2026)
#     + Secure Pseudo Validation
#     + Reserved System Nicknames
#     + Anti-Spam Helper Structure
# ============================================

import re
from py.state import users


# =====================================================
#   RESERVED SYSTEM PSEUDOS (case-insensitive)
# =====================================================

RESERVED_PSEUDOS = {
    "lexyo",
    "admin",
    "system",
}


# =====================================================
#   SECURE PSEUDO VALIDATION (letters, numbers, _ -)
# =====================================================

# NOTE:
#  - 1 to 13 characters max
#  - Allows AnonymousXXXX
#  - No whitespace, unicode, emoji, HTML, etc.
PSEUDO_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,13}$")


def is_valid_pseudo(pseudo: str) -> bool:
    """
    Validate a nickname:
        - 1 to 13 characters
        - A–Z, a–z, 0–9, underscore, dash
        - rejects HTML, emoji, unicode, whitespace, accents
    """
    if not isinstance(pseudo, str):
        return False

    pseudo = pseudo.strip()
    return bool(PSEUDO_REGEX.fullmatch(pseudo))


def is_reserved_pseudo(pseudo: str) -> bool:
    """
    Returns True if the nickname is reserved for system / admin usage.
    Case-insensitive.
    """
    if not isinstance(pseudo, str):
        return False

    return pseudo.lower() in RESERVED_PSEUDOS


# =====================================================
#   GET USERS IN A PUBLIC ROOM
# =====================================================

def get_users_in_room(room):
    """
    Returns a lightweight list of users currently inside a given public room.

    Return format:
    [
        {"pseudo": str, "lang": str, "color": str},
        ...
    ]
    """
    return [
        {
            "pseudo": u["pseudo"],
            "lang": u["lang"],
            "color": u.get("color"),
        }
        for u in users.values()
        if u.get("room") == room
    ]


# =====================================================
#   FIND USER SID BY NICKNAME (case-insensitive)
# =====================================================

def get_sid_by_pseudo(pseudo):
    """
    Returns:
        (sid, user_dict)
    Or:
        (None, None) if no matching nickname is found.

    Case-insensitive search.
    """
    if not pseudo:
        return None, None

    target = pseudo.lower()

    for sid, u in users.items():
        if u["pseudo"].lower() == target:
            return sid, u

    return None, None


# =====================================================
#   INIT USER ANTI-SPAM FIELDS
# =====================================================

def init_user_struct(user: dict) -> dict:
    """
    Initialize all anti-spam related fields on the user dict.

    Fields:
        spam_score: int             -> global spam score
        last_msg_text: str          -> last sent message text
        msg_timestamps: list[float] -> recent message timestamps (burst detection)
        spam_warned: bool           -> has the system already warned this user
    """
    if user is None:
        return None

    user.setdefault("spam_score", 0)
    user.setdefault("last_msg_text", "")
    user.setdefault("msg_timestamps", [])
    user.setdefault("spam_warned", False)

    return user
