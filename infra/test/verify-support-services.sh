#!/usr/bin/env bash
# TEST support tier: Redis broker + Celery worker + MinIO upload/download.
#
# Prerequisites: prod-like stack up (`./deploy.sh`).
#
# Usage (from infra/test):
#   ./verify-support-services.sh
#   ./verify-support-services.sh --broker-only   # redis + minio, skip worker task
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

mode="${1:---all}"

echo "=== Redis ==="
compose exec -T redis redis-cli ping | grep -q PONG \
  || die "redis-cli ping failed"
echo "OK: redis-cli PONG"

echo "=== MinIO live ==="
compose exec -T minio curl -sf http://127.0.0.1:9000/minio/health/live >/dev/null \
  || die "MinIO health/live failed"
echo "OK: minio /minio/health/live"

case "${mode}" in
  --broker-only)
    echo "=== Backend: broker + object store (no worker) ==="
    compose exec -T backend python manage.py verify_support_services --skip-celery-worker
    ;;
  --all|"")
    echo "=== Celery inspect ==="
    compose exec -T celery-worker \
      celery -A sufler inspect ping --timeout=10 2>/dev/null | grep -qi pong \
      || die "celery inspect ping failed"
    echo "OK: celery inspect pong"

    echo "=== Backend: broker + worker task + MinIO round-trip ==="
    compose exec -T backend python manage.py verify_support_services
    ;;
  *)
    die "Unknown option: ${mode} (use --all|--broker-only)"
    ;;
esac

echo "OK: support services ready (redis + minio + celery)"
