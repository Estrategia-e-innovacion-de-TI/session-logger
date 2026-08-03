# Session Logger Hook Configuration

This document explains how the session logger hooks are configured to run automatically for both GitHub Copilot and Claude Code.

## Configuration Files

### 1. GitHub Copilot Hooks
**Location**: `.github/hooks/copilot-hooks.json`

This file configures hooks for GitHub Copilot events. The hooks are triggered automatically by GitHub Copilot when the following events occur:
- `sessionStart` - When a Copilot session begins
- `userPromptSubmitted` - When a user submits a prompt
- `preToolUse` - Before a tool is executed
- `postToolUse` - After a tool completes execution
- `sessionEnd` - When a Copilot session ends
- `errorOccurred` - When an error occurs

**Environment Variables**:
```bash
COPILOT_SESSION_LOGGER_LOKI_ENABLED=true
COPILOT_SESSION_LOGGER_LOKI_ENDPOINT=http://localhost:3100/loki/api/v1/push
COPILOT_SESSION_LOGGER_OTLP_ENABLED=true
COPILOT_SESSION_LOGGER_OTLP_ENDPOINT=http://localhost:4318
SESSION_LOGGER_SOURCE=copilot
```

### 2. Claude Code Hooks
**Location**: `.claude/settings.json`

This file configures hooks for Claude Code events. The hooks are triggered automatically by Claude Code when the following events occur:
- `SessionStart` - When a Claude session begins
- `UserPromptSubmit` - When a user submits a prompt
- `PreToolUse` - Before a tool is executed
- `PostToolUse` - After a tool completes execution
- `Stop` - When a Claude session ends

**Environment Variables**:
```bash
COPILOT_SESSION_LOGGER_LOKI_ENABLED=true
COPILOT_SESSION_LOGGER_LOKI_ENDPOINT=http://localhost:3100/loki/api/v1/push
COPILOT_SESSION_LOGGER_OTLP_ENABLED=true
COPILOT_SESSION_LOGGER_OTLP_ENDPOINT=http://localhost:4318
SESSION_LOGGER_SOURCE=claude
```

## Session Logger Script
**Location**: `.github/hooks/session-logger/session-logger.sh`

The session logger script processes events from both agents and:
1. Detects the agent source (Copilot, Claude, or unknown)
2. Normalizes event types across different agent formats
3. Manages session state and correlation
4. Sends telemetry to configured observability backends (Loki and OTLP)

## How It Works

### Automatic Execution
Both hook configurations are designed to run automatically without manual intervention:

1. **GitHub Copilot**: The hooks are registered with Copilot through the `copilot-hooks.json` file. When Copilot runs in your repository, it automatically loads and executes these hooks.

2. **Claude Code**: The hooks are registered through the `.claude/settings.json` file. When you use Claude Code in this repository, it automatically loads and executes these hooks.

### Event Flow

```
User Action (Prompt/Tool Use)
        ↓
Agent Triggers Hook Event
        ↓
Hook Executes session-logger.sh
        ↓
Script Detects Agent Source
        ↓
Script Normalizes Event Data
        ↓
Script Sends to Observability Backends
```

### Agent Detection

The session logger automatically detects which agent triggered the event by analyzing the payload:

- **Claude Code**: Detected by the presence of Claude-specific fields in the hook payload
- **GitHub Copilot**: Detected by Copilot-specific event structures
- **Unknown**: Fallback for unrecognized sources

This is handled by `lib/agent-detector.sh` and `lib/claude-payload.sh`.

## Testing

### Test GitHub Copilot Hooks
```bash
# Dry-run test
COPILOT_SESSION_LOGGER_LOKI_ENABLED=true \
  SESSION_LOGGER_SOURCE=copilot \
  .github/hooks/session-logger/session-logger.sh --event sessionStart --dry-run
```

### Test Claude Code Hooks
```bash
# Dry-run test with sample payload
echo '{"tool_name":"Edit","tool_input":{"file_path":"test.txt"},"session_id":"test"}' | \
  COPILOT_SESSION_LOGGER_LOKI_ENABLED=true \
  SESSION_LOGGER_SOURCE=claude \
  .github/hooks/session-logger/session-logger.sh --event PostToolUse --dry-run
```

## Configuration Customization

### Change Observability Endpoints

Edit the environment variables in the hook configuration files:

**For Loki**:
```bash
COPILOT_SESSION_LOGGER_LOKI_ENABLED=true
COPILOT_SESSION_LOGGER_LOKI_ENDPOINT=http://your-loki-endpoint:3100/loki/api/v1/push
```

**For OTLP**:
```bash
COPILOT_SESSION_LOGGER_OTLP_ENABLED=true
COPILOT_SESSION_LOGGER_OTLP_ENDPOINT=http://your-otlp-endpoint:4318
```

### Disable Specific Events

In `.claude/settings.json` or `copilot-hooks.json`, remove or comment out the unwanted event hooks.

### Adjust Timeouts

Modify the `timeout` (Claude) or `timeoutSec` (Copilot) values in the hook configurations if hooks are timing out.

## Troubleshooting

### Hooks Not Running

1. **Check file permissions**:
   ```bash
   chmod +x .github/hooks/session-logger/session-logger.sh
   ```

2. **Verify dependencies**:
   ```bash
   .github/hooks/session-logger/session-logger.sh doctor
   ```

3. **Check Claude Code hook loading**:
   - Open `/hooks` in Claude Code UI to review loaded hooks
   - Restart Claude Code if the `.claude` directory was just created

### View Hook Execution

For Claude Code, hooks show a status message while running. Check the terminal output for:
- "Logging session start..."
- "Logging user prompt..."
- "Logging post-tool use..."

### Debug Mode

Run the session logger script directly with `--dry-run` to see what would be sent:
```bash
echo '{"session_id":"test"}' | \
  .github/hooks/session-logger/session-logger.sh --event PostToolUse --dry-run
```

## Notes

- The `.claude/settings.json` file is added to `.gitignore` as it may contain local configuration
- The `.github/hooks/copilot-hooks.json` file is committed to version control for team-wide Copilot hook configuration
- Both configurations use the same underlying session logger script for consistency
- Session correlation works across both agents using the same session management logic
