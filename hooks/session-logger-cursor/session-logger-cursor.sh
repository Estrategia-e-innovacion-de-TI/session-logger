#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../session-logger" && pwd)"

# Map CURSOR_SESSION_LOGGER_* observability/env vars onto the shared
# COPILOT_SESSION_LOGGER_* vars consumed by lib/logger.sh, so Cursor's
# documented env vars actually take effect (lib/logger.sh is shared across
# editors and only reads the COPILOT_ prefix).
: "${COPILOT_SESSION_LOGGER_SOURCE:=cursor_hook}"
: "${COPILOT_SESSION_LOGGER_LOKI_ENABLED:=${CURSOR_SESSION_LOGGER_LOKI_ENABLED:-}}"
: "${COPILOT_SESSION_LOGGER_LOKI_ENDPOINT:=${CURSOR_SESSION_LOGGER_LOKI_ENDPOINT:-}}"
: "${COPILOT_SESSION_LOGGER_LOKI_TENANT_ID:=${CURSOR_SESSION_LOGGER_LOKI_TENANT_ID:-}}"
: "${COPILOT_SESSION_LOGGER_OTLP_ENABLED:=${CURSOR_SESSION_LOGGER_OTLP_ENABLED:-}}"
: "${COPILOT_SESSION_LOGGER_OTLP_ENDPOINT:=${CURSOR_SESSION_LOGGER_OTLP_ENDPOINT:-}}"
: "${COPILOT_SESSION_LOGGER_OTLP_CLIENT_CERT:=${CURSOR_SESSION_LOGGER_OTLP_CLIENT_CERT:-}}"
: "${COPILOT_SESSION_LOGGER_OTLP_CLIENT_KEY:=${CURSOR_SESSION_LOGGER_OTLP_CLIENT_KEY:-}}"
: "${COPILOT_SESSION_LOGGER_OTLP_CA_CERT:=${CURSOR_SESSION_LOGGER_OTLP_CA_CERT:-}}"
export COPILOT_SESSION_LOGGER_SOURCE COPILOT_SESSION_LOGGER_LOKI_ENABLED \
  COPILOT_SESSION_LOGGER_LOKI_ENDPOINT COPILOT_SESSION_LOGGER_LOKI_TENANT_ID \
  COPILOT_SESSION_LOGGER_OTLP_ENABLED COPILOT_SESSION_LOGGER_OTLP_ENDPOINT \
  COPILOT_SESSION_LOGGER_OTLP_CLIENT_CERT COPILOT_SESSION_LOGGER_OTLP_CLIENT_KEY \
  COPILOT_SESSION_LOGGER_OTLP_CA_CERT

# shellcheck source=../session-logger/lib/logger.sh
source "$REPO_ROOT/lib/logger.sh"
# shellcheck source=../session-logger/lib/state.sh
source "$REPO_ROOT/lib/state.sh"
# shellcheck source=../session-logger/lib/agent-detector.sh
source "$REPO_ROOT/lib/agent-detector.sh"
# shellcheck source=../session-logger/lib/claude-payload.sh
source "$REPO_ROOT/lib/claude-payload.sh"
# shellcheck source=../session-logger/lib/payload.sh
source "$REPO_ROOT/lib/payload.sh"
# shellcheck source=../session-logger/lib/transport.sh
source "$REPO_ROOT/lib/transport.sh"

ACTION="log"
EVENT_TYPE_OVERRIDE="${CURSOR_SESSION_LOGGER_EVENT_TYPE:-}"
SESSION_ID_OVERRIDE="${CURSOR_SESSION_LOGGER_SESSION_ID:-}"
DRY_RUN="${CURSOR_SESSION_LOGGER_DRY_RUN:-false}"
METADATA_JSON="${CURSOR_SESSION_LOGGER_METADATA_JSON:-{}}"


