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
export COPILOT_SESSION_LOGGER_HTTP_ENABLED=false
export COPILOT_SESSION_LOGGER_STRICT=true

bash "$REPO_ROOT/hooks/session-logger.sh" doctor >/dev/null

prompt_event="$(
  bash "$REPO_ROOT/hooks/session-logger.sh" --event userPromptSubmitted --dry-run \
    < "$REPO_ROOT/examples/payload-user-prompt.json"
)"

session_id="$(jq -r '.session_id' <<< "$prompt_event")"

bash "$REPO_ROOT/hooks/session-logger.sh" --event userPromptSubmitted \
  < "$REPO_ROOT/examples/payload-user-prompt.json" >/dev/null

state_file="$COPILOT_SESSION_LOGGER_HOME/state/$session_id.json"
user_prompt_id="$(jq -r '.last_userPrompt_id' "$state_file")"

tool_event="$(
  bash "$REPO_ROOT/hooks/session-logger.sh" --event preToolUse --session-id "$session_id" --dry-run \
    < "$REPO_ROOT/examples/payload-tool-use.json"
)"

parent_id="$(jq -r '.parent_userPrompt_id' <<< "$tool_event")"
if [ "$parent_id" != "$user_prompt_id" ]; then
  echo "Expected parent_userPrompt_id=$user_prompt_id but got $parent_id" >&2
  exit 1
fi

log_count="$(find "$COPILOT_SESSION_LOGGER_HOME/logs" -name events.jsonl -type f -exec cat {} \; | jq -R 'fromjson?' | jq -s 'length')"
if [ "$log_count" -lt 1 ]; then
  echo "Expected at least one JSONL event" >&2
  exit 1
fi

echo "session logger shell test passed"
