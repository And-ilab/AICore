#!/usr/bin/env bash
# TEST AI inference tier: deployment profile=test, ASR + LLM gateway + suggest smoke.
#
# Prerequisites: prod-like stack up (includes `asr` stub service).
#
# Usage (from infra/test):
#   ./verify-inference-tier.sh
#   ./verify-inference-tier.sh --skip-asr
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${ROOT}/docker-compose.prod-like.yml"
ENV_FILE="${ROOT}/.env"
PROJECT="sufler-test"

die() { echo "ERROR: $*" >&2; exit 1; }
[[ -f "${ENV_FILE}" ]] || die "Missing ${ENV_FILE}"

compose() {
  docker compose -p "${PROJECT}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

extra_args=()
case "${1:---all}" in
  --skip-asr) extra_args+=(--skip-asr) ;;
  --all|"") ;;
  *) die "Unknown option: $1" ;;
esac

echo "=== ASR container health ==="
compose ps asr | grep -qi healthy || compose ps asr
compose exec -T asr \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8764/health', timeout=3)" \
  || die "ASR /health failed"
echo "OK: asr /health"

echo "=== Inference verify (profile=test) ==="
compose exec -T backend python manage.py verify_inference_tier "${extra_args[@]}"
echo "OK: inference tier ready"
