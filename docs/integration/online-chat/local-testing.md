# Локальная проверка онлайн-чата

## Запуск

```bash
cd infra
cp .env.example .env
# Заменить обязательные пароли в .env
docker compose up --build -d
docker compose ps
```

Основные адреса:

- портал и модуль: <http://localhost:5173/online-chat>
- операторы (для супервизора): <http://localhost:5173/online-chat/operators>
- симулятор: <http://localhost:5173/online-chat/simulator>
- супервизор: <http://localhost:5173/online-chat/supervisor>
- управление: <http://localhost:5173/online-chat/admin>
- клиентский виджет: <http://localhost:5173/widget/sample.html>
- тестовые письма: <http://localhost:8025>

## DeepSeek + Telegram (локальное демо)

В `infra/.env` (не коммитить секреты):

```bash
MODEL_GATEWAY_MODE=openai
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-...
OPENAI_MODEL=deepseek-chat
TELEGRAM_BOT_TOKEN=...
```

Перезапустить backend/celery после изменения `.env`.

### База знаний для демо-вопросов

```bash
# из корня репозитория
python tools/seed_manual_kb.py   # или через docker compose exec backend
```

Файлы: `local/kb/manual/limity-snyatiya-nalichnyh.txt`, `komissii-bankomatov.txt`.

Демо-вопросы:

1. Виджет: «Какой суточный лимит снятия наличных в банкоматах Беларусбанка?»
2. Telegram (тот же телефон): «Какая комиссия за снятие в банкоматах других банков?»

### Telegram (long polling, без ngrok)

Для тестового контура бот ходит в Telegram через **getUpdates** (сервис `telegram-poller`). HTTPS и ngrok не нужны.

В `infra/.env`:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_MODE=polling
```

Поднять / перезапустить poller:

```bash
cd infra
docker compose up -d telegram-poller
docker compose logs -f telegram-poller
```

При старте poller вызывает `deleteWebhook` (если раньше стоял webhook через ngrok) и начинает long poll. Напишите боту `/start` — в логах должно появиться `telegram_poll handled`.

Сценарий бота: приветствие → вопрос → ФИО → телефон → диалог в общей очереди АРМ.

Опционально без Docker:

```bash
cd backend
export TELEGRAM_BOT_TOKEN=... TELEGRAM_MODE=polling
python manage.py poll_telegram
```

Webhook + ngrok по-прежнему поддерживаются: `TELEGRAM_MODE=webhook` и `tools/set_telegram_webhook.py` (см. ниже).

### Telegram webhook через ngrok (альтернатива)

Важно: сам по себе ngrok **ничего не регистрирует** в Telegram. Нужны `TELEGRAM_MODE=webhook` и `setWebhook`.

```bash
# 1) туннель на backend (порт из BACKEND_PORT_HOST, обычно 8001)
ngrok http 8001

# 2) зарегистрировать webhook (подставьте HTTPS URL из ngrok)
cd ..   # корень репозитория
export TELEGRAM_BOT_TOKEN='...'   # тот же, что в infra/.env
# в .env: TELEGRAM_MODE=webhook  (и остановить telegram-poller)
python3 tools/set_telegram_webhook.py https://XXXX.ngrok-free.app

# или одной командой:
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook?url=https://XXXX.ngrok-free.app/api/v1/channels/telegram/webhook/&drop_pending_updates=true"
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
```

Проверка: после `/start` в ngrok должен появиться `POST /api/v1/channels/telegram/webhook/`.

Сценарий бота: приветствие → вопрос → ФИО → телефон → диалог в общей очереди АРМ.

### База знаний для суфлёра (`cc_production`)

Суфлёр читает индекс `cc_production` (таблица `CCProductionChunk`), а не файлы из `local/kb/manual`.
Если chunks = 0 или relevance < threshold — подсказки пустые («нет релевантных статей»).

Локальный демо-сид (3 статьи + порог 0.45 под stub-эмбеддинги):

```bash
cd infra
docker compose cp ../tools/seed_cc_demo_kb.py backend:/tmp/seed_cc_demo_kb.py
docker compose exec backend python /tmp/seed_cc_demo_kb.py
```

Проверка: виджет → вопрос про лимит снятия → в АРМ суфлёр должен вернуть подсказку.

Телефон нормализуется к единому виду (`8029…` / `29…` → `+37529…`); иностранные номера сохраняются как `+<digits>`.

### Режимы распределения

В меню АРМ → «Настройки»:

- **Только авто** — автоназначение по FIFO (`last_client_message_at`);
- **Ручной + авто (10 сек)** — после закрытия диалога 10 секунд на ручной выбор, иначе авто.

Кнопка «Взять диалог» доступна в общей очереди (лимит 3/3 по ТЗ соблюдается).

### Супервизор

Три вкладки: **Чаты** (своя пустая АРМ, без автоназначения) · **Операторы** · **Супервизор**.
В просмотре АРМ оператора — кнопка «Взять на себя». Перевод: оператор или супервизор.

## Несколько операторов и клиентов

1. Открыть `/online-chat/simulator`.
2. Выбрать готовый сценарий или задать число операторов и клиентов.
3. Нажать «Создать сценарий».
4. Ссылки операторов и клиентов открывать в отдельных окнах. Каждое окно
   представляет отдельного человека.
5. Панель супервизора обновляется автоматически; кнопка «Запустить
   маршрутизацию» повторно распределяет очередь.

Для изоляции cookie и `sessionStorage` удобно использовать обычное окно,
инкогнито и разные профили браузера.

## Что проверять вручную

1. Новые обращения распределяются только на операторов со статусом «Онлайн»
   и не превышают установленный лимит.
2. При смене статуса оператора очередь перераспределяется.
3. Супервизор видит очередь, нагрузку и может перевести диалог.
4. После отключения клиента обращение получает статус offline, после
   настроенного таймаута — lost.
5. Вложения принимаются только разрешённых типов и размеров.
6. После закрытия обязательна тема, затем доступны оценка и отправка
   транскрипта в Mailpit.
7. Изменения размещения виджета (приветствие, цвет, поля формы, домены)
   применяются после перезагрузки страницы виджета.

## Автоматические проверки

```bash
cd infra
docker compose run --rm --no-deps \
  -v "$PWD/../backend:/app" \
  -e POSTGRES_HOST= \
  -e AUTH_BACKEND=mock_ldap \
  backend python manage.py test online_chat

cd ../frontend
npm run build
```

Проверка миграций:

```bash
cd ../infra
docker compose run --rm --no-deps \
  -v "$PWD/../backend:/app" \
  -e POSTGRES_HOST= \
  -e AUTH_BACKEND=mock_ldap \
  backend python manage.py makemigrations --check --dry-run
```

## Переключение на TEST/prod

Код не содержит токенов и адресов внешних систем. На стенде заполняются
переменные окружения:

- `AUTH_BACKEND=ldaps` и `AUTH_LDAP_*`;
- SMTP: `EMAIL_HOST`, `EMAIL_PORT`, TLS/SSL, `ONLINE_CHAT_FROM_EMAIL`;
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`;
- `VIBER_AUTH_TOKEN`;
- `VK_ACCESS_TOKEN`, `VK_WEBHOOK_SECRET`, `OK_ACCESS_TOKEN`;
- `ONLINE_CHAT_API_CHANNEL_SIGNING_SECRET`;
- MinIO: `MINIO_ENDPOINT`, учётные данные и `MINIO_ONLINE_CHAT_BUCKET`;
- Redis/PostgreSQL и внешний TLS/FQDN.

После заполнения переменных повторяются те же сценарии симулятора и CHAT-T.
