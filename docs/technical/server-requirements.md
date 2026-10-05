# Требования к серверу AI Hub (тестовый и целевой контуры)

**Статус:** DRAFT · спецификация Исполнителя (VII.3 ТЗ)  
**Дата:** 2026-07-21  
**Договор:** № 14-03/2026 · Заказчик: ОАО «АСБ Беларусбанк»  
**Основание:** Прил.1 §10; единое ТЗ v1.4 (VII.3, II.7.4, FR-ASR-03/04, FR-SUF-06, FR-LLM-07, FR-ASS-36); `infra/docker-compose.yml`; `docs/technical/model-selection-v1.md`

> Документ закрывает поручение **«требования к тестовому серверу»** (ТЗ: Исполнитель → ДИТ → ВМ).  
> **GPU/RAM production для ASR/LLM/OCR не утверждены** до measured benchmark на целевой ВМ (`model-selection-v1`: capacity `TBD measured`). Ниже — обоснованные стартовые конфигурации для поставки стенда и ориентиры под договорную нагрузку.

---

## 1. Назначение

Спецификация описывает, на каком оборудовании и с какими ОС/сетевыми условиями запускать контур **AI Hub / Суфлёр**:

| Контур | Назначение | Кто предоставляет |
|--------|------------|-------------------|
| **DEV** | Локальная разработка Исполнителя | Исполнитель |
| **TEST** | Совместные SUF-T / CHAT-T / ASS-T / DOC-T / INT-T, интеграция СУЗ/Oktell/AD | Заказчик (ВМ по этой спецификации) |
| **PROD** | Промышленная эксплуатация on-prem / air-gap | Заказчик после sign-off моделей и нагрузочных замеров |

---

## 2. Договорные ограничения (Прил.1 §10)

| № | Требование | Следствие для стенда |
|---|------------|----------------------|
| 10.1 | Архитектура **x64** | Только x86_64 / amd64 |
| 10.2 | Виртуализация **VMware** (кроме высоконагруженных серверов) | TEST — VMware VM; узлы ASR/LLM под пиковой нагрузкой допускается bare-metal / выделенный GPU-хост вне общей виртуализации |
| 10.3 | ОС семейства **Linux**, не EoL | Рекомендация: **Ubuntu 22.04/24.04 LTS** или **RHEL/Rocky 9** (актуальный минор без EoL) |
| 10.4 | СУБД open source, TCP/IP, многопользовательская консистентность | **PostgreSQL 16** + расширение **pgvector** |
| §8–9, FR-CC-01/04 | On-prem, защищённый сегмент; без выхода в Интернет для QU/ASR/RAG/LLM КЦ (кроме согласованного egress виджета чата / ассистента — TBD ИБ) | TEST/PROD в сегменте банка; исходящий Internet по умолчанию **запрещён** |
| §8.10 | Антивирус на серверной части — ПО Заказчика | Установка по регламенту ДИТ |

---

## 3. Что уже реализовано vs что потребует ресурсов позже

### 3.1. Уже в репозитории (текущий runnable-стек)

| Компонент | Реализация | Ресурсы |
|-----------|------------|---------|
| Backend | Django 5, Channels/WebSocket, REST | CPU + RAM |
| БД | PostgreSQL 16 + **pgvector** (`infra/`) | CPU + RAM + SSD |
| Очереди | Redis 7 + Celery worker | CPU + RAM |
| Объектное хранилище | MinIO (S3-совместимое) | SSD |
| Аудит | JSONL / HTTP sink под KUMA | диск + сеть к коллектору |
| Auth | mock LDAP (dev); stub LDAPS (P7) | сеть к AD на TEST |
| Ingest СУЗ | webhook → chunking → embedding → `cc_production` | CPU + RAM (embedding) |
| ASR | Dev: Vosk `vosk-model-small-ru-0.22`, WebSocket | **CPU** (GPU не обязателен) |
| LLM | **Stub** профили `sufler_cc` / `assistant_bank` / `docs_ocr` | минимальные |
| Frontend | Vite / React / TS (сборка статики) | Node только на build |
| Оркестрация | Docker Compose (`infra/docker-compose.yml`) | Docker Engine |

Минимум для **DEV** (из `backend/README.md`): Docker Desktop, порты `8000/5432/6379/9000/9001`, **≥ 8 GB RAM**.

### 3.2. По ТЗ — ещё не на production-моделях (потребует GPU/масштаба)

