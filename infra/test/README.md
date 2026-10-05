# Bank TEST — prod-like Compose

Separate from local `infra/docker-compose.yml` (dev hot-reload, published DB ports).

| | Dev (`infra/docker-compose.yml`) | TEST (`docker-compose.prod-like.yml`) |
| --- | --- | --- |
| Project name | `sufler` | `sufler-test` |
| Backend | `runserver` | Daphne ASGI + migrate + collectstatic |
| Frontend | Vite + source mounts | nginx static (`Dockerfile.prod`) |
| Data ports | postgres/redis/minio on host | **internal only** |
| Secrets | `infra/.env` | `infra/test/.env` (never committed) |

## Deploy

Ops runbook (CI + manual, rollback, verify, FAQ): [`docs/runbooks/deploy-test.md`](../../docs/runbooks/deploy-test.md)

```bash
cd infra/test
cp .env.example .env
# fill POSTGRES_PASSWORD, MINIO_*, DJANGO_SECRET_KEY, LDAP/SUZ/Oktell/KUMA from vault
chmod +x deploy.sh gen-self-signed-cert.sh
./gen-self-signed-cert.sh ai-hub-test.bank.local   # or localhost — self-signed OK for lab
./deploy.sh config   # validate Compose + TLS files present
./deploy.sh          # build + up -d
./deploy.sh ps
./deploy.sh logs
```

**Public URL is HTTPS only:** <https://localhost/> (or your FQDN).  
Plain HTTP on `:80` returns **301** to HTTPS. App routes (`/api`, `/ws`, `/health/`, `/metrics/`) are proxied to **Daphne** (`backend:8000`).

```bash
curl -kI http://localhost/health/          # → 301 https://…
curl -k https://localhost/health/          # → 200 JSON (db+redis)
curl -k https://localhost/metrics/         # → Prometheus text
./deploy.sh nginx-test                     # nginx -t
```

## Edge TLS (nginx)

Config: [`nginx.conf`](./nginx.conf) · Compose service: `edge` · Certs: [`certs/`](./certs/)

| Path | Upstream |
| --- | --- |
| `/health/`, `/metrics/`, `/api/`, `/ws`, `/admin/`, … | **Daphne** `backend:8000` |
| `/`, `/static/` | SPA `frontend:80` |
| `http://` any | **301** → `https://` |

### Certificate instructions

**Self-signed (dev / lab OK):**

```bash
cd infra/test
./gen-self-signed-cert.sh                  # CN=localhost
./gen-self-signed-cert.sh ai-hub-test.bank.local
# writes certs/fullchain.pem + certs/privkey.pem (gitignored)
```

**Bank / ДИТ CA (TEST VM):** place the issued chain and key at the same paths:

- `infra/test/certs/fullchain.pem`
- `infra/test/certs/privkey.pem` (mode `600`)

Never commit private keys. Rotate per bank policy; replace files and `docker compose … restart edge`.

`./deploy.sh up` refuses to start without both PEM files.

## Application health (TEST)

Application tier: **Django + Daphne (ASGI/Channels) + Celery**.

| Check | URL | Expect |
| --- | --- | --- |
| App health | **`GET https://<host>/health/`** | **HTTP 200**, JSON `checks.database` + `checks.redis` = `ok` |
| Metrics | **`GET https://<host>/metrics/`** | Prometheus text; `sufler_health_ok 1` |
| HTTP→HTTPS | `GET http://<host>/…` | **301** to `https://` |
| Edge liveness | `GET http://<host>/healthz` | plain `ok` (redirect server only) |
| Legacy smoke | `GET https://<host>/client-info/` | HTTP 200 |
| WebSocket | `wss://<host>/ws/sufler/<call_id>/` | Daphne + Channels (`ping` → `pong`) |

```bash
# Via edge TLS (prod-like TEST)
curl -k -sS "https://localhost/health/"
# Behind bank FQDN (ДИТ cert)
curl -sS "https://ai-hub-test.bank.local/health/"
```

Example body:

