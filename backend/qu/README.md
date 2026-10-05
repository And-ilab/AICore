# QU automatic retraining

This package defines the FR-UND-08 Celery chain between incremental indexing
and Query Understanding retraining:

```text
ingest.reindex_kb -> qu.qu_retrain
```

## Event contract

Batch and manual reindex implementations can emit the Django signal after the
new index version has been committed and is searchable:

```python
from qu.tasks import reindex_completed

reindex_completed.send(
    sender=MyReindexTask,
    kb_id="cc_production",
    reindex_job_id="reindex-20260720-001",
    content_version="suz-version-42",
)
```

Required fields:

- `kb_id` — logical KB/index ID;
- `reindex_job_id` — unique indexing job ID;
- `content_version` — committed content/index version.

The receiver validates the payload and enqueues:

```text
reindex.completed
  -> 60 second debounce countdown
  -> qu.qu_retrain
```

The same three fields produce a deterministic Celery `task_id` for
correlation. Reusing a Celery task ID does not itself prevent duplicate
execution. P3-02 must add a Redis/database lock and merge duplicate updates
for the same KB/version during the debounce window.

## Task result

`qu_retrain` currently validates and completes the task contract:

```json
{
  "status": "completed",
  "kb_id": "cc_production",
  "reindex_job_id": "reindex-20260720-001",
  "content_version": "suz-version-42",
  "trigger": "reindex.completed"
}
```

The task is the registered execution boundary for P1-33. The classifier
adapter can replace its current contract body while preserving the task name
and payload.

## Admin Preview (FR-UND-12)

`POST /api/admin/qu/preview/` accepts a non-empty `query` and optional `limit`
(1–5). The endpoint requires `qu.admin`, ranks active `cc_production`
documents, and returns both `relevance_score`/`relevance_percent` and the
matched active `QuReferenceExample`.

The Hub screen «Модуль понимания» displays the ranked document, percentage,
configured minimum relevance threshold, and matched source question. Preview
is read-only and does not publish settings or require a code deployment.

## Test

```powershell
.\backend\.venv\Scripts\python.exe -m pytest `
  .\tests\test_qu_tasks.py .\tests\test_qu_preview.py -v
```

The tests verify the signal contract and run an eager end-to-end webhook with
a fake article, asserting that the index is committed before `qu_retrain`
starts.

## Ops runbooks

- [Reindex](../../docs/runbooks/reindex.md)
- [QU retrain](../../docs/runbooks/qu-retrain.md)
- [Rollback QU](../../docs/runbooks/rollback-qu.md)
