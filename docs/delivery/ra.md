# Руководство по администрированию (РА)

**Статус:** каркас поставки (скелет) · заполнение этапа 2–7  
**Основание:** [Прил.1 §11.1.3](../sources/technical-requirements/prilozhenie-1.md) (в т.ч. элементы §11.1.4 — интеграции); [ТЗ v1.4 VII.4](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx)  
**Договор:** № 14-03/2026  
**Заказчик:** ОАО «АСБ Беларусбанк»  
**Исполнитель:** ООО «ГС Ритейл»

| Поле | Значение |
|------|----------|
| Полное наименование ПО | Программное обеспечение на базе искусственного интеллекта для банковских процессов (**AI Hub / Суфлёр**) |
| Краткое наименование | AI Hub |
| Версия документа | 0.1-skeleton |
| Аудитория | Администраторы приложения и инфраструктуры контура |
| Связанные документы | [ПТР](ptr.md), [РЭ](re.md), [`backend/README.md`](../../backend/README.md), runbooks в `docs/runbooks/` |

> **Маркер заполнения.** `_TBD: …_` — утверждение Заказчиком (хосты, секреты, AD). Процедуры развёртывания ниже опираются на канонический стек из [`backend/README.md`](../../backend/README.md) и `infra/`.

---

## 1. Введение

### 1.1. Назначение

Инструкция по **развёртыванию**, **инсталляции** компонент, **настройке** ПО, форматам данных, **взаимодействию** с иными ИС, управлению **учётными записями и правами**, **сопровождению** (включая обновление версий) — Прил.1 §11.1.3. Описание интеграционных API может входить в состав РА (§11.1.4).

### 1.2. Роли администраторов (каркас I.4)

| Роль | Зона ответственности |
|------|----------------------|
| Администратор ПО / software | Контур Hub, релизы |
| Админ модуля КЦ / ассистента / OCR | Настройки модулей в `/ai-hub/admin/` |
| Админ ИБ / аудит | KUMA, журналы |
| ДИТ (инфраструктура) | ВМ, сеть, AD, сертификаты |

_TBD: именной список УЗ prod._

---

## 2. Состав контура и модулей

Модули §2.2 — как в [ПТР §2](ptr.md) и ТЗ v1.4. Технические сервисы стека:

| Сервис | Репозиторий / образ | Назначение |
|--------|---------------------|------------|
| `backend` | `backend/` | Django API, миграции, admin |
| `celery-worker` | тот же код | Фоновые задачи |
| `postgres` | `infra/postgres` | PostgreSQL + pgvector |
| `redis` | Compose | Celery broker/result |
| `minio` | Compose | Объектное хранилище |
| `frontend` | `frontend/` | SPA (Vite) |
| ASR | `backend/services/asr` | Отдельный процесс (не в Compose) |

---

## 3. Развёртывание и инсталляция

### 3.1. Предварительные требования

Из [`backend/README.md`](../../backend/README.md):

- Docker Desktop (WSL 2 на Windows) / Linux Docker Engine; Compose v2;
- свободные host-порты **8000, 5432, 6379, 9000, 9001** (или переопределение в `.env`);
- рекомендуется ≥ **8 GB RAM**;
- для prod: ВМ по [`server-requirements.md`](../technical/server-requirements.md).

Проверка:

```powershell
docker --version
docker compose version
docker info
```

### 3.2. Инсталляция стека (Docker Compose)

```powershell
cd infra
Copy-Item .env.example .env
# Задать: DJANGO_SECRET_KEY, POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD
docker compose config
docker compose up --build -d
docker compose ps
```

Backend дожидается healthy PostgreSQL и выполняет **миграции** перед стартом.

| URL | Назначение |
|-----|------------|
| `http://localhost:8000/` | Приложение |
| `http://localhost:8000/health/` | Health (HTTP 200; `checks.database` + `checks.redis`) |
| `http://localhost:8000/admin/` | Django admin |
| `http://localhost:9001/` | MinIO Console |

Остановка с сохранением данных: `docker compose down`.  
Полный сброс volumes (только dev): `docker compose down -v`.

### 3.3. Management-команды

