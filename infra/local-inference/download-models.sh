#!/usr/bin/env bash
# Download CPU GGUF models (+ optional E5 prefetch) for Linux / Docker volumes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${ROOT}/../.." && pwd)"
MODELS_DIR="${MODELS_DIR:-${REPO}/models}"
LLM_DIR="${MODELS_DIR}/llm"
HF_CACHE="${MODELS_DIR}/hf-cache"
PREFETCH_E5="${PREFETCH_E5:-0}"

mkdir -p "${LLM_DIR}" "${HF_CACHE}"
[[ -d "${LLM_DIR}" && -w "${LLM_DIR}" ]] || {
  echo "ERROR: cannot write to ${LLM_DIR}" >&2
  exit 1
}

# Prefer native curl — Snap curl often cannot write outside its sandbox.
resolve_curl() {
  local candidate
  for candidate in /usr/bin/curl /bin/curl; do
    if [[ -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  if command -v curl >/dev/null 2>&1; then
    local resolved
    resolved="$(command -v curl)"
    # Skip snap wrapper when a better option may still fail; caller has python fallback.
    if [[ "${resolved}" == /snap/* ]] || [[ -L "${resolved}" && "$(readlink -f "${resolved}" 2>/dev/null || true)" == /snap/* ]]; then
      return 1
    fi
    echo "${resolved}"
    return 0
  fi
  return 1
}

download_with_curl() {
  local url="$1"
  local tmp="$2"
  local curl_bin="$3"
  "${curl_bin}" -fL --retry 3 --retry-delay 2 --connect-timeout 30 \
    -o "${tmp}" "${url}"
}

download_with_python() {
  local url="$1"
  local tmp="$2"
  python3 - "${url}" "${tmp}" <<'PY'
import sys
import urllib.request

url, out = sys.argv[1], sys.argv[2]
req = urllib.request.Request(url, headers={"User-Agent": "sufler-download-models/1.0"})
with urllib.request.urlopen(req, timeout=600) as resp, open(out, "wb") as fh:
    while True:
        chunk = resp.read(1024 * 1024)
        if not chunk:
            break
        fh.write(chunk)
print("python download ok", out, flush=True)
PY
}

download() {
  local url="$1"
  local out="$2"
  if [[ -f "${out}" && -s "${out}" ]]; then
    echo "OK (exists): ${out}"
    return 0
  fi
  echo "Downloading → ${out}"

  local tmp
  tmp="$(mktemp "${TMPDIR:-/tmp}/sufler-gguf.XXXXXX")"
  # shellcheck disable=SC2064
  trap "rm -f '${tmp}'" RETURN

  local ok=0
  local curl_bin=""
  if curl_bin="$(resolve_curl)"; then
    echo "Using curl: ${curl_bin}"
    if download_with_curl "${url}" "${tmp}" "${curl_bin}"; then
      ok=1
    else
      echo "WARN: curl failed, trying python3…" >&2
    fi
  else
    echo "WARN: no usable native curl (snap curl is skipped), using python3…" >&2
  fi

  if [[ "${ok}" -ne 1 ]]; then
    download_with_python "${url}" "${tmp}"
  fi

  if [[ ! -s "${tmp}" ]]; then
    echo "ERROR: empty download for ${url}" >&2
    return 1
  fi

  # Hugging Face sometimes returns a tiny HTML error page.
  local size
  size="$(wc -c < "${tmp}" | tr -d ' ')"
  if [[ "${size}" -lt 1048576 ]]; then
    echo "ERROR: download too small (${size} bytes) — not a GGUF. URL may need auth or redirect failed:" >&2
    echo "  ${url}" >&2
    head -c 200 "${tmp}" >&2 || true
    echo >&2
    return 1
  fi

  mv -f "${tmp}" "${out}"
  trap - RETURN
  echo "OK: ${out} ($(du -h "${out}" | awk '{print $1}'))"
}

download \
  "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf" \
  "${LLM_DIR}/qwen2.5-1.5b-instruct-q4_k_m.gguf"

download \
  "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf" \
  "${LLM_DIR}/qwen2.5-3b-instruct-q4_k_m.gguf"

if [[ "${PREFETCH_E5}" == "1" ]]; then
  echo "Prefetching intfloat/multilingual-e5-large into ${HF_CACHE}"
  docker run --rm \
    -e HF_HOME=/cache \
    -e TRANSFORMERS_CACHE=/cache \
    -v "${HF_CACHE}:/cache" \
    python:3.12-slim-bookworm \
    bash -lc '
      pip install -q --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 \
        && pip install -q sentence-transformers==3.4.1 \
        && python -c "from sentence_transformers import SentenceTransformer as S; m=S(\"intfloat/multilingual-e5-large\"); print(\"dim\", len(m.encode([\"query: test\"], normalize_embeddings=True)[0]))"
    '
fi

echo "Done. Mount ${MODELS_DIR} into llm/embedding containers."
echo "  GGUF: ${LLM_DIR}"
echo "  HF:   ${HF_CACHE}"
