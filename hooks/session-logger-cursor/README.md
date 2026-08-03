# Session Logger para Cursor

Integración de hooks para captura de prompts y eventos de sesión en **Cursor** AI Editor, complementando el soporte existente para GitHub Copilot y Claude Code.

## Descripción

Esta carpeta contiene scripts y configuración para conectar eventos de Cursor con el sistema de observabilidad del session-logger. Los scripts reutilizan la mayoría de la infraestructura compartida del proyecto.

## Diferencias con Copilot

| Aspecto | Copilot | Cursor |
|--------|---------|--------|
| **Campos de usuario** | `copilotUser`, `copilot_user` | `cursorUser`, `cursor_user` |
| **Variables de entorno** | `COPILOT_SESSION_LOGGER_*` | `CURSOR_SESSION_LOGGER_*` |
| **Ruta de configuración** | `.github/hooks/session-logger/` | `hooks/session-logger-cursor/` |
| **Eventos** | camelCase (userPromptSubmitted) | camelCase (userPromptSubmitted) |
| **Sistema de detección** | Detecta automáticamente por campos distintivos | Forzado a "cursor" en scripts específicos |

## Archivos

- **session-logger-cursor.sh** — Script principal para macOS/Linux
- **session-logger-cursor.ps1** — Script principal para Windows (PowerShell)
- **cursor-hooks.json** — Configuración de hooks para Cursor
- **README.md** — Este archivo

## Instalación

### Paso 1: Copiar configuración de hooks a Cursor

Cursor tiene su propia ubicación para archivos de configuración. La ruta varía según el OS:

**macOS:**
```bash
~/.cursor/settings/hooks/
```

**Linux:**
```bash
~/.config/cursor/settings/hooks/
```

**Windows:**
```
%APPDATA%\Cursor\settings\hooks\
```

Copia el archivo `cursor-hooks.json` a una de estas ubicaciones.

### Paso 2: Configurar rutas en el JSON

Edita `cursor-hooks.json` para ajustar las rutas de los scripts según tu setup:

```json
{
  "hooks": {
    "sessionStart": [
      {
        "bash": "CURSOR_SESSION_LOGGER_LOKI_ENABLED=true ... /ruta/a/hooks/session-logger-cursor/session-logger-cursor.sh --event sessionStart"
      }
    ]
  }
}
```

### Paso 3: (Opcional) Configurar observabilidad

Si deseas enviar eventos a Loki y/o OTLP, actualiza los endpoints:

```bash
CURSOR_SESSION_LOGGER_LOKI_ENDPOINT=http://tu-servidor:3100/loki/api/v1/push
CURSOR_SESSION_LOGGER_OTLP_ENDPOINT=http://tu-servidor:4318
```

## Uso Rápido

### Prueba local (macOS/Linux)

```bash
# Test básico con dry-run
CURSOR_SESSION_LOGGER_DRY_RUN=true \
bash hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted < examples/payload-user-prompt.json
```

### Con observabilidad activa

```bash
CURSOR_SESSION_LOGGER_LOKI_ENABLED=true \
CURSOR_SESSION_LOGGER_LOKI_ENDPOINT=http://localhost:3100/loki/api/v1/push \
CURSOR_SESSION_LOGGER_OTLP_ENABLED=true \
CURSOR_SESSION_LOGGER_OTLP_ENDPOINT=http://localhost:4318 \
bash hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted < examples/payload-user-prompt.json
```

### Diagnóstico

```bash
bash hooks/session-logger-cursor/session-logger-cursor.sh doctor
```

Genera un reporte de configuración y dependencias.

## Variables de Entorno

Todas las variables usan el prefijo `CURSOR_SESSION_LOGGER_*`:

| Variable | Default | Descripción |
|----------|---------|------------|
| `CURSOR_SESSION_LOGGER_EVENT_TYPE` | (de payload) | Sobrescribe el tipo de evento |
| `CURSOR_SESSION_LOGGER_SESSION_ID` | (generado) | ID de sesión explícito |
| `CURSOR_SESSION_LOGGER_DRY_RUN` | `false` | Modo simulación (sin enviar datos) |
| `CURSOR_SESSION_LOGGER_METADATA_JSON` | `{}` | Metadata adicional en formato JSON |
| `CURSOR_SESSION_LOGGER_LOKI_ENABLED` | `false` | Activar envío a Loki |
| `CURSOR_SESSION_LOGGER_LOKI_ENDPOINT` | `http://localhost:3100/loki/api/v1/push` | Endpoint de Loki |
| `CURSOR_SESSION_LOGGER_LOKI_TENANT_ID` | (vacío) | Tenant ID de Loki (header X-Scope-OrgID) |
| `CURSOR_SESSION_LOGGER_OTLP_ENABLED` | `false` | Activar envío OTLP (Tempo) |
| `CURSOR_SESSION_LOGGER_OTLP_ENDPOINT` | `http://localhost:4318` | Endpoint base del colector OTLP |
| `CURSOR_SESSION_LOGGER_TIMEOUT_SECONDS` | `2` | Timeout para requests HTTP |
| `CURSOR_SESSION_LOGGER_REDACT_SECRETS` | `true` | Sanitización de secretos |
| `CURSOR_SESSION_LOGGER_ACTOR` | (usuario del SO) | Actor fallback si no está en payload |
| `CURSOR_SESSION_LOGGER_STRICT` | `false` | Modo estricto (fallar en errores) |

