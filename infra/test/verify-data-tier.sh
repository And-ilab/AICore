#!/usr/bin/env bash
# TEST data tier: migrate → ensure pgvector indexes → verify backend DB connection.
#
# Usage (from infra/test, stack must be up):
#   ./verify-data-tier.sh
#   ./verify-data-tier.sh --sql-only   # apply ensure_pgvector.sql only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${ROOT}/docker-compose.prod-like.yml"
ENV_FILE="${ROOT}/.env"
SQL_FILE="${ROOT}/sql/ensure_pgvector.sql"
PROJECT="sufler-test"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "${ENV_FILE}" ]] || die "Missing ${ENV_FILE}"
[[ -f "${SQL_FILE}" ]] || die "Missing ${SQL_FILE}"

# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1091
source "${ENV_FILE}"
set +a
POSTGRES_DB="${POSTGRES_DB:-sufler}"
POSTGRES_USER="${POSTGRES_USER:-sufler}"

compose() {
  docker compose -p "${PROJECT}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

apply_sql() {
  echo "Applying ${SQL_FILE}…"
  compose exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    < "${SQL_FILE}"
}

verify_sql() {
  echo "Verifying extension + HNSW index…"
  compose exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';" \
    -c "SELECT indexname FROM pg_indexes WHERE tablename='cc_production' AND indexname='cc_prod_embedding_hnsw_idx';" \
    | tee /dev/stderr | grep -q cc_prod_embedding_hnsw_idx \
    || die "HNSW index cc_prod_embedding_hnsw_idx missing"
  echo "OK: pgvector + cc_prod_embedding_hnsw_idx"
}

mode="${1:---all}"

case "${mode}" in
  --sql-only)
    apply_sql
    verify_sql
    ;;
  --all|"")
    echo "Running Django migrations on backend…"
    compose exec -T backend python manage.py migrate --noinput
    apply_sql
    verify_sql
    echo "Backend connection + index check…"
    compose exec -T backend python manage.py verify_data_tier
    echo "OK: data tier ready"
    ;;
  *)
    die "Unknown option: ${mode}"
    ;;
esac
