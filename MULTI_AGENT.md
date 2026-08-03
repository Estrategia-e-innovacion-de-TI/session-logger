# Multi-Agent Detection

El session-logger soporta detección automática de múltiples agentes de IA para proporcionar observabilidad unificada.

## Agentes Soportados

### GitHub Copilot
- **Detección**: Campos `copilotUser`, `githubCopilotUser`, eventos en camelCase
- **Eventos**: `sessionStart`, `userPromptSubmitted`, `preToolUse`, `postToolUse`, `sessionEnd`, `errorOccurred`
- **Herramientas**: Herramientas de VS Code, GitHub Copilot CLI

### Claude Code
- **Detección**: Campo `hook_event_name` en PascalCase, `transcript_path` con `.claude/`, herramientas específicas
- **Eventos**: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SessionEnd`, `ErrorOccurred`
- **Herramientas**: Read, Write, Edit, Bash, Agent, Workflow, etc.

## Arquitectura de Detección

```
┌─────────────────────┐
│   Hook Payload      │
│   (JSON via stdin)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  detect_agent_source│
│  (agent-detector.sh)│
└──────────┬──────────┘
           │
           ├─► Distinctive fields check
           │   • copilot_user → github_copilot
           │   • transcript_path w/.claude/ → claude_code
           │   • tool_name in [Read,Write,Edit] → claude_code
           │
           ├─► Event naming convention
           │   • camelCase → github_copilot
           │   • PascalCase → claude_code
           │
           └─► Environment variable fallback
               • SESSION_LOGGER_SOURCE → github_copilot (si contiene "copilot")
               • Default → unknown
```

## Campos Distintivos

### GitHub Copilot
```json
{
  "copilot_user": "usuario",
  "copilotUser": "usuario",
  "github_copilot_user": "usuario",
  "invocation": {
    "copilotUser": "usuario"
  },
  "eventType": "userPromptSubmitted"  // camelCase
}
```

### Claude Code
```json
{
  "hook_event_name": "UserPromptSubmit",  // PascalCase
  "transcript_path": "/Users/.../.claude/projects/.../session.jsonl",
  "tool_name": "Read",  // Herramientas específicas de Claude
  "tool_input": {
    "file_path": "/path/to/file"
  }
}
```

## Normalización de Eventos

Ambos agentes normalizan sus eventos a un formato común:

| GitHub Copilot       | Claude Code         | Normalizado    |
|---------------------|---------------------|----------------|
| sessionStart        | SessionStart        | session_start  |
| userPromptSubmitted | UserPromptSubmit    | user_prompt    |
| preToolUse          | PreToolUse          | tool_use       |
| postToolUse         | PostToolUse         | tool_result    |
| sessionEnd          | SessionEnd          | session_end    |
| errorOccurred       | ErrorOccurred       | error          |

## Payload Normalizado

Todos los eventos incluyen:

```json
{
  "event_id": "evt_...",
  "session_id": "sess_...",
  "agent_source": "github_copilot | claude_code | unknown",
  "event_type": "user_prompt | tool_use | tool_result | ...",
  "timestamp": "2026-06-18T21:35:15.250Z",
  "actor": "jomaver",
  "repository": "session-logger",
  "branch": "development",
  "tool_name": "Bash",
  "prompt_text": "...",
  "metadata": {
    "agent_source": "claude_code",
    "hook_event_type": "UserPromptSubmit",
    "logger_version": "0.2.0-shell"
  }
}
```

## Labels de Loki

Los eventos enviados a Loki incluyen el label `agent_source`:

```json
{
  "streams": [{
    "stream": {
      "job": "session-logger-shell",
      "agent_source": "claude_code",
      "event_type": "user_prompt",
      "session_id": "...",
      "repository": "...",
      "actor": "..."
    },
    "values": [[...]]
  }]
}
```

## Métricas OTLP

Las métricas incluyen el atributo `agent_source`:

```json
{
  "attributes": [
    {"key": "agent_source", "value": {"stringValue": "claude_code"}},
    {"key": "event_type", "value": {"stringValue": "user_prompt"}},
    {"key": "repository", "value": {"stringValue": "session-logger"}}
  ]
}
```

## Consultas de Ejemplo

### Loki

```logql
# Eventos de Claude Code en la última hora
{job="session-logger-shell", agent_source="claude_code"} |= "" | json | line_format "{{.event_type}}: {{.tool_name}}"

# Comparar volumen de prompts entre agentes
sum by (agent_source) (count_over_time({job="session-logger-shell", event_type="user_prompt"}[24h]))

# Herramientas más usadas por Claude
topk(10, sum by (tool_name) (count_over_time({job="session-logger-shell", agent_source="claude_code", event_type="tool_use"}[24h])))

# Sesiones activas por agente
count by (agent_source, session_id) ({job="session-logger-shell"})
```

### Tempo (Traces)

```
# Traces de Claude Code
{ resource.service.name="session-logger" } && { span.agent_source="claude_code" }

# Duración de tool calls por agente
histogram_quantile(0.95, rate(span.duration{span.event_type="tool_result"}[5m])) by (agent_source)
```

## Extensión para Nuevos Agentes

Para agregar soporte para un nuevo agente:

1. **Identificar campos distintivos** en los payloads del agente
2. **Agregar lógica de detección** en `lib/agent-detector.sh`:
   ```bash
   has_new_agent_fields=$(jq -r '
     if (.specific_field or .unique_pattern) then "true" else "false" end
   ' <<< "$payload")
   ```
3. **Agregar extractores específicos** en `lib/new-agent-payload.sh`
4. **Actualizar normalización** en `lib/payload.sh` con fallbacks
5. **Crear payloads de ejemplo** en `examples/new-agent-payloads/`
6. **Agregar tests** en suite de testing

## Testing

Ejecutar suite de tests multi-agente:

```bash
# Crear script de test
cat > /tmp/test-agents.sh << 'EOF'
#!/usr/bin/env bash
SCRIPT_DIR="$PWD"

# Test Copilot
cat examples/payload-user-prompt.json | \
  bash .github/hooks/session-logger/session-logger.sh --event userPromptSubmitted --dry-run | \
  jq -r '.agent_source'

# Test Claude
cat examples/claude-payloads/user-prompt-submit.json | \
  bash .github/hooks/session-logger/session-logger.sh --event UserPromptSubmit --dry-run | \
  jq -r '.agent_source'
EOF

bash /tmp/test-agents.sh
# Salida esperada:
# github_copilot
# claude_code
```

## Troubleshooting

### Agente detectado como "unknown"

1. Verificar que el payload contiene campos distintivos
2. Revisar la convención de nombres de eventos (camelCase vs PascalCase)
3. Agregar variable de entorno `SESSION_LOGGER_SOURCE` como hint
4. Habilitar modo debug: `set -x` en `agent-detector.sh`

### Eventos no normalizados correctamente

1. Verificar que `extract_event_type()` incluye todos los campos necesarios
2. Revisar fallbacks en `normalize_event_type()`
3. Agregar campos específicos del agente a las funciones extractoras

### Labels faltantes en Loki

1. Verificar que `agent_source` se pasa a `build_normalized_event()`
2. Confirmar que `build_loki_payload()` incluye el label
3. Revisar metadata del evento normalizado
