# II.7.4 load tests — sufler suggest (75 VUs, p95 ≤ 2 s)

| File | Purpose |
| --- | --- |
| `run_load.py` | CI/manual runner → writes `report.md` |
| `locustfile.py` | Locust users (pipeline + HTTP) |
| `k6_suggest.js` | k6 script (ops hosts with k6) |
| `report.md` | Latest p95 vs 2 s target |
| `requirements.txt` | `locust` |

## Quick start (CI / local)

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r tests\acceptance\load\requirements.txt
.\backend\.venv\Scripts\python.exe tests\acceptance\load\run_load.py --users 75 --duration 45
```

Open [`report.md`](report.md) for verdict.

## HTTP against running backend

```powershell
$env:LOAD_MODE = "http"
$env:SUFLER_BASE_URL = "http://127.0.0.1:8000"
$env:SUFLER_LOAD_USERNAME = "dev-role-04"
$env:SUFLER_LOAD_PASSWORD = "dev-only-password"
.\backend\.venv\Scripts\python.exe tests\acceptance\load\run_load.py --http --users 75 --duration 60
```
