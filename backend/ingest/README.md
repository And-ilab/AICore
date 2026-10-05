# SUZ → RAG ingest

`ingest` receives the Model B webhook defined in
`docs/integration/suz-bitrix-rag/tz-bitrix-rag-sufler.md`.

## Endpoint

```text
POST /api/v1/knowledge/events
Content-Type: application/json
X-Sufler-Event-Id: <event_id>
X-Sufler-Signature: HMAC-SHA256(raw_body, shared_secret)
```

### Env (cutover)

| Variable | Mock (local) | Prod / TEST |
| --- | --- | --- |
| `SUZ_INGEST_MODE` | `mock` | `prod` |
| `SUZ_WEBHOOK_HMAC_SECRET` | optional | **required** |
| `SUZ_ALLOWED_IBLOCK_IDS` | empty | Bitrix KC iblock id(s) |
| `BITRIX_REST_BASE_URL` | empty → mock `/changes` | Bitrix host |
| `BITRIX_SERVICE_TOKEN` | — | Bearer for INT-09 |
| `BITRIX_CHANGES_PATH` | `/local/api/sufler/v1/changes` | same |
| `SUZ_RECONCILE_ENABLED` | `true` for local INT-09 | `true` on TEST/PROD |

Documented for TEST cutover in [`infra/test/.env.example`](../../infra/test/.env.example).
Local defaults: [`infra/.env.example`](../../infra/.env.example).

An empty HMAC secret disables signature checks **only** when `SUZ_INGEST_MODE=mock`.

Responses follow INT-07:

- `202 {"status":"accepted","outcome":"queued", ...}` when the event is queued;
- `400 {"error":"validation","fields":[...]}` for invalid input;
- `401 {"error":"auth"}` for an invalid HMAC;
- `503 {"error":"temporary"}` when the Redis broker is unavailable;
- `503 {"error":"misconfigured"}` when `prod` mode has no HMAC secret.

Repeated `event_id` values are accepted by the broker but resolved
idempotently by the worker.

## INT-09 reconciliation (Model B polling fallback)

```text
GET  /api/v1/knowledge/reconcile/
POST /api/v1/knowledge/reconcile/run/
POST /api/v1/knowledge/reconcile/run/?async=1
```

Celery task: `ingest.reconcile_suz_changes` — polls Bitrix
`GET {BITRIX_CHANGES_PATH}?since={cursor}&limit=` and enqueues each event
through the same pipeline as the webhook (full body in payload, no GET article).

## INT-01..05 pipeline

1. Validate the full SUZ payload and checksum.
2. Enqueue the Celery chain `ingest.reindex_kb -> qu.qu_retrain`.
3. Normalize whitespace in `body_plain`.
4. Split text using frozen `kb_cc_production` settings from ModelRegistry
   (currently 512 tokens with 100-token overlap).
5. Produce deterministic 1024-dimensional dev embeddings.
6. Upsert chunks into the PostgreSQL `cc_production` table. Its `embedding`
   column is `pgvector` and has a cosine HNSW index.
7. Run `qu_retrain` only after `reindex_kb` commits successfully.

The event mapping is:

- **INT-01:** publish and index a current KC article;
- **INT-02:** record a draft without changing production;
- **INT-03:** soft-delete an unpublished article;
- **INT-04:** hard-delete all article vectors;
- **INT-05:** replace the previous article version without duplicate chunks.

## Verification

```powershell
.\backend\.venv\Scripts\python.exe backend\manage.py migrate
.\backend\.venv\Scripts\python.exe -m pytest tests\test_ingest_webhook.py tests\test_suz_reconcile.py -v
```

Ops (FR-UND-08): [reindex](../../docs/runbooks/reindex.md) · [qu-retrain](../../docs/runbooks/qu-retrain.md) · [rollback-qu](../../docs/runbooks/rollback-qu.md).