```json
{
  "status": "ok",
  "checks": {
    "database": {"status": "ok"},
    "redis": {"status": "ok", "host": "redis", "port": 6379}
  },
  "service": "sufler-backend",
  "asgi": "daphne",
  "channel_layer": "RedisChannelLayer"
}
```

Compose backend healthcheck uses `http://127.0.0.1:8000/health/` inside the container.

## Observability (metrics + alerts + logs)

Baseline for TEST ops: scrape **`/metrics/`**, alert when health would fail, aggregate structured logs.

| Artifact | Path |
| --- | --- |
| Ops guide (metrics + logging aggregation) | [`observability/README.md`](./observability/README.md) |
| Prometheus scrape stub | [`observability/prometheus-scrape.yml`](./observability/prometheus-scrape.yml) |
| Alert rules (`SuflerTestHealthFail`) | [`observability/prometheus-alerts.yml`](./observability/prometheus-alerts.yml) |

```bash
curl -k -sS https://localhost/metrics/ | grep sufler_health_ok
# Load alert stub into bank Prometheus; until then:
curl -kf -sS -o /dev/null https://localhost/health/ || echo "ALERT: /health/ fail"
```

## Data tier (PostgreSQL + pgvector)

Stack service `postgres` uses image `pgvector/pgvector:pg16`. Extension `vector` is
created on first volume init (`infra/postgres/init.sql`) and again by Django
migrations (`ingest.0001` / `ingest.0003`).

| Step | Command |
| --- | --- |
| Migrate + ensure HNSW + verify backend | `./deploy.sh db-verify` or `./verify-data-tier.sh` |
| SQL only (idempotent) | `./verify-data-tier.sh --sql-only` |
| Backup stub (dry-run) | `./deploy.sh backup-stub` or `./backup-postgres.sh --dry-run` |
| Backup stub (real dump) | `./backup-postgres.sh` → `infra/test/backups/*.sql.gz` |

Expected indexes on `cc_production`:

- `cc_prod_embedding_hnsw_idx` — HNSW / `vector_cosine_ops`
- `cc_prod_article_active_idx` — `(article_id, is_active)`

Backend probe (from container):

```bash
docker compose -p sufler-test exec backend python manage.py verify_data_tier
# connection: ok (postgresql)
# pgvector: ok
# index: cc_prod_embedding_hnsw_idx ok
```

SQL source: [`sql/ensure_pgvector.sql`](./sql/ensure_pgvector.sql).

## Support tier (Redis + MinIO + Celery)

Async jobs (OCR, ingest, reindex) use **Redis** as Celery broker and **MinIO**
for OCR object storage (`MINIO_OCR_BUCKET`, default `sufler-ocr`).

| Check | Command |
| --- | --- |
| Full (broker + worker task + MinIO put/get) | `./deploy.sh support-verify` |
| Broker + MinIO only | `./verify-support-services.sh --broker-only` |
| From backend container | `python manage.py verify_support_services` |

Expected:

```text
OK: redis-cli PONG
OK: minio /minio/health/live
OK: celery inspect pong
redis broker: ok (redis:6379)
celery worker: ok (sufler.ping → pong)
object store: ok (MinioObjectStore, bucket=sufler-ocr, …)
verify_support_services: OK
```

Compose sets `OCR_OBJECT_STORE_BACKEND=minio` on `backend` and `celery-worker`.

## AI inference tier (ASR + LLM gateway, profile=test)

ModelRegistry **`deployment_profiles.test`**: approved_dev stubs by default
(`ASR_MODE=stub`, LLM `gateway_mode: stub`). **GPU not required**.

| Check | Command |
| --- | --- |
| Full (ASR health + LLM chat + suggest smoke) | `./deploy.sh inference-verify` |
| Management command | `python manage.py verify_inference_tier` |
| ASR only | `curl http://asr:8764/health` (inside network) |

```text
deployment profile: test (status=approved_dev, gpu_required=False)
LLM sufler_cc / assistant_bank / docs_ocr: ok (mode=stub, …)
ASR: ok (mode=stub, profile=test)
suggest smoke: ok
verify_inference_tier: OK
```

