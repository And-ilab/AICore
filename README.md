# Sufler — руководство по репозиторию

**Проект:** программное обеспечение на базе ИИ для банковских процессов  
**Заказчик:** ОАО «АСБ Беларусбанк» · **Договор:** № 14-03/2026  
**Исполнитель:** ООО «ГС Ритейл»

Единая точка входа в репозиторий `C:\sufler`. Подробный индекс документации — в [`docs/README.md`](docs/README.md).

---

## Быстрый старт

| Задача | Куда идти |
|--------|-----------|
| Техническое задание | [`docs/modules/ai-hub/TZ-unified-v1.8 (МИХ).docx`](docs/modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) |
| Технические требования (Прил. 1) | [`docs/sources/technical-requirements/prilozhenie-1.md`](docs/sources/technical-requirements/prilozhenie-1.md) |
| Макеты интерфейсов | [`canvases/`](canvases/) |
| Backend и АРМ оператора | [`backend/`](backend/) |
| Запуск | [`infra/docker-compose.yml`](infra/docker-compose.yml) |
| Требования к серверу / ВМ | [`docs/technical/server-requirements.md`](docs/technical/server-requirements.md) |

---

## Карта репозитория

```
sufler/
├── backend/           ← канонический Django-проект sufler, app chat и ASR
├── infra/             ← Docker Compose: PostgreSQL/pgvector, Redis, MinIO, Celery
├── tests/
│   └── acceptance/    ← сквозные smoke/acceptance-тесты backend
├── frontend/          ← интерфейс оператора
├── docs/              ← ТЗ, технические требования, runbook'и
├── canvases/          ← макеты интерфейсов
├── dashboard/app/     ← legacy-обёртки Django для обратной совместимости
└── recognizer/        ← legacy-обёртка ASR для обратной совместимости
```

---

## 1. Документация (`docs/`)

### Слои

| Слой | Путь | Назначение |
|------|------|------------|
| **Техническое задание** | [`docs/modules/ai-hub/`](docs/modules/ai-hub/) | Один файл: `TZ-unified-v1.8 (МИХ).docx` |
| **Технические требования** | [`docs/sources/technical-requirements/`](docs/sources/technical-requirements/) | Приложение 1 и сценарии приложения 2 |
| **Исходники заказчика** | [`docs/sources/`](docs/sources/) | AD, SIEM, Oktell, СУЗ |
| **Интеграции и UI** | [`docs/integration/`](docs/integration/), [`docs/ui/`](docs/ui/) | Как устроены Oktell, СУЗ, чат и экраны |

### Модули продукта

| Модуль | Путь | Ключевой файл |
|--------|------|---------------|
| **Контур AI Hub** | [`docs/modules/ai-hub/`](docs/modules/ai-hub/) | `TZ-unified-v1.8 (МИХ).docx` |
| **ИИ-ассистент** | [`docs/modules/ai-assistant/`](docs/modules/ai-assistant/) | Часть III того же ТЗ |

**Структура единого ТЗ v1.4** (§2.2 Прил. 1):

| Часть | Содержание |
|-------|------------|
| **0** | Реквизиты документа (ГОСТ §1) |
| **I** | Общие положения, глоссарий, роли, ИБ, LDAPS, портальный лаунчер |
| **II** | Модуль Контакт-центра (суфлёр, онлайн-чат, отчётность) |
| **III** | Модуль ИИ-ассистент |
| **IV** | Модуль распознавания документов |
| **V** | Модуль LLM |
| **VI** | Интеграции (СУЗ, Oktell, SIEM/KUMA) |
| **VII** | Работы, приёмка, документирование, открытые вопросы |
| **Прил. A–D** | Согласование, сценарии, источники, индекс замечаний |

### Интеграции

| Интеграция | Путь | Версия ТЗ | Раздел unified |
|------------|------|-----------|----------------|
| Oktell ↔ суфлёр | [`docs/integration/oktell-sufler-telephony/`](docs/integration/oktell-sufler-telephony/) | v0.1 | Part VI.2 |
| СУЗ ↔ RAG (1С-Битрикс) | [`docs/integration/suz-bitrix-rag/`](docs/integration/suz-bitrix-rag/) | v1.2 | Part VI.1 |
| Онлайн-чат (АРМ КЦ) | [`docs/integration/online-chat/`](docs/integration/online-chat/) | v0.1 | Part II.5 |

### Исходники заказчика

| Категория | Папка |
|-----------|-------|
| Технические требования (Прил. 1–2) | [`technical-requirements/`](docs/sources/technical-requirements/) |
| Active Directory | [`active-directory/`](docs/sources/active-directory/) |
| SIEM (Kaspersky KUMA) | [`siem/`](docs/sources/siem/) |
| Oktell (документация вендора) | [`oktell/`](docs/sources/oktell/) |
| СУЗ (система управления знаниями) | [`suz/`](docs/sources/suz/) |

---

## 2. Техническое задание

В репозитории одна версия ТЗ: [`TZ-unified-v1.8 (МИХ).docx`](docs/modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx).

### Договорный источник истины

| Файл | Роль |
|------|------|
| `docs/sources/technical-requirements/prilozhenie-1.md` | **Приложение 1** — главный договорный источник |
| `docs/sources/technical-requirements/app2-scenarios/manifest.yaml` | **Приложение 2** — 10 эталонных сценариев (CC-SCR-001…010) |