```powershell
cd infra
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py check
docker compose exec celery-worker celery -A sufler inspect ping --timeout=10
```

### 3.4. Локальный Django без контейнера backend

См. раздел «Локальный запуск» в [`backend/README.md`](../../backend/README.md): venv Python 3.12, `migrate`, `runserver`. Без `POSTGRES_HOST` — SQLite `backend/db.sqlite3` (только DEV).

### 3.5. ASR + LLM gateway (TEST inference tier)

Prod-like Compose includes **`asr`** stub (`ASR_MODE=stub`, no GPU).
ModelRegistry **`deployment_profiles.test`** binds ASR + ModelGateway stubs.

```bash
cd infra/test
./deploy.sh inference-verify
# or: docker compose exec backend python manage.py verify_inference_tier
```

ASR health: `http://asr:8764/health` · WS: `ws://asr:8765/`.  
LLM: in-process ModelGateway (`stub:sufler_cc` / …).  
Suggest smoke: QU → RAG → gateway → hints.

Vosk / real LLM candidate: see [`infra/test/README.md`](../../infra/test/README.md#ai-inference-tier-asr--llm-gateway-profiletest).

### 3.6. ASR (локальный Vosk с микрофоном)

```powershell
cd backend
# pip install -r services/asr/requirements.txt
# VOSK_MODEL_PATH=...
# python -m services.asr.main
```

WebSocket: `ws://localhost:8765`. _TBD: prod unit/systemd._

---

## 4. Настройка ПО

### 4.1. Переменные окружения (каркас)

| Группа | Примеры | Примечание |
|--------|---------|------------|
| Django | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Prod: `DEBUG=false` |
| БД | `POSTGRES_*` | |
| Auth | `AUTH_MODE` / `AUTH_BACKEND=ldaps`, LDAP URL, bind | См. runbook I.10 |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Redis |
| MinIO | `MINIO_*` | |
| Audit | `AUDIT_KUMA_COLLECTOR_URL` | VI.3 |
| Oktell / SUZ | _TBD по спецификациям VI_ | |

Секреты **не** коммитить в Git.

### 4.2. Админ-центр AI Hub

Маршрут `/ai-hub/admin/` — конфигурация LLM, промптов, KB, QU preview, политики суфлёра, типы документов и др. (по ролям администраторов модулей).

_TBD: чек-лист первичной настройки после установки на TEST._

### 4.3. ModelRegistry

KB profile: `kb_cc_production`. LLM API profiles: `assistant_bank`, `sufler_cc`, `docs_ocr`.  
**TEST deployment profile:** `deployment_profiles.test` (`AI_INFERENCE_PROFILE=test`).

Параметры generation / chunk / retrieval — через UI или API model-params.

---

## 5. Форматы входных и выходных данных

| Контур | Вход | Выход | Где описано |
|--------|------|-------|-------------|
| Суфлёр suggest | JSON text / session | hints + citations + latency | OpenAPI / ТЗ II |
| Виджет / каналы | сообщения клиента | reply + inbox | channels API |
| Ассистент chat | messages[] | SSE tokens | `/api/v1/assistant` |
| OCR | файл (pdf/image) | поля + confidence | DOC-T / OCR API |
| SUZ ingest | webhook Bitrix | chunks в pgvector | VI.1 |
| Отчёты | фильтры дат | JSON / CSV / XLSX | reports API |
| Audit | внутренние события | JSON lines → KUMA/file | VI.3 |

_TBD: приложить актуальные OpenAPI/JSON Schema в приложении к РА._

---

## 6. Взаимодействие с иными информационными системами

| Система | Назначение | Документ / runbook |
|---------|------------|-------------------|
| СУЗ (Bitrix) | RAG `cc_production` | `docs/integration/suz-bitrix-rag/` |
| Oktell | Телефония / события | `docs/integration/oktell-sufler-telephony/`, [oktell-t45-smoke](../runbooks/oktell-t45-smoke.md) |
| AD / LDAPS | УЗ и группы ролей | [i10-ldaps-auth-smoke](../runbooks/i10-ldaps-auth-smoke.md) |
| SIEM KUMA | Аудит | [vi3-kuma-audit-smoke](../runbooks/vi3-kuma-audit-smoke.md) |

Детальные контракты API — §11.1.4 (допускается как том РА или отдельный файл `_TBD: docs/delivery/integration.md_`).

---

## 7. Учётные записи и права пользователей

### 7.1. Модель доступа

- 13 ролей I.4 / §2.4; маппинг на AD-группы (_TBD C2 / VII.5_).
- Production: `AUTH_BACKEND=ldaps`.
- Development only: `AUTH_MODE=mock_ldap`, учётки `dev-role-01`…`dev-role-13` ([`auth/README.md`](../../backend/auth/README.md)).

### 7.2. Порядок управления

| Операция | Кто | Шаги (каркас) |
|----------|-----|----------------|
| Выдать роль | Админ AD + админ Hub | Добавить УЗ в группу AD → проверить `/api/auth/me/` |
| Отозвать доступ | Админ AD | Исключить из группы; сессии _TBD TTL_ |
| Superuser Django | Админ ПО | `createsuperuser` — только break-glass |
| Аудит входов | ИБ | Журнал audit / KUMA |

_TBD: регламент паролей и MFA — политики Заказчика._

---

## 8. Сопровождение и обновление версий

### 8.1. Журнал изменений

_TBD: ссылка на CHANGELOG / релизные notes договора._

### 8.2. Типовой порядок обновления (каркас)

1. Backup PostgreSQL и MinIO (_TBD процедура ДИТ_).
2. `git pull` / поставка артефакта версии N.
3. `docker compose build` / rolling update образов.
4. `migrate --noinput`.
5. Прогон smoke: [acceptance-smoke](../../.github/workflows/ci.yml) (SUF-T-01, CHAT-T-04), runbooks интеграций.
6. Мониторинг логов `backend`, `celery-worker`.

Откат: _TBD (предыдущий image tag + restore DB)._

### 8.3. Мониторинг и диагностика

| Проверка | Команда / URL |
|----------|----------------|
| Health | `GET /health/` → 200 (`checks.database`, `checks.redis`) |
| Compose | `docker compose ps` |
| Логи | `docker compose logs -f backend` |
| Celery | `celery -A sufler inspect ping` / `sufler.ping` → `pong` |
| Redis | `redis-cli ping` → PONG |
| MinIO | `/minio/health/live` + `./deploy.sh support-verify` (put/get) |
| Support tier | `infra/test` → `./deploy.sh support-verify` |
| pgvector | `SELECT extversion FROM pg_extension WHERE extname='vector';` |
| HNSW index | `cc_prod_embedding_hnsw_idx` on `cc_production` (`./deploy.sh db-verify`) |

Troubleshooting — раздел в [`backend/README.md`](../../backend/README.md) (порты, Docker Engine, PostgreSQL, Redis).

---

## 9. Резервное копирование и восстановление

| Объект | Метод | RPO/RTO | Статус |
|--------|-------|---------|--------|
| PostgreSQL | [`infra/test/backup-postgres.sh`](../../infra/test/backup-postgres.sh) stub (`pg_dump` → `infra/test/backups/`) | RPO/RTO — ДИТ | stub |
| MinIO | _TBD_ | _TBD_ | |
| Конфиги `.env` | _TBD vault_ | — | |
| Модели LLM/ASR на диске | _TBD_ | _TBD_ | |

---

## 10. Приложения

| № | Содержание | Статус |
|---|------------|--------|
| А | Пример заполненного `infra/.env` (без секретов) | _TBD_ |
| Б | Матрица AD-групп → роли I.4 | _TBD Заказчик_ |
| В | OpenAPI / Postman коллекции | _TBD_ |
| Г | Регламент обновления (утверждённый) | _TBD_ |

Обучение администраторов (VII.3, ≥3 чел.): slide outline
[`docs/training/admin-guide-outline.md`](../training/admin-guide-outline.md).

---

## 11. Лист согласования

| Роль | ФИО | Подпись | Дата |
|------|-----|---------|------|
| Заказчик (ДИТ) | _TBD_ | ______ | ______ |
| Заказчик (ИБ) | _TBD_ | ______ | ______ |
| Исполнитель | _TBD_ | ______ | ______ |
