#!/usr/bin/env bash

set -euo pipefail

readonly PORTS=(3000 8000)
readonly GRACE_PERIOD_SECONDS=5

find_listener_pids() {
  local port="$1"
  lsof -nP -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true
}

wait_for_shutdown() {
  local pid="$1"
  local attempts=$((GRACE_PERIOD_SECONDS * 10))

  for ((attempt = 0; attempt < attempts; attempt++)); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 0.1
  done

  return 1
}

stop_port() {
  local port="$1"
  local pids
  pids="$(find_listener_pids "${port}")"

  if [[ -z "${pids}" ]]; then
    echo "Port ${port}: no service running"
    return
  fi

  while IFS= read -r pid; do
    [[ -z "${pid}" ]] && continue
    echo "Port ${port}: stopping process ${pid}"
    kill -TERM "${pid}" 2>/dev/null || true

    if wait_for_shutdown "${pid}"; then
      echo "Port ${port}: stopped"
    else
      echo "Port ${port}: graceful shutdown timed out; forcing process ${pid}"
      kill -KILL "${pid}" 2>/dev/null || true
    fi
  done <<< "${pids}"
}

for port in "${PORTS[@]}"; do
  stop_port "${port}"
done

