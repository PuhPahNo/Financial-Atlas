#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-10000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"

api_pid=""
web_pid=""

cleanup() {
  if [[ -n "${web_pid}" ]]; then kill "${web_pid}" 2>/dev/null || true; fi
  if [[ -n "${api_pid}" ]]; then kill "${api_pid}" 2>/dev/null || true; fi
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "${APP_ROOT}/backend"
"${PYTHON_BIN}" -m uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT}" &
api_pid="$!"

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null; then
    break
  fi
  sleep 1
done

if ! kill -0 "${api_pid}" 2>/dev/null; then
  echo "FastAPI failed to start"
  exit 1
fi

cd "${APP_ROOT}/frontend"
npm run start -- -H 0.0.0.0 -p "${PORT}" &
web_pid="$!"

while true; do
  if ! kill -0 "${api_pid}" 2>/dev/null; then
    wait "${api_pid}" || exit $?
    exit 0
  fi
  if ! kill -0 "${web_pid}" 2>/dev/null; then
    wait "${web_pid}" || exit $?
    exit 0
  fi
  sleep 1
done
