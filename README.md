# copilot-session-logger

`copilot-session-logger` captura eventos entregados por hooks de GitHub Copilot, los normaliza a un `EventRecord`, sanitiza secretos y los guarda localmente en JSONL. Opcionalmente envia el mismo evento sanitizado a una API HTTP central y usa una cola offline cuando la red o el backend fallan.

No hace keylogging, no intercepta trafico, no inspecciona internals del IDE y no captura datos fuera del payload recibido por hooks, variables configuradas y contexto Git disponible.

## Arquitectura

```text
GitHub Copilot hook
        |
        v
copilot-session-logger log
        |
        +--> normalizacion + sanitizacion
        |
        +--> JSONL local
        |    ~/.copilot-session-logger/logs/YYYY-MM-DD/events.jsonl
        |
        +--> HTTP POST opcional
             |
             +--> backend FastAPI /v1/events
             |    ~/.copilot-log-backend/events/YYYY-MM-DD/events.jsonl
             |
             +--> si falla: cola offline local
                  ~/.copilot-session-logger/queue/pending.jsonl
```

El almacenamiento local es siempre el primer fallback. Si HTTP esta habilitado y falla con un error reintentable, el evento se guarda en cola offline. En ejecuciones futuras y con `flush`, el logger reintenta eventos pendientes.

## Instalacion

```bash
pip install -e ".[dev]"
```

PowerShell:

```powershell
python -m pip install -e ".[dev]"
```

## Uso rapido

```bash
copilot-session-logger doctor
```

```bash
echo '{"timestamp":1704614500000,"cwd":"/tmp/project","prompt":"Explicame este codigo"}' \
  | copilot-session-logger log --event userPromptSubmitted --dry-run
```

```bash
copilot-session-logger demo
```

## CLI

`log` lee JSON desde `stdin`, construye un `EventRecord`, guarda JSONL local y, si HTTP esta activo, intenta enviarlo al backend. En modo normal no imprime stdout para no interferir con hooks como `preToolUse`.

```bash
copilot-session-logger log --event userPromptSubmitted
```

Opciones utiles:

- `--dry-run`: imprime el evento sanitizado; no persiste ni envia HTTP.
- `--sqlite`: habilita SQLite local en esa ejecucion.
- `--session-id`, `--actor`, `--tool-name`, `--command`, `--status`, `--error`: overrides explicitos.
- `--metadata-json '{"team":"platform"}'`: metadata adicional.

`flush` reintenta manualmente eventos en cola:

```bash
copilot-session-logger flush
```

`doctor` valida configuracion efectiva, escritura local, Git y HTTP. La conectividad HTTP es opcional:

```bash
copilot-session-logger doctor --check-http
```

`demo --send-http` genera eventos simulados, los persiste localmente y los envia al endpoint configurado:

```bash
copilot-session-logger demo --send-http
```

## Variables del logger

| Variable | Default | Uso |
| --- | --- | --- |
| `COPILOT_SESSION_LOGGER_HOME` | `~/.copilot-session-logger` | Base local del cliente. |
| `COPILOT_SESSION_LOGGER_LOGS_DIR` | `$HOME/logs` | JSONL local. |
| `COPILOT_SESSION_LOGGER_SQLITE_ENABLED` | `false` | SQLite local opcional. |
| `COPILOT_SESSION_LOGGER_HTTP_ENABLED` | `false` | Habilita envio HTTP. |
| `COPILOT_SESSION_LOGGER_ENDPOINT` | vacio | URL, por ejemplo `http://localhost:8080/v1/events`. |
| `COPILOT_SESSION_LOGGER_API_KEY` | vacio | Token Bearer enviado al backend. |
| `COPILOT_SESSION_LOGGER_TIMEOUT_SECONDS` | `2` | Timeout por request HTTP. |
| `COPILOT_SESSION_LOGGER_OFFLINE_QUEUE_ENABLED` | `true` | Habilita cola offline. |
| `COPILOT_SESSION_LOGGER_MAX_RETRIES` | `3` | Reintentos antes de `dead_letter`. |
| `COPILOT_SESSION_LOGGER_REDACT_SECRETS` | `true` | Sanitiza secretos antes de persistir/enviar. |

Tambien puede usarse `~/.copilot-session-logger/config.yaml`:

```yaml
actor: your-user
redact_secrets: true
storage:
  jsonl_enabled: true
  sqlite_enabled: false
http:
  enabled: true
  endpoint: http://localhost:8080/v1/events
  api_key: dev-token
  timeout_seconds: 2
  offline_queue_enabled: true
  max_retries: 3
```

## Configuracion de hooks

