#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
readonly WAIT_TIMEOUT="${TAILER_COMPOSE_WAIT_TIMEOUT:-300}"
readonly LOG_TAIL="${TAILER_COMPOSE_LOG_TAIL:-200}"

usage() {
  cat <<'EOF'
Usage: ./tailer.sh <command> [service...]

Commands:
  start       Build and start the stack, then wait for healthy services
  stop        Stop the stack and remove its containers and network
  restart     Stop, rebuild, and start the complete stack
  status      Show Compose service status; optionally limit to services
  logs        Follow recent logs; optionally limit to services
  config      Validate the rendered Compose configuration
  gemini-smoke Run the opt-in live Gemini pipeline using ignored .gemini_api
  help        Show this help

Environment:
  TAILER_COMPOSE_WAIT_TIMEOUT  Startup health timeout in seconds (default: 300)
  TAILER_COMPOSE_LOG_TAIL      Lines shown before following logs (default: 200)
EOF
}

fail() {
  printf 'TAILER: %s\n' "$*" >&2
  exit 1
}

compose() {
  docker compose \
    --project-directory "$SCRIPT_DIR" \
    --file "$COMPOSE_FILE" \
    "$@"
}

require_compose() {
  command -v docker >/dev/null 2>&1 || fail "Docker is not installed or is not on PATH."
  docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is not available."
}

ensure_environment() {
  if [[ ! -f "${SCRIPT_DIR}/.env" && -f "${SCRIPT_DIR}/.env.example" ]]; then
    cp -- "${SCRIPT_DIR}/.env.example" "${SCRIPT_DIR}/.env"
    printf 'Created %s from .env.example\n' "${SCRIPT_DIR}/.env"
  fi
}

start_stack() {
  ensure_environment
  compose up --build --detach --wait --wait-timeout "$WAIT_TIMEOUT"
  compose ps
}

stop_stack() {
  compose down
}

gemini_smoke() {
  local python_bin=""
  if [[ -x "${SCRIPT_DIR}/backend/venv/bin/python" ]]; then
    python_bin="${SCRIPT_DIR}/backend/venv/bin/python"
  elif [[ -x "${SCRIPT_DIR}/backend/.venv/bin/python" ]]; then
    python_bin="${SCRIPT_DIR}/backend/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    python_bin="$(command -v python3)"
  else
    fail "Python 3 is required for the Gemini smoke pipeline."
  fi
  "$python_bin" -u "${SCRIPT_DIR}/scripts/gemini_smoke.py"
}

readonly COMMAND="${1:-help}"
if (($# > 0)); then
  shift
fi

case "$COMMAND" in
  start)
    require_compose
    start_stack
    ;;
  stop)
    require_compose
    stop_stack
    ;;
  restart)
    require_compose
    stop_stack
    start_stack
    ;;
  status)
    require_compose
    compose ps "$@"
    ;;
  logs)
    require_compose
    compose logs --follow --tail "$LOG_TAIL" "$@"
    ;;
  config)
    require_compose
    compose config --quiet
    printf 'Compose configuration is valid.\n'
    ;;
  gemini-smoke)
    require_compose
    gemini_smoke
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    printf 'Unknown command: %s\n\n' "$COMMAND" >&2
    usage >&2
    exit 2
    ;;
esac
