# Deploy TEST (P10-03 companion)

**Audience:** Ops / ДИТ on the bank TEST VM  
**Goal:** Deploy, verify, and roll back the prod-like TEST stack safely.  
**Customer URL:** `https://ai-hub-test.bank.local/` (lab: `https://localhost/`)

| Related | Path |
| --- | --- |
| Compose + `deploy.sh` | [`infra/test/README.md`](../../infra/test/README.md) |
| CI secrets / dry-run (P10-03) | [`infra/test/github-actions-deploy.md`](../../infra/test/github-actions-deploy.md) |
| Workflow | [`.github/workflows/deploy-test.yml`](../../.github/workflows/deploy-test.yml) |
| Observability | [`infra/test/observability/README.md`](../../infra/test/observability/README.md) |
| Cutover / INT-T | [`infra/test/cutover-checklist.md`](../../infra/test/cutover-checklist.md) |

---

## Prerequisites

1. BelVPN / jump access to the TEST VM; Docker Engine + Compose v2.
2. Repo checkout on VM (typical: `/opt/sufler` = `TEST_DEPLOY_PATH`).
3. `infra/test/.env` filled from vault (never in GitHub secrets). Required non-placeholder: `POSTGRES_PASSWORD`, `MINIO_ROOT_*`, `DJANGO_SECRET_KEY`.
4. TLS PEMs present: `infra/test/certs/fullchain.pem` + `privkey.pem` (`./gen-self-signed-cert.sh` for lab).
5. For CI path: GitHub secrets from [github-actions-deploy.md](../../infra/test/github-actions-deploy.md).

```bash
cd /opt/sufler/infra/test   # or your TEST_DEPLOY_PATH
./deploy.sh config          # Compose + certs OK
./deploy.sh ps              # optional: current stack
```

**Pass:** `config` prints OK; no placeholder-secret errors.

---

## Deploy

### Path A — CI/CD (preferred on bank TEST)

Companion to **P10-03**: build → registry → SSH `pull-up`.

#### A1. Dry-run (no push, no SSH)

Actions → **Deploy TEST** → Run workflow → **`dry_run = true`**.

**Pass:** backend + frontend images build on the runner; secrets checklist printed (names only).

#### A2. Full deploy

| Trigger | Tag / input |
| --- | --- |
| Manual | Actions → dry_run=`false`, optional `image_tag` |
| Tag push | `git tag test-vX.Y.Z && git push origin test-vX.Y.Z` (also `v*`) |

Pipeline:

1. Build `backend/Dockerfile` + `frontend/Dockerfile.prod`
2. Push `…/backend:<tag>` and `…/frontend:<tag>`
3. SSH → `cd $TEST_DEPLOY_PATH/infra/test && ./deploy.sh pull-up`

On the VM, `pull-up` writes `BACKEND_IMAGE` / `FRONTEND_IMAGE` into `.env`, logs into the registry if credentials are set, `docker compose pull`, then `up -d --no-build`.

**Pass:** workflow green; on VM `./deploy.sh ps` shows `backend`, `celery-worker`, `frontend`, `edge`, data services healthy.

#### A3. Record the image tag

Note the deployed tag (Actions output or `.env` `BACKEND_IMAGE=…`) for rollback.

---

### Path B — Manual on the TEST VM

Use when CI is unreachable or for first bring-up / local image build.

```bash
cd /opt/sufler/infra/test
cp -n .env.example .env    # first time only; fill vault secrets
./gen-self-signed-cert.sh ai-hub-test.bank.local   # if certs missing
./deploy.sh config
./deploy.sh                # = up --build -d
```

**Registry pull without CI** (images already pushed):

```bash
export BACKEND_IMAGE=ghcr.io/<org>/<repo>/backend:<known-good-tag>
export FRONTEND_IMAGE=ghcr.io/<org>/<repo>/frontend:<known-good-tag>
# optional: REGISTRY_HOST, REGISTRY_USERNAME, REGISTRY_PASSWORD
./deploy.sh pull-up
```