---

## 3. Макеты интерфейсов

### Макеты (`canvases/`)

Экраны интерфейса для согласования.

| Canvas | Назначение |
|--------|------------|
| `tray-launcher-mockup.canvas.tsx` | Портальный лаунчер AI Hub → «Суфлёр \| Ассистент» |
| `sufer-phone-mockup.canvas.tsx` | Суфлёр телефонии — реплики, подсказки, % релевантности |
| `ai-assistant-ui-mockup.canvas.tsx` | Окно ИИ-ассистента |
| `ai-hub-panel-mockup.canvas.tsx` | Панель AI Hub (FAB, RBAC, вкладки) |
| `online-chat-mockups.canvas.tsx` | АРМ оператора чата |
| `internal-user-kc-mockup.canvas.tsx` | Тест промптов внутреннего пользователя КЦ |
| `ai-hub-settings-mockup.canvas.tsx` | Центр настроек `/ai-hub/admin` |
| `ocr-documents-mockup.canvas.tsx` | Модуль распознавания документов |

**Backlog (в ТЗ, ещё не в репо):** `widget-sites-mockup`, `widget-client-mockup`, `reporting-builder-mockup`.

### Markdown-спеки UI (`docs/ui/`)

| Файл | Описание |
|------|----------|
| `ai-hub-panel-mockup.md` | Правая панель AI Hub: FAB, RBAC, 3 вкладки |
| `ai-hub-settings-mockup.md` | Админ-центр — 18 экранов, LLM, промпты, сценарии |

---

## 4. Прототипы кода

### Backend — Django-проект `sufler` (`backend/`)

**Стек:** Django 5 · SQLite · channels · websockets

Единая точка сборки backend и прототип операторского рабочего места
онлайн-чата: регистрация клиента, сессии по каналам, история сообщений,
отчёты. Django-приложение находится в `backend/chat/`; старый
`dashboard/app/manage.py` сохранён как совместимая точка входа.

| Модель | Назначение |
|--------|------------|
| `Client` | Профиль клиента (имя, телефон, email, UUID сессии) |
| `ChatSession` | Сессия чата/звонка (chat, Telegram, Viber, WhatsApp, phone) |
| `Message` | Сообщения (клиент, оператор, рекомендация ИИ, ответ ИИ) |
| `CallLog` | Длительность и транскрипция звонка |

| Маршрут | Назначение |
|---------|------------|
| `/` | Главная |
| `/client-info/` | Регистрация клиента |
| `/chat/` | Интерфейс чата |
| `/dashboard/` | История сессий |
| `/reports/` | Статистика |
| `/api/*` | REST API |

### Recognizer — ASR-прототип (`backend/services/asr/`)

Dev-прототип потокового распознавания речи: Vosk `vosk-model-ru-0.22` +
WebSocket (`main.py`). Старый `recognizer/main.py` перенаправляет запуск в
новый сервис.

> В production-ТЗ ASR — on-prem streaming (вендор TBD); встроенный STT Oktell (Yandex/Google) **исключён**.

---

## 5. Модели и компоненты ИИ (по ТЗ)

| Компонент | Технология | Контекст |
|-----------|------------|----------|
| **ASR** | On-prem streaming (prod); Vosk (dev) | Part II, FR-ASR-*; dual-leg audio Oktell |
| **QU** (понимание запросов) | Embedding + cosine similarity | FR-UND-04/06 |
| **RAG** | Vector store + chunking/embedding | KB: `cc_production`, `assistant_*` |
| **LLM** | On-prem generative (вендор не фиксирован) | Part V; профили `sufler_cc`, `assistant_bank` |
| **OCR** | Модуль распознавания документов | Part IV |

---

## 6. Поток документов

```
docs/sources/technical-requirements/     docs/modules/ai-hub/
(Прил. 1 и сценарии)                     TZ-unified-v1.8 (МИХ).docx
        │                                          │
        └──────────────────┬───────────────────────┘
                           ▼
                  canvases/ + docs/ui/
                           ▼
                       backend/ + frontend/
```

---

## 7. Конвенции

- Техническое задание — один файл `docs/modules/ai-hub/TZ-unified-v1.8 (МИХ).docx`.
- Технические требования — `docs/sources/technical-requirements/`.
- Исходники заказчика — `docs/sources/`.
- Код приложения — `backend/`, `frontend/`, `infra/`.

---

## 8. Навигация по README в подпапках

| README | Путь |
|--------|------|
| Backend и структура monorepo | [`backend/README.md`](backend/README.md) |
| Индекс документации | [`docs/README.md`](docs/README.md) |
| Исходники заказчика | [`docs/sources/README.md`](docs/sources/README.md) |
| Контур AI Hub | [`docs/modules/ai-hub/README.md`](docs/modules/ai-hub/README.md) |
| ИИ-ассистент | [`docs/modules/ai-assistant/README.md`](docs/modules/ai-assistant/README.md) |
| Oktell ↔ суфлёр | [`docs/integration/oktell-sufler-telephony/README.md`](docs/integration/oktell-sufler-telephony/README.md) |
| СУЗ ↔ RAG | [`docs/integration/suz-bitrix-rag/README.md`](docs/integration/suz-bitrix-rag/README.md) |
| Онлайн-чат | [`docs/integration/online-chat/README.md`](docs/integration/online-chat/README.md) |
