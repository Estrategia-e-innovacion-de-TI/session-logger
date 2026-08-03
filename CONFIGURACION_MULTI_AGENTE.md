# Configuración Multi-Agente para Session Logger

## Resumen

Los archivos `copilot-hooks.json` han sido actualizados para soportar detección automática de múltiples agentes de IA (GitHub Copilot y Claude Code).

## Cambios Realizados

### Variable de Entorno `SESSION_LOGGER_SOURCE`

Se agregó la variable de entorno `SESSION_LOGGER_SOURCE=copilot` a **todos los hooks** en ambos archivos:
- `.github/hooks/copilot-hooks.json`
- `hooks/copilot-hooks.json`

Esta variable sirve como **fallback** para el sistema de detección cuando los campos distintivos del payload no son suficientes para identificar el agente.

### Ejemplo de Configuración

#### Bash (Linux/macOS)
```bash
SESSION_LOGGER_SOURCE=copilot .github/hooks/session-logger/session-logger.sh --event sessionStart
```

#### PowerShell (Windows)
```powershell
$env:SESSION_LOGGER_SOURCE='copilot'; & .github/hooks/session-logger/session-logger-windows.ps1 -Event sessionStart
```

## Cómo Funciona la Detección

### 1. Detección por Campos Distintivos (Prioridad Alta)

El script `agent-detector.sh` primero busca campos únicos en el payload JSON:

#### GitHub Copilot
```json
{
  "copilot_user": "usuario",
  "copilotUser": "usuario",
  "eventType": "userPromptSubmitted"  // camelCase
}
```

#### Claude Code
```json
{
  "hook_event_name": "UserPromptSubmit",  // PascalCase
  "transcript_path": "/Users/.../.claude/projects/.../session.jsonl",
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/path/to/file"
  }
}
```

### 2. Detección por Convención de Nombres (Prioridad Media)

Si los campos distintivos no se encuentran, se analiza la convención de nombres del evento:

| Convención | Agente          | Ejemplo              |
|------------|-----------------|----------------------|
| camelCase  | GitHub Copilot  | `userPromptSubmitted`|
| PascalCase | Claude Code     | `UserPromptSubmit`   |

### 3. Variable de Entorno (Fallback)

Si ninguno de los métodos anteriores identifica el agente, se usa `SESSION_LOGGER_SOURCE`:

```bash
# En agent-detector.sh línea 62-66
if [[ "${SESSION_LOGGER_SOURCE:-}" == *"copilot"* ]]; then
  echo "github_copilot"
else
  echo "unknown"
fi
```

## Estructura de Eventos

### Eventos Soportados

Todos los hooks configurados:

| Hook                  | GitHub Copilot        | Claude Code        | Normalizado    |
|-----------------------|-----------------------|--------------------|----------------|
| Session start         | `sessionStart`        | `SessionStart`     | `session_start`|
| User prompt           | `userPromptSubmitted` | `UserPromptSubmit` | `user_prompt`  |
| Pre-tool              | `preToolUse`          | `PreToolUse`       | `tool_use`     |
| Post-tool             | `postToolUse`         | `PostToolUse`      | `tool_result`  |
| Session end           | `sessionEnd`          | `SessionEnd`       | `session_end`  |
| Error                 | `errorOccurred`       | `ErrorOccurred`    | `error`        |

## Payload Enviado a Loki/OTLP

Todos los eventos incluyen el campo `agent_source`:

```json
{
  "event_id": "evt_abc123",
  "session_id": "sess_xyz789",
  "agent_source": "github_copilot",  // ← Campo de detección
  "event_type": "user_prompt",
  "timestamp": "2026-06-18T21:35:15.250Z",
  "actor": "jomaver",
  "repository": "session-logger",
  "branch": "development",
  "metadata": {
    "agent_source": "github_copilot",
    "hook_event_type": "userPromptSubmitted",
    "logger_version": "0.2.0-shell"
  }
}
```

## Labels de Loki

Los eventos en Loki incluyen el label `agent_source` para facilitar consultas:

```logql
# Filtrar por agente específico
{job="session-logger-shell", agent_source="github_copilot"}

# Comparar prompts entre agentes
sum by (agent_source) (
  count_over_time({job="session-logger-shell", event_type="user_prompt"}[24h])
)

# Herramientas más usadas por agente
topk(10, 
  sum by (agent_source, tool_name) (
    count_over_time({job="session-logger-shell", event_type="tool_use"}[24h])
  )
)
```

## Métricas OTLP

Las métricas incluyen el atributo `agent_source`:

```json
{
  "attributes": [
    {"key": "agent_source", "value": {"stringValue": "github_copilot"}},
    {"key": "event_type", "value": {"stringValue": "user_prompt"}},
    {"key": "repository", "value": {"stringValue": "session-logger"}}
  ]
}
```

