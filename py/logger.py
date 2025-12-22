# ============================================
#   Lexyo — Central logger (CLEAN PROD)
#   PATCH 01: Persist logs to DATA_DIR/_logs (Render disk)
# ============================================

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

from py.config import LOGS_DIR

# Ensure persistent logs directory exists
os.makedirs(LOGS_DIR, exist_ok=True)

# --------------------------------------------
#   Logger identity (overrideable by env)
# --------------------------------------------
# - If LEXYO_LOG_FILE is absolute, keep it as-is.
# - If it is relative, store it under LOGS_DIR.
DEFAULT_LOG_FILE = os.path.join(LOGS_DIR, "lexyo.log")
_env_log_file = os.getenv("LEXYO_LOG_FILE", "").strip()

if _env_log_file:
    LOG_FILE = _env_log_file if os.path.isabs(_env_log_file) else os.path.join(LOGS_DIR, _env_log_file)
else:
    LOG_FILE = DEFAULT_LOG_FILE

# Global app logger name
ROOT_LOGGER_NAME = os.getenv("LEXYO_LOGGER_NAME", "lexyo")

# Log level (INFO by default)
LOG_LEVEL = os.getenv("LEXYO_LOG_LEVEL", "INFO").upper()


def _configure_root_logger() -> logging.Logger:
    """
    Configure the root Lexyo logger once (idempotent).
    Uses a daily rotating file, keeps 30 days of history.

    PATCH 01:
    - File logs are written under LOGS_DIR (persistent disk).
    - If file handler fails, fall back to stderr to avoid crashing the app.
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)

    if logger.handlers:
        # Already configured (avoid duplicate handlers on reload)
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        # Ensure directory exists even if LOG_FILE points elsewhere inside LOGS_DIR
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

        handler = TimedRotatingFileHandler(
            LOG_FILE,
            when="midnight",
            backupCount=30,
            encoding="utf-8",
            utc=False,
        )
    except Exception:
        # Safe fallback: still log somewhere, but do not crash server
        handler = logging.StreamHandler(stream=sys.stderr)

    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False  # prevent double logging to root

    return logger


def get_logger(module_name: str) -> logging.Logger:
    """
    Return a child logger for a given module name.
    Example: get_logger("sockets_public") → lexyo.sockets_public
    """
    root = _configure_root_logger()
    return root.getChild(module_name)


def log_info(module: str, message: str):
    get_logger(module).info(message)


def log_warning(module: str, message: str):
    get_logger(module).warning(message)


def log_error(module: str, message: str):
    get_logger(module).error(message)


def log_exception(module: str, message: str):
    """
    Log an exception with traceback. To be used inside except blocks.
    """
    get_logger(module).exception(message)
