# Rollback QU / KB after bad retrain (FR-UND-08 / FR-UND-15)

**Audience:** Администратор базы знаний LLM + ops  
**Goal:** Restore usable подсказки / QU after a bad index or training iteration without waiting for developers.  
**Spec:** FR-UND-08 (auto retrain) · FR-UND-15 (журнал и откат выборки) · UC-UND-01

Related: [reindex.md](reindex.md) · [qu-retrain.md](qu-retrain.md)

## Decision guide

| Symptom | Prefer |
| --- | --- |
| One bad SUZ article in index | Soft-delete / republish correct version in СУЗ → webhook (Path 1) |
| Wrong эталоны QU (examples) | Deactivate bad `QuReferenceExample` rows (Path 2) |
| Whole index / preview broken after batch | Restore DB snapshot of `ingest_*` + `qu_*` (Path 3) |
| Need previous “training iteration” | Path 2 + reindex + retrain; full version UI is FR-UND-15 (see note below) |

> **Implementation note:** versioned training-journal UI (FR-UND-15) is specified in ТЗ; current runtime stores active `QuReferenceExample` and `CCProductionChunk`. Until the journal UI ships, ops rollback = **content + example flags + optional DB restore**, then reindex/retrain.

---

## Prerequisites

1. Incident window agreed with КЦ (operators may see temporary empty hints).
2. Recent backup of PostgreSQL (TEST/PROD procedure from ДИТ) **before** destructive steps.
3. Access: Compose/`psql`, or Django shell; KB admin role for Hub APIs.
4. Know last **good** SUZ `version_id` / article set and approximate time of last good suggest.

```powershell
cd infra
docker compose ps postgres backend celery-worker
```

---

## Path 1 — Fix source content (preferred, no DB restore)

1. In **СУЗ (Bitrix)** unpublish or correct the bad article; publish known-good version.
2. Confirm webhook or run reconcile:

```powershell
curl -s -X POST http://127.0.0.1:8000/api/v1/knowledge/reconcile/run/
```

3. Wait for `ingest.reindex_kb` + 60s + `qu.qu_retrain` ([qu-retrain.md](qu-retrain.md)).
4. Verify suggest + preview (steps below).

**Pass:** bad title/snippet gone from hints; relevance back to expected articles.

---

## Path 2 — Roll back QU examples (эталоны)

Bad matched questions pollute preview explanations and may skew ops judgment.

### 2.1 List recent examples

```powershell
cd infra
docker compose exec backend python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','sufler.settings')
django.setup()
from qu.models import QuReferenceExample
for e in QuReferenceExample.objects.order_by('-id')[:20]:
    print(e.id, e.is_active, e.article_id, e.question[:80])
"
```

### 2.2 Deactivate bad rows (soft rollback)

```powershell
cd infra
docker compose exec backend python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','sufler.settings')
django.setup()
from qu.models import QuReferenceExample
ids = [/* paste ids */]
n = QuReferenceExample.objects.filter(id__in=ids).update(is_active=False)
print('deactivated', n)
"
```

### 2.3 Re-run QU contract

Enqueue retrain after documenting the change:

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
    reindex_job_id='rollback-examples-001',
    content_version='rollback-examples-001',
)
print('retrain scheduled')
"
```

### 2.4 Optional — restore specific examples

Set `is_active=True` for previously good ids (from journal / backup CSV).

**Pass:** preview no longer returns the bad `matched_example`; suggest still returns KB citations.

---

## Path 3 — Database restore (last resort)

Use when chunks/embeddings are corrupted or mass-wrong.

1. **Stop writers** (brief):

```powershell
cd infra
docker compose stop celery-worker
# keep backend read-only if possible; or stop backend too during restore
```

2. Restore PostgreSQL from last known-good dump (**ДИТ procedure**).  
   Minimum tables if doing surgical restore (coordinate with DBA):

   - `ingest_ccproductionchunk` (and related ingest event tables)
   - `qu_qureferenceexample`
   - Hub KB tables if Hub path was used (`hub_contactcenterknowledgebase`, documents)

3. Start workers:

```powershell
docker compose start celery-worker backend
```

4. **Do not** blindly reindex from current bad СУЗ until content is fixed — otherwise you re-poison the index.
5. After content is fixed in СУЗ, run [reindex.md](reindex.md) Path A, then verify.

**Pass:** chunk counts match pre-incident journal; suggest smoke OK.

---

## Verify (all paths)

### Suggest

```powershell
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/sufler/suggest `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"<known-good query from journal>\",\"limit\":3}"
```

| Check | Expected |
| --- | --- |
| HTTP | 200 |
| `kb_id` | `cc_production` |
| hints | ≥1; citation title matches good article |
| latency | within SLO (p95 ≤2s on TEST smoke) |

### QU preview

```powershell
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/admin/qu/preview/ `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"<same query>\",\"limit\":5}"
```

**Pass:** top document is the expected article; `meets_min_relevance` true for #1 when content is good.

### Acceptance smoke (optional)

```powershell
.\backend\.venv\Scripts\python.exe -m pytest `
  tests\acceptance\test_suf_t.py::SufTSmokeAcceptanceTest::test_suf_t_01_telephony_hints_after_client_utterance -q
```

---

## After rollback

1. File incident: time detected, path used (1/2/3), ids deactivated / backup label.
2. Block further auto-enrichment (`FR-UND-09` policy) until Администратор БЗ reviews queue — _TBD Hub setting_.
3. If SUZ remains wrong, leave reconcile paused (`SUZ_RECONCILE_ENABLED=false`) until editors finish — then re-enable and run [reindex.md](reindex.md).

## Fail / escalate to Исполнитель

- Restore fails integrity checks / migrations mismatch  
- Need classifier artifact rollback beyond current `qu_retrain` contract  
- Cross-KB contamination (`assistant_*` vs `cc_production`)

Attach: Celery task ids, `reindex_job_id`, sample suggest JSON, PostgreSQL backup id.