usage() {
  cat <<'USAGE'
Usage:
  hooks/session-logger-cursor/session-logger-cursor.sh --event <hook-event> [--session-id <id>] [--dry-run]
  hooks/session-logger-cursor/session-logger-cursor.sh log --event <hook-event>
  hooks/session-logger-cursor/session-logger-cursor.sh doctor

Cursor AI Editor Hook Integration for session-logger

Required runtime dependencies: bash, jq, curl.

Environment Variables:
  CURSOR_SESSION_LOGGER_EVENT_TYPE              Override event type from payload
  CURSOR_SESSION_LOGGER_SESSION_ID              Override session ID
  CURSOR_SESSION_LOGGER_DRY_RUN                 Dry run mode (no sending to backends)
  CURSOR_SESSION_LOGGER_METADATA_JSON           Additional metadata to include
  CURSOR_SESSION_LOGGER_LOKI_ENABLED            Enable Loki endpoint (default: false)
  CURSOR_SESSION_LOGGER_LOKI_ENDPOINT           Loki push endpoint (default: http://localhost:3100/loki/api/v1/push)
  CURSOR_SESSION_LOGGER_OTLP_ENABLED            Enable OTLP endpoint (default: false)
  CURSOR_SESSION_LOGGER_OTLP_ENDPOINT           OTLP collector endpoint (default: http://localhost:4318)
  CURSOR_SESSION_LOGGER_OTLP_CLIENT_CERT        Client certificate for mTLS (PEM)
  CURSOR_SESSION_LOGGER_OTLP_CLIENT_KEY         Client private key for mTLS (PEM)
  CURSOR_SESSION_LOGGER_OTLP_CA_CERT            CA certificate to verify the collector (PEM)

Example:
  CURSOR_SESSION_LOGGER_LOKI_ENABLED=true \\
  CURSOR_SESSION_LOGGER_OTLP_ENABLED=true \\
  bash hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted < payload.json
USAGE
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      log)
        ACTION="log"
        shift
        ;;
      doctor)
        ACTION="doctor"
        shift
        ;;
      --event)
        EVENT_TYPE_OVERRIDE="${2:-}"
        shift 2
        ;;
      --event=*)
        EVENT_TYPE_OVERRIDE="${1#--event=}"
        shift
        ;;
      --session-id)
        SESSION_ID_OVERRIDE="${2:-}"
        shift 2
        ;;
      --session-id=*)
        SESSION_ID_OVERRIDE="${1#--session-id=}"
        shift
        ;;
      --metadata-json)
        METADATA_JSON="${2:-{}}"
        shift 2
        ;;
      --metadata-json=*)
        METADATA_JSON="${1#--metadata-json=}"
        shift
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        json_log "error" "invalid_argument" "$1"
        usage >&2
        return 2
        ;;
    esac
  done
}

doctor_report() {
  jq -cn \
    --arg timestamp "$(logger_now)" \
    --arg home "$SESSION_LOGGER_HOME" \
    --arg state "$SESSION_LOGGER_STATE_DIR" \
    --arg loki_endpoint "$SESSION_LOGGER_LOKI_ENDPOINT" \
    --arg otlp_endpoint "$SESSION_LOGGER_OTLP_ENDPOINT" \
    --argjson loki_enabled "$(logger_bool_true "$SESSION_LOGGER_LOKI_ENABLED" && echo true || echo false)" \
    --argjson otlp_enabled "$(logger_bool_true "$SESSION_LOGGER_OTLP_ENABLED" && echo true || echo false)" \
    '{
      timestamp:$timestamp,
      runtime:"bash",
      editor:"cursor",
      home_dir:$home,
      state_dir:$state,
      observability:{
        loki:{enabled:$loki_enabled,endpoint:$loki_endpoint},
        otlp:{enabled:$otlp_enabled,endpoint:$otlp_endpoint}
      },
      dependencies:{
        bash:true,
        jq:true,
        curl:true
      }
    }'
}

build_scope_key() {
  local git_context="$1"
  local workspace="$2"
  local actor="$3"
  jq -nr \
    --argjson git "$git_context" \
    --arg workspace "$workspace" \
    --arg actor "$actor" \
    '"\($actor // "unknown")::\($git.repo_path // $workspace // "unknown")"'
}

