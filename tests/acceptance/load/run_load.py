#!/usr/bin/env python3
"""Run II.7.4 sufler suggest load (75 VUs) and write report.md.

Default mode: Locust in-process pipeline (no HTTP server) — CI / manual.

  python tests/acceptance/load/run_load.py
  python tests/acceptance/load/run_load.py --users 75 --duration 60

HTTP mode (backend already running):

  LOAD_MODE=http SUFLER_BASE_URL=http://127.0.0.1:8000 \\
    python tests/acceptance/load/run_load.py --http
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


LOAD_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = LOAD_DIR.parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
REPORT_PATH = LOAD_DIR / "report.md"
STATS_PATH = LOAD_DIR / "last_stats.json"
TARGET_P95_MS = 2000
DEFAULT_USERS = 75
DEFAULT_DURATION_S = 45
DEFAULT_SPAWN_RATE = 25

QUERIES = (
    "как оформить дебетовую карту",
    "замена пин-кода карты",
    "лимит снятия наличных",
    "как открыть вклад",
    "комиссия за перевод",
    "блокировка карты при утере",
    "реквизиты для перевода",
    "справка о состоянии счета",
)


def _setup_django() -> None:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
    import django

    django.setup()


def _seed_kb() -> int:
    from ingest.models import CCProductionChunk
    from ingest.pipeline import deterministic_embedding

    created = 0
    for index, query in enumerate(QUERIES, start=1):
        article_id = 8800 + index
        if CCProductionChunk.objects.filter(article_id=article_id).exists():
            continue
        CCProductionChunk.objects.create(
            article_id=article_id,
            version_id=1,
            chunk_index=0,
            title=f"Load article {index}",
            content=f"{query}. Подробная инструкция для оператора КЦ.",
            permalink=f"https://suz.local/articles/{article_id}",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum=f"sha256:{article_id:064x}",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(query),
            is_active=True,
        )
        created += 1
    return created


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def run_locust_pipeline(*, users: int, duration_s: int, spawn_rate: float) -> dict:
    """Headless Locust with SuflerSuggestPipelineUser."""
    os.environ["LOAD_MODE"] = "pipeline"
    # Patch before Django so DB thread-locals are greenlet-aware under Locust.
    from gevent import monkey

    monkey.patch_all()
    _setup_django()
    seeded = _seed_kb()
    from django.db import connections

    connections.close_all()

    from locust import events
    from locust.env import Environment
    from locust.log import setup_logging

    from tests.acceptance.load.locustfile import SuflerSuggestPipelineUser

    setup_logging("INFO", None)
    env = Environment(user_classes=[SuflerSuggestPipelineUser], events=events)
    env.create_local_runner()
    assert env.runner is not None

    env.runner.start(users, spawn_rate=spawn_rate)
    time.sleep(duration_s)
    env.runner.quit()

    # Give greenlets a moment to flush stats.
    time.sleep(0.5)
    entry = env.stats.get("sufler_suggest", "PIPELINE")
    if entry is None or entry.num_requests == 0:
        # Fallback: aggregate all.
        entry = env.stats.total

    # Locust stores response_times as {ms_bucket: count}; expand approx samples.
    samples: list[float] = []
    for bucket, count in entry.response_times.items():
        samples.extend([float(bucket)] * int(count))
    samples.sort()

    p50 = entry.get_response_time_percentile(0.50) or _percentile(samples, 50)
    p95 = entry.get_response_time_percentile(0.95) or _percentile(samples, 95)
    p99 = entry.get_response_time_percentile(0.99) or _percentile(samples, 99)

    return {
        "mode": "pipeline",
        "tool": "locust",
        "users": users,
        "duration_s": duration_s,
        "spawn_rate": spawn_rate,
        "seeded_chunks": seeded,
        "requests": entry.num_requests,
        "failures": entry.num_failures,
        "rps": round(entry.total_rps, 3),
        "latency_ms": {
            "min": entry.min_response_time or 0,
            "median": p50,
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "max": entry.max_response_time or 0,
            "avg": entry.avg_response_time or 0,
        },
        "target_p95_ms": TARGET_P95_MS,
        "pass": (p95 or 0) <= TARGET_P95_MS and entry.num_failures == 0,
    }


def run_locust_http(*, users: int, duration_s: int, spawn_rate: float, host: str) -> dict:
    os.environ["LOAD_MODE"] = "http"
    os.environ["SUFLER_BASE_URL"] = host
    _setup_django()

    from locust import events
    from locust.env import Environment
    from locust.log import setup_logging

    from tests.acceptance.load.locustfile import SuflerSuggestHttpUser

    setup_logging("INFO", None)
    SuflerSuggestHttpUser.host = host
    env = Environment(user_classes=[SuflerSuggestHttpUser], events=events, host=host)
    env.create_local_runner()
    assert env.runner is not None
    env.runner.start(users, spawn_rate=spawn_rate)
    time.sleep(duration_s)
    env.runner.quit()
    time.sleep(0.5)

    entry = env.stats.get("sufler_suggest", "POST") or env.stats.total
    p95 = entry.get_response_time_percentile(0.95) or 0
    p50 = entry.get_response_time_percentile(0.50) or 0
    p99 = entry.get_response_time_percentile(0.99) or 0
    return {
        "mode": "http",
        "tool": "locust",
        "host": host,
        "users": users,
        "duration_s": duration_s,
        "spawn_rate": spawn_rate,
        "seeded_chunks": 0,
        "requests": entry.num_requests,
        "failures": entry.num_failures,
        "rps": round(entry.total_rps, 3),
        "latency_ms": {
            "min": entry.min_response_time or 0,
            "median": p50,
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "max": entry.max_response_time or 0,
            "avg": entry.avg_response_time or 0,
        },
        "target_p95_ms": TARGET_P95_MS,
        "pass": (p95 or 0) <= TARGET_P95_MS and entry.num_failures == 0,
    }


def write_report(stats: dict) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lat = stats["latency_ms"]
    passed = bool(stats["pass"])
    verdict = "PASS" if passed else "FAIL"
    lines = [
        "# II.7.4 Sufler suggest load report",
        "",
        f"**Generated:** {now}  ",
        f"**Criterion:** 75 virtual operators · `sufler suggest` **p95 ≤ {TARGET_P95_MS} ms** "
        f"(FR-SUF-06 / SUF-T-08 / II.7.4)",
        "",
        "## Verdict",
        "",
        f"**{verdict}** — p95 = **{lat['p95']:.1f} ms** "
        f"(target ≤ {TARGET_P95_MS} ms); "
        f"requests = {stats['requests']}, failures = {stats['failures']}",
        "",
        "## Configuration",
        "",
        "| Parameter | Value |",
        "| --- | --- |",
        f"| Tool | {stats.get('tool', 'locust')} |",
        f"| Mode | {stats['mode']} |",
        f"| Virtual operators (VUs) | {stats['users']} |",
        f"| Duration | {stats['duration_s']} s |",
        f"| Spawn rate | {stats.get('spawn_rate', 'n/a')} |",
        f"| Host | {stats.get('host', 'in-process pipeline')} |",
        f"| Seeded KB chunks | {stats.get('seeded_chunks', 0)} |",
        "",
        "## Latency",
        "",
        "| Metric | ms |",
        "| --- | ---: |",
        f"| min | {lat['min']:.1f} |",
        f"| avg | {lat['avg']:.1f} |",
        f"| p50 | {lat['p50']:.1f} |",
        f"| **p95** | **{lat['p95']:.1f}** |",
        f"| p99 | {lat['p99']:.1f} |",
        f"| max | {lat['max']:.1f} |",
        f"| RPS | {stats['rps']} |",
        "",
        "## How to reproduce",
        "",
        "```powershell",
        "# CI / local pipeline (default):",
        r".\backend\.venv\Scripts\python.exe tests\acceptance\load\run_load.py --users 75 --duration 45",
        "",
        "# Locust UI / headless HTTP against running backend:",
        r"$env:LOAD_MODE='http'",
        r"$env:SUFLER_BASE_URL='http://127.0.0.1:8000'",
        r".\backend\.venv\Scripts\locust.exe -f tests\acceptance\load\locustfile.py SuflerSuggestHttpUser --headless -u 75 -r 25 -t 60s --host http://127.0.0.1:8000",
        "",
        "# k6 (if installed):",
        r"$env:SUFLER_BASE_URL='http://127.0.0.1:8000'",
        r"$env:SUFLER_LOAD_SESSIONID='<sessionid>'",
        "k6 run tests/acceptance/load/k6_suggest.js",
        "```",
        "",
        "## Notes",
        "",
        "- Pipeline mode measures `orchestrator.sufler.suggest` end-to-end "
        "(QU → RAG → stub LLM) — capacity of the suggest path used by the API.",
        "- HTTP mode includes Django/auth/network overhead; use on TEST/staging.",
        "- Stub LLM (`stub:sufler_cc`) is used unless ModelRegistry points at a real endpoint.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    STATS_PATH.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="II.7.4 sufler suggest load runner")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS)
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION_S)
    parser.add_argument("--spawn-rate", type=float, default=DEFAULT_SPAWN_RATE)
    parser.add_argument(
        "--http",
        action="store_true",
        help="HTTP Locust against SUFLER_BASE_URL instead of in-process pipeline",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SUFLER_BASE_URL", "http://127.0.0.1:8000"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))

    if args.http:
        stats = run_locust_http(
            users=args.users,
            duration_s=args.duration,
            spawn_rate=args.spawn_rate,
            host=args.host,
        )
    else:
        stats = run_locust_pipeline(
            users=args.users,
            duration_s=args.duration,
            spawn_rate=args.spawn_rate,
        )

    write_report(stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Wrote {REPORT_PATH}")
    return 0 if stats["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
