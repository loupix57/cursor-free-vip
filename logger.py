# logger.py - Central logging for Cursor Free VIP
"""
Logs are written to:
  - File: Documents/.cursor-free-vip/logs/cursor-free-vip.log (with daily rotation)
  - Console: same format, level controlled by LOG_LEVEL env or default INFO
"""
import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler

from utils import get_user_documents_path

LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "cursor-free-vip.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_log_initialized = False
_file_handler = None


def get_log_dir():
    """Return the log directory path (Documents/.cursor-free-vip/logs)."""
    base = get_user_documents_path()
    log_dir = os.path.join(base, ".cursor-free-vip", LOG_DIR_NAME)
    return log_dir


def get_log_path():
    """Return the main log file path."""
    return os.path.join(get_log_dir(), LOG_FILE_NAME)


def setup_logging(
    level=None,
    log_to_console=True,
    log_to_file=True,
):
    """
    Initialize central logging. Safe to call multiple times; only initializes once.
    """
    global _log_initialized, _file_handler

    if _log_initialized:
        return

    if level is None:
        # Réduire le bruit par défaut : WARNING au lieu de INFO.
        # Possibilité de réactiver INFO via la variable d'environnement
        # CURSOR_FREE_VIP_LOG_LEVEL=INFO si besoin.
        level = os.environ.get("CURSOR_FREE_VIP_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level, logging.WARNING)

    root = logging.getLogger("cursor_free_vip")
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    if log_to_console:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(formatter)
        root.addHandler(console)

    if log_to_file:
        try:
            log_dir = get_log_dir()
            os.makedirs(log_dir, exist_ok=True)
            log_path = get_log_path()
            _file_handler = TimedRotatingFileHandler(
                log_path,
                when="midnight",
                interval=1,
                backupCount=7,
                encoding="utf-8",
            )
            _file_handler.setLevel(level)
            _file_handler.setFormatter(formatter)
            root.addHandler(_file_handler)
            root.info("Logs written to %s", log_path)
        except Exception as e:
            if log_to_console:
                sys.stdout.write(f"[cursor-free-vip] Could not create log file: {e}\n")

    _log_initialized = True


def get_logger(name):
    """
    Return a logger for the given module name.
    Use after setup_logging() has been called (e.g. from main.py).
    """
    if not _log_initialized:
        setup_logging()
    full_name = "cursor_free_vip." + (name or "app")
    return logging.getLogger(full_name)