## Testing

### Probar Detección de GitHub Copilot

```bash
# Crear payload de ejemplo de Copilot
cat > /tmp/copilot-test.json << 'EOF'
{
  "copilotUser": "jomaver",
  "eventType": "userPromptSubmitted",
  "prompt": "test"
}
EOF

# Ejecutar con variable de entorno
cat /tmp/copilot-test.json | \
  SESSION_LOGGER_SOURCE=copilot \
  bash .github/hooks/session-logger/session-logger.sh \
  --event userPromptSubmitted --dry-run | \
  jq -r '.agent_source'

# Salida esperada: github_copilot
```

### Probar Detección de Claude Code

```bash
# Crear payload de ejemplo de Claude
cat > /tmp/claude-test.json << 'EOF'
{
  "hook_event_name": "UserPromptSubmit",
  "transcript_path": "/Users/jomaver/.claude/projects/test/session.jsonl",
  "prompt": "test"
}
EOF

# Ejecutar sin variable (debería detectar por campos)
cat /tmp/claude-test.json | \
  bash .github/hooks/session-logger/session-logger.sh \
  --event UserPromptSubmit --dry-run | \
  jq -r '.agent_source'

# Salida esperada: claude_code
```

## Configuración Personalizada

### Cambiar Endpoints de Observabilidad

Edita las variables de entorno en el JSON:

```json
{
  "bash": "COPILOT_SESSION_LOGGER_LOKI_ENABLED=true COPILOT_SESSION_LOGGER_LOKI_ENDPOINT=https://mi-loki.ejemplo.com/loki/api/v1/push COPILOT_SESSION_LOGGER_OTLP_ENABLED=true COPILOT_SESSION_LOGGER_OTLP_ENDPOINT=https://mi-otlp.ejemplo.com:4318 SESSION_LOGGER_SOURCE=copilot .github/hooks/session-logger/session-logger.sh --event sessionStart"
}
```

### Deshabilitar Transporte Específico

```json
{
  "bash": "COPILOT_SESSION_LOGGER_LOKI_ENABLED=false COPILOT_SESSION_LOGGER_OTLP_ENABLED=true COPILOT_SESSION_LOGGER_OTLP_ENDPOINT=http://localhost:4318 SESSION_LOGGER_SOURCE=copilot .github/hooks/session-logger/session-logger.sh --event sessionStart"
}
```

### Agregar Metadata Personalizada

```bash
SESSION_LOGGER_SOURCE=copilot \
COPILOT_SESSION_LOGGER_METADATA_JSON='{"team":"platform","env":"prod"}' \
.github/hooks/session-logger/session-logger.sh --event sessionStart
```

## Troubleshooting

### Agente Detectado como "unknown"

1. **Verificar payload**: Asegúrate de que contiene campos distintivos
   ```bash
   cat payload.json | jq .
   ```

2. **Verificar variable de entorno**:
   ```bash
   echo $SESSION_LOGGER_SOURCE
   ```

3. **Modo debug**:
   ```bash
   # Agregar set -x al inicio de agent-detector.sh
   bash -x .github/hooks/session-logger/lib/agent-detector.sh
   ```

### Campos no Capturados Correctamente

1. **Verificar extractores específicos**:
   - GitHub Copilot: `lib/payload.sh`
   - Claude Code: `lib/claude-payload.sh`

2. **Agregar campos faltantes**:
   ```bash
   # En claude-payload.sh
   extract_claude_custom_field() {
     local payload="$1"
     jq -r '.my_custom_field // empty' <<< "$payload"
   }
   ```

### Labels no Aparecen en Loki

1. **Verificar build_loki_payload()** en `transport.sh`:
   ```bash
   jq '.streams[0].stream' <<< "$(build_loki_payload ...)"
   ```

2. **Confirmar que agent_source se pasa**:
   ```bash
   grep -n "agent_source" .github/hooks/session-logger/lib/transport.sh
   ```

## Archivos Modificados

```
.github/hooks/copilot-hooks.json  ← Actualizado con SESSION_LOGGER_SOURCE
hooks/copilot-hooks.json          ← Sincronizado con .github/hooks/
```

## Scripts de Detección

```
.github/hooks/session-logger/lib/
├── agent-detector.sh      ← Lógica de detección multi-agente
├── claude-payload.sh      ← Extractores para Claude Code
└── payload.sh             ← Extractores genéricos y de Copilot
```

## Referencias

- [MULTI_AGENT.md](./MULTI_AGENT.md) - Documentación detallada de detección multi-agente
- [CHANGELOG_MULTI_AGENT.md](./CHANGELOG_MULTI_AGENT.md) - Historial de cambios
- [README.md](./README.md) - Documentación principal del proyecto
