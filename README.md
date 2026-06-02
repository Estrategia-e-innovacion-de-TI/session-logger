# session-logger

Hook de monitoreo para GitHub Copilot orientado a observabilidad.

Estado actual de esta rama:
- Sin backend de ingesta.
- Sin almacenamiento local de logs JSONL.
- Envio directo a Loki y Tempo (OTLP traces + metrics).
- `files_added` basado en adjuntos explicitos del payload/herramientas (no en `git diff`).
- Soporte de ejecucion para macOS/Linux (`bash`) y Windows (`PowerShell`).

## Arquitectura

```text
Copilot Hook Event
  -> hooks/session-logger.sh (macOS/Linux) o .github/hooks/session-logger/session-logger-windows.ps1 (Windows)
  -> normalizacion + sanitizacion
  -> envio a Loki (/loki/api/v1/push)
  -> envio OTLP a Tempo/Collector (/v1/traces y /v1/metrics)
```

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

### macOS / Linux

```bash
COPILOT_SESSION_LOGGER_LOKI_ENABLED=true \
COPILOT_SESSION_LOGGER_OTLP_ENABLED=true \
bash hooks/session-logger.sh --event userPromptSubmitted < examples/payload-user-prompt.json
```

### Windows (PowerShell)

```powershell
$env:COPILOT_SESSION_LOGGER_LOKI_ENABLED = "true"
$env:COPILOT_SESSION_LOGGER_OTLP_ENABLED = "true"
Get-Content examples/payload-user-prompt.json | .github/hooks/session-logger/session-logger-windows.ps1 -Event userPromptSubmitted
```

## Hooks de referencia

- Configuracion lista para usar: `.github/hooks/copilot-hooks.json`
- Ejemplo alterno: `examples/copilot-hooks.json`

## Prueba rapida del script bash

```bash
bash scripts/test-session-logger.sh
```

