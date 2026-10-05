#!/usr/bin/env bash
# Bring up Sufler + Ollama + embedding on Linux (no custom LLM scripts).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA="$(cd "${ROOT}/.." && pwd)"
ENV_FILE="${INFRA}/.env"
FALLBACK_MODEL="qwen2.5:3b"

cd "${INFRA}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: missing ${ENV_FILE}" >&2
  exit 1
fi

set_env() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "${ENV_FILE}"; then
    tmp="${ENV_FILE}.tmp.$$"
    awk -v k="${key}" -v v="${value}" '
      BEGIN { FS="="; OFS="=" }
      $1==k { print k, v; next }
      { print }
    ' "${ENV_FILE}" > "${tmp}"
    mv "${tmp}" "${ENV_FILE}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

# Only write if key is missing or empty — never clobber OPENAI_MODEL on redeploy.
set_env_default() {
  local key="$1"
  local value="$2"
  local current=""
  if grep -qE "^${key}=" "${ENV_FILE}"; then
    current="$(grep -E "^${key}=" "${ENV_FILE}" | head -n1 | cut -d= -f2-)"
    if [[ -n "${current}" ]]; then
      return 0
    fi
  fi
  set_env "${key}" "${value}"
}

env_get() {
  local key="$1"
  grep -E "^${key}=" "${ENV_FILE}" | head -n1 | cut -d= -f2- || true
}

set_env MODEL_GATEWAY_MODE openai
set_env OPENAI_BASE_URL http://ollama:11434/v1
set_env OPENAI_API_KEY ollama
# Preserve user's model (e.g. llama3.2:3b); default only on first setup.
set_env_default OPENAI_MODEL "${OPENAI_MODEL:-${OLLAMA_MODEL:-${FALLBACK_MODEL}}}"
set_env OLLAMA_BASE_URL http://ollama:11434
set_env OPENAI_TIMEOUT_SECONDS "${OPENAI_TIMEOUT_SECONDS:-600}"
set_env EMBEDDING_MODE http
set_env EMBEDDING_BASE_URL http://embedding:8090
set_env EMBEDDING_MODEL intfloat/multilingual-e5-large
set_env EMBEDDING_DIMENSIONS 1024
set_env EMBEDDING_TIMEOUT_SECONDS "${EMBEDDING_TIMEOUT_SECONDS:-180}"
set_env ASSISTANT_MAX_TOKENS "${ASSISTANT_MAX_TOKENS:-256}"
set_env COMPOSE_PROFILES cpu-inference

ACTIVE_MODEL="$(env_get OPENAI_MODEL)"
ACTIVE_MODEL="${ACTIVE_MODEL:-${FALLBACK_MODEL}}"

export COMPOSE_PROFILES=cpu-inference
# Prod SPA (nginx) by default — Vite HMR on the server causes white screens (504 on react.js).
# Local Vite: FRONTEND_MODE=vite ./local-inference/up-cpu.sh
FRONTEND_MODE="${FRONTEND_MODE:-prod}"
COMPOSE_FILES=(
  -f docker-compose.yml
  -f local-inference/docker-compose.cpu.yml
)
if [[ "${FRONTEND_MODE}" == "prod" ]]; then
  COMPOSE_FILES+=(-f docker-compose.frontend-prod.yml)
fi

# --remove-orphans drops legacy sufler-llm-1 (old llama.cpp on :8080)
docker compose \
  --env-file "${ENV_FILE}" \
  "${COMPOSE_FILES[@]}" \
  up -d --build --remove-orphans "$@"

echo
echo "Stack started. Pull / switch models with plain Ollama CLI:"
echo "  docker compose --profile cpu-inference -f docker-compose.yml -f local-inference/docker-compose.cpu.yml exec ollama ollama pull ${ACTIVE_MODEL}"
echo "  docker compose --profile cpu-inference -f docker-compose.yml -f local-inference/docker-compose.cpu.yml exec ollama ollama list"
echo
echo "Active chat model = OPENAI_MODEL in .env → ${ACTIVE_MODEL}"
echo "Change model: edit OPENAI_MODEL in .env, then docker compose restart backend"
echo "Verify: ./local-inference/verify-cpu.sh"
