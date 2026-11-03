"""One dictConfig for every process that loads Django settings.

Backend, Celery and the Telegram poller are separate processes. Each gets
its own pair of files (``LOG_NAME.log`` and ``LOG_NAME.error.log``) so
rotation does not fight over a single open file on Windows.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from contextvars import ContextVar
from pathlib import Path

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_LOG_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,40}$")
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5
_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RequestIdFilter(logging.Filter):
    """Put the current HTTP request id on every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def _running_tests() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    joined = " ".join(sys.argv).lower()
    return "pytest" in joined or any(arg in {"test", "pytest"} for arg in sys.argv[1:2])


def _log_level() -> str:
    raw = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    return raw if raw in _LEVELS else "INFO"


def _log_name() -> str:
    raw = os.getenv("LOG_NAME", "app").strip() or "app"
    return raw if _LOG_NAME.match(raw) else "app"


def _console_enabled(*, debug: bool) -> bool:
    raw = os.getenv("LOG_TO_CONSOLE", "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return debug


def build_logging(*, base_dir: Path, debug: bool) -> dict:
    """Return a logging config dict. File handlers stay off under pytest."""
    if _running_tests():
        return {"version": 1, "disable_existing_loggers": False}

    log_dir = Path(base_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    name = _log_name()
    level = _log_level()
    handlers = ["app_file", "error_file"]
    if _console_enabled(debug=debug):
        handlers.append("console")

    handler_config = {
        "app_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_dir / f"{name}.log"),
            "maxBytes": _MAX_BYTES,
            "backupCount": _BACKUP_COUNT,
            "encoding": "utf-8",
            "level": level,
            "formatter": "standard",
            "filters": ["request_id"],
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_dir / f"{name}.error.log"),
            "maxBytes": _MAX_BYTES,
            "backupCount": _BACKUP_COUNT,
            "encoding": "utf-8",
            "level": "ERROR",
            "formatter": "standard",
            "filters": ["request_id"],
        },
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "level": level,
            "formatter": "standard",
            "filters": ["request_id"],
        },
    }
    active_handlers = {key: handler_config[key] for key in handlers}

    # Empty handler lists clear Django's default console/mail handlers so a
    # line is written once, through the root handlers below.
    quiet_loggers = {
        logger_name: {
            "handlers": [],
            "level": "INFO",
            "propagate": True,
        }
        for logger_name in (
            "django",
            "django.server",
            "django.request",
            "celery",
            "celery.task",
            "celery.worker",
        )
    }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": RequestIdFilter},
        },
        "formatters": {
            "standard": {"format": _FORMAT, "datefmt": _DATE_FORMAT},
        },
        "handlers": active_handlers,
        "root": {"handlers": handlers, "level": level},
        "loggers": quiet_loggers,
    }
