#!/usr/bin/env bash
set -euo pipefail

SESSION_LOGGER_VERSION="0.2.0-shell"
SESSION_LOGGER_SOURCE="${COPILOT_SESSION_LOGGER_SOURCE:-github_copilot_hook}"
SESSION_LOGGER_HOME="${COPILOT_SESSION_LOGGER_HOME:-$HOME/.session-logger}"
SESSION_LOGGER_LOGS_DIR="${COPILOT_SESSION_LOGGER_LOGS_DIR:-$SESSION_LOGGER_HOME/logs}"
SESSION_LOGGER_STATE_DIR="${COPILOT_SESSION_LOGGER_STATE_DIR:-$SESSION_LOGGER_HOME/state}"
SESSION_LOGGER_QUEUE_DIR="${COPILOT_SESSION_LOGGER_QUEUE_DIR:-$SESSION_LOGGER_HOME/queue}"
SESSION_LOGGER_HTTP_ENABLED="${COPILOT_SESSION_LOGGER_HTTP_ENABLED:-false}"
SESSION_LOGGER_ENDPOINT="${COPILOT_SESSION_LOGGER_ENDPOINT:-}"
SESSION_LOGGER_API_KEY="${COPILOT_SESSION_LOGGER_API_KEY:-${COPILOT_SESSION_LOGGER_TOKEN:-}}"
SESSION_LOGGER_LOKI_ENABLED="${COPILOT_SESSION_LOGGER_LOKI_ENABLED:-false}"
SESSION_LOGGER_LOKI_ENDPOINT="${COPILOT_SESSION_LOGGER_LOKI_ENDPOINT:-http://localhost:3100/loki/api/v1/push}"
SESSION_LOGGER_LOKI_TENANT_ID="${COPILOT_SESSION_LOGGER_LOKI_TENANT_ID:-}"
SESSION_LOGGER_OTLP_ENABLED="${COPILOT_SESSION_LOGGER_OTLP_ENABLED:-false}"
SESSION_LOGGER_OTLP_ENDPOINT="${COPILOT_SESSION_LOGGER_OTLP_ENDPOINT:-http://localhost:4318}"
SESSION_LOGGER_TIMEOUT_SECONDS="${COPILOT_SESSION_LOGGER_TIMEOUT_SECONDS:-2}"
SESSION_LOGGER_REDACT_SECRETS="${COPILOT_SESSION_LOGGER_REDACT_SECRETS:-true}"
SESSION_LOGGER_OFFLINE_QUEUE_ENABLED="${COPILOT_SESSION_LOGGER_OFFLINE_QUEUE_ENABLED:-true}"
SESSION_LOGGER_ACTOR="${COPILOT_SESSION_LOGGER_ACTOR:-${GITHUB_ACTOR:-${GITHUB_USER:-${USER:-${USERNAME:-}}}}}"
SESSION_LOGGER_COPILOT_USER="${COPILOT_SESSION_LOGGER_COPILOT_USER:-${GITHUB_COPILOT_USER:-${COPILOT_USER:-${GITHUB_USER:-${GITHUB_ACTOR:-}}}}}"

logger_now() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

logger_bool_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

validate_dependencies() {
  local missing=()
  command -v bash >/dev/null 2>&1 || missing+=("bash")
  command -v jq >/dev/null 2>&1 || missing+=("jq")
  command -v curl >/dev/null 2>&1 || missing+=("curl")

  if [ "${#missing[@]}" -gt 0 ]; then
    printf 'session-logger missing dependencies: %s\n' "${missing[*]}" >&2
    return 1
  fi
}

ensure_logger_directories() {
  mkdir -p "$SESSION_LOGGER_LOGS_DIR" "$SESSION_LOGGER_STATE_DIR" "$SESSION_LOGGER_QUEUE_DIR"
}

json_log() {
  local level="$1"
  local event="$2"
  local message="${3:-}"
  jq -cn \
    --arg timestamp "$(logger_now)" \
    --arg level "$level" \
    --arg event "$event" \
    --arg message "$message" \
    '{timestamp:$timestamp,level:$level,event:$event,message:$message}' >&2
}

json_compact() {
  jq -c .
}

safe_file_key() {
  printf '%s' "$1" | sed -E 's/[^A-Za-z0-9_.-]+/_/g'
}

collect_git_context() {
  local workspace="${1:-$PWD}"
  jq -c -n \
    --arg ws "$workspace" \
    --arg git_avail "$(command -v git >/dev/null 2>&1 && echo true || echo false)" \
    '{git_available:($git_avail=="true"),is_repo:false,workspace:$ws}'
}
