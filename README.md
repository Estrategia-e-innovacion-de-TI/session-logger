# copilot-session-logger

`copilot-session-logger` es un hook logger para GitHub Copilot que captura prompts, eventos de sesion, uso de herramientas y errores en un formato apto para auditoria, analitica y troubleshooting.

El proyecto esta basado en el ejemplo oficial `hooks/session-logger` de `github/awesome-copilot`, pero extiende el enfoque con:

- persistencia estructurada en JSONL
- SQLite opcional
- sanitizacion de secretos
- correlacion best-effort de `session_id`
- enriquecimiento con contexto Git
- CLI reusable para hooks y pruebas locales

## Problema que resuelve

Los hooks oficiales muestran un ejemplo minimo para loggear eventos de Copilot, pero no cubren observabilidad suficiente para auditoria real. Este proyecto agrega un collector local que:

- guarda el payload crudo sanitizado
- intenta extraer el prompt del usuario aunque el schema cambie
- correlaciona eventos por sesion cuando el payload no trae `sessionId`
- agrega branch, commit, repo, archivos modificados y tool use cuando aplica

## Que informacion captura

Cada `EventRecord` incluye:

- `event_id`
- `session_id`
- `event_type`
- `timestamp`
- `user_prompt`
- `prompt_hash`
- `repo_path`
- `repo_name`
- `git_branch`
- `git_commit`
- `working_directory`
- `actor`
- `files_changed`
- `tool_name`
- `command`
- `status`
- `error`
- `raw_payload`
- `metadata`

`metadata` conserva informacion adicional como `tool_args`, `tool_result`, `source`, `reason`, estado del parser de stdin y diagnostico Git.

## Instalacion

```bash
pip install -e ".[dev]"
```

## Uso rapido

```bash
copilot-session-logger doctor
```

```bash
echo '{"prompt":"Explicame este codigo"}' | copilot-session-logger log --event userPromptSubmitted --dry-run
```

```bash
copilot-session-logger demo
```

## CLI

### `log`

Lee JSON desde `stdin` y genera un `EventRecord`. Si `stdin` viene vacio, usa argumentos, variables de entorno y contexto Git.

```bash
copilot-session-logger log --event userPromptSubmitted
```

Opciones utiles:

- `--dry-run`: imprime el `EventRecord` en stdout y no escribe archivos
- `--sqlite`: habilita SQLite para esa ejecucion
- `--session-id`: fuerza un `session_id`
- `--actor`: fuerza el usuario/actor
- `--metadata-json '{"team":"platform"}'`: agrega metadata libre

Nota importante:

- El comando `log` es silencioso por defecto para no interferir con hooks como `preToolUse`, cuyo stdout puede ser interpretado por Copilot.

### `doctor`

Imprime un reporte JSON con:

- version de Python
- rutas efectivas
- config cargada
- diagnostico Git
- estado de almacenamiento

### `demo`

Genera tres eventos simulados:

1. `sessionStart`
2. `userPromptSubmitted`
3. `postToolUse`

## Persistencia

Por defecto los eventos se escriben en:

```text
~/.copilot-session-logger/logs/YYYY-MM-DD/events.jsonl
```

SQLite opcional:

```text
~/.copilot-session-logger/session_logs.db
```

Puedes cambiar la base de almacenamiento con:

```text
COPILOT_SESSION_LOGGER_HOME
```

## Configuracion YAML

El archivo por defecto es:

```text
~/.copilot-session-logger/config.yaml
```

Ejemplo:

```yaml
actor: your-user
dry_run: false
redact_secrets: true
storage:
  jsonl_enabled: true
  sqlite_enabled: true
paths:
  home_dir: ~/.copilot-session-logger
  logs_dir: ~/.copilot-session-logger/logs
  sqlite_path: ~/.copilot-session-logger/session_logs.db
  session_state_path: ~/.copilot-session-logger/state/active_sessions.json
```

## Configuracion del hook en GitHub Copilot

La documentacion actual de hooks de GitHub Copilot no usa el formato simplificado `{"command":"..."}`. El formato compatible actual usa:

- `version: 1`
- `hooks`
- por evento, un arreglo de objetos `type: "command"`
- claves `bash` y/o `powershell`

