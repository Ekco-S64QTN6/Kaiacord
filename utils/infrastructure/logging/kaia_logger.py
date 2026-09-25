"""
Kaia's logging functions.

Thin, named wrappers over the unified logger (unified_logging.logger), which
owns the file, the level filtering, compaction and the dashboard feed. Every
module logs through these rather than holding the logger itself.
"""

from utils.infrastructure.logging.unified_logging import logger as global_logger


def log_success(message):
    global_logger.log(message, "SUCCESS")


def log_ready(message):
    global_logger.log(message, "READY")


def log_action(message):
    global_logger.log(message, "ACTION")


def log_critical(message):
    global_logger.log(message, "CRITICAL")


def log_warning(message):
    global_logger.log(message, "WARNING")


def log_error(message):
    global_logger.log(message, "ERROR")


def log_info(message):
    global_logger.log(message, "INFO")


def log_debug(message):
    global_logger.log(message, "DEBUG")


def log_separator():
    """Separators are clutter in the dashboard; kept as a no-op for callers."""
