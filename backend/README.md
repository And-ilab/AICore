# Backend Sufler

Канонический Django backend проекта Sufler: приложение чата, модели и
административная часть, Celery и конфигурация AI-моделей. Локальный
инфраструктурный контур находится в `infra/`.

## Prerequisites

Для рекомендуемого запуска через Docker:

- Git;
- Docker Desktop с WSL 2 на Windows;
- Docker Compose v2 (`docker compose`);
- свободные host-порты `8000`, `5432`, `6379`, `9000`, `9001`;
- рекомендуется не менее 8 GB RAM.

Проверка:

```powershell
docker --version
docker compose version
docker info
```

Для запуска Django без контейнера дополнительно нужен Python 3.12. PostgreSQL,
Redis и MinIO локально устанавливать не требуется: их можно оставить в Docker.

## Основные каталоги

```text
backend/
├── manage.py
├── requirements.txt
├── Dockerfile
├── sufler/                  # settings, urls, ASGI/WSGI, Celery
├── audit/                   # VI.3 JSON audit, file/HTTP KUMA sinks
├── auth/                    # dev mock LDAP, P7-03 LDAP stub, I.4 RBAC
├── chat/                    # Django app
├── config/                  # YAML-конфигурация, включая ModelRegistry
├── core/                    # общая backend-инфраструктура
├── hub/                     # Admin API и DB-настройки ModelRegistry
├── ingest/                  # SUZ webhook → cc_production pgvector
├── services/asr/            # dev ASR-сервис
├── templates/
├── static/
└── staticfiles/

infra/
├── docker-compose.yml
├── .env.example
└── postgres/init.sql

tests/
└── acceptance/
```

## Быстрый запуск всего стека через Docker

Из корня репозитория:

```powershell
cd infra
Copy-Item .env.example .env
```

Замените в `.env` значения `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD` и
`MINIO_ROOT_PASSWORD`. Файл `.env` не должен попадать в Git.

```powershell
docker compose config
docker compose up --build -d
docker compose ps
```

Запускаются PostgreSQL/pgvector, Redis, MinIO, backend и Celery worker. Backend
ждёт healthy PostgreSQL и автоматически выполняет миграции перед `runserver`.

Основные URL:

- приложение: <http://localhost:8000/>
- **health (db + redis):** <http://localhost:8000/health/>
- legacy smoke: <http://localhost:8000/client-info/>
- Django admin: <http://localhost:8000/admin/>
- MinIO Console: <http://localhost:9001/>

`GET /health/` returns HTTP **200** with JSON body including `checks.database` and
`checks.redis` (both `status: ok`). Used by Docker healthchecks on the TEST
prod-like stack (`infra/test/docker-compose.prod-like.yml`). WebSocket traffic
is served by **Daphne** via `sufler.asgi:application` (`/ws/sufler/…`).

On bank TEST via nginx: `https://<fqdn>/health/` — see
[`infra/test/README.md`](../infra/test/README.md).

Логи и остановка:

```powershell
docker compose logs -f backend
docker compose logs -f celery-worker
docker compose down
```

`docker compose down` сохраняет данные. Команда `docker compose down -v`
удаляет volumes PostgreSQL, Redis и MinIO и должна использоваться только для
полного сброса локального dev-окружения.

## Django management-команды в Docker

Миграции:

```powershell
cd infra
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py showmigrations
```

Суперпользователь:

```powershell
docker compose exec backend python manage.py createsuperuser
```

Проверка Django:

```powershell
docker compose exec backend python manage.py check
```

## Локальный запуск Django без backend-контейнера

Из корня репозитория:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Без `POSTGRES_HOST` backend использует локальную SQLite-базу
`backend/db.sqlite3`. Сервер доступен на <http://127.0.0.1:8000/>.

## Development authentication and RBAC

При `DJANGO_DEBUG=true` по умолчанию используется development-only mock LDAP:

```powershell
$env:AUTH_MODE = "mock_ldap"
$env:AUTH_MOCK_LDAP_DEFAULT_PASSWORD = "local-dev-secret"
.\.venv\Scripts\python.exe manage.py runserver
```

Аккаунты `dev-role-01`…`dev-role-13` соответствуют 13 ролям I.4.
`dev-role-01` может войти в Django admin. Для production требуется
`AUTH_MODE=ldap` / `AUTH_BACKEND=ldaps`, реальные AD-группы (VII.5 C2) и human sign-off.

Полная конфигурация и примеры decorators:
[`auth/README.md`](auth/README.md).