| Модуль | Договорная нагрузка / KPI | Что появится на сервере |
|--------|---------------------------|-------------------------|
| **ASR телефония** | ≥ **70** одновременных звонков; p95 ≤ **1 с**; accuracy ≥ **90%** (FR-ASR-03/04) | Кластер ASR-воркеров; возможна NVIDIA GPU (Riva/Whisper и т.п. — TBD) |
| **Суфлёр КЦ** | **75** операторов; подсказка p95 ≤ **2 с** (II.7.4, FR-SUF-06) | QU + RAG + LLM `sufler_cc` on-prem |
| **LLM платформа** | ≥ **10 RPS**; p95 ≤ **2 с**; галлюцинации ≤ **3%** (FR-LLM-06/07) | Inference-сервер (vLLM / Triton / vendor) |
| **ИИ-ассистент** | до **2000** одновременных пользователей; p95 ≤ **2 с** (FR-ASS-21/36) | Отдельный или общий LLM endpoint + индексы `assistant_*` |
| **OCR / документы** | ≥ **1 стр/с** на поток; accuracy ≥ **95%**; air-gap (FR-OCR-18/19/22) | OCR runtime; GPU вероятен для Paddle/IDP |
| **Интеграции** | СУЗ (модель B), Oktell (WS/MRCP), AD LDAPS, KUMA | Сетевые доступы + тестовые контуры Заказчика |

До sign-off в `model-selection-v1.md` production-кандидаты моделей = `null`; **не закупать GPU «вслепую»** — сначала TEST без тяжёлого inference, затем замер на выделенном AI-узле.

---

## 4. Рекомендуемая топология

### 4.1. TEST (минимальный контур для интеграций и UI-приёмки)

Одна ВМ (или 2: app + data) достаточна, пока LLM/ASR в stub/dev:

```text
┌─────────────────────────────────────────────────────────────┐
│  VM: sufler-test                                            │
│  ┌──────────────┐  ┌────────────┐  ┌─────────┐  ┌────────┐ │
│  │ Django/ASGI  │  │ Celery     │  │ Redis   │  │ MinIO  │ │
│  │ + static UI  │  │ worker(s)  │  └─────────┘  └────────┘ │
│  └──────┬───────┘  └─────┬──────┘                           │
│         │                │                                  │
│         └────────┬───────┘                                  │
│                  ▼                                          │
│           PostgreSQL 16 + pgvector                          │
│           (+ Vosk ASR process, optional)                    │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
      LDAPS/AD      СУЗ Bitrix      Oktell WS      KUMA HTTP
      (Заказчик)    (тест-копия)    (тест-линия)   (collector)
```

### 4.2. Целевая (нагрузка II.7.4 / 70 ASR / LLM 10 RPS) — ориентир PROD

Разделение ролей (допускается объединение на этапе PoC):

| Роль узла | Назначение | Виртуализация |
|-----------|------------|---------------|
| **app** | Django/ASGI, API, Hub, ingest webhook, Celery | VMware OK |
| **data** | PostgreSQL/pgvector, Redis, MinIO (или объектное СХД банка) | VMware OK |
| **asr** | Потоковое ASR ≥70 сессий | Prefer bare-metal / GPU-host (§10.2 исключение) |
| **llm** | On-prem generative inference (≥10 RPS, 3 профиля) | Prefer bare-metal / GPU-host |
| **ocr** *(опц.)* | Распознавание документов | GPU по результату PoC |

Горизонтальное масштабирование ASR/поиска/LLM — требование FR-CC-11.

---

## 5. Аппаратные требования

### 5.1. DEV (локально у Исполнителя)

| Параметр | Минимум | Рекомендуется |
|----------|---------|---------------|
| CPU | 4 vCPU | 8 vCPU |
| RAM | **8 GB** | 16 GB |
| Диск | 40 GB SSD | 100 GB SSD |
| GPU | не требуется | не требуется |
| ОС | Windows 10/11 + Docker Desktop (WSL2) или Linux | — |

### 5.2. TEST — контур Заказчика (поставка ВМ, этап VII.3)

Конфигурация для текущего стека + интеграций + embedding/ASR **dev**, без production LLM:

| Параметр | Минимум (smoke / INT-T) | Рекомендуется (SUF-T / CHAT-T / ASS-T stub) |
|----------|-------------------------|--------------------------------------------|
| Платформа | VMware, x64 | то же |
| vCPU | **8** | **16** |
| RAM | **32 GB** | **64 GB** |
| Системный диск | 100 GB SSD | 200 GB SSD |
| Data-диск | 200 GB SSD | **500 GB** SSD (модели, индексы, MinIO, логи ≥90 дней) |
| GPU | не обязателен | **1× NVIDIA** с ≥24 GB VRAM — *желательно*, если на стенде сразу гоняют ASR/OCR PoC / не-stub LLM |
| Сеть | 1 Gbit, сегмент банка | то же + маршруты к AD / Bitrix / Oktell / KUMA |