Este repositorio incluye un ejemplo listo en [examples/copilot-hooks.json](examples/copilot-hooks.json).

Ejemplo:

```json
{
  "version": 1,
  "hooks": {
    "userPromptSubmitted": [
      {
        "type": "command",
        "bash": "copilot-session-logger log --event userPromptSubmitted",
        "powershell": "copilot-session-logger log --event userPromptSubmitted",
        "cwd": ".",
        "timeoutSec": 15
      }
    ]
  }
}
```

Para usarlo en un repositorio con Copilot CLI o agentes, coloca un archivo `.json` dentro de `.github/hooks/`.

## Probar sin Copilot

```bash
echo '{"prompt":"Explícame este código"}' | copilot-session-logger log --event userPromptSubmitted --dry-run
```

PowerShell:

```powershell
'{"prompt":"Explicame este codigo"}' | copilot-session-logger log --event userPromptSubmitted --dry-run
```

## Ejemplo de evento JSONL

```json
{
  "event_id": "7cb355f9-d8de-45b7-a4db-387cb16fe545",
  "session_id": "2ee7f2df-0f18-4dc1-b661-7df32d07a7be",
  "event_type": "userPromptSubmitted",
  "timestamp": "2024-01-07T18:41:00+00:00",
  "user_prompt": "Explain this code safely",
  "prompt_hash": "4b36209d7d5e6380d4d99257ed67665f302e5f0fcbf5f7f5ca4e6867437c14b1",
  "repo_path": "/workspace/project",
  "repo_name": "project",
  "git_branch": "main",
  "git_commit": "9cc8dc18f748fd405f0f22d0782343cbf6f4f75f",
  "working_directory": "/workspace/project",
  "actor": "alice",
  "files_changed": [
    "README.md",
    "src/app.py"
  ],
  "tool_name": null,
  "command": null,
  "status": null,
  "error": null,
  "raw_payload": {
    "timestamp": 1704652860000,
    "cwd": "/workspace/project",
    "prompt": "Explain this code safely"
  },
  "metadata": {
    "stdin": {
      "stdin_present": true,
      "stdin_mode": "json"
    },
    "session_strategy": "payload_or_arg",
    "git": {
      "git_available": true,
      "is_repo": true,
      "error": null
    }
  }
}
```

## Sanitizacion

Antes de persistir, el logger redacta:

- GitHub tokens
- AWS access keys
- OpenAI keys
- Anthropic keys
- JWT
- passwords
- private keys

La sanitizacion aplica a:

- `user_prompt`
- `command`
- `error`
- `raw_payload`
- `metadata`

## Limitaciones

- Solo se capturan prompts si Copilot entrega el payload al hook.
- Si el payload cambia, se conserva `raw_payload` para analisis posterior.
- No intercepta trafico ni hace keylogging.
- La correlacion de `session_id` es best-effort cuando el payload no incluye un identificador explicito.
- `files_changed` depende de que `git` este disponible y el directorio sea un repositorio Git.

## Privacidad

- Los datos se almacenan localmente.
- Los secretos conocidos se redactan antes de persistirse.
- Aun asi, los prompts pueden contener informacion sensible de negocio; define politicas claras antes de habilitar el logger en equipos amplios.
- Si vas a exportar logs a un SIEM o data lake, agrega controles de retencion y acceso.

## Extender a Claude, Codex y Cursor

La base ya separa:

- normalizacion de payload
- sanitizacion
- persistencia
- CLI

Para soportar otros agentes mas adelante, normalmente basta con:

1. agregar extractores de prompt y session metadata para sus payloads
2. mapear sus eventos a `EventRecord`
3. mantener la misma capa de storage y redaccion

## Estructura del proyecto

```text
copilot-session-logger/
  README.md
  pyproject.toml
  src/copilot_session_logger/
    __init__.py
    cli.py
    config.py
    git_context.py
    sanitizer.py
    schema.py
    storage_jsonl.py
    storage_sqlite.py
  examples/
    copilot-hooks.json
    sample_payload_tool_use.json
    sample_payload_user_prompt.json
  tests/
    test_cli.py
    test_git_context.py
    test_sanitizer.py
    test_schema.py
    test_storage_jsonl.py
```

