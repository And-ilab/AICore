#!/usr/bin/env bash
# PostgreSQL backup stub for bank TEST (data tier).
#
# Stub only — not a ДИТ-approved PROD schedule. Replace RPO/RTO with bank policy.
# Writes logical dumps under infra/test/backups/ (gitignored).
#
# Usage (from infra/test):
#   ./backup-postgres.sh --dry-run    # print plan, exit 0 (no Docker required)
#   ./backup-postgres.sh             # pg_dump via compose service `postgres`
#   ./backup-postgres.sh --list       # list local dump files
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${ROOT}/docker-compose.prod-like.yml"
ENV_FILE="${ROOT}/.env"
PROJECT="sufler-test"
BACKUP_DIR="${ROOT}/backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${BACKUP_DIR}/sufler-test-${STAMP}.sql.gz"

die() { echo "ERROR: $*" >&2; exit 1; }

compose() {
  docker compose -p "${PROJECT}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

load_db_env() {
  [[ -f "${ENV_FILE}" ]] || die "Missing ${ENV_FILE}"
  # shellcheck disable=SC1090
  set -a
  # shellcheck disable=SC1091
  source "${ENV_FILE}"
  set +a
  POSTGRES_DB="${POSTGRES_DB:-sufler}"
  POSTGRES_USER="${POSTGRES_USER:-sufler}"
}

cmd="${1:---run}"

case "${cmd}" in
  --dry-run|-n)
    POSTGRES_DB=sufler
    POSTGRES_USER=sufler
    if [[ -f "${ENV_FILE}" ]]; then
      # shellcheck disable=SC1090
      set -a
      # shellcheck disable=SC1091
      source "${ENV_FILE}"
      set +a
      POSTGRES_DB="${POSTGRES_DB:-sufler}"
      POSTGRES_USER="${POSTGRES_USER:-sufler}"
    fi
    mkdir -p "${BACKUP_DIR}"
    cat <<EOF
[backup-postgres STUB — dry-run]
Would run:
  docker compose -p ${PROJECT} -f ${COMPOSE_FILE} exec -T postgres \\
    pg_dump -U ${POSTGRES_USER} -d ${POSTGRES_DB} --no-owner --format=plain \\
    | gzip -c > ${BACKUP_DIR}/sufler-test-<UTC>.sql.gz

Restore hint (manual):
  gunzip -c <dump>.sql.gz | docker compose … exec -T postgres \\
    psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

Bank note: schedule / retention / encryption = bank DIT policy (docs/delivery/ra.md section 9).
EOF
    exit 0
    ;;
  --list|-l)
    mkdir -p "${BACKUP_DIR}"
    ls -la "${BACKUP_DIR}" || true
    exit 0
    ;;
  --run|"")
    load_db_env
    command -v docker >/dev/null || die "docker not found"
    mkdir -p "${BACKUP_DIR}"
    echo "Dumping ${POSTGRES_DB} → ${OUT_FILE}"
    compose exec -T postgres \
      pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --no-owner --format=plain \
      | gzip -c > "${OUT_FILE}"
    echo "OK: ${OUT_FILE} ($(wc -c < "${OUT_FILE}" | tr -d ' ') bytes)"
    ;;
  -h|--help)
    sed -n '2,20p' "$0"
    ;;
  *)
    die "Unknown option: ${cmd} (use --dry-run|--list|--run)"
    ;;
esac
