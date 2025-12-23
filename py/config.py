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
#   PATHS — SINGLE SOURCE OF TRUTH (PERSISTENCE)
# =========================================
# Render filesystem is ephemeral. All persistent writes MUST go to a durable mount.
# In production on Render, Persistent Disk is mounted at: /var/data
#
# Override options:
#   - LEXYO_PERSIST_ROOT=/custom/path
#   - LEXYO_DATA_DIR=/custom/path   (legacy alias for persist root)
#
# In dev, we default to a local folder inside the repo: ./var/data

# Project root = one level above /py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PERSIST_ROOT = (
    os.getenv("LEXYO_PERSIST_ROOT")
    or os.getenv("LEXYO_DATA_DIR")
    or ("/var/data" if IS_PROD else os.path.join(PROJECT_ROOT, "var", "data"))
)

# Keep legacy variable names for backward compatibility across the codebase:
DATA_DIR = PERSIST_ROOT

# Core persistence files/folders
CHANNELS_FILE = os.path.join(PERSIST_ROOT, "channels.json")
PUBLIC_DIR = os.path.join(PERSIST_ROOT, "public")
PRIVATE_DIR = os.path.join(PERSIST_ROOT, "private")

# Cache persistence (translations, etc.)
CACHE_DIR = os.path.join(PERSIST_ROOT, "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "translations.json")

# Logs persistence
LOG_DIR = os.path.join(PERSIST_ROOT, "logs")
DEFAULT_LOG_FILE = os.path.join(LOG_DIR, "lexyo.log")
LOG_FILE = os.getenv("LEXYO_LOG_FILE", DEFAULT_LOG_FILE)

# Ensure folders exist at startup
os.makedirs(PUBLIC_DIR, exist_ok=True)
os.makedirs(PRIVATE_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

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