## Detección Multi-Agente

El sistema detecta automáticamente la fuente del evento (Copilot, Claude, Cursor o desconocido). Sin embargo, los scripts específicos de Cursor fuerzan la detección a `agent_source: "cursor"` para garantizar que los eventos se etiqueten correctamente.

Campos detectados como Cursor:
- `cursorUser`, `cursor_user`
- `cursorSessionId`, `cursor_session_id`
- `editor: "cursor"`, `editorType: "cursor"`
- Presencia de `invocation.cursorUser`

## Estructura del Payload Esperado

Cursor envía eventos similares a Copilot con esta estructura aproximada:

```json
{
  "eventType": "userPromptSubmitted",
  "sessionId": "sess_...",
  "cursorUser": "usuario@empresa.com",
  "workspaceId": "workspace_...",
  "prompt": "tu pregunta aquí",
  "timestamp": "2026-07-28T10:15:00Z",
  "repository": "mi-repo",
  "branch": "main"
}
```

## Soporte de Plataformas

- **macOS/Linux** — Bash: `session-logger-cursor.sh`
- **Windows** — PowerShell 5.1+: `session-logger-cursor.ps1`

Ambos scripts reutilizan las librerías compartidas de `../session-logger/lib/`:
- `logger.sh` — Logging and utilities
- `agent-detector.sh` — Detección multi-agente *(actualizado para Cursor)*
- `payload.sh` — Extracción y normalización de payloads
- `transport.sh` — Envío a Loki y OTLP
- `state.sh` — Gestión de estado de sesión

## Troubleshooting

### "agente no detectado" o "agent_source: unknown"

**Causa:** El payload no tiene campos distintivos de Cursor.

**Solución:** Verifica que el payload incluya `cursorUser` o `cursor_session_id`. Alternativamente, asegúrate que la variable `SESSION_LOGGER_SOURCE=cursor` esté configurada.

### "Timeout al conectar con Loki/OTLP"

Verifica que:
1. Los endpoints están accesibles (`curl -I http://localhost:3100`)
2. Los firewalls no bloquean las conexiones
3. `CURSOR_SESSION_LOGGER_LOKI_ENABLED=true` y `CURSOR_SESSION_LOGGER_OTLP_ENABLED=true` están configuradas

### Script no encuentra librerías

Los scripts asumen que están en `hooks/session-logger-cursor/` y las librerías compartidas están en `hooks/session-logger/lib/`.

Verifica la estructura:
```
hooks/
  session-logger/
    lib/
      agent-detector.sh
      logger.sh
      payload.sh
      transport.sh
      state.sh
  session-logger-cursor/
    session-logger-cursor.sh
    cursor-hooks.json
```

## Ejemplos

Puedes encontrar ejemplos de payloads en `examples/`:
- `payload-user-prompt.json` — Estructura básica compatible con Cursor
- `test_session_logger.jsonl` — Stream de eventos de prueba

Adapta estos para enviar como:
```bash
cat examples/payload-user-prompt.json | bash hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted
```

## Integración con Docker Observability Stack

Si tienes el stack de observabilidad ejecutándose (Loki, Tempo, etc.):

```bash
docker-compose -f Stack-observabilidad/docker-compose.observability.yml up -d
```

Luego ejecuta:
```bash
CURSOR_SESSION_LOGGER_LOKI_ENABLED=true \
CURSOR_SESSION_LOGGER_OTLP_ENABLED=true \
bash hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted < examples/payload-user-prompt.json
```

Los eventos aparecerán en:
- **Loki**: http://localhost:3100
- **Tempo** (Grafana): http://localhost:3000 (credenciales: admin/admin)

## Contribuciones

Para mejorar la integración de Cursor:
1. Documenta campos adicionales que Cursor envía en sus payloads
2. Abre un PR con ejemplos reales de eventos de Cursor
3. Reporta incompatibilidades con nuevas versiones de Cursor

## Licencia

Mismo que el proyecto principal (ver LICENSE).
