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
SESSION_LOGGER_TIMEOUT_SECONDS="${COPILOT_SESSION_LOGGER_TIMEOUT_SECONDS:-2}"
SESSION_LOGGER_REDACT_SECRETS="${COPILOT_SESSION_LOGGER_REDACT_SECRETS:-true}"
SESSION_LOGGER_OFFLINE_QUEUE_ENABLED="${COPILOT_SESSION_LOGGER_OFFLINE_QUEUE_ENABLED:-true}"
SESSION_LOGGER_ACTOR="${COPILOT_SESSION_LOGGER_ACTOR:-${GITHUB_ACTOR:-${GITHUB_USER:-${USER:-${USERNAME:-}}}}}"

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
  local repo_path=""
  local repo_name=""
  local branch=""
  local commit=""
  local files_json="[]"
  local error=""
  local git_available=false
  local is_repo=false

  if command -v git >/dev/null 2>&1; then
    git_available=true
    if repo_path="$(git -C "$workspace" rev-parse --show-toplevel 2>/dev/null)"; then
      is_repo=true
      repo_name="$(basename "$repo_path")"
      branch="$(git -C "$workspace" branch --show-current 2>/dev/null || true)"
      commit="$(git -C "$workspace" rev-parse HEAD 2>/dev/null || true)"
      files_json="$(
        git -C "$workspace" status --porcelain 2>/dev/null |
          sed -E 's/^..[[:space:]]+//' |
          sed -E 's/^.* -> //' |
          jq -R -s 'split("\n") | map(select(length > 0))'
      )"
    else
      error="current directory is not a git repository"
    fi
  else
    error="git executable not found in PATH"
  fi

  jq -cn \
    --argjson git_available "$git_available" \
    --argjson is_repo "$is_repo" \
    --arg repo_path "$repo_path" \
    --arg repo_name "$repo_name" \
    --arg branch "$branch" \
    --arg commit "$commit" \
    --arg error "$error" \
    --argjson files_changed "$files_json" \
    '{
      git_available:$git_available,
      is_repo:$is_repo,
      repo_path:($repo_path | select(length > 0)),
      repo_name:($repo_name | select(length > 0)),
      git_branch:($branch | select(length > 0)),
      git_commit:($commit | select(length > 0)),
      files_changed:$files_changed,
      error:($error | select(length > 0))
    }'
}
