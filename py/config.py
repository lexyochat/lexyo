# ============================================
#     Lexyo — Global Configuration
#     CLEAN PROD + Security Hardening (2026)
# ============================================

import os

# =========================================
#   ENVIRONMENT
# =========================================
# Expected values: "dev", "prod"
ENV = os.getenv("ENV", "dev").lower()
IS_PROD = ENV == "prod"

# =========================================
#   RENDER / PERSISTENT DISK
# =========================================
# On Render, attach a disk mounted for example at:
#   /var/data
#
# We make DATA_DIR resolve to the disk when available,
# so conversations/files survive restarts & deploys.
#
# Priority:
#  1) DATA_DIR env (absolute or relative)
#  2) RENDER_DISK_MOUNT env (absolute)
#  3) If /var/data exists -> use it
#  4) fallback to ./data (local)

def _resolve_data_dir() -> str:
    env_data_dir = os.getenv("DATA_DIR", "").strip()
    if env_data_dir:
        if os.path.isabs(env_data_dir):
            return env_data_dir
        return os.path.abspath(env_data_dir)

    env_mount = os.getenv("RENDER_DISK_MOUNT", "").strip()
    if env_mount and os.path.isabs(env_mount):
        return env_mount

    if os.path.isdir("/var/data"):
        return "/var/data"

    return os.path.abspath("data")


DATA_DIR = _resolve_data_dir()

# =========================================
#   STORAGE DIRECTORIES
# =========================================
CHANNELS_FILE = os.path.join(DATA_DIR, "channels.json")
PUBLIC_DIR = os.path.join(DATA_DIR, "public")
PRIVATE_DIR = os.path.join(DATA_DIR, "private")

CACHE_DIR = os.path.join(DATA_DIR, "_cache")
TRANSLATIONS_CACHE_FILE = os.path.join(CACHE_DIR, "translations.json")

LOGS_DIR = os.path.join(DATA_DIR, "_logs")

# Ensure folders exist at startup
os.makedirs(PUBLIC_DIR, exist_ok=True)
os.makedirs(PRIVATE_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# =========================================
#   GENERAL PARAMETERS
# =========================================
HISTORY_LIMIT = 100             # Max messages kept per room
ROOM_TTL_SECONDS = 60 * 10      # Auto-delete empty public rooms after 10 min
CLEANUP_INTERVAL_SECONDS = 60   # Background cleanup scan interval (seconds)
MIN_DELAY = 0.8                 # Anti-spam: minimum delay between messages
MAX_MESSAGE_LENGTH = 1000       # Hard cap on message size (chars)

# =========================================
#   CLOUDFLARE TURNSTILE (Invisible Captcha)
# =========================================
# Must be set in your environment (.env / Render secrets):
#   TURNSTILE_SECRET_KEY=xxxxxxxxxxxx
#   TURNSTILE_SITE_KEY=xxxxxxxxxxxx

TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "")

# In production, captcha MUST be enforced.
# In dev, missing keys will bypass captcha for convenience.
REQUIRE_TURNSTILE = (
    os.getenv("REQUIRE_TURNSTILE", "true" if IS_PROD else "false")
    .lower()
    in ("1", "true", "yes", "on")
)

# =========================================
#   /ADMIN BRUTE-FORCE PROTECTION (S2C)
# =========================================
# Rolling window rate limit for /admin attempts (per user_id)
ADMIN_RATE_WINDOW_SECONDS = int(os.getenv("ADMIN_RATE_WINDOW_SECONDS", "60"))
ADMIN_RATE_MAX_ATTEMPTS = int(os.getenv("ADMIN_RATE_MAX_ATTEMPTS", "5"))
ADMIN_LOCK_SECONDS = int(os.getenv("ADMIN_LOCK_SECONDS", "300"))

# =========================================
#   GLOBAL RATE LIMIT (S3-B)
# =========================================
# Soft protection against floods & multi-sessions (IP + user_id)
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "10"))
RATE_LIMIT_MAX_IP = int(os.getenv("RATE_LIMIT_MAX_IP", "40"))
RATE_LIMIT_MAX_USER = int(os.getenv("RATE_LIMIT_MAX_USER", "25"))

# =========================================
#   MP SERVER-SIDE ENCRYPTION
# =========================================
# Must be set in your environment:
#   MP_SECRET_KEY=long_random_secret (>=32 chars recommended)
#
# IMPORTANT:
# - This key protects all private messages at rest.
# - If missing, MP storage MUST fail loudly.

MP_SECRET_KEY = os.getenv("MP_SECRET_KEY", "")

# =========================================
#   OFFICIAL CHANNELS (SAFE FROM CLEANUP)
# =========================================
# These rooms are:
# - pre-created
# - never auto-deleted
# - safe from /cleanup and TTL rules

OFFICIAL_ROOMS = [
    # Universal / Social
    "#general",

    # Tech / Dev / AI
    "#coding",
    "#linux",
    "#security",
    "#ai",
    "#opensource",

    # Underground / Privacy / Old Web
    "#anonymous",
    "#underground",
    "#privacy",
    "#torrent",
    "#deepweb",

    # Crypto / Finance
    "#crypto",
    "#bitcoin",
    "#defi",
    "#trading",

    # Chill / Culture
    "#gaming",
    "#music",
    "#memes",
    "#philosophy",
    "#nsfw",
]
