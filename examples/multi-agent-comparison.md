# Comparación de Payloads Multi-Agente

## GitHub Copilot

### Payload de Entrada
```json
{
  "copilotUser": "jomaver",
  "eventType": "userPromptSubmitted",
  "prompt": "Fix the authentication bug",
  "timestamp": "2026-06-18T21:35:15.250Z",
  "version": "1.0.0"
}
```

### Detección
```
1️⃣ Buscar campos distintivos
   ✅ Encontrado: copilotUser
   ✅ Encontrado: eventType (camelCase)
   
2️⃣ Resultado: github_copilot
```

### Payload Normalizado de Salida
```json
{
  "event_id": "evt_1718746515250_abc123",
  "session_id": "sess_xyz789",
  "agent_source": "github_copilot",
  "event_type": "user_prompt",
  "timestamp": "2026-06-18T21:35:15.250Z",
  "actor": "jomaver",
  "repository": "session-logger",
  "branch": "development",
  "working_directory": "/Users/jomaver/Desktop/Code/session-logger",
  "prompt_text": "Fix the authentication bug",
  "metadata": {
    "agent_source": "github_copilot",
    "hook_event_type": "userPromptSubmitted",
    "logger_version": "0.2.0-shell",
    "agent_version": "1.0.0"
  }
}
```

### Labels de Loki
```json
{
  "job": "session-logger-shell",
  "agent_source": "github_copilot",
  "event_type": "user_prompt",
  "session_id": "sess_xyz789",
  "repository": "session-logger",
  "actor": "jomaver"
}
```

---

## Claude Code

### Payload de Entrada
```json
{
  "hook_event_name": "UserPromptSubmit",
  "sessionId": "5c3d4e5f-6a7b-8c9d-0e1f-2a3b4c5d6e7f",
  "transcript_path": "/Users/jomaver/.claude/projects/-Users-jomaver-Desktop-Code-session-logger/session.jsonl",
  "prompt": "Refactor the session logger",
  "timestamp": "2026-06-18T21:40:30.123Z",
  "actor": "jomaver",
  "repository": "session-logger",
  "branch": "development"
}
```

### Detección
```
1️⃣ Buscar campos distintivos
   ✅ Encontrado: hook_event_name (PascalCase)
   ✅ Encontrado: transcript_path con .claude/
   
2️⃣ Resultado: claude_code
```

### Payload Normalizado de Salida
```json
{
  "event_id": "evt_1718746830123_def456",
  "session_id": "5c3d4e5f-6a7b-8c9d-0e1f-2a3b4c5d6e7f",
  "agent_source": "claude_code",
  "event_type": "user_prompt",
  "timestamp": "2026-06-18T21:40:30.123Z",
  "actor": "jomaver",
  "repository": "session-logger",
  "branch": "development",
  "working_directory": "/Users/jomaver/Desktop/Code/session-logger",
  "prompt_text": "Refactor the session logger",
  "session_transcript": "/Users/jomaver/.claude/projects/-Users-jomaver-Desktop-Code-session-logger/session.jsonl",
  "metadata": {
    "agent_source": "claude_code",
    "hook_event_type": "UserPromptSubmit",
    "logger_version": "0.2.0-shell"
  }
}
```

### Labels de Loki
```json
{
  "job": "session-logger-shell",
  "agent_source": "claude_code",
  "event_type": "user_prompt",
  "session_id": "5c3d4e5f-6a7b-8c9d-0e1f-2a3b4c5d6e7f",
  "repository": "session-logger",
  "actor": "jomaver"
}
```

---

## Tool Use: Copilot vs Claude

### GitHub Copilot - PreToolUse

#### Entrada
```json
{
  "eventType": "preToolUse",
  "copilotUser": "jomaver",
  "toolName": "file_read",
  "toolArgs": {
    "path": "src/auth.js"
  }
}
```

#### Salida Normalizada
```json
{
  "event_id": "evt_...",
  "agent_source": "github_copilot",
  "event_type": "tool_use",
  "tool_name": "file_read",
  "tool_input": {
    "path": "src/auth.js"
  },
  "files_touched": ["src/auth.js"]
}
```

### Claude Code - PreToolUse

#### Entrada
```json
{
  "hook_event_name": "PreToolUse",
  "tool_name": "Read",
  "tool_use_id": "toolu_abc123",
  "tool_input": {
    "file_path": "/Users/jomaver/Desktop/Code/session-logger/src/auth.js"
  }
}
```