**Ориентир диска под артефакты (TEST):**

| Артефакт | Порядок объёма |
|----------|----------------|
| ОС + Docker images | 20–40 GB |
| Vosk RU (+ EN) | 1–2 GB (small) … **до ~2 GB+** на крупные модели |
| Embedding `multilingual-e5-large` | ~2–3 GB весов + runtime cache |
| pgvector индекс `cc_production` + `assistant_*` | десятки GB (растёт с корпусом СУЗ) |
| MinIO (вложения чата, OCR-файлы) | зависит от политики хранения |
| Audit JSONL / логи | резерв под ротацию ≥90 дней |

### 5.3. Ориентир под договорную нагрузку (PROD / нагрузочный стенд) — **TBD measured**

Пока модели не выбраны, фиксируются **целевые KPI**, а не жёсткий SKU GPU:

| Нагрузка | KPI | Предварительный ориентир железа* |
|----------|-----|----------------------------------|
| ASR 70 потоков | p95 ≤1 с, accuracy ≥90% | отдельный **asr**-узел: 16–32 CPU **или** 1–2× GPU (зависит от кандидата); RAM 64–128 GB |
| 75 операторов суфлёра | p95 подсказки ≤2 с | app 16 vCPU / 32–64 GB + llm ≥10 RPS |
| LLM ≥10 RPS, context до ~8k (ассистент) | p95 ≤2 с | **1–2× GPU** класса data-center (VRAM зависит от quant/модели; часто 48–80 GB суммарно) |
| Ассистент 2000 concurrent | p95 ≤2 с | отдельный scaling llm/app; не укладывать в одну TEST VM §5.2 |
| OCR ≥1 стр/с | accuracy ≥95% | CPU (Tesseract) или GPU (Paddle/IDP) |

\*Ориентиры **не** являются утверждённым sizing. После P1-13 / `llm_load` / OCR-bench обновить таблицу и ModelRegistry.

---

## 6. Программный стек на сервере

| Слой | Версия / продукт | Примечание |
|------|------------------|------------|
| ОС | Linux x64, не EoL | Ubuntu 22.04/24.04 LTS или RHEL/Rocky 9 |
| Контейнеры | Docker Engine 24+ / Podman; Compose v2 | На PROD возможен K8s — вне текущего compose |
| Runtime app | Python **3.12** | образ `backend/Dockerfile` |
| СУБД | PostgreSQL **16** + **pgvector** | init: `infra/postgres/init.sql` |
| Брокер | Redis **7** | AOF включён в compose |
| Object storage | MinIO или S3-совместимое СХД банка | bucket для вложений/OCR |
| Reverse proxy | nginx / HAProxy (Заказчик) | TLS терминация (§4.4.44.1 / §5.1.26.1 — SSL) |
| Node.js | LTS (только CI/build frontend) | на runtime-сервере не обязателен, если отдаётся собранный static |
| Антивирус | ПО Заказчика | §8.10 |
| NTP | синхронизация времени | §9.1.5 → корректные метки audit/KUMA |

---

## 7. Сеть, порты, интеграции

### 7.1. Порты внутри контура AI Hub (по `infra/`)

| Сервис | Порт (контейнер) | Host (dev default) | Назначение |
|--------|------------------|--------------------|------------|
| Backend HTTP/WS | 8000 | 8000 | API, АРМ, Hub |
| PostgreSQL | 5432 | 5432 | БД / pgvector |
| Redis | 6379 | 6379 | Celery broker/result |
| MinIO API | 9000 | 9000 | S3 API |
| MinIO Console | 9001 | 9001 | админ UI (на PROD ограничить) |
| ASR WebSocket (dev) | по конфигурации сервиса | TBD | потоковое распознавание |

На TEST/PROD наружу публиковать только **HTTPS (443)** через reverse proxy Заказчика; БД/Redis/MinIO — во внутреннюю сеть.

### 7.2. Исходящие / входящие к системам банка

| Система | Направление | Протокол / порт (типовой) | Статус |
|---------|-------------|--------------------------|--------|
| **AD / LDAPS** | AI Hub → AD | LDAPS **636** (TLS), CA банка | параметры prod — TBD Заказчик (VII.5 №4) |
| **СУЗ Bitrix** | Bitrix → AI Hub ingest | HTTPS webhook + HMAC | тест-копия Bitrix T+30 |
| **Oktell** | Oktell ↔ AI Hub | WebSocket события / dual-leg audio; резерв MRCP v1/v2 + RTP | тест-линия T+45; binding TBD |
| **KUMA** | AI Hub → collector | HTTPS HTTP sink audit | URL коллектора — Заказчик |
| **Мессенджеры / виджет** | по политике ИБ | HTTPS к API каналов | egress согласовать (VII.5 №20) |
| **Internet (модели, pip)** | — | — | на TEST/PROD **закрыт**; артефакты доставлять offline |

