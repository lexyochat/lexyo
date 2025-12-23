# ============================================
#   Lexyo — Central logger (CLEAN PROD)
# ============================================

import logging
from logging.handlers import TimedRotatingFileHandler

from py.config import LOG_DIR, LOG_FILE

# Ensure log directory exists (defensive; config.py already does it)
try:
    import os
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    pass


# --------------------------------------------
#   Logger identity (overrideable by env)
# --------------------------------------------

# Global app logger name
ROOT_LOGGER_NAME = os.getenv("LEXYO_LOGGER_NAME", "lexyo")

# Log level (INFO by default)
LOG_LEVEL = os.getenv("LEXYO_LOG_LEVEL", "INFO").upper()


def _configure_root_logger() -> logging.Logger:
    """
    Configure the root Lexyo logger once (idempotent).
    Uses a daily rotating file, keeps 30 days of history.
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)

    # Prevent duplicate handlers on hot reload / multiple imports
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        backupCount=30,
        encoding="utf-8",
        utc=False,
    )

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
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
