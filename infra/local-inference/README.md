# Local CPU inference — Ollama + embeddings

Простой стек: **официальный контейнер Ollama** для LLM и отдельный сервис embedding.
Без кастомного llama-manager и без скриптов переключения моделей.

## Быстрый старт (сервер / CPU)

`up-cpu.sh` по умолчанию поднимает **production frontend** (nginx + `vite build`), не Vite.
Иначе в Network видны `main.tsx` / `@react-refresh` и 504 → белый экран.

```bash
cd infra
./local-inference/up-cpu.sh
# скачать модель:
docker compose --profile cpu-inference \
  -f docker-compose.yml -f local-inference/docker-compose.cpu.yml \
  -f docker-compose.frontend-prod.yml \
  exec ollama ollama pull qwen2.5:3b

./local-inference/verify-cpu.sh
```

Локально с Vite HMR: `FRONTEND_MODE=vite ./local-inference/up-cpu.sh`

В `infra/.env` скрипт пропишет:

```text
MODEL_GATEWAY_MODE=openai
OPENAI_BASE_URL=http://ollama:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=qwen2.5:3b
OLLAMA_BASE_URL=http://ollama:11434
EMBEDDING_MODE=http
EMBEDDING_BASE_URL=http://embedding:8090
```

Порты на хосте: Ollama `:11434`, embedding `:8090`.

## Смена / проба моделей

Только стандартный CLI Ollama:

```bash
# список
docker compose --profile cpu-inference \
  -f docker-compose.yml -f local-inference/docker-compose.cpu.yml \
  exec ollama ollama list

# скачать другую
docker compose --profile cpu-inference \
  -f docker-compose.yml -f local-inference/docker-compose.cpu.yml \
  exec ollama ollama pull llama3.2:3b

# активировать в чате — имя в .env и рестарт backend
# OPENAI_MODEL=llama3.2:3b
docker compose restart backend
```

`up-cpu.sh` / `deploy.sh` **не затирают** уже заданный `OPENAI_MODEL` (default только если ключа нет).

В чате ассистента — селект **Модель**: список из `ollama list` на сервере; выбор сохраняется в runtime (без рестарта).  
`OPENAI_MODEL` в `.env` — стартовый default, пока пользователь не выбрал другое в UI.

С хоста (если порт проброшен): `ollama pull …` / `http://127.0.0.1:11434`.

## Модель в RAM / белый экран после деплоя

По умолчанию `OLLAMA_KEEP_ALIVE=30m` (не `-1`).  
На слабом сервере `-1` + embedding + redeploy часто даёт **OOM** → белый экран UI, помогает только reboot.

Если RAM достаточно и нужна модель всегда в памяти — в `.env`:

```text
OLLAMA_KEEP_ALIVE=-1
```

затем:

```bash
docker compose --profile cpu-inference \
  -f docker-compose.yml -f local-inference/docker-compose.cpu.yml \
  up -d --force-recreate ollama
```

Deploy workflow **больше не** гоняет `download-models.sh` (старые GGUF).

## TEST prod-like

```bash
cd infra/test
# в .env:
# MODEL_GATEWAY_MODE=openai
# OPENAI_BASE_URL=http://ollama:11434/v1
# OPENAI_MODEL=qwen2.5:3b
# OLLAMA_BASE_URL=http://ollama:11434
./deploy.sh up --cpu-inference
docker compose --profile cpu-inference exec ollama ollama pull qwen2.5:3b
```

## Embedding

Сервис `embedding` (E5-large) без изменений. Веса кэшируются в `infra/models` / volume.

Опционально прогреть кэш:

```bash
# PREFETCH_E5=1 ./local-inference/download-models.sh
```

## Устаревшее

Сервис `llm` (порт **8080**, образ `sufler-llm`) **удалён** из compose.
При `up` / `deploy.sh` используется `--remove-orphans` — старый `sufler-llm-1` снимается сам.

`llm_manager.py`, `start-llm*.ps1`, `Dockerfile.llm` — не используются; LLM только `ollama/ollama` (:11434).