### 7.3. Доступы людей

| Доступ | Срок / условие |
|--------|----------------|
| BelVPN сотрудникам Исполнителя | заявка Исполнителя; заключение ЦКБ |
| Учётные записи на ВМ / sudo / Docker | ДИТ |
| Доступ к тест Bitrix / Oktell | по поручениям протокола |

---

## 8. Хранение, резервное копирование, журналы

| Объект | Требование |
|--------|------------|
| PostgreSQL | ежедневный backup; RPO/RTO — по регламенту ДИТ |
| Volumes MinIO / файлы OCR | включить в бэкап или репликацию СХД |
| Audit / логи ASR | ротация **≥ 90 дней** on-prem; без ПДн в открытом тексте |
| Модели / индексы | версионирование revision + checksum; откат совместимым bundle (`model-selection-v1`) |
| Секреты | не в Git; vault / защищённые переменные окружения Заказчика |

---

## 9. Информационная безопасность (кратко для стенда)

- Размещение **только** в контуре банка (FR-CC-01, FR-UND-02, FR-OCR-22).
- TLS на внешних endpoint; внутренние сервисы — сегментация VLAN/SG.
- RBAC по 13 ролям §2.4; prod-маппинг AD-групп — Заказчик.
- Запрет автоматического fallback в cloud ASR/LLM/OCR.
- Антивирус Заказчика на серверах (§8.10).
- Передача событий ИБ в KUMA (VI.3).
- Перед PROD: air-gap evidence, SBOM, лицензии моделей — gate в `model-selection-v1.md`.

---

## 10. Заявка Заказчику на ВМ TEST (чеклист)

Передать ДИТ вместе с этим документом:

1. **1×** VMware VM: **16 vCPU / 64 GB RAM / 200+500 GB SSD**, Ubuntu 22.04 или 24.04 LTS (или RHEL/Rocky 9).
2. Установка Docker Engine + Compose v2 (или согласованный runtime).
3. Сетевые маршруты: LDAPS AD, тест Bitrix, тест Oktell, KUMA collector; **без** общего Internet egress.
4. TLS-сертификат / запись DNS на reverse proxy для HTTPS UI/API.
5. Учётки Исполнителя (BelVPN + SSH/RDP по политике банка).
6. *(Опционально на том же этапе)* GPU-хост или PCI passthrough ≥24 GB VRAM — если планируется сразу PoC не-stub ASR/LLM/OCR.

**Готовый шаблон заявки ДИТ (T+28):** [`infra/test/server-requirements.md`](../../infra/test/server-requirements.md) — CPU/RAM/GPU/disk/OS + BelVPN, sizing under `approved_dev`.

После выдачи ВМ Исполнитель разворачивает `infra/` + backend, проводит healthcheck и INT-T smoke.

---

## 11. Открытые пункты (обновить после замеров)

| ID | Вопрос | Блокер |
|----|--------|--------|
| SR-01 | Итоговый ASR engine + GPU SKU под 70 потоков | P1-13 load report |
| SR-02 | LLM vendor/model + VRAM под 10 RPS и 2000 users | `llm_load` + sign-off |
| SR-03 | Нужен ли отдельный OCR GPU-узел | P1-51 OCR report |
| SR-04 | Prod LDAPS host/port/CA | VII.5 №4 |
| SR-05 | Oktell WS vs MRCP binding, порты RTP | VII.5 №1–2 |
| SR-06 | Разрешённый egress для ассистента / виджета | VII.5 №20 |
| SR-07 | HA / 2-й ЦОД | проектное решение §11.1.1 |

---

## 12. Связанные документы

| Документ | Роль |
|----------|------|
| [TZ-unified-v1.8%20(МИХ).docx](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) §VII.3, II.7.4 | договорные сроки стенда и нагрузка |
| [prilozhenie-1.md](../sources/technical-requirements/prilozhenie-1.md) §10 | системные требования банка |
| [model-selection-v1.md](model-selection-v1.md) | запрет prod sizing до measured |
| [infra/README.md](../../infra/README.md) | текущий Docker Compose |
| [backend/README.md](../../backend/README.md) | DEV prerequisites |
| [asr-candidates.md](../benchmarks/asr-candidates.md) | кандидаты ASR / GPU |

---

## История

| Дата | Изменение |
|------|-----------|
| 2026-07-21 | Первая редакция: DEV / TEST / PROD-ориентир по ТЗ v1.4 и текущему compose-стеку |