#### Salida Normalizada
```json
{
  "event_id": "evt_...",
  "agent_source": "claude_code",
  "event_type": "tool_use",
  "tool_name": "Read",
  "tool_use_id": "toolu_abc123",
  "tool_input": {
    "file_path": "/Users/jomaver/Desktop/Code/session-logger/src/auth.js"
  },
  "files_touched": [
    "/Users/jomaver/Desktop/Code/session-logger/src/auth.js"
  ],
  "tool_input_summary": "/Users/jomaver/Desktop/Code/session-logger/src/auth.js"
}
```

---

## Comparación de Campos

| Campo                  | GitHub Copilot       | Claude Code               | Normalizado          |
|------------------------|----------------------|---------------------------|----------------------|
| Usuario                | `copilotUser`        | `actor`                   | `actor`              |
| Tipo de evento         | `eventType`          | `hook_event_name`         | `event_type`         |
| ID de sesión           | Generado por logger  | `sessionId`               | `session_id`         |
| Nombre de herramienta  | `toolName`           | `tool_name`               | `tool_name`          |
| Argumentos herramienta | `toolArgs`           | `tool_input`              | `tool_input`         |
| Ruta de archivo        | `toolArgs.path`      | `tool_input.file_path`    | `files_touched[]`    |
| Transcript             | N/A                  | `transcript_path`         | `session_transcript` |
| Versión del agente     | `version`            | N/A                       | `metadata.agent_version` |

---

## Consultas de Loki

### Eventos por Agente (Últimas 24h)
```logql
sum by (agent_source) (
  count_over_time({job="session-logger-shell"}[24h])
)
```

**Resultado esperado:**
```
github_copilot  142
claude_code     89
```

### Prompts de Usuario por Agente
```logql
{job="session-logger-shell", event_type="user_prompt"} 
| json 
| line_format "{{.agent_source}}: {{.prompt_text}}"
```

**Resultado esperado:**
```
github_copilot: Fix the authentication bug
claude_code: Refactor the session logger
github_copilot: Add error handling
claude_code: Update documentation
```

### Herramientas Más Usadas por Agente
```logql
topk(5, 
  sum by (agent_source, tool_name) (
    count_over_time({
      job="session-logger-shell", 
      event_type="tool_use"
    }[24h])
  )
)
```

**Resultado esperado:**
```
claude_code, Read       45
claude_code, Edit       32
claude_code, Bash       18
github_copilot, file_read   28
github_copilot, file_write  15
```

### Duración de Sesiones por Agente
```logql
# Calcular duración desde sessionStart hasta sessionEnd
sum by (agent_source) (
  max_over_time({
    job="session-logger-shell", 
    event_type="session_end"
  }[24h]) 
  - 
  min_over_time({
    job="session-logger-shell", 
    event_type="session_start"
  }[24h])
)
```

---

## Ventajas de la Detección Multi-Agente

### 1. Observabilidad Unificada
```logql
# Una sola consulta para todos los agentes
{job="session-logger-shell"} | json
```

### 2. Comparación Directa
```logql
# Comparar prompts por hora entre agentes
sum by (agent_source) (
  rate({job="session-logger-shell", event_type="user_prompt"}[1h])
)
```

### 3. Debugging Específico
```logql
# Solo errores de un agente específico
{job="session-logger-shell", agent_source="claude_code", event_type="error"}
```

### 4. Análisis de Patrones
```logql
# Patrones de uso de herramientas
{job="session-logger-shell", event_type="tool_use"} 
| json 
| line_format "{{.agent_source}} → {{.tool_name}}"
| pattern "<agent> → <tool>"
| unwrap tool
```

---

## Casos de Uso

### 1. Identificar Agente Más Activo
```bash
curl -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query=sum by (agent_source) (count_over_time({job="session-logger-shell"}[24h]))' | \
  jq -r '.data.result[] | "\(.metric.agent_source): \(.value[1])"'
```

### 2. Alertar en Errores por Agente
```yaml
# Prometheus Alert Rule
- alert: ClaudeCodeHighErrorRate
  expr: |
    rate({job="session-logger-shell", agent_source="claude_code", event_type="error"}[5m]) > 0.1
  annotations:
    summary: Claude Code tiene una tasa de errores alta
```

### 3. Dashboard de Comparación
```json
{
  "dashboard": "Multi-Agent Comparison",
  "panels": [
    {
      "title": "Eventos por Agente",
      "query": "sum by (agent_source) (count_over_time({job=\"session-logger-shell\"}[24h]))"
    },
    {
      "title": "Herramientas por Agente",
      "query": "sum by (agent_source, tool_name) (count_over_time({job=\"session-logger-shell\", event_type=\"tool_use\"}[24h]))"
    }
  ]
}
```
