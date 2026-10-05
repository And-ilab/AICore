#!/usr/bin/env bash
# Generate self-signed TLS certs for TEST edge nginx (dev / lab OK).
# Bank TEST with ДИТ CA: replace files in certs/ — do not commit private keys.
#
# Usage (from infra/test):
#   ./gen-self-signed-cert.sh
#   ./gen-self-signed-cert.sh ai-hub-test.bank.local
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${ROOT}/certs"
CN="${1:-localhost}"
DAYS="${CERT_DAYS:-825}"

mkdir -p "${CERT_DIR}"
umask 077

KEY="${CERT_DIR}/privkey.pem"
CRT="${CERT_DIR}/fullchain.pem"

if [[ -f "${KEY}" || -f "${CRT}" ]]; then
  echo "Certs already exist in ${CERT_DIR} — remove them first to regenerate."
  ls -la "${CERT_DIR}"
  exit 0
fi

command -v openssl >/dev/null || { echo "ERROR: openssl required" >&2; exit 1; }

# Avoid Git Bash rewriting /CN=... into a Windows path.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "${KEY}" \
  -out "${CRT}" \
  -days "${DAYS}" \
  -subj "/CN=${CN}/O=Sufler-TEST/OU=AI-Hub" \
  -addext "subjectAltName=DNS:${CN},DNS:localhost,IP:127.0.0.1"

chmod 600 "${KEY}"
chmod 644 "${CRT}"

echo "Wrote:"
echo "  ${CRT}"
echo "  ${KEY}"
echo "Mount into edge nginx (compose service). Do NOT commit privkey.pem."
echo "Smoke: curl -k https://${CN}/health/"