Ejemplo para `.github/hooks/copilot-hooks.json`:

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
        "timeoutSec": 5
      }
    ],
    "sessionStart": [
      {
        "type": "command",
        "bash": "copilot-session-logger log --event sessionStart",
        "powershell": "copilot-session-logger log --event sessionStart",
        "cwd": ".",
        "timeoutSec": 5
      }
    ]
  }
}
```

Este repositorio incluye un ejemplo completo en [examples/copilot-hooks.json](examples/copilot-hooks.json).

## Backend local

El backend vive en [backend/](backend/) y expone:

- `GET /health`
- `POST /v1/events`
- `POST /v1/events/batch`
- `GET /v1/events`

Variables del backend:

| Variable | Default | Uso |
| --- | --- | --- |
| `COPILOT_LOG_BACKEND_API_KEYS` | vacio | Lista de tokens validos separada por comas. |
| `COPILOT_LOG_BACKEND_STORAGE` | `jsonl` | `jsonl` o `sqlite`. |
| `COPILOT_LOG_BACKEND_HOME` | `~/.copilot-log-backend` | Base de persistencia del backend. |
| `COPILOT_LOG_BACKEND_MAX_BODY_MB` | `2` | Tamano maximo de request. |
| `ALLOW_UNKNOWN_EVENT_TYPES` | `false` | Acepta eventos no conocidos si es `true`. |

Ejecutar:

```bash
cd backend
pip install -e ".[dev]"
export COPILOT_LOG_BACKEND_API_KEYS=dev-token
uvicorn copilot_log_backend.main:app --reload --port 8080
```

PowerShell:

```powershell
cd backend
python -m pip install -e ".[dev]"
$env:COPILOT_LOG_BACKEND_API_KEYS = "dev-token"
uvicorn copilot_log_backend.main:app --reload --port 8080
```

## Prueba end-to-end local

Terminal 1:

```bash
cd backend
export COPILOT_LOG_BACKEND_API_KEYS=dev-token
uvicorn copilot_log_backend.main:app --reload --port 8080
```

Terminal 2:

```bash
export COPILOT_SESSION_LOGGER_HTTP_ENABLED=true
export COPILOT_SESSION_LOGGER_ENDPOINT=http://localhost:8080/v1/events
export COPILOT_SESSION_LOGGER_API_KEY=dev-token
```

```bash
echo '{"timestamp":1704614500000,"cwd":"/tmp/project","prompt":"Explicame este codigo"}' \
  | copilot-session-logger log --event userPromptSubmitted --dry-run
```

```bash
echo '{"timestamp":1704614500000,"cwd":"/tmp/project","prompt":"Explicame este codigo"}' \
  | copilot-session-logger log --event userPromptSubmitted
```

Consulta:

```bash
curl -s -H "Authorization: Bearer dev-token" \
  "http://localhost:8080/v1/events?event_type=userPromptSubmitted&limit=5"
```

Respuesta exitosa de ingesta directa:

```json
{
  "status": "accepted",
  "event_id": "7cb355f9-d8de-45b7-a4db-387cb16fe545"
}
```

Si el backend esta caido, el evento queda en:

```text
~/.copilot-session-logger/queue/pending.jsonl
```

Cuando el backend vuelva:

```bash
copilot-session-logger flush
```

## Docker

```bash
cd backend
docker compose up --build
```

El compose publica `http://localhost:8080` y persiste eventos en `backend/data`.

## Persistencia

Cliente local:

```text
~/.copilot-session-logger/logs/YYYY-MM-DD/events.jsonl
~/.copilot-session-logger/session_logs.db
~/.copilot-session-logger/queue/pending.jsonl
~/.copilot-session-logger/queue/sent.jsonl
~/.copilot-session-logger/queue/dead_letter.jsonl
```

Backend:

```text
~/.copilot-log-backend/events/YYYY-MM-DD/events.jsonl
~/.copilot-log-backend/events.db
```

## Matriz de decisiones

| Modo | Cuando usarlo | Tradeoff |
| --- | --- | --- |
| Local only | Desarrollo individual, pilotos o equipos sin collector central. | Simple y resiliente, pero sin visibilidad organizacional. |
| Local + API | Observabilidad central con fallback local. | Requiere operar token, endpoint y retencion. |
| API + SIEM futuro | Auditoria enterprise, correlacion y dashboards. | Mayor complejidad, requiere gobierno de datos y controles de acceso. |

## Privacidad y seguridad

- Consentimiento: informa a los usuarios antes de habilitar captura organizacional.
- Minimizacion: el logger solo usa payload del hook, variables configuradas y contexto Git permitido.
- Sanitizacion: cliente y backend redactan tokens, passwords, private keys, JWT y claves comunes antes de persistir.
- Retencion: define TTL para JSONL, SQLite y backups antes de adopcion amplia.
- Acceso restringido: protege `COPILOT_SESSION_LOGGER_API_KEY`, `COPILOT_LOG_BACKEND_API_KEYS` y directorios de logs.
- Consola: el backend no loguea prompts completos; solo `event_id`, `event_type`, `actor`, `repo_name` y estado.

## Limitaciones

- Solo captura prompts si Copilot los entrega al hook.
- No cubre audit logs empresariales de GitHub.
- No intercepta trafico ni internals del IDE.
- La correlacion de `session_id` es best-effort cuando el payload no incluye identificador.
- `files_changed` depende de que `git` este disponible y el `cwd` sea un repositorio.

## Roadmap

- Envio a S3.
- OpenSearch/SIEM.
- Dashboards.
- Soporte Claude, Codex y Cursor mediante adaptadores.

## Tests

Cliente:

```bash
python -m pytest -q
```

Backend:

```bash
python -m pytest backend/tests -q
```
