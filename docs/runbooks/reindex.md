# KB reindex (FR-UND-08)

**Audience:** Администратор базы знаний LLM / ops on TEST·PROD  
**Goal:** Rebuild searchable index `cc_production` (or Hub KB) after SUZ/content change, then let QU retrain enqueue automatically.  
**Spec:** [tz-unified-v1.4 §FR-UND-08](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) · [ingest/README](../../backend/ingest/README.md) · [qu/README](../../backend/qu/README.md)

Related runbooks: [qu-retrain.md](qu-retrain.md) · [rollback-qu.md](rollback-qu.md)

## When to run

| Trigger | Action |
| --- | --- |
| SUZ article published/changed/deleted (INT-01…05) | **Automatic** via webhook → Celery chain (preferred) |
| Webhook missed / batch load / ETL FAQ | Manual reconcile or Hub «Reindex» |
| Admin uploaded/deleted document in Hub KB | Hub `POST …/reindex/` |
| Index looks stale vs СУЗ | This runbook |

## Prerequisites

1. Stack up: PostgreSQL (+ pgvector), Redis, backend, **celery-worker**.
2. Role with `kb.admin` (Hub KB) or ops access to Compose / Celery.
3. Know which path you need:
   - **A — SUZ → `cc_production`** (runtime суфлёр / RAG КЦ)
   - **B — Hub admin KB** (`/api/admin/kb/<id>/reindex/`)

```powershell
cd infra
docker compose ps backend celery-worker postgres redis
```

**Pass:** `backend` and `celery-worker` healthy; Redis `PONG`.

---

## Path A — SUZ incremental reindex (preferred)

### A1. Confirm ingest mode

| Env | Expected |
| --- | --- |
| `SUZ_INGEST_MODE` | `mock` (local) or `prod` (TEST/PROD) |
| `SUZ_WEBHOOK_HMAC_SECRET` | set when mode=`prod` |
| Celery broker | `CELERY_BROKER_URL` → Redis |

### A2. Trigger one event (or reconcile)

**Webhook (normal):** СУЗ sends `POST /api/v1/knowledge/events` → chain  
`ingest.reindex_kb` → (60s debounce) → `qu.qu_retrain`.

**Missed events — INT-09 reconcile:**

```powershell
cd infra
# Status / cursor
curl -s http://127.0.0.1:8000/api/v1/knowledge/reconcile/

# Run now (sync)
curl -s -X POST http://127.0.0.1:8000/api/v1/knowledge/reconcile/run/

# Or async Celery
curl -s -X POST "http://127.0.0.1:8000/api/v1/knowledge/reconcile/run/?async=1"
```

On prod, `SUZ_RECONCILE_ENABLED=true` is required or you get HTTP 403.

### A3. Watch Celery

```powershell
cd infra
docker compose logs -f celery-worker
```

Look for task names:

- `ingest.reindex_kb`
- `qu.qu_retrain` (≈60s after reindex — `QU_RETRAIN_DEBOUNCE_SECONDS`)

### A4. Verify index

```powershell
cd infra
docker compose exec backend python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','sufler.settings')
django.setup()
from ingest.models import CCProductionChunk
n = CCProductionChunk.objects.filter(is_active=True).count()
print('active_chunks', n)
print('sample', list(CCProductionChunk.objects.filter(is_active=True).values_list('article_id','title')[:5]))
"
```

**Suggest smoke** (operator session / mock role with sufler permission):

```powershell
# After login cookie or force_login in shell — example body:
curl -s -X POST http://127.0.0.1:8000/api/v1/sufler/suggest `
  -H "Content-Type: application/json" `
  -b cookies.txt `
  -d "{\"text\":\"как оформить дебетовую карту\",\"limit\":3}"
```

**Pass criteria**

| Check | Expected |
| --- | --- |
| `reindex_kb` | result `outcome` in `indexed` / `soft_deleted` / `hard_deleted` |
| Chunks | `active_chunks` > 0 for published content |
| Suggest | HTTP 200, `kb_id=cc_production`, ≥1 hint with citation |
| QU | `qu.qu_retrain` status `completed` (see [qu-retrain.md](qu-retrain.md)) |

---

## Path B — Hub admin KB reindex

For documents uploaded in Hub → «Базы знаний КЦ» (not the live SUZ webhook path).

1. Login as KB admin (`llm_knowledge_base_administrator` / `dev-role-02` in mock).
2. List KBs:

```powershell
curl -s -b cookies.txt http://127.0.0.1:8000/api/admin/kb/
```

3. Reindex:

```powershell
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/admin/kb/<kb_id>/reindex/
```

**Pass:** HTTP 200, JSON `status` = `ready`, `last_reindexed_at` set, documents `indexed`.

4. Optional — emit FR-UND-08 signal so QU retrain runs (if not already chained):

```powershell
cd infra
docker compose exec backend python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','sufler.settings')
django.setup()
from qu.tasks import reindex_completed
reindex_completed.send(
    sender=None,
    kb_id='cc_production',
    reindex_job_id='manual-hub-reindex-001',
    content_version='hub-manual',
)
print('enqueued')
"
```

Then follow [qu-retrain.md](qu-retrain.md) verify steps.

---

## Fail / escalate

| Symptom | What to do |
| --- | --- |
| Celery not consuming | `docker compose restart celery-worker`; check Redis |
| `503 temporary` on webhook | Broker down — fix Redis, retry event |
| `401 auth` on webhook | Check `X-Sufler-Signature` / HMAC secret |
| Hub KB `status=error` | Read `status_message`; fix document text; reindex again |
| Suggest empty after reindex | Confirm article in `CCProductionChunk`; wait for embeddings; see [rollback-qu.md](rollback-qu.md) |

**Do not** run `docker compose down -v` on TEST/PROD (destroys volumes).

## Record in journal

Note: time, `reindex_job_id` / `event_id`, chunk count before/after, Celery task ids, operator who approved. Required for FR-UND-15 / UC-UND-01 audit trail.