**Pass:** same as A2; then run [Verify](#verify).

---

## Verify

Run from `infra/test` on the VM (or via BelVPN to the FQDN). Prefer HTTPS through edge.

### 1. Edge + app health

```bash
./deploy.sh nginx-test
./deploy.sh ps
curl -kf -sS -o /dev/null -w "%{http_code}\n" https://127.0.0.1/health/
curl -k -sS https://127.0.0.1/health/ | head -c 400; echo
curl -k -sS https://127.0.0.1/metrics/ | grep sufler_health_ok
```

| Check | Expect |
| --- | --- |
| `nginx-test` | `syntax is ok` / `test is successful` |
| `GET /health/` | **HTTP 200**, `checks.database` + `checks.redis` = `ok` |
| `GET /metrics/` | `sufler_health_ok 1` |
| HTTP `:80` | **301** → HTTPS |

### 2. Tier probes

```bash
./deploy.sh db-verify
./deploy.sh support-verify
./deploy.sh inference-verify
```

**Pass:** each script exits 0 (pgvector / Redis·Celery·MinIO / ASR·LLM stub).

### 3. Smoke (from a machine with pytest + DB access, or CI)

```bash
# Formal SUF-T + CHAT-T (customer URL evidence)
pytest -v \
  tests/acceptance/test_suf_t.py::SufTSmokeAcceptanceTest \
  tests/acceptance/test_chat_t.py::ChatTSmokeAcceptanceTest
# Results log: tests/acceptance/test_env_results.md
```

After flag cutover: [`cutover-checklist.md`](../../infra/test/cutover-checklist.md) + INT-T subset.

### 4. Observability (optional)

Confirm scrape/alert stubs loaded per [`observability/README.md`](../../infra/test/observability/README.md). Until Alertmanager is wired:

```bash
curl -kf -sS -o /dev/null https://ai-hub-test.bank.local/health/ \
  || echo "ALERT: TEST /health/ failed"
```

---

## Rollback

Rollback = **re-deploy the last known-good image pair**. App data (Postgres volume) is **not** wiped by `pull-up` / image swap.

### R1. Identify previous good tag

| Source | Where |
| --- | --- |
| Actions history | Last green **Deploy TEST** before the bad release |
| VM `.env` | Previous `BACKEND_IMAGE` / `FRONTEND_IMAGE` (if you keep a note / backup of `.env`) |
| Registry | Tags `test-*` / `v*` |

Do **not** roll back by deleting the Postgres volume unless explicitly recovering from data corruption (separate incident).

### R2. Redeploy previous images

```bash
cd /opt/sufler/infra/test
export BACKEND_IMAGE=ghcr.io/<org>/<repo>/backend:<previous-good-tag>
export FRONTEND_IMAGE=ghcr.io/<org>/<repo>/frontend:<previous-good-tag>
./deploy.sh pull-up
```

Or re-run Actions with `dry_run=false` and `image_tag=<previous-good-tag>`.

### R3. If containers are wedged

```bash
./deploy.sh ps
./deploy.sh logs          # Ctrl+C after capturing errors
./deploy.sh down          # stop containers; volumes kept
./deploy.sh pull-up       # or ./deploy.sh with local build
```

### R4. Re-verify

Repeat [Verify](#verify) §1–2. If migrations in the bad release are incompatible with the old image, restore DB from [`backup-postgres.sh`](../../infra/test/backup-postgres.sh) / bank backup **before** starting the old image — escalate to DBA.

### R5. Feature-flag rollback (integrations)

If only SUZ / Oktell / AD broke (stack healthy): flip flags in `.env` per [cutover-checklist.md](../../infra/test/cutover-checklist.md) (e.g. `OKTELL_MODE=mock`, `SUZ_INGEST_MODE=mock`), then:

```bash
docker compose -p sufler-test --env-file .env -f docker-compose.prod-like.yml up -d backend celery-worker
```

---

## Common failures FAQ

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| `deploy.sh config` / `up`: missing `.env` or `CHANGE_ME` | Secrets not filled | Copy `.env.example` → `.env`; set vault values; never commit |
| `Missing TLS certs` | No PEMs under `certs/` | `./gen-self-signed-cert.sh [CN]` or install bank CA chain + key |
| `curl` health **301** only | Hitting HTTP without `-L` / wrong scheme | Use `https://` or `curl -kL`; edge redirects `:80` → HTTPS |
| `/health/` **503** / `sufler_health_ok 0` | Postgres or Redis down | `./deploy.sh ps`; `logs` for `postgres`/`redis`/`backend`; `./deploy.sh db-verify` |
| Edge up, backend unhealthy | Daphne crash / migrate fail | `./deploy.sh logs`; check `DJANGO_SECRET_KEY`, DB URL, migrate on start |
| CI: missing `TEST_SSH_*` | Secrets not configured | [github-actions-deploy.md](../../infra/test/github-actions-deploy.md); use dry-run until SSH works |
| CI green, VM `pull` denied | Registry auth on VM | Set `REGISTRY_USERNAME`/`PASSWORD` (PAT `read:packages`) for `pull-up` |
| `pull-up` wrong/old code | Stale checkout or wrong tag | `git fetch` + correct `BACKEND_IMAGE` tag; confirm Actions output tag |
| `nginx-test` fails | Bad `nginx.conf` or cert path | Fix conf; ensure `fullchain.pem`/`privkey.pem` mounted paths match |
| `support-verify` fails | Redis/MinIO/Celery | `./deploy.sh support-verify`; check `OCR_OBJECT_STORE_BACKEND=minio`, Celery broker |
| `inference-verify` fails | ASR stub / profile | Ensure `AI_INFERENCE_PROFILE=test`, `asr` service up |
| UI blank / API OK | Frontend image mismatch | Confirm `FRONTEND_IMAGE` tag matches backend release; hard-refresh browser |
| SSH timeout from Actions | BelVPN / firewall / wrong host | Runner must reach `TEST_SSH_HOST`; check port secret; jump host policy |
| Concurrent deploys | Two workflows | Workflow uses concurrency group `deploy-test` (no cancel); wait for in-flight job |
| Need DB snapshot before risky deploy | — | `./deploy.sh backup-stub` (see README); keep bank backup path |

---

## Quick reference

```bash
cd /opt/sufler/infra/test
./deploy.sh config|up|pull-up|down|ps|logs
./deploy.sh nginx-test|db-verify|support-verify|inference-verify|backup-stub
```

| Action | Command / place |
| --- | --- |
| CI dry-run | Actions → Deploy TEST → `dry_run=true` |
| CI deploy | Tag `test-*` / `v*` or dispatch `dry_run=false` |
| Health | `curl -kf https://<host>/health/` |
| Metrics | `curl -k https://<host>/metrics/` |
| Rollback | `BACKEND_IMAGE`/`FRONTEND_IMAGE`=<good-tag> → `./deploy.sh pull-up` |