## Celery

В Docker worker запускается автоматически. Проверка:

```powershell
cd infra
docker compose ps celery-worker
docker compose exec celery-worker celery -A sufler inspect ping --timeout=10
```

Ожидаемый ответ содержит `pong`.

На bank TEST (prod-like):

```bash
cd infra/test
./deploy.sh support-verify
# redis-cli PONG · celery sufler.ping → pong · MinIO upload/download
```

Для локального worker на Windows сначала запустите Redis через Docker:

```powershell
cd infra
docker compose up -d redis
cd ..\backend
$env:CELERY_BROKER_URL = "redis://localhost:6379/0"
$env:CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
.\.venv\Scripts\celery.exe -A sufler worker --loglevel=info --pool=solo
```

## Тесты и lint

Из корня репозитория:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install pytest ruff
.\backend\.venv\Scripts\python.exe -m ruff check backend tests dashboard/app recognizer
.\backend\.venv\Scripts\python.exe -m pytest tests -v
```

Эти же проверки выполняет GitHub Actions.

## OpenAPI / Postman

- Schema: `GET /api/schema/` (Accept: `application/json`)
- Swagger UI (DEBUG): <http://127.0.0.1:8000/api/docs/>
- Collection: [`docs/api/postman_collection.json`](../docs/api/postman_collection.json)

```powershell
.\.venv\Scripts\python.exe -m api_docs.export_postman
```

## KB / QU ops (FR-UND-08)

Admin step-by-step (no developer required):

| Runbook | When |
| --- | --- |
| [`docs/runbooks/reindex.md`](../docs/runbooks/reindex.md) | Rebuild `cc_production` / Hub KB index |
| [`docs/runbooks/qu-retrain.md`](../docs/runbooks/qu-retrain.md) | Verify or manually enqueue `qu.qu_retrain` |
| [`docs/runbooks/rollback-qu.md`](../docs/runbooks/rollback-qu.md) | Recover after bad index / эталоны |

Package notes: [`ingest/README.md`](ingest/README.md), [`qu/README.md`](qu/README.md).

## ASR

ASR запускается отдельно от Docker Compose. Зависимости и модель:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r services\asr\requirements.txt
$env:VOSK_MODEL_PATH = "C:\models\vosk-model-ru-0.22"
.\.venv\Scripts\python.exe -m services.asr.main
```

WebSocket ASR: `ws://localhost:8765`.

## Troubleshooting

### Docker Desktop Linux Engine не запущен

Ошибка содержит `dockerDesktopLinuxEngine` или `pipe ... not found`.

1. Запустите Docker Desktop.
2. Убедитесь, что включён WSL 2 engine.
3. Выполните `docker info` и повторите `docker compose up -d`.

### Порт уже занят

Ошибка содержит `Ports are not available` или `bind: Only one usage`.
Измените только host-порт в `infra/.env`, например:

```env
POSTGRES_PORT_HOST=5433
BACKEND_PORT_HOST=8001
```

Внутренние порты контейнеров менять не нужно.

### PostgreSQL не запускается

```powershell
cd infra
docker compose ps -a postgres
docker compose logs --tail=100 postgres
docker compose up -d postgres
```

Проверьте непустой `POSTGRES_PASSWORD` и доступность host-порта.

### pgvector отсутствует

```powershell
docker compose exec postgres psql -U sufler -d sufler -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker compose exec postgres psql -U sufler -d sufler -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
```

`infra/postgres/init.sql` создаёт расширение автоматически только при первой
инициализации нового PostgreSQL volume.

### Redis недоступен

```powershell
docker compose ps redis
docker compose exec redis redis-cli ping
docker compose logs --tail=100 redis
```

Ожидаемый ответ Redis — `PONG`.

### Backend или Celery не запускаются

```powershell
docker compose ps -a
docker compose logs --tail=100 backend
docker compose logs --tail=100 celery-worker
docker compose up --build -d backend celery-worker
```

Backend стартует только после healthy PostgreSQL, Redis и MinIO. Повторяющиеся
`GET /health/` со статусом 200 в логах — нормальная работа healthcheck
(на TEST prod-like; legacy `/client-info/` остаётся для smoke).

## Legacy compatibility

Старые точки входа `dashboard/app/manage.py` и `recognizer/main.py`, а также
импорты `app.settings`, `app.urls`, `app.wsgi` и `app.asgi` сохранены через
совместимые wrapper/shim-модули.
