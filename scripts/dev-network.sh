#!/usr/bin/env bash

set -euo pipefail

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly CERTIFICATE_DIR="${PROJECT_ROOT}/.certs"
readonly CERTIFICATE_PATH="${CERTIFICATE_DIR}/dev.crt"
readonly KEY_PATH="${CERTIFICATE_DIR}/dev.key"
readonly OPENSSL_CONFIG="${CERTIFICATE_DIR}/openssl.cnf"

find_lan_ip() {
  local address=""

  if command -v ipconfig >/dev/null 2>&1; then
    address="$(ipconfig getifaddr en0 2>/dev/null || true)"
    [[ -n "${address}" ]] || address="$(ipconfig getifaddr en1 2>/dev/null || true)"
  elif command -v hostname >/dev/null 2>&1; then
    address="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi

  echo "${CROSS_TALKER_LAN_IP:-${address}}"
}

write_openssl_config() {
  local lan_ip="$1"

  {
    echo "[req]"
    echo "distinguished_name = distinguished_name"
    echo "x509_extensions = extensions"
    echo "prompt = no"
    echo
    echo "[distinguished_name]"
    echo "CN = cross-talker.local"
    echo
    echo "[extensions]"
    echo "subjectAltName = @subject_alt_names"
    echo "keyUsage = critical, digitalSignature, keyEncipherment"
    echo "extendedKeyUsage = serverAuth"
    echo
    echo "[subject_alt_names]"
    echo "DNS.1 = localhost"
    echo "DNS.2 = cross-talker.local"
    echo "IP.1 = 127.0.0.1"
    if [[ -n "${lan_ip}" ]]; then
      echo "IP.2 = ${lan_ip}"
    fi
  } > "${OPENSSL_CONFIG}"
}

generate_certificate() {
  local lan_ip="$1"

  mkdir -p "${CERTIFICATE_DIR}"
  write_openssl_config "${lan_ip}"
  openssl req \
    -x509 \
    -nodes \
    -newkey rsa:2048 \
    -days 30 \
    -keyout "${KEY_PATH}" \
    -out "${CERTIFICATE_PATH}" \
    -config "${OPENSSL_CONFIG}" \
    >/dev/null 2>&1
  chmod 600 "${KEY_PATH}"
}

choose_frontend_command() {
  if command -v pnpm >/dev/null 2>&1; then
    FRONTEND_COMMAND=(pnpm dev --hostname 0.0.0.0)
  elif command -v npm >/dev/null 2>&1; then
    FRONTEND_COMMAND=(npm run dev -- --hostname 0.0.0.0)
  else
    echo "Neither pnpm nor npm is available." >&2
    exit 1
  fi
}

cleanup() {
  trap - EXIT INT TERM
  kill -TERM "${API_PID:-}" "${UI_PID:-}" 2>/dev/null || true
  wait "${API_PID:-}" "${UI_PID:-}" 2>/dev/null || true
}

if [[ ! -x "${PROJECT_ROOT}/.venv/bin/uvicorn" ]]; then
  echo "Python environment is missing. Create .venv and install the project first." >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "OpenSSL is required to generate the local HTTPS certificate." >&2
  exit 1
fi

LAN_IP="$(find_lan_ip)"
generate_certificate "${LAN_IP}"
choose_frontend_command

"${PROJECT_ROOT}/scripts/reset.sh"

echo "Starting Cross Talker with HTTPS"
echo "  UI:  https://localhost:3000"
echo "  API: https://localhost:8000"
if [[ -n "${LAN_IP}" ]]; then
  echo "  LAN: https://${LAN_IP}:3000"
fi
echo "Certificate: ${CERTIFICATE_PATH}"
echo "Trust this certificate on each device before opening the LAN URL."

(
  cd "${PROJECT_ROOT}"
  exec .venv/bin/uvicorn cross_talker.api:app \
    --host 0.0.0.0 \
    --port 8000 \
    --ssl-certfile "${CERTIFICATE_PATH}" \
    --ssl-keyfile "${KEY_PATH}"
) &
API_PID=$!

(
  cd "${PROJECT_ROOT}/ui"
  export CROSS_TALKER_TLS_CERT="${CERTIFICATE_PATH}"
  export CROSS_TALKER_TLS_KEY="${KEY_PATH}"
  exec "${FRONTEND_COMMAND[@]}"
) &
UI_PID=$!

trap cleanup EXIT INT TERM
wait "${API_PID}" "${UI_PID}"
