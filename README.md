# session-logger

Hook de monitoreo multi-agente (GitHub Copilot y Claude Code) orientado a observabilidad.

Estado actual de esta rama:
- Sin backend de ingesta.
- Sin almacenamiento local de logs JSONL.
- Envio directo a Loki y Tempo (OTLP traces + metrics).
- `files_added` basado en adjuntos explicitos del payload/herramientas (no en `git diff`).
- Soporte de ejecucion para macOS/Linux (`bash`) y Windows (`PowerShell`).

## Arquitectura

```text
Hook Event (Copilot o Claude)
  -> session-logger.sh (macOS/Linux) o session-logger-windows.ps1 (Windows)
  -> deteccion automatica de agente (github_copilot | claude_code | unknown)
  -> normalizacion + sanitizacion
  -> envio a Loki (/loki/api/v1/push) con label agent_source
  -> envio OTLP a Tempo/Collector (/v1/traces y /v1/metrics)
```

## Soporte Multi-Agente

El logger detecta automáticamente la fuente del evento:

- **GitHub Copilot**: Detectado por campos `copilotUser`, `githubCopilotUser`, o eventos en camelCase (`userPromptSubmitted`)
- **Claude Code**: Detectado por `hook_event_name` en PascalCase (`UserPromptSubmit`), campo `transcript_path`, o herramientas específicas (`Read`, `Write`, `Edit`)
- **Unknown**: Fallback cuando no se puede determinar el agente

Todos los eventos normalizados incluyen:
- Campo `agent_source`: `github_copilot`, `claude_code`, o `unknown`
- Label `agent_source` en Loki para filtrado
- Atributo `agent_source` en métricas OTLP

## Variables de entorno

| Variable | Default | Uso |
| --- | --- | --- |
| `COPILOT_SESSION_LOGGER_SOURCE` | `github_copilot_hook` | Fuente del evento. |
| `COPILOT_SESSION_LOGGER_STATE_DIR` | `~/.session-logger/state` | Estado minimo de sesion (`userPrompt_id`). |
| `COPILOT_SESSION_LOGGER_LOKI_ENABLED` | `false` | Activa envio a Loki. |
| `COPILOT_SESSION_LOGGER_LOKI_ENDPOINT` | `http://localhost:3100/loki/api/v1/push` | Endpoint Loki. |
| `COPILOT_SESSION_LOGGER_LOKI_TENANT_ID` | vacio | Tenant Loki opcional (`X-Scope-OrgID`). |
| `COPILOT_SESSION_LOGGER_OTLP_ENABLED` | `false` | Activa envio OTLP (Tempo). |
| `COPILOT_SESSION_LOGGER_OTLP_ENDPOINT` | `http://localhost:4318` | Endpoint base OTLP. |
| `COPILOT_SESSION_LOGGER_TIMEOUT_SECONDS` | `2` | Timeout HTTP de transporte. |
| `COPILOT_SESSION_LOGGER_REDACT_SECRETS` | `true` | Sanitiza secretos antes de enviar. |
| `COPILOT_SESSION_LOGGER_ACTOR` | usuario del entorno | Actor fallback. |
| `COPILOT_SESSION_LOGGER_METADATA_JSON` | `{}` | Metadata adicional del evento. |

## `files_added`

`files_added` captura adjuntos explicitos y rutas enviadas por herramientas.

Fuentes soportadas:
- Campos directos: `files_added`, `added_files`, `attachments`, `attachment_files` y variantes camelCase.
- Campos anidados en `payload`.
- Campos en `toolArgs`/`toolResult` (incluye `filePath`, `paths`, `files`, `attachments`, `images`, etc.).

No se usa fallback por estado de Git para `files_added`.

## Uso rapido

### GitHub Copilot (macOS / Linux)

```bash
COPILOT_SESSION_LOGGER_LOKI_ENABLED=true \
COPILOT_SESSION_LOGGER_OTLP_ENABLED=true \
bash .github/hooks/session-logger/session-logger.sh --event userPromptSubmitted < examples/payload-user-prompt.json
```

### Claude Code (macOS / Linux)

```bash
COPILOT_SESSION_LOGGER_LOKI_ENABLED=true \
COPILOT_SESSION_LOGGER_OTLP_ENABLED=true \
bash .github/hooks/session-logger/session-logger.sh --event UserPromptSubmit < examples/claude-payloads/user-prompt-submit.json
```

### Windows (PowerShell)

```powershell
$env:COPILOT_SESSION_LOGGER_LOKI_ENABLED = "true"
$env:COPILOT_SESSION_LOGGER_OTLP_ENABLED = "true"
Get-Content examples/payload-user-prompt.json | .github/hooks/session-logger/session-logger-windows.ps1 -Event userPromptSubmitted
```

## Hooks de referencia

### GitHub Copilot
- Configuracion lista para usar: `.github/hooks/copilot-hooks.json`
- Ejemplo alterno: `examples/copilot-hooks.json`
- Payloads de ejemplo: `examples/payload-*.json`

### Claude Code
- Configuracion para Claude: `.claude/settings.local.json` (este proyecto)
- Payloads de ejemplo: `examples/claude-payloads/*.json`
- Eventos soportados: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SessionEnd`, `ErrorOccurred`

## Configuracion de hooks

### GitHub Copilot

Coloca `copilot-hooks.json` en la raíz del proyecto y configura las variables de entorno en los comandos bash/powershell.

### Claude Code

Agrega hooks en `.claude/settings.json` o `.claude/settings.local.json`:

```json
{
  "version": 1,
  "hooks": {
    "UserPromptSubmit": [{
      "type": "command",
      "bash": "COPILOT_SESSION_LOGGER_LOKI_ENABLED=true COPILOT_SESSION_LOGGER_OTLP_ENABLED=true .github/hooks/session-logger/session-logger.sh --event UserPromptSubmit",
      "cwd": ".",
      "timeoutSec": 5
    }],
    "PreToolUse": [{
      "type": "command",
      "bash": "COPILOT_SESSION_LOGGER_LOKI_ENABLED=true COPILOT_SESSION_LOGGER_OTLP_ENABLED=true .github/hooks/session-logger/session-logger.sh --event PreToolUse",
      "cwd": ".",
      "timeoutSec": 5
    }],
    "PostToolUse": [{
      "type": "command",
      "bash": "COPILOT_SESSION_LOGGER_LOKI_ENABLED=true COPILOT_SESSION_LOGGER_OTLP_ENABLED=true .github/hooks/session-logger/session-logger.sh --event PostToolUse",
      "cwd": ".",
      "timeoutSec": 5
    }]
  }
}
```

**Nota**: Claude Code usa nombres de eventos en PascalCase (`UserPromptSubmit`) mientras que GitHub Copilot usa camelCase (`userPromptSubmitted`).

## Consultas en Loki

### Filtrar por agente

```logql
# Solo eventos de GitHub Copilot
{job="session-logger-shell", agent_source="github_copilot"}

# Solo eventos de Claude Code
{job="session-logger-shell", agent_source="claude_code"}

# Comparar uso entre agentes
sum by (agent_source) (count_over_time({job="session-logger-shell"}[1h]))

# Herramientas más usadas por agente
sum by (agent_source, tool_name) (count_over_time({job="session-logger-shell", event_type="tool_use"}[1h]))
```

## Prueba rapida del script bash

```bash
bash scripts/test-session-logger.sh
```

