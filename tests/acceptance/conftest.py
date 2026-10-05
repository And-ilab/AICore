"""Pytest hooks for P0-04 acceptance matrix status updates.

Django is set up here so shared fixtures can import models.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django

django.setup()

from tests.acceptance.fixtures import (  # noqa: E402
    api_client_for,
    parse_sse_content,
    post_json,
    seed_cc_chunk,
    user_for_role,
)

__all__ = [
    "api_client_for",
    "parse_sse_content",
    "post_json",
    "seed_cc_chunk",
    "user_for_role",
]


def pytest_runtest_makereport(item, call):
    """Optional hook for pytest-style @pytest.mark.acceptance tests."""
    if call.when != "call":
        return
    marker = item.get_closest_marker("acceptance")
    if marker is None or not marker.args:
        return
    case_id = str(marker.args[0])
    # Outcome is available via the hookwrapper pattern; keep simple:
    # unittest @mark_acceptance decorator remains the primary updater.
    del case_id
