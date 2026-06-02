#!/usr/bin/env bash
set -euo pipefail

SESSION_LOGGER_VERSION="0.2.0-shell"
SESSION_LOGGER_SOURCE="${COPILOT_SESSION_LOGGER_SOURCE:-github_copilot_hook}"
SESSION_LOGGER_HOME="${COPILOT_SESSION_LOGGER_HOME:-$HOME/.session-logger}"
SESSION_LOGGER_STATE_DIR="${COPILOT_SESSION_LOGGER_STATE_DIR:-$SESSION_LOGGER_HOME/state}"
SESSION_LOGGER_LOKI_ENDPOINT="${COPILOT_SESSION_LOGGER_LOKI_ENDPOINT:-http://localhost:3100/loki/api/v1/push}"
SESSION_LOGGER_LOKI_TENANT_ID="${COPILOT_SESSION_LOGGER_LOKI_TENANT_ID:-}"
SESSION_LOGGER_OTLP_ENDPOINT="${COPILOT_SESSION_LOGGER_OTLP_ENDPOINT:-http://localhost:4318}"
if [ -n "${COPILOT_SESSION_LOGGER_LOKI_ENABLED:-}" ]; then
  SESSION_LOGGER_LOKI_ENABLED="$COPILOT_SESSION_LOGGER_LOKI_ENABLED"
elif [ -n "${COPILOT_SESSION_LOGGER_LOKI_ENDPOINT:-}" ] || [ -n "${COPILOT_SESSION_LOGGER_LOKI_TENANT_ID:-}" ]; then
  SESSION_LOGGER_LOKI_ENABLED="true"
else
  SESSION_LOGGER_LOKI_ENABLED="false"
fi
if [ -n "${COPILOT_SESSION_LOGGER_OTLP_ENABLED:-}" ]; then
  SESSION_LOGGER_OTLP_ENABLED="$COPILOT_SESSION_LOGGER_OTLP_ENABLED"
elif [ -n "${COPILOT_SESSION_LOGGER_OTLP_ENDPOINT:-}" ]; then
  SESSION_LOGGER_OTLP_ENABLED="true"
else
  SESSION_LOGGER_OTLP_ENABLED="false"
fi
SESSION_LOGGER_TIMEOUT_SECONDS="${COPILOT_SESSION_LOGGER_TIMEOUT_SECONDS:-2}"
SESSION_LOGGER_REDACT_SECRETS="${COPILOT_SESSION_LOGGER_REDACT_SECRETS:-true}"
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
  mkdir -p "$SESSION_LOGGER_STATE_DIR"
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
  local probe_path="$workspace"
  local git_available="false"
  local is_repo="false"
  local repo_path=""
  local repo_name=""
  local git_branch=""
  local git_commit=""
  local remote_url=""
  local error=""
  local files_changed="[]"

  if [ -f "$probe_path" ]; then
    probe_path="$(dirname "$probe_path")"
  fi
  if [ -z "$probe_path" ] || [ ! -d "$probe_path" ]; then
    probe_path="$PWD"
  fi

  if command -v git >/dev/null 2>&1; then
    git_available="true"
    if git -C "$probe_path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      is_repo="true"
      repo_path="$(git -C "$probe_path" rev-parse --show-toplevel 2>/dev/null || true)"
      git_branch="$(git -C "$probe_path" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
      git_commit="$(git -C "$probe_path" rev-parse HEAD 2>/dev/null || true)"
      remote_url="$(git -C "$probe_path" config --get remote.origin.url 2>/dev/null || true)"
      files_changed="$({
        git -C "$probe_path" diff --name-only --cached 2>/dev/null || true
        git -C "$probe_path" diff --name-only 2>/dev/null || true
        git -C "$probe_path" ls-files --others --exclude-standard 2>/dev/null || true
      } | awk 'NF' | sort -u | jq -R -s 'split("\n") | map(select(length>0))')"

      if [ "$git_branch" = "HEAD" ]; then
        git_branch="detached"
      fi
      if [ -n "$repo_path" ]; then
        repo_name="$(basename "$repo_path")"
      fi
      if [ -z "$repo_name" ] && [ -n "$remote_url" ]; then
        repo_name="${remote_url##*/}"
        repo_name="${repo_name%.git}"
      fi
    else
      error="not_a_git_repository"
    fi
  else
    error="git_not_available"
  fi

  jq -c -n \
    --arg ws "$workspace" \
    --arg probe "$probe_path" \
    --arg git_avail "$git_available" \
    --arg is_repo "$is_repo" \
    --arg repo_path "$repo_path" \
    --arg repo_name "$repo_name" \
    --arg git_branch "$git_branch" \
    --arg git_commit "$git_commit" \
    --arg remote_url "$remote_url" \
    --arg error "$error" \
    --argjson files_changed "$files_changed" \
    --argjson files_added '[]' \
    '{
      git_available:($git_avail=="true"),
      is_repo:($is_repo=="true"),
      workspace:$ws,
      probe_path:$probe,
      repo_path:(if $repo_path=="" then null else $repo_path end),
      repo_name:(if $repo_name=="" then null else $repo_name end),
      git_branch:(if $git_branch=="" then null else $git_branch end),
      git_commit:(if $git_commit=="" then null else $git_commit end),
      remote_url:(if $remote_url=="" then null else $remote_url end),
      files_changed:$files_changed,
      files_added:$files_added,
      error:(if $error=="" then null else $error end)
    }'
}
