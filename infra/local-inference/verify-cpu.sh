#!/usr/bin/env bash
# Smoke-check Ollama + embedding.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA="$(cd "${ROOT}/.." && pwd)"
COMPOSE_DIR="${COMPOSE_DIR:-${INFRA}}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${COMPOSE_DIR}/.env}"
PROJECT="${COMPOSE_PROJECT_NAME:-sufler}"
WAIT_SECONDS="${VERIFY_WAIT_SECONDS:-300}"
EXTRA_COMPOSE_FILE="${EXTRA_COMPOSE_FILE:-}"

cd "${COMPOSE_DIR}"
[[ -f "${ENV_FILE}" ]] || { echo "ERROR: missing ${ENV_FILE}" >&2; exit 1; }

compose() {
  local args=(
    -p "${PROJECT}"
    --env-file "${ENV_FILE}"
    -f "${COMPOSE_FILE}"
  )
  if [[ -n "${EXTRA_COMPOSE_FILE}" ]]; then
    args+=(-f "${EXTRA_COMPOSE_FILE}")
  elif [[ "${COMPOSE_FILE}" == "docker-compose.yml" && -f "${COMPOSE_DIR}/local-inference/docker-compose.cpu.yml" ]]; then
    args+=(-f local-inference/docker-compose.cpu.yml)
    if [[ "${FRONTEND_MODE:-prod}" == "prod" && -f "${COMPOSE_DIR}/docker-compose.frontend-prod.yml" ]]; then
      args+=(-f docker-compose.frontend-prod.yml)
    fi
  fi
  COMPOSE_PROFILES=cpu-inference docker compose "${args[@]}" "$@"
}

die() { echo "ERROR: $*" >&2; exit 1; }

wait_http() {
  local service="$1"
  local url="$2"
  local label="$3"
  local deadline=$((SECONDS + WAIT_SECONDS))
  echo "Waiting for ${label} (${url}, timeout ${WAIT_SECONDS}s)…"
  while (( SECONDS < deadline )); do
    if compose exec -T "${service}" \
      python -c "import urllib.request; urllib.request.urlopen('${url}', timeout=3).read()" \
      >/dev/null 2>&1; then
      echo "OK: ${label} is up"
      return 0
    fi
    # Ollama image has no python — use ollama CLI / wget inside container
    if [[ "${service}" == "ollama" ]]; then
      if compose exec -T ollama ollama list >/dev/null 2>&1; then
        echo "OK: ${label} is up"
        return 0
      fi
    fi
    compose ps "${service}" || true
    sleep 5
  done
  echo "---- ${service} logs (tail) ----" >&2
  compose logs --tail=80 "${service}" >&2 || true
  die "${label} not ready within ${WAIT_SECONDS}s"
}

echo "=== container status ==="
compose ps ollama embedding backend || true

echo "=== ollama ==="
wait_http ollama "http://127.0.0.1:11434/api/tags" "ollama"
compose exec -T ollama ollama list || die "ollama list failed"

echo "=== ollama OpenAI /v1/models ==="
compose exec -T backend \
  python -c "
import os, urllib.request
oa = os.environ.get('OPENAI_BASE_URL', 'http://ollama:11434/v1').rstrip('/')
print(urllib.request.urlopen(oa + '/models', timeout=10).read().decode()[:500])
" || die "OpenAI /v1/models via backend failed"

echo "=== embedding /health ==="
wait_http embedding "http://127.0.0.1:8090/health" "embedding"

echo "=== backend → ollama / embedding ==="
compose exec -T backend \
  python -c "
import os, urllib.request
oa = os.environ.get('OPENAI_BASE_URL', 'http://ollama:11434/v1').rstrip('/')
emb = os.environ.get('EMBEDDING_BASE_URL', 'http://embedding:8090').rstrip('/')
ollama = os.environ.get('OLLAMA_BASE_URL', 'http://ollama:11434').rstrip('/')
print('ollama tags', urllib.request.urlopen(ollama + '/api/tags', timeout=5).status)
print('openai', urllib.request.urlopen(oa + '/models', timeout=5).status)
print('embedding', urllib.request.urlopen(emb + '/health', timeout=5).status)
print('OPENAI_MODEL', os.environ.get('OPENAI_MODEL'))
" || die "backend cannot reach inference services"

echo "OK: Ollama + embedding ready"
