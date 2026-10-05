# Документация проекта Sufler

**Заказчик:** ОАО «АСБ Беларусбанк» · **Договор:** № 14-03/2026

> Полное руководство по репозиторию (код, макеты, модели, скрипты) — в корневом [`README.md`](../README.md).

## Слои документации

| Слой | Путь | Назначение |
|------|------|------------|
| **Исходники заказчика** | [`sources/`](sources/) | Входящие материалы: договор (Прил.1–2), протоколы совещаний с поручениями, доки AD / SIEM / Oktell / СУЗ |
| **ТЗ и спецификации (Исполнитель)** | [`integration/`](integration/), [`modules/`](modules/), [`ui/`](ui/) | Наши рабочие документы для согласования и разработки |
| **Runbooks (ops)** | [`runbooks/`](runbooks/) | [**Deploy TEST**](runbooks/deploy-test.md) · [Oktell T+45](runbooks/oktell-t45-smoke.md) · [I.10 LDAPS](runbooks/i10-ldaps-auth-smoke.md) · [VI.3 KUMA](runbooks/vi3-kuma-audit-smoke.md) · **FR-UND-08:** [reindex](runbooks/reindex.md) · [qu-retrain](runbooks/qu-retrain.md) · [rollback-qu](runbooks/rollback-qu.md) · **TEST cutover:** [cutover-checklist](../infra/test/cutover-checklist.md) |
| **Development** | [`development/`](development/) | [**Code review**](development/code-review-checklist.md) · [**BelVPN / ДИТ**](development/vpn-request-template.md) · [**Demo script**](development/demo-script.md) · [**VII.5 decisions**](development/vii5-decisions-tracker.md) (D1–D4; human only) |
| **Поставка (ГОСТ §11.1)** | [`delivery/`](delivery/) | Скелеты [ПТР](delivery/ptr.md) · [РЭ](delivery/re.md) · [РА](delivery/ra.md) |
| **Обучение (VII.3)** | [`training/`](training/) | Slide outlines: [admin ≥3](training/admin-guide-outline.md) · [users ≥5](training/user-guide-outline.md) |
| **API (OpenAPI / Postman)** | [`api/`](api/) | Schema `/api/schema/`, [Postman collection](api/postman_collection.json) |

## Исходники заказчика — [`sources/`](sources/)

| Категория | Папка |
|-----------|-------|
| Технические требования (Приложение 1) | [technical-requirements/](sources/technical-requirements/) |
| Active Directory | [active-directory/](sources/active-directory/) |
| SIEM | [siem/](sources/siem/) |
| Oktell (исходная документация) | [oktell/](sources/oktell/) |
| СУЗ (система управления знаниями) | [suz/](sources/suz/) |

## ТЗ и интеграции

| Область | Путь |
|---------|------|
| Контур AI Hub (зонтичное ТЗ) | [modules/ai-hub/](modules/ai-hub/) |
| Модуль «Ассистент» | [modules/ai-assistant/](modules/ai-assistant/) |
| Oktell ↔ суфлёр | [integration/oktell-sufler-telephony/](integration/oktell-sufler-telephony/) |
| СУЗ ↔ RAG | [integration/suz-bitrix-rag/](integration/suz-bitrix-rag/) |
| Онлайн-чат | [integration/online-chat/](integration/online-chat/) |

## UI

| Тип | Путь |
|-----|------|
| Markdown-спеки | [ui/](ui/) |
| Интерактивные макеты (Cursor Canvas) | `canvases/` в корне репозитория |

## Технические спецификации — [`technical/`](technical/)

| Документ | Назначение |
|----------|------------|
| [server-requirements.md](technical/server-requirements.md) | **Требования к серверу / ВМ** (VII.3): DEV, TEST, ориентир PROD |
| [infra/test/server-requirements.md](../infra/test/server-requirements.md) | **Заявка ДИТ T+28** — TEST VM CPU/RAM/GPU/disk/OS + BelVPN |
| [infra/test/README.md](../infra/test/README.md) | **Prod-like Compose + deploy.sh** (отдельный от local `infra/docker-compose.yml`); data tier pgvector / backup stub |
| [infra/test/observability/README.md](../infra/test/observability/README.md) | **TEST observability** — `/metrics/`, health-fail alert stub, structured logging aggregation |
| [infra/test/cutover-checklist.md](../infra/test/cutover-checklist.md) | **TEST cutover** — SUZ/Oktell/AD flags + INT-T subset before demo |
| [infra/test/cutover-int-t-results.md](../infra/test/cutover-int-t-results.md) | INT-T subset results log |
| [test_env_results.md](../tests/acceptance/test_env_results.md) | **SUF-T + CHAT-T formal smoke** + customer TEST URL |
| [infra/test/github-actions-deploy.md](../infra/test/github-actions-deploy.md) | **Deploy TEST** workflow secrets + dry-run |
| [deploy-test.md](runbooks/deploy-test.md) | **Ops runbook** — TEST deploy / rollback / verify / FAQ (P10-03) |
| [code-review-checklist.md](development/code-review-checklist.md) | **Merge → main** — human reviewer checklist (pytest, lint, FR, security, canvas) |
| [vpn-request-template.md](development/vpn-request-template.md) | **BelVPN / ДИТ** — TEST access request template (T+28; do not auto-send) |
| [demo-script.md](development/demo-script.md) | **Customer demo** — CC / chat / Assistant / OCR / Admin (v1.4; human-led) |
| [vii5-decisions-tracker.md](development/vii5-decisions-tracker.md) | **VII.5 D1–D4** — open decisions tracker (MRCP/WS, СУЗ, KUMA, Assistant; human only) |
| [model-selection-v1.md](technical/model-selection-v1.md) | Выбор моделей и gate по GPU/RAM |
| [qu-architecture.md](technical/qu-architecture.md) | Архитектура понимания запросов |
| [ocr-llm-pipeline.md](technical/ocr-llm-pipeline.md) | Пайплайн OCR → LLM |
