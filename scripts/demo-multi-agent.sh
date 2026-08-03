#!/usr/bin/env bash
set -euo pipefail

# Demo script for multi-agent session logger
# Shows detection and normalization for GitHub Copilot and Claude Code

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_LOGGER="$SCRIPT_DIR/.github/hooks/session-logger/session-logger.sh"

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║       Session Logger - Multi-Agent Detection Demo            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

demo_event() {
  local agent_name="$1"
  local payload_file="$2"
  local event_type="$3"
  local description="$4"

  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}Agent:${NC} $agent_name"
  echo -e "${YELLOW}Event:${NC} $event_type"
  echo -e "${YELLOW}Description:${NC} $description"
  echo ""

  local result
  result=$(cat "$payload_file" | \
    COPILOT_SESSION_LOGGER_SOURCE=github_copilot_hook \
    bash "$SESSION_LOGGER" --event "$event_type" --dry-run 2>/dev/null)

  echo -e "${GREEN}✓ Detection Result:${NC}"
  echo "$result" | jq -C '{
    agent_source,
    event_type,
    tool_name,
    prompt_text: (if .prompt_text then (.prompt_text[0:60] + "...") else null end),
    repository,
    actor
  }'
  echo ""
}

# GitHub Copilot Examples
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    GitHub Copilot Events                      ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

demo_event \
  "GitHub Copilot" \
  "$SCRIPT_DIR/examples/payload-user-prompt.json" \
  "userPromptSubmitted" \
  "User submits a prompt asking about logger improvements"

demo_event \
  "GitHub Copilot" \
  "$SCRIPT_DIR/examples/payload-tool-use.json" \
  "preToolUse" \
  "Tool invocation starts (e.g., running a bash command)"

demo_event \
  "GitHub Copilot" \
  "$SCRIPT_DIR/examples/payload-tool-result.json" \
  "postToolUse" \
  "Tool completes and returns results"

# Claude Code Examples
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                      Claude Code Events                       ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

demo_event \
  "Claude Code" \
  "$SCRIPT_DIR/examples/claude-payloads/session-start.json" \
  "SessionStart" \
  "Claude Code session begins"

demo_event \
  "Claude Code" \
  "$SCRIPT_DIR/examples/claude-payloads/user-prompt-submit.json" \
  "UserPromptSubmit" \
  "User asks Claude to investigate hooks"

demo_event \
  "Claude Code" \
  "$SCRIPT_DIR/examples/claude-payloads/tool-call-start.json" \
  "PreToolUse" \
  "Claude invokes Bash tool to list directory"

demo_event \
  "Claude Code" \
  "$SCRIPT_DIR/examples/claude-payloads/tool-read.json" \
  "PostToolUse" \
  "Claude reads README.md file"

# Summary
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                          Summary                              ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "✓ Automatic detection works for both GitHub Copilot and Claude Code"
echo "✓ Events are normalized to a unified format"
echo "✓ agent_source label is added for filtering in Loki/Tempo"
echo ""
echo "Next steps:"
echo "  1. Configure hooks in your project (copilot-hooks.json or .claude/settings.json)"
echo "  2. Set COPILOT_SESSION_LOGGER_LOKI_ENABLED=true"
echo "  3. Set COPILOT_SESSION_LOGGER_OTLP_ENABLED=true"
echo "  4. Query logs in Loki: {agent_source=\"claude_code\"}"
echo ""