To use the Vosk approved_dev candidate on a GPU/CPU host: set `ASR_MODE=vosk`,
mount weights, and optionally add Compose `device_requests` for NVIDIA.

### CPU LLM + embeddings (Linux server)

Compose profile **`cpu-inference`**: services `ollama` (official image) and
`embedding` (E5-large). No GPU. Details: [`../local-inference/README.md`](../local-inference/README.md).

Manual on the VM:

```bash
./deploy.sh up --cpu-inference
docker compose --profile cpu-inference exec ollama ollama pull qwen2.5:3b
./deploy.sh cpu-verify
```

This sets `MODEL_GATEWAY_MODE=openai`, `OPENAI_BASE_URL=http://ollama:11434/v1`,
`OPENAI_MODEL=qwen2.5:3b`, `OLLAMA_BASE_URL=http://ollama:11434`,
`EMBEDDING_MODE=http`, `EMBEDDING_BASE_URL=http://embedding:8090`.

Env: `AI_INFERENCE_PROFILE=test` (default on TEST compose).

## Cutover — SUZ / Oktell / AD (before customer demo)

Ordered steps, feature flags, INT-T smoke subset:

- Checklist: [`cutover-checklist.md`](./cutover-checklist.md)
- Results log: [`cutover-int-t-results.md`](./cutover-int-t-results.md)

```bash
# After Phases 0–3 flags are set for available bank endpoints:
pytest -v tests/acceptance/test_int_t.py
# Record outcomes in cutover-int-t-results.md

# Formal SUF-T + CHAT-T smoke (customer URL evidence):
pytest -v \
  tests/acceptance/test_suf_t.py::SufTSmokeAcceptanceTest \
  tests/acceptance/test_chat_t.py::ChatTSmokeAcceptanceTest
# → tests/acceptance/test_env_results.md
```

## CI deploy (GitHub Actions)

**Ops runbook (deploy / rollback / verify / FAQ):** [`docs/runbooks/deploy-test.md`](../../docs/runbooks/deploy-test.md)

Automated build → registry → SSH `pull-up`:

- Workflow: [`.github/workflows/deploy-test.yml`](../../.github/workflows/deploy-test.yml)
- Secrets checklist + dry-run: [`github-actions-deploy.md`](./github-actions-deploy.md)

```text
Actions → Deploy TEST → Run workflow → dry_run=true   # build only
git tag test-v0.1.0 && git push origin test-v0.1.0    # full deploy
```

## Secrets

- Template only: [`.env.example`](./.env.example)
- Runtime: `.env` (gitignored via root `.gitignore` pattern `.env`)
- `deploy.sh` refuses empty/`replace-*` placeholders for required keys
- GitHub Actions secrets for SSH/registry: [`github-actions-deploy.md`](./github-actions-deploy.md) (not app `.env`)

Do **not** commit `.env`, vault exports, or TLS private keys.

## Topology

```
browser → edge:443 (TLS nginx)  ·  edge:80 → 301 HTTPS
            ├─ /health/, /api/, /ws, /admin/…  → backend:8000 (Daphne)
            ├─ /static/, /                     → frontend:80 (SPA)
backend → asr:8764/8765 (stub ASR) · ModelGateway (stub LLM, profile=test)
backend / celery-worker / asr → postgres · redis · minio  (internal network)
```

## Validate without full deploy

```bash
cp .env.example .env   # then set real-looking non-placeholder secrets for dry-run
./deploy.sh config
# or:
docker compose -p sufler-test --env-file .env -f docker-compose.prod-like.yml config --quiet
```

## Related

- **Ops runbook:** [`docs/runbooks/deploy-test.md`](../../docs/runbooks/deploy-test.md) — deploy, rollback, verify, common failures
- VM sizing / BelVPN: [`server-requirements.md`](./server-requirements.md)
- BelVPN / ДИТ access ticket template: [`docs/development/vpn-request-template.md`](../../docs/development/vpn-request-template.md)
- Local dev Compose: [`../docker-compose.yml`](../docker-compose.yml)
- Infra overview: [`../README.md`](../README.md)
