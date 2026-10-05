# Infrastructure

Локальный инфраструктурный контур Sufler запускается через Docker Compose:

- PostgreSQL 16 с расширением pgvector;
- Redis;
- MinIO;
- Django backend;
- Celery worker;
- Vite frontend (React).

## Подготовка

Нужен Docker Desktop с поддержкой `docker compose`.

```powershell
cd infra
Copy-Item .env.example .env
```

Перед запуском замените значения паролей и `DJANGO_SECRET_KEY` в `.env`.
Файл `.env` игнорируется Git; `.env.example` содержит только шаблон.

## Запуск

```powershell
docker compose config
docker compose up --build -d
docker compose ps
```

По умолчанию стартуют только лёгкие сервисы: PostgreSQL, Redis, MinIO,
Mailpit, backend и frontend. Celery, Telegram-poller и embedding (ML-модель
~1 GB RAM) выключены — их можно включить через `COMPOSE_PROFILES` в `.env`:

```powershell
# фоновые задачи онлайн-чата
COMPOSE_PROFILES=workers

# Telegram long-polling (нужен TELEGRAM_BOT_TOKEN)
COMPOSE_PROFILES=telegram

# всё вместе + embedding (тяжело для MacBook)
COMPOSE_PROFILES=workers,telegram,embedding
EMBEDDING_MODE=http
```

### macOS: MacBook греется / всё тормозит

Docker Desktop на Mac эмулирует Linux и делит ограниченную RAM с хостом.
Полный стек (10 контейнеров + embedding + Celery каждые 20 с) легко
перегружает ноутбук.

1. **Docker Desktop → Settings → Resources**: выделите **8 GB RAM** и **4 CPU**
   (если сейчас ~4 GB — это главная причина подвисаний).
2. **Не поднимайте лишнее**: оставьте `EMBEDDING_MODE=stub` и не задавайте
   `COMPOSE_PROFILES`, пока не нужны фоновые задачи или RAG с embeddings.
3. **Останавливайте стек**, когда не работаете: `docker compose down`.
4. **Только UI**: можно запустить frontend на хосте (`cd frontend && npm run dev`),
   а в Docker оставить `postgres redis minio backend`.
5. **Профили по необходимости** — см. `COMPOSE_PROFILES` выше.

Backend запускает миграции перед web-сервером и стартует только после
успешного healthcheck PostgreSQL. Redis и MinIO также должны перейти в
состояние `healthy`; Celery worker ожидает готовый backend.

Логи:

```powershell
docker compose logs -f backend
docker compose logs -f celery-worker
```

Остановка:

```powershell
docker compose down
```

Для удаления локальных данных PostgreSQL, Redis и MinIO:

```powershell
docker compose down -v
```

## Порты

- `5173` (`FRONTEND_PORT_HOST`) — Vite frontend: <http://localhost:5173/>
- `8001` (`BACKEND_PORT_HOST`) — Django: <http://localhost:8001/> (на проде за nginx — снаружи открыт только 8000, проксирующий `/api/` на 8001)
- `5432` (`POSTGRES_PORT_HOST`) — PostgreSQL/pgvector
- `6379` (`REDIS_PORT_HOST`) — Redis
- `9000` (`MINIO_API_PORT_HOST`) — MinIO S3 API
- `9001` (`MINIO_CONSOLE_PORT_HOST`) — MinIO Console:
  <http://localhost:9001/>

Celery worker не публикует порт наружу. Все host-порты можно изменить в
`infra/.env`; внутренние имена сервисов и порты остаются фиксированными.

Frontend проксирует `/api` на сервис `backend` внутри Docker-сети.
Для локальной разработки без Django-сессии задайте `VITE_DEV_RBAC_ROLES`
в `.env` (через запятую). Исходники монтируются из `../frontend` с
hot-reload; `node_modules` хранятся в volume `frontend_node_modules`.

## Healthchecks

- PostgreSQL — `pg_isready`;
- Redis — `redis-cli ping`;
- MinIO — `/minio/health/live`;
- backend — HTTP `GET /health/` (db + redis JSON; TEST prod-like) / `GET /metrics/` (Prometheus) / legacy `GET /client-info/`;
- Celery worker — `celery inspect ping`.

Расширение `vector` создаётся при первой инициализации PostgreSQL скриптом
`postgres/init.sql`. Данные сервисов хранятся в именованных Docker volumes.

## Bank TEST VM (VII.3 / T+28)

ДИТ request template (CPU/RAM/GPU/disk/OS + BelVPN), sized for ModelRegistry
`approved_dev`:

- [`test/server-requirements.md`](test/server-requirements.md)
- Env cutover: [`test/.env.example`](test/.env.example)

### Prod-like stack (TEST) — not the local `docker-compose.yml`

On the bank TEST VM use a **separate** Compose file and deploy script:

- Compose: [`test/docker-compose.prod-like.yml`](test/docker-compose.prod-like.yml)  
  (postgres · redis · minio · Daphne backend · celery · nginx frontend; no published DB ports)
- Deploy: [`test/deploy.sh`](test/deploy.sh) — `config` / `up` / `down` / `logs` / `ps`
- Docs: [`test/README.md`](test/README.md)

```bash
cd infra/test
cp .env.example .env   # secrets from vault — never commit
./deploy.sh config
./deploy.sh
```

Local developer workflow stays on `infra/docker-compose.yml` + `infra/.env`.

CI (tag or manual dispatch): [`.github/workflows/deploy-test.yml`](../.github/workflows/deploy-test.yml) —
see [`test/github-actions-deploy.md`](test/github-actions-deploy.md) for required secrets and dry-run.
Ops runbook: [`docs/runbooks/deploy-test.md`](../docs/runbooks/deploy-test.md).

Data tier (pgvector migrate / indexes / backup stub): [`test/README.md`](test/README.md#data-tier-postgresql--pgvector).

Support tier (Redis + Celery + MinIO): [`test/README.md`](test/README.md#support-tier-redis--minio--celery).

Inference tier (ASR + LLM, `profile=test`): [`test/README.md`](test/README.md#ai-inference-tier-asr--llm-gateway-profiletest).

CPU LLM + embeddings (Linux): [`local-inference/README.md`](local-inference/README.md) · `./local-inference/up-cpu.sh` · TEST: `./test/deploy.sh up --cpu-inference`.

Edge TLS (HTTPS only): [`test/nginx.conf`](test/nginx.conf) · [`test/README.md`](test/README.md#edge-tls-nginx).

Cutover (SUZ/Oktell/AD + INT-T): [`test/cutover-checklist.md`](test/cutover-checklist.md).
