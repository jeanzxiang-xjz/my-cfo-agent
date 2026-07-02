#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${CFO_WEB_HOST:-127.0.0.1}"
PORT="${CFO_WEB_PORT:-8091}"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-./cfo_agent_poc/bin/cloudflared}"

if [[ ! -x "${CLOUDFLARED_BIN}" ]]; then
  if command -v cloudflared >/dev/null 2>&1; then
    CLOUDFLARED_BIN="$(command -v cloudflared)"
  fi
fi

if [[ ! -x "${CLOUDFLARED_BIN}" ]]; then
  echo "cloudflared is required for public demo mode." >&2
  echo "Install with: brew install cloudflared, or place it at cfo_agent_poc/bin/cloudflared." >&2
  exit 1
fi

if [[ -f cfo_agent_poc/.env ]]; then
  set -a
  source cfo_agent_poc/.env
  set +a
fi

if [[ -z "${CFO_ACCESS_TOKEN:-}" ]]; then
  echo "CFO_ACCESS_TOKEN is required before exposing the app publicly." >&2
  echo "Set it in cfo_agent_poc/.env first." >&2
  exit 1
fi

WEB_PID=""
if ! lsof -ti "tcp:${PORT}" >/dev/null 2>&1; then
  ./cfo_agent_poc/start_cfo_web.sh --host "${HOST}" --port "${PORT}" &
  WEB_PID="$!"
  sleep 1
fi

cleanup() {
  if [[ -n "${WEB_PID}" ]]; then
    kill "${WEB_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "Starting Cloudflare Quick Tunnel for http://${HOST}:${PORT}"
"${CLOUDFLARED_BIN}" tunnel --url "http://${HOST}:${PORT}"
