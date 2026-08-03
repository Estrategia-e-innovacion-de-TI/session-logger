#!/usr/bin/env bash
set -euo pipefail

# Claude Code specific payload extractors
# These functions extract fields from Claude Code hook payloads

extract_claude_event_type() {
  local payload="$1"
  jq -r '
    .hook_event_name // .event_type // .eventType // empty
  ' <<< "$payload"
}

normalize_claude_event_type() {
  local event_type="$1"
  # Claude uses PascalCase, normalize to snake_case
  jq -nr --arg event_type "$event_type" '
    def normalize($event):
      if $event == "SessionStart" then "session_start"
      elif $event == "UserPromptSubmit" then "user_prompt"
      elif $event == "PreToolUse" then "tool_use"
      elif $event == "PostToolUse" then "tool_result"
      elif $event == "SessionEnd" then "session_end"
      elif $event == "ErrorOccurred" then "error"
      else ($event | ascii_downcase | gsub("[^a-z0-9]+"; "_") | gsub("^_|_$"; ""))
      end;
    normalize($event_type)
  '
}

extract_claude_session_id() {
  local payload="$1"
  jq -r '
    .sessionId // .session_id // empty
  ' <<< "$payload"
}

extract_claude_user_prompt() {
  local payload="$1"
  jq -r '
    .prompt // .message // .text // empty
  ' <<< "$payload"
}

extract_claude_actor() {
  local payload="$1"
  jq -r --arg fallback "$SESSION_LOGGER_ACTOR" '
    .actor // .user // .username // $fallback // empty
  ' <<< "$payload"
}

extract_claude_tool_name() {
  local payload="$1"
  jq -r '
    .tool_name // .toolName // empty
  ' <<< "$payload"
}

extract_claude_tool_input() {
  local payload="$1"
  jq -c '
    .tool_input // .toolInput // .tool_args // .toolArgs // {}
  ' <<< "$payload"
}

extract_claude_tool_response() {
  local payload="$1"
  jq -c '
    .tool_response // .toolResponse // .tool_result // .toolResult // null
  ' <<< "$payload"
}

extract_claude_tool_use_id() {
  local payload="$1"
  jq -r '
    .tool_use_id // .toolUseId // .tool_id // empty
  ' <<< "$payload"
}

extract_claude_repository() {
  local payload="$1"
  jq -r '
    .repository // .repo // empty
  ' <<< "$payload"
}

extract_claude_branch() {
  local payload="$1"
  jq -r '
    .branch // empty
  ' <<< "$payload"
}

extract_claude_working_directory() {
  local payload="$1"
  jq -r --arg pwd "$PWD" '
    .cwd // .working_directory // .workspace // $pwd
  ' <<< "$payload"
}

extract_claude_transcript_path() {
  local payload="$1"
  jq -r '
    .transcript_path // .transcriptPath // empty
  ' <<< "$payload"
}

# Extract files from Claude tool calls
# Claude tools like Read, Write, Edit have file_path in tool_input
extract_claude_files_touched() {
  local payload="$1"
  jq -c '
    [
      (.tool_input.file_path // .tool_input.filePath // empty),
      (.tool_input.paths[]? // empty),
      (.tool_input.files[]? // empty),
      (.tool_response.file_path // empty),
      (.attachments[]? // empty)
    ] | map(select(. != null and . != "")) | unique
  ' <<< "$payload"
}

# Summarize tool input for logging
summarize_claude_tool_input() {
  local tool_name="$1"
  local tool_input="$2"

  case "$tool_name" in
    Read)
      jq -r '.file_path // "unknown file"' <<< "$tool_input"
      ;;
    Write|Edit)
      jq -r '(.file_path // "unknown file") + " (" + ((.content // .old_string) | tostring | length | tostring) + " chars)"' <<< "$tool_input"
      ;;
    Bash)
      jq -r '.command // "unknown command"' <<< "$tool_input"
      ;;
    Agent)
      jq -r '.prompt[0:100] // "agent task"' <<< "$tool_input"
      ;;
    *)
      jq -r 'tostring[0:200]' <<< "$tool_input"
      ;;
  esac
}

# Summarize tool response for logging
summarize_claude_tool_response() {
  local tool_name="$1"
  local tool_response="$2"

  if [[ "$tool_response" == "null" || -z "$tool_response" ]]; then
    echo ""
    return
  fi

  case "$tool_name" in
    Read)
      jq -r 'if type == "string" then (.[0:200] + "...") else "file content" end' <<< "$tool_response"
      ;;
    Write|Edit)
      echo "success"
      ;;
    Bash)
      jq -r 'if type == "string" then (.[0:200]) else tostring[0:200] end' <<< "$tool_response"
      ;;
    *)
      jq -r 'tostring[0:200]' <<< "$tool_response"
      ;;
  esac
}