run_log() {
  ensure_logger_directories
  local payload
  local agent_source
  local hook_event_type
  local normalized_event_type
  local explicit_session_id
  local workspace
  local git_context
  local actor
  local scope_key
  local session_id
  local event_id
  local user_prompt_id=""
  local parent_user_prompt_id=""
  local existing_user_prompt_id
  local explicit_parent
  local event_json

  payload="$(read_stdin_payload)" || return $?

  # Detect agent source - force "cursor" for this hook script
  agent_source="cursor"

  hook_event_type="$(extract_event_type "$payload" "$EVENT_TYPE_OVERRIDE")" || return $?
  if [ -z "$hook_event_type" ]; then
    json_log "error" "event_type_required" "Provide --event or event_type in payload"
    return 2
  fi

  normalized_event_type="$(normalize_event_type "$hook_event_type")" || return $?
  explicit_session_id="$(extract_session_id "$payload" "$SESSION_ID_OVERRIDE")" || return $?
  workspace="$(extract_working_directory "$payload")" || return $?
  git_context="$(collect_git_context "$workspace")" || git_context='{}'
  [ -z "$git_context" ] && git_context='{}'
  actor="$(extract_actor "$payload")" || return $?
  scope_key="$(build_scope_key "$git_context" "$workspace" "$actor")" || return $?
  session_id="$(resolve_session_id "$explicit_session_id" "$hook_event_type" "$scope_key" "$([ "$DRY_RUN" = "true" ] && echo false || echo true)")" || return $?
  event_id="$(generate_event_id)" || return $?

  existing_user_prompt_id="$(extract_existing_userPrompt_id "$payload")" || return $?
  explicit_parent="$(extract_existing_parent_userPrompt_id "$payload")" || return $?
  if [ "$normalized_event_type" = "user_prompt" ]; then
    user_prompt_id="${existing_user_prompt_id:-$(generate_userPrompt_id)}" || return $?
  else
    parent_user_prompt_id="$(resolve_parent_userPrompt_id "$normalized_event_type" "$session_id" "$explicit_parent")" || return $?
  fi

  if ! jq -e . >/dev/null 2>&1 <<< "$METADATA_JSON"; then
    json_log "warn" "invalid_metadata_json" "CURSOR_SESSION_LOGGER_METADATA_JSON ignored"
    METADATA_JSON="{}"
  fi
  METADATA_JSON="$(echo "$METADATA_JSON" | jq -c .)" || METADATA_JSON="{}"

  event_json="$(
    build_normalized_event \
      "$payload" \
      "$hook_event_type" \
      "$event_id" \
      "$session_id" \
      "$user_prompt_id" \
      "$parent_user_prompt_id" \
      "$git_context" \
      "$actor" \
      "$METADATA_JSON" \
      "$agent_source"
  )" || return $?

  if logger_bool_true "$DRY_RUN"; then
    jq . <<< "$event_json"
    return 0
  fi

  if [ "$normalized_event_type" = "user_prompt" ] && [ -n "$user_prompt_id" ]; then
    set_last_userPrompt_id "$session_id" "$user_prompt_id" || return $?
  fi
  send_event_to_observability "$event_json" || return $?
}

main() {
  parse_args "$@" || return $?
  validate_dependencies || return $?
  case "$ACTION" in
    doctor)
      ensure_logger_directories || return $?
      doctor_report || return $?
      ;;
    log)
      run_log || return $?
      ;;
    *)
      usage >&2
      return 2
      ;;
  esac
}

set +e
main "$@"
exit_code=$?
set -e
if [ "$exit_code" -ne 0 ]; then
  if logger_bool_true "${CURSOR_SESSION_LOGGER_STRICT:-false}"; then
    exit "$exit_code"
  fi
  if command -v jq >/dev/null 2>&1; then
    json_log "error" "session_logger_failed" "non-strict mode swallowed exit code $exit_code"
  else
    printf 'session-logger failed in non-strict mode; swallowed exit code %s\n' "$exit_code" >&2
  fi
  exit 0
fi
