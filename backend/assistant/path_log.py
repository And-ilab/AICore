"""One JSON timing line for an assistant chat or understanding preview.

The logger name is ``assistant.path``. Django logging config gives it its
own file and does not propagate to the root logger. This module does not
import Django and does not touch the database.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Mapping

logger = logging.getLogger("assistant.path")


def elapsed_ms(started: float) -> float:
    """Milliseconds since ``started`` (``time.perf_counter``)."""
    return (time.perf_counter() - started) * 1000.0


def _json_ready(record: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in record.items():
        if (
            key.endswith("_ms")
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            payload[key] = round(float(value), 1)
        else:
            payload[key] = value
    return payload


def log_path(record: Mapping[str, Any]) -> None:
    """Write one INFO JSON object. A logging failure does not propagate."""
    try:
        logger.info("%s", json.dumps(_json_ready(record), ensure_ascii=False))
    except Exception:
        return
