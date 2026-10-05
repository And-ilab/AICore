# II.7.4 Sufler suggest load report

**Generated:** 2026-07-27 12:10:57Z  
**Criterion:** 75 virtual operators · `sufler suggest` **p95 ≤ 2000 ms** (FR-SUF-06 / SUF-T-08 / II.7.4)

## Verdict

**PASS** — p95 = **120.0 ms** (target ≤ 2000 ms); requests = 1050, failures = 0

## Configuration

| Parameter | Value |
| --- | --- |
| Tool | locust |
| Mode | pipeline |
| Virtual operators (VUs) | 75 |
| Duration | 45 s |
| Spawn rate | 25.0 |
| Host | in-process pipeline |
| Seeded KB chunks | 0 |

## Latency

| Metric | ms |
| --- | ---: |
| min | 21.1 |
| avg | 53.6 |
| p50 | 27.0 |
| **p95** | **120.0** |
| p99 | 170.0 |
| max | 266.9 |
| RPS | 18.389 |

## How to reproduce

```powershell
# CI / local pipeline (default):
.\backend\.venv\Scripts\python.exe tests\acceptance\load\run_load.py --users 75 --duration 45

# Locust UI / headless HTTP against running backend:
$env:LOAD_MODE='http'
$env:SUFLER_BASE_URL='http://127.0.0.1:8000'
.\backend\.venv\Scripts\locust.exe -f tests\acceptance\load\locustfile.py SuflerSuggestHttpUser --headless -u 75 -r 25 -t 60s --host http://127.0.0.1:8000

# k6 (if installed):
$env:SUFLER_BASE_URL='http://127.0.0.1:8000'
$env:SUFLER_LOAD_SESSIONID='<sessionid>'
k6 run tests/acceptance/load/k6_suggest.js
```

## Notes

- Pipeline mode measures `orchestrator.sufler.suggest` end-to-end (QU → RAG → stub LLM) — capacity of the suggest path used by the API.
- HTTP mode includes Django/auth/network overhead; use on TEST/staging.
- Stub LLM (`stub:sufler_cc`) is used unless ModelRegistry points at a real endpoint.
