# Changelog - Multi-Agent Support

## [0.3.0] - 2026-06-18

### Added - Multi-Agent Detection System

#### 🎯 Core Features
- **Automatic agent detection** from hook payloads (GitHub Copilot, Claude Code, Unknown)
- **Unified event normalization** across different AI agents
- **Agent-specific labels** in Loki streams and OTLP metrics
- **Extensible architecture** for adding future agents

#### 📦 New Files
- `.github/hooks/session-logger/lib/agent-detector.sh`
  - `detect_agent_source()`: Main detection logic
  - `normalize_agent_label()`: Agent name normalization
  - `extract_agent_metadata()`: Agent-specific metadata extraction

- `.github/hooks/session-logger/lib/claude-payload.sh`
  - Claude Code specific extractors
  - Tool input/response summarization for Claude tools
  - Support for Claude-specific fields (transcript_path, PascalCase events)

- `examples/claude-payloads/`
  - 6 example payloads for Claude Code events
  - Coverage: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, SessionEnd, Read tool

- `MULTI_AGENT.md`
  - Complete architecture documentation
  - Detection strategy explanation
  - Query examples for Loki and Tempo
  - Extension guide for new agents

- `scripts/demo-multi-agent.sh`
  - Interactive demo showing both agents
  - Color-coded output
  - Side-by-side comparison

#### 🔧 Modified Files

**`.github/hooks/session-logger/session-logger.sh`**
- Load agent-detector and claude-payload modules
- Call `detect_agent_source()` on every payload
- Pass `agent_source` to `build_normalized_event()`

**`.github/hooks/session-logger/lib/payload.sh`**
- Added `hook_event_name` to event type extraction
- Support PascalCase event normalization (SessionStart, UserPromptSubmit, etc.)
- Added fallbacks for `toolInput`, `toolResponse`, `tool_response`
- New parameter `agent_source` in `build_normalized_event()`
- Include `agent_source` in normalized event JSON and metadata
- Defensive handling of `tool_result` as string or object

**`.github/hooks/session-logger/lib/transport.sh`**
- Added `agent_source` label to Loki stream
- Added `agent_source` attribute to OTLP metrics

**`README.md`**
- Updated title to reflect multi-agent support
- Added "Soporte Multi-Agente" section
- Updated architecture diagram
- Added Claude Code usage examples
- Added hook configuration for Claude
- Added Loki query examples for filtering by agent

#### 🧪 Testing
- Comprehensive test suite: 9/9 tests passing
- Coverage for both GitHub Copilot and Claude Code
- Verified detection, normalization, and label generation

### Changed

#### Event Normalization
Both agents now map to the same normalized event types:

| GitHub Copilot       | Claude Code         | Normalized    |
|---------------------|---------------------|----------------|
| sessionStart        | SessionStart        | session_start  |
| userPromptSubmitted | UserPromptSubmit    | user_prompt    |
| preToolUse          | PreToolUse          | tool_use       |
| postToolUse         | PostToolUse         | tool_result    |
| sessionEnd          | SessionEnd          | session_end    |
| errorOccurred       | ErrorOccurred       | error          |

#### Payload Structure
All normalized events now include:
```json
{
  "agent_source": "github_copilot | claude_code | unknown",
  "event_type": "session_start | user_prompt | tool_use | ...",
  "metadata": {
    "agent_source": "...",
    "hook_event_type": "..."
  }
}
```

#### Loki Labels
Stream labels now include `agent_source`:
```json
{
  "stream": {
    "job": "session-logger-shell",
    "agent_source": "claude_code",
    "event_type": "user_prompt",
    "session_id": "...",
    "repository": "...",
    "branch": "..."
  }
}
```

#### OTLP Metrics
Metric attributes now include `agent_source`:
```json
{
  "attributes": [
    {"key": "agent_source", "value": {"stringValue": "claude_code"}},
    {"key": "event_type", "value": {"stringValue": "user_prompt"}},
    {"key": "tool_name", "value": {"stringValue": "Read"}}
  ]
}
```

### Fixed
- Defensive handling of `tool_result` when it's a string instead of object
- Prevents jq errors when accessing `.resultType` on string values

### Compatibility
- ✅ **Backward compatible**: All existing Copilot payloads work without changes
- ✅ **No breaking changes**: Existing hooks and configurations continue to work
- ✅ **Graceful fallback**: Unknown agents are handled as `agent_source="unknown"`

### Performance
- No performance impact: Detection is O(1) with simple field checks
- Minimal overhead: Single jq pass for detection before existing normalization

### Documentation
- Complete architecture documentation in `MULTI_AGENT.md`
- Updated `README.md` with multi-agent examples
- Interactive demo script with usage examples
- Query examples for Loki and Tempo

### Migration Guide
No migration needed! Existing installations work as-is.

To add Claude Code logging:
1. Add hooks to `.claude/settings.json` (see README.md)
2. Use PascalCase event names (SessionStart, UserPromptSubmit, etc.)
3. Query logs with `{agent_source="claude_code"}`

### Future Work
- [ ] Support for additional agents (Cursor, Cody, Tabnine)
- [ ] Agent-specific metrics (token usage, latency percentiles)
- [ ] Grafana dashboard comparing agents
- [ ] Alerting rules based on agent patterns
- [ ] Cost tracking per agent
- [ ] A/B testing framework for agent comparison

---

## Detection Strategy

The system uses a multi-layered detection approach:

1. **Distinctive Fields** (highest confidence)
   - Copilot: `copilot_user`, `copilotUser`, `githubCopilotUser`
   - Claude: `transcript_path` with `.claude/`, tools like `Read`/`Write`/`Edit`

2. **Naming Conventions** (high confidence)
   - Copilot: camelCase events (`userPromptSubmitted`)
   - Claude: PascalCase events (`UserPromptSubmit`)

3. **Environment Hints** (fallback)
   - `SESSION_LOGGER_SOURCE` containing "copilot"

4. **Unknown** (safe default)
   - When detection is impossible, mark as `unknown`

This layered approach ensures reliable detection while maintaining safe fallbacks.
