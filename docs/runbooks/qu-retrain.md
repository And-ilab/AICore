# QU retrain (FR-UND-08)

**Audience:** Администратор базы знаний LLM / ops  
**Goal:** Ensure Query Understanding retrains after KB index update (automatic chain or manual enqueue).  
**Spec:** FR-UND-08 · [backend/qu/README.md](../../backend/qu/README.md) · debounce **60s**

Related: [reindex.md](reindex.md) · [rollback-qu.md](rollback-qu.md)

## What “retrain” does today

Celery task `qu.qu_retrain`:

1. Accepts result of `ingest.reindex_kb` **or** kwargs `kb_id`, `reindex_job_id`, `content_version`.
2. Skips if reindex `outcome` is not one of `indexed` / `soft_deleted` / `hard_deleted`.
3. Returns contract JSON `{status, kb_id, reindex_job_id, content_version, trigger}`.

Classifier weights may be swapped in later (P1-33); **task name and payload stay stable**. Ops verify the **contract + preview/suggest**, not model files.

## Automatic path (default)

```text
SUZ webhook / reconcile
  → ingest.reindex_kb
  → countdown 60s (QU_RETRAIN_DEBOUNCE_SECONDS)
  → qu.qu_retrain
```

Also: Django signal `reindex.completed` → same enqueue with deterministic `task_id`  
`qu-retrain-<sha256…>` from `(kb_id, reindex_job_id, content_version)`.

**Admin action:** usually **none** after a successful reindex. Wait ≥60s, then verify.

---

## Prerequisites

1. Reindex finished successfully ([reindex.md](reindex.md)).
2. `celery-worker` running and connected to Redis.
3. Role able to call Hub QU preview (`qu.admin`) for verification.

```powershell
cd infra
docker compose exec celery-worker celery -A sufler inspect ping --timeout=10
```

**Pass:** response contains `pong`.

---

## Manual enqueue (when auto did not fire)

Use when Hub reindex did not chain QU, or you need a controlled retrain after fixing content.

### Option 1 — signal (recommended)

```powershell
cd infra
docker compose exec backend python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sufler.settings')
django.setup()
from qu.tasks import reindex_completed
reindex_completed.send(
    sender=None,
    kb_id='cc_production',
    reindex_job_id='ops-manual-001',
    content_version='ops-manual-001',
)
print('qu_retrain scheduled (+60s debounce)')
"
```

### Option 2 — call task directly (eager / debug)

```powershell
cd infra
docker compose exec backend python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sufler.settings')
django.setup()
from qu.tasks import qu_retrain
print(qu_retrain.apply(
    kwargs={
        'kb_id': 'cc_production',
        'reindex_job_id': 'ops-direct-001',
        'content_version': 'ops-direct-001',
        'trigger': 'ops.manual',
    }
).get())
"
```

Or via Celery async:

```powershell
cd infra
docker compose exec backend python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sufler.settings')
django.setup()
from qu.tasks import qu_retrain
async_result = qu_retrain.delay(
    kb_id='cc_production',
    reindex_job_id='ops-async-001',
    content_version='ops-async-001',
    trigger='ops.manual',
)
print(async_result.id)
print(async_result.get(timeout=120))
"
```

---

## Verify

### 1. Task result

In worker logs or `.get()` output:

```json
{
  "status": "completed",
  "kb_id": "cc_production",
  "reindex_job_id": "…",
  "content_version": "…",
  "trigger": "reindex.completed"
}
```

`status: skipped` means reindex outcome was not index/delete — fix reindex first.

### 2. Hub QU preview (FR-UND-12)

```powershell
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/admin/qu/preview/ `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"оформление отпуска сотруднику\",\"limit\":5}"
```

**Pass:** HTTP 200; `documents[]` with `relevance_percent`; `min_relevance` present; preferably `matched_example` when эталон exists.

UI: Hub → «Модуль понимания» → Preview (same API).

### 3. Operator suggest

```powershell
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/sufler/suggest `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"оформление отпуска\",\"limit\":3}"
```

**Pass:** HTTP 200, hints ranked, citations present.

### 4. Regression tests (optional on TEST)

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\test_qu_tasks.py tests\test_qu_preview.py -q
```

---

## Debounce / duplicates

- Same `(kb_id, reindex_job_id, content_version)` → same Celery `task_id` (correlation).
- Celery **does not** fully dedupe by task id alone; production lock (P3-02) merges bursts within 60s.
- **Ops rule:** do not spam manual enqueue for the same content version; wait for the scheduled run.

---

## Fail / escalate

| Symptom | Action |
| --- | --- |
| No `qu_retrain` after webhook | Check chain in logs; Redis; re-run [reindex.md](reindex.md) |
| Preview empty | Index empty — reindex; check `QuReferenceExample` for matched questions |
| Retrain `skipped` | Reindex outcome not searchable change — inspect ingest result |
| Bad relevance after retrain | See [rollback-qu.md](rollback-qu.md) |

## Journal

Record: timestamp, `reindex_job_id`, `content_version`, Celery task id, preview query used, pass/fail. Ties to FR-UND-15 training journal.
