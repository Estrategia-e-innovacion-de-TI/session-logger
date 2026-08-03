#!/usr/bin/env bash
set -euo pipefail

# Agent detection logic for multi-agent session logging
# Detects whether a payload comes from GitHub Copilot, Claude Code, or Cursor

detect_agent_source() {
  local payload="$1"

  # Priority 0: explicit override via SESSION_LOGGER_SOURCE env var.
  # Hook configs (copilot-hooks.json, cursor-hooks.json) set this explicitly
  # per-editor, so it's authoritative and must win over payload heuristics
  # below (which can false-positive, e.g. shared tool/field naming across
  # editors causes real Copilot/Cursor events to look like Claude Code).
  case "${SESSION_LOGGER_SOURCE:-}" in
    *cursor*)
      echo "cursor"
      return 0
      ;;
    *copilot*)
      echo "github_copilot"
      return 0
      ;;
    *claude*)
      echo "claude_code"
      return 0
      ;;
  esac

  # Strategy: Check for distinctive fields that uniquely identify each agent
  local has_copilot_fields has_claude_fields has_cursor_fields

  # GitHub Copilot indicators:
  # - Fields: copilot_user, copilotUser, github_copilot_user, githubCopilotUser
  # - Event names: userPromptSubmitted (camelCase)
  # - Invocation structure: .invocation.copilotUser
  has_copilot_fields=$(jq -r '
    if (
      .copilot_user or .copilotUser or .github_copilot_user or .githubCopilotUser or
      .invocation.copilotUser or
      (.event_type == "userPromptSubmitted") or
      (.eventType == "userPromptSubmitted")
    ) then "true" else "false" end
  ' <<< "$payload")

  # Claude Code indicators:
  # - Event names: UserPromptSubmit, PreToolUse, PostToolUse (PascalCase)
  # - Field: hook_event_name with PascalCase values
  # - Tool names: Read, Write, Edit, Bash, Agent (Claude-specific capitalization)
  # - Session IDs: UUID format (both have this, but combined with other signals)
  # - Transcript path: .claude/projects/...
  has_claude_fields=$(jq -r '
    if (
      (.hook_event_name and (.hook_event_name | test("^[A-Z][a-zA-Z]+$"))) or
      (.transcript_path and (.transcript_path | contains("/.claude/"))) or
      ((.tool_name == "Read" or .tool_name == "Write" or .tool_name == "Edit") and (.tool_input.file_path))
    ) then "true" else "false" end
  ' <<< "$payload")

  # Cursor indicators:
  # - Fields: cursor_user, cursorUser
  # - Event names: userPromptSubmitted (camelCase, similar to Copilot)
  # - Workspace ID or similar cursor-specific fields
  has_cursor_fields=$(jq -r '
    if (
      .cursor_user or .cursorUser or .cursorSessionId or .cursor_session_id or
      (.invocation.cursorUser) or
      (.editor == "cursor" or .editorType == "cursor")
    ) then "true" else "false" end
  ' <<< "$payload")

  # Decision logic with priority
  if [[ "$has_claude_fields" == "true" ]]; then
    # Claude has more distinctive markers, check first
    echo "claude_code"
  elif [[ "$has_cursor_fields" == "true" ]]; then
    echo "cursor"
  elif [[ "$has_copilot_fields" == "true" ]]; then
    echo "github_copilot"
  else
    # Fallback: try to infer from event type naming convention
    local event_type
    event_type=$(jq -r '.event_type // .eventType // .hook_event_name // "unknown"' <<< "$payload")

    case "$event_type" in
      # Claude uses PascalCase (check first as it's more specific)
      SessionStart|UserPromptSubmit|PreToolUse|PostToolUse|SessionEnd|ErrorOccurred)
        echo "claude_code"
        ;;
      # Copilot and Cursor use camelCase
      sessionStart|userPromptSubmitted|preToolUse|postToolUse|sessionEnd|errorOccurred)
        # Differentiate between Copilot and Cursor by checking env var hint
        if [[ "${SESSION_LOGGER_SOURCE:-}" == *"cursor"* ]]; then
          echo "cursor"
        else
          echo "github_copilot"
        fi
        ;;
      *)
        # Final fallback: if source env var suggests cursor, assume cursor
        if [[ "${SESSION_LOGGER_SOURCE:-}" == *"cursor"* ]]; then
          echo "cursor"
        elif [[ "${SESSION_LOGGER_SOURCE:-}" == *"copilot"* ]]; then
          echo "github_copilot"
        else
          echo "unknown"
        fi
        ;;
    esac
  fi
}

normalize_agent_label() {
  local agent_source="$1"
  case "$agent_source" in
    github_copilot)
      echo "copilot"
      ;;
    claude_code)
      echo "claude"
      ;;
    cursor)
      echo "cursor"
      ;;
    *)
      echo "unknown"
      ;;
  esac
}

extract_agent_metadata() {
  local payload="$1"
  local agent_source="$2"

  case "$agent_source" in
    github_copilot)
      jq -c '{
        agent: "github_copilot",
        agent_user: (.copilot_user // .copilotUser // .invocation.copilotUser // null),
        agent_version: (.version // null)
      }' <<< "$payload"
      ;;
    claude_code)
      jq -c '{
        agent: "claude_code",
        agent_user: (.actor // .user // null),
        session_transcript: (.transcript_path // null)
      }' <<< "$payload"
      ;;
    cursor)
      jq -c '{
        agent: "cursor",
        agent_user: (.cursor_user // .cursorUser // .invocation.cursorUser // null),
        workspace_id: (.workspaceId // .workspace_id // null)
      }' <<< "$payload"
      ;;
    *)
      jq -cn '{agent: "unknown"}'
      ;;
  esac
}
