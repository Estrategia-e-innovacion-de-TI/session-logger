#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TMP_HOME="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_HOME"
}
trap cleanup EXIT

export COPILOT_SESSION_LOGGER_HOME="$TMP_HOME/.session-logger"
export COPILOT_SESSION_LOGGER_LOKI_ENABLED=false
export COPILOT_SESSION_LOGGER_OTLP_ENABLED=false
export COPILOT_SESSION_LOGGER_STRICT=false

bash "$REPO_ROOT/hooks/session-logger/session-logger.sh" doctor >/dev/null

prompt_event="$(
  bash "$REPO_ROOT/hooks/session-logger/session-logger.sh" --event userPromptSubmitted --dry-run \
    < "$REPO_ROOT/examples/payload-user-prompt.json"
)"

session_id="$(jq -r '.session_id' <<< "$prompt_event")"

bash "$REPO_ROOT/hooks/session-logger/session-logger.sh" --event userPromptSubmitted \
  < "$REPO_ROOT/examples/payload-user-prompt.json" >/dev/null

state_file="$COPILOT_SESSION_LOGGER_HOME/state/$session_id.json"
user_prompt_id="$(jq -r '.last_userPrompt_id' "$state_file")"

tool_event="$(
  bash "$REPO_ROOT/hooks/session-logger/session-logger.sh" --event preToolUse --session-id "$session_id" --dry-run \
    < "$REPO_ROOT/examples/payload-tool-use.json"
)"

parent_id="$(jq -r '.parent_userPrompt_id' <<< "$tool_event")"
if [ "$parent_id" != "$user_prompt_id" ]; then
  echo "Expected parent_userPrompt_id=$user_prompt_id but got $parent_id" >&2
  exit 1
fi

repo_value="$(jq -r '.repository // empty' <<< "$tool_event")"
branch_value="$(jq -r '.branch // empty' <<< "$tool_event")"
mode_value="$(jq -r '.mode // empty' <<< "$tool_event")"
execution_mode_value="$(jq -r '.execution_mode // empty' <<< "$tool_event")"

if [ -z "$repo_value" ] || [ "$repo_value" = "null" ]; then
  echo "Expected repository to be present in tool event" >&2
  exit 1
fi

if [ -z "$branch_value" ] || [ "$branch_value" = "null" ]; then
  echo "Expected branch to be present in tool event" >&2
  exit 1
fi

if [ "$mode_value" != "ask" ]; then
  echo "Expected mode=ask but got $mode_value" >&2
  exit 1
fi

if [ "$execution_mode_value" != "sync" ]; then
  echo "Expected execution_mode=sync but got $execution_mode_value" >&2
  exit 1
fi

if [ -d "$COPILOT_SESSION_LOGGER_HOME/logs" ]; then
  echo "Expected no local logs directory in observability-only mode" >&2
  exit 1
fi

echo "session logger shell test passed"
