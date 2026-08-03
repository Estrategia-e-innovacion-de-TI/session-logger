# Integración de Cursor - Guía Rápida

## Visión General

Se ha agregado soporte para **Cursor AI Editor** al session-logger, complementando el soporte existente para GitHub Copilot y Claude Code.

## Cambios Realizados

### 1. Sistema de Detección Multi-Agente Actualizado
**Archivo:** `hooks/session-logger/lib/agent-detector.sh`

- ✅ Agregado soporte para detectar Cursor
- ✅ Nuevos campos de búsqueda: `cursorUser`, `cursor_user`, `cursorSessionId`
- ✅ Normalización de etiqueta: Cursor → "cursor"
- ✅ Extracción de metadata específica de Cursor: `cursor_user`, `workspace_id`

### 2. Nueva Carpeta para Cursor
**Ubicación:** `hooks/session-logger-cursor/`

Contiene:
- `session-logger-cursor.sh` — Script principal (macOS/Linux)
- `session-logger-cursor.ps1` — Script principal (Windows)
- `cursor-hooks.json` — Configuración de hooks integrada
- `README.md` — Documentación completa
- `cursor-payload-example.json` — Ejemplo de payload para testing

## Diferencias Principales vs Copilot

```
┌─────────────────────────────────────────────────────────┐
│           Copilot vs Cursor vs Claude                    │
├─────────────────┬──────────────┬──────────────┬──────────┤
│     Campo       │   Copilot    │   Cursor     │  Claude  │
├─────────────────┼──────────────┼──────────────┼──────────┤
│ Usuario         │ copilotUser  │ cursorUser   │ actor    │
│ Variables env   │ COPILOT_*    │ CURSOR_*     │ COPILOT_*│
│ Formato eventos │ camelCase    │ camelCase    │ Pascal   │
│ Carpeta         │ session-log* │ session-log* │ session- │
│                 │ -cursor/     │ cursor/      │ logger/  │
│ Detección       │ Automática   │ Automática   │ Automát. │
└─────────────────┴──────────────┴──────────────┴──────────┘
```

## Uso Rápido

### Test Local (Dry Run)
```bash
CURSOR_SESSION_LOGGER_DRY_RUN=true \
bash hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted \
  < hooks/session-logger-cursor/cursor-payload-example.json
```

### Con Observabilidad
```bash
CURSOR_SESSION_LOGGER_LOKI_ENABLED=true \
CURSOR_SESSION_LOGGER_OTLP_ENABLED=true \
bash hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted \
  < hooks/session-logger-cursor/cursor-payload-example.json
```

### Diagnóstico
```bash
bash hooks/session-logger-cursor/session-logger-cursor.sh doctor
```

## Configuración en Cursor

### Ubicación de Hooks por OS

| SO | Ruta |
|---|---|
| macOS | `~/.cursor/settings/hooks/` |
| Linux | `~/.config/cursor/settings/hooks/` |
| Windows | `%APPDATA%\Cursor\settings\hooks\` |

### Agregar cursor-hooks.json

1. Ubica tu archivo de hooks de Cursor
2. Copia `hooks/session-logger-cursor/cursor-hooks.json` allí
3. Ajusta las rutas de scripts según tu setup

**Ejemplo en macOS:**
```bash
mkdir -p ~/.cursor/settings/hooks
cp hooks/session-logger-cursor/cursor-hooks.json ~/.cursor/settings/hooks/
```

## Campos Detectados para Cursor

El sistema espera estos campos en payloads de Cursor:

```json
{
  "eventType": "userPromptSubmitted",
  "sessionId": "sess_...",
  "cursorUser": "user@empresa.com",
  "cursorSessionId": "cursor_sess_...",
  "workspaceId": "workspace_..."
}
```

## Detección Automática

El agent-detector ahora prioriza:

1. **Claude** — PascalCase events + `hook_event_name` + `.claude/` paths
2. **Cursor** — `cursorUser` + `cursorSessionId` + `workspaceId`
3. **Copilot** — `copilotUser` + camelCase events
4. **Fallback** — Revisa `SESSION_LOGGER_SOURCE` env var

## Compatibilidad Backwards

✅ **Todos los cambios son 100% compatibles hacia atrás**

- Copilot sigue funcionando exactamente igual
- Claude sigue funcionando exactamente igual
- Se agregó soporte para Cursor sin romper nada existente

## Próximos Pasos Opcionales

1. **Validar payloads reales de Cursor** — Algunos campos adicionales pueden estar en payloads reales
2. **Agregar más eventos específicos de Cursor** — Si Cursor tiene eventos únicos
3. **Documentar diferencias de herramientas** — Cursor podría tener tools diferentes a Copilot
4. **Crear un test suite específico para Cursor** — Valida detección e integración

## Archivos Modificados

```
✏️  hooks/session-logger/lib/agent-detector.sh  (actualizado para Cursor)
📁  hooks/session-logger-cursor/                (NUEVA carpeta)
  ├── session-logger-cursor.sh               (NUEVO)
  ├── session-logger-cursor.ps1              (NUEVO)
  ├── cursor-hooks.json                      (NUEVO)
  ├── README.md                              (NUEVO)
  └── cursor-payload-example.json            (NUEVO)
```

## Soporte y Troubleshooting

Consulta `hooks/session-logger-cursor/README.md` para:
- Instalación paso a paso
- Variables de entorno disponibles
- Troubleshooting de problemas comunes
- Ejemplos avanzados
- Integración con Docker stack

---

**Nota:** La detección automática de agentes se hace en el agent-detector.sh compartido. Los scripts específicos de cursor (`session-logger-cursor.sh`) fuerzan `agent_source="cursor"` para evitar ambigüedades.
