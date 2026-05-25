# session-logger

Repositorio para observar sesiones asistidas por GitHub Copilot.

Tiene dos componentes separados:

- Hook / Session Logger local: captura payloads de hooks de Copilot, normaliza eventos, sanitiza datos sensibles, escribe JSONL local y opcionalmente envia al backend.
- Backend FastAPI: recibe eventos normalizados, aplica idempotencia por `event_id`, persiste en PostgreSQL y expone consultas operativas y analiticas.

El logger local activo esta implementado en Bash. El backend no se migra a Shell.

## Diagnostico Del Repo

Archivos del Hook / Session Logger local:

- Activo: `hooks/session-logger.sh`
- Activo: `lib/logger.sh`
- Activo: `lib/payload.sh`
- Activo: `lib/state.sh`
- Activo: `lib/transport.sh`
- Activo: `scripts/test-session-logger.sh`
- Ejemplos: `examples/payload-user-prompt.json`, `examples/payload-tool-use.json`, `examples/payload-tool-result.json`, `examples/copilot-hooks.json`
- Legacy/deprecated: `src/copilot_session_logger/*`

Archivos del backend FastAPI:

- `backend/app/main.py`
- `backend/app/domain/*`
- `backend/app/usecase/*`
- `backend/app/entrypoints/*`
- `backend/app/driven_adapters/*`
- `backend/app/config/*`
- `backend/tests/*`

Se migra a Bash solo el logger local. El paquete Python `src/copilot_session_logger` queda marcado como deprecated para compatibilidad temporal.

## Flujo End-To-End

```text
GitHub Copilot Hook
        |
        v
hooks/session-logger.sh
        |
        +--> lib/payload.sh
        |    lee stdin, normaliza JSON con jq, sanitiza secretos
        |
        +--> lib/state.sh
        |    mantiene ultimo userPrompt_id por session_id
        |
        +--> lib/transport.sh
             +--> JSONL local ~/.session-logger/logs/YYYY-MM-DD/events.jsonl
             +--> POST opcional a FastAPI /api/v1/events
             +--> Push opcional a Loki /loki/api/v1/push
             +--> OTLP opcional a Collector /v1/traces y /v1/metrics
             +--> fallback ~/.session-logger/queue/pending.jsonl si algun transporte falla
```

## Logger Bash

Dependencias runtime:

- `bash`
- `jq`
- `curl`

### Windows (PowerShell Nativo)

En Windows, el logger usa **PowerShell nativo sin dependencias externas** (versión 5.1+). Usar `session-logger-windows.ps1` no requiere bash, jq ni WSL. Solo usa capacidades nativas de PowerShell 5.1+ y `Invoke-WebRequest` (disponible en Windows 10+).

El script valida las dependencias al iniciar. En modo no estricto intenta no bloquear la experiencia del desarrollador; en modo estricto falla con codigo distinto de cero.

```bash
export COPILOT_SESSION_LOGGER_STRICT=true
bash hooks/session-logger.sh doctor
```

Ejecutar localmente:

```bash
bash hooks/session-logger.sh --event userPromptSubmitted --dry-run \
  < examples/payload-user-prompt.json
```

Persistir JSONL local:

```bash
bash hooks/session-logger.sh --event userPromptSubmitted \
  < examples/payload-user-prompt.json
```

Probar correlacion prompt -> tool:

```bash
bash scripts/test-session-logger.sh
```

## Variables Del Logger

| Variable | Default | Uso |
| --- | --- | --- |
| `COPILOT_SESSION_LOGGER_HOME` | `~/.session-logger` | Directorio base local. |
| `COPILOT_SESSION_LOGGER_LOGS_DIR` | `$HOME/logs` dentro del home del logger | JSONL local. |
| `COPILOT_SESSION_LOGGER_STATE_DIR` | `$HOME/state` dentro del home del logger | Estado por sesion. |
| `COPILOT_SESSION_LOGGER_QUEUE_DIR` | `$HOME/queue` dentro del home del logger | Cola offline. |
| `COPILOT_SESSION_LOGGER_HTTP_ENABLED` | `false` | Habilita envio HTTP. |
| `COPILOT_SESSION_LOGGER_ENDPOINT` | vacio | Endpoint, normalmente `http://localhost:8080/api/v1/events`. |
| `COPILOT_SESSION_LOGGER_API_KEY` | vacio | Token enviado como `Authorization: Bearer` y `X-Logger-Token`. |
| `COPILOT_SESSION_LOGGER_LOKI_ENABLED` | `false` | Habilita envio directo a Loki. |
| `COPILOT_SESSION_LOGGER_LOKI_ENDPOINT` | `http://localhost:3100/loki/api/v1/push` | Endpoint de ingestion de Loki. |
| `COPILOT_SESSION_LOGGER_LOKI_TENANT_ID` | vacio | Tenant para Loki multitenant (`X-Scope-OrgID`). |
| `COPILOT_SESSION_LOGGER_OTLP_ENABLED` | `false` | Habilita envio OTLP al collector de observabilidad. |
| `COPILOT_SESSION_LOGGER_OTLP_ENDPOINT` | `http://localhost:4318` | Endpoint base OTLP HTTP (se usan `/v1/traces` y `/v1/metrics`). |
| `COPILOT_SESSION_LOGGER_TIMEOUT_SECONDS` | `2` | Timeout de `curl`. |
| `COPILOT_SESSION_LOGGER_REDACT_SECRETS` | `true` | Redacta secretos con jq antes de persistir/enviar. |
| `COPILOT_SESSION_LOGGER_OFFLINE_QUEUE_ENABLED` | `true` | Guarda eventos si HTTP falla. |
| `COPILOT_SESSION_LOGGER_ACTOR` | usuario del entorno | Actor fallback. |
| `COPILOT_SESSION_LOGGER_COPILOT_USER` | vacio | Usuario de GitHub Copilot como metadata adicional (`metadata.copilot_user`). |
| `COPILOT_SESSION_LOGGER_METADATA_JSON` | `{}` | Metadata adicional, sanitizada. |

## Hooks De Copilot

El hook se activa automaticamente en cada evento de Copilot (prompts, llamadas a herramientas, inicio/fin de sesion). Los archivos ya listos estan en `.github/hooks/session-logger/`.

### Instalacion En Un Repositorio Nuevo

1. Crea el directorio destino:

```bash
mkdir -p .github/hooks/session-logger
```

2. Copia los scripts de hooks (bash para Unix, PowerShell para Windows):

```bash
cp hooks/session-logger.sh .github/hooks/session-logger/session-logger.sh
cp .github/hooks/session-logger/session-logger-windows.ps1 .github/hooks/session-logger/session-logger-windows.ps1
cp .github/hooks/copilot-hooks.json .github/hooks/copilot-hooks.json
```

> Si aun no tienes el `copilot-hooks.json`, usa el ejemplo de referencia:
> ```bash
> cp examples/copilot-hooks.json .github/hooks/copilot-hooks.json
> ```

3. Da permisos de ejecucion al script:

```bash
chmod +x .github/hooks/session-logger/session-logger.sh
```

4. Verifica que el hook funciona:

```bash
bash .github/hooks/session-logger/session-logger.sh doctor
```

### Estructura Esperada

```text
.github/
  hooks/
    session-logger/
      copilot-hooks.json   <- archivo leido por Copilot al arrancar
      session-logger.sh    <- ejecutable con permisos +x
```

### Referencia De copilot-hooks.json

El archivo registra todos los eventos que Copilot debe interceptar. Ejemplo completo en `.github/hooks/session-logger/copilot-hooks.json`:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "type": "command",
        "bash": ".github/hooks/session-logger/session-logger.sh --event sessionStart",
        "powershell": "& .github/hooks/session-logger/session-logger.ps1 -Event sessionStart",
        "cwd": ".",
        "timeoutSec": 5
      }
    ],
    "userPromptSubmitted": [
      {
        "type": "command",
        "bash": ".github/hooks/session-logger/session-logger.sh --event userPromptSubmitted",
        "powershell": "& .github/hooks/session-logger/session-logger.ps1 -Event userPromptSubmitted",
        "cwd": ".",
        "timeoutSec": 5
      }
    ]
  }
}
```

El archivo completo cubre ademas `preToolUse`, `postToolUse`, `sessionEnd` y `errorOccurred`.

## Trazabilidad Prompt -> Eventos

Reglas implementadas:

- Cada evento `userPromptSubmitted` se normaliza como `event_type=user_prompt`.
- Cada prompt recibe `userPrompt_id`.
- Eventos derivados como `tool_use`, `tool_result`, `assistant_response`, `command_execution`, `file_edit` o `error` incluyen `parent_userPrompt_id` cuando se puede asociar.
- El estado local minimo vive en `~/.session-logger/state/<session_id>.json`.
- Si el payload no trae `session_id`, el logger usa un cache best-effort por actor y workspace. Si no puede asociar de forma confiable, `parent_userPrompt_id` queda `null`.
- No se inventa una relacion a partir del contenido del prompt; solo se usa payload explicito o ultimo prompt activo por `session_id`.

Estado ejemplo:

```json
{
  "session_id": "sess_demo_001",
  "last_userPrompt_id": "up_...",
  "updated_at": "2026-05-04T10:15:00Z"
}
```

## Contrato Normalizado

`POST /api/v1/events` recibe eventos como:

```json
{
  "event_id": "evt_...",
  "session_id": "sess_...",
  "timestamp": "2026-05-04T10:15:00Z",
  "event_type": "tool_use",
  "userPrompt_id": null,
  "parent_userPrompt_id": "up_...",
  "actor": "developer",
  "source": "github_copilot_hook",
  "repository": "session-logger",
  "branch": "main",
  "workspace": "/workspace/project",
  "tool_name": "bash",
  "tool_input_summary": "rg --files",
  "tool_result_summary": null,
  "prompt_text": null,
  "assistant_response_summary": null,
  "files_touched": [],
  "commands_executed": ["rg --files"],
  "metadata": {},
  "raw_payload": {}
}
```

El backend tambien acepta nombres legacy del logger Python mientras dure la compatibilidad.

## Troubleshooting

### Datos no llegan a observabilidad

**Sintoma**: Backend o Loki reciben eventos pero Tempo no ve trazas OTLP.

**Causa posible**: En zsh, la variable de shell `status` es reservada. Si se usa directamente en scripts bash/sh, causa error silencioso.

**Solucion**: Usar nombres de variables alternativos como `otlp_send_status` en lugar de `status` para OTLP send status tracking.

**Verificacion**: Ejecutar con debug y revisar logs de error para "read-only variable: status".

## Mapeo De Valores Por Destino

El logger envia el evento normalizado a multiples destinos en paralelo segun configuracion.

### Resumen Por Destino

| Destino | Endpoint | Formato enviado | Cobertura de campos |
| --- | --- | --- | --- |
| Backend FastAPI | `POST /api/v1/events` (`COPILOT_SESSION_LOGGER_ENDPOINT`) | JSON del evento normalizado | Todos los campos del contrato normalizado. |
| Loki | `POST /loki/api/v1/push` (`COPILOT_SESSION_LOGGER_LOKI_ENDPOINT`) | `streams[].values[][1]` con el evento normalizado serializado como JSON string | Todos los campos en el log line + labels operativos del stream. |
| Tempo (OTLP traces) | `POST /v1/traces` sobre `COPILOT_SESSION_LOGGER_OTLP_ENDPOINT` | OTLP JSON (`resourceSpans`) | Todos los campos top-level del evento como atributos del span. |
| Prometheus (via collector OTLP) | `POST /v1/metrics` sobre `COPILOT_SESSION_LOGGER_OTLP_ENDPOINT` | OTLP JSON (`resourceMetrics`) con contador monotonic | Subconjunto de campos como labels de `marvin_session_logger_events_total`. |

### Campos Enviados A Cada Destino

| Campo normalizado | Backend | Loki | Tempo (span attribute) | Prometheus (label) |
| --- | --- | --- | --- | --- |
| `event_id` | JSON body | Log line JSON | Si, como atributo | No |
| `session_id` | JSON body | Log line JSON + label `session_id` | Si, como atributo | No |
| `timestamp` | JSON body | Log line JSON | Si, como atributo | No |
| `event_type` | JSON body | Log line JSON + label `event_type` | Si, como atributo | Si (`event_type`) |
| `userPrompt_id` | JSON body | Log line JSON | Si, como atributo | No |
| `parent_userPrompt_id` | JSON body | Log line JSON | Si, como atributo | No |
| `actor` | JSON body | Log line JSON + label `actor` | Si, como atributo | No |
| `user_id` | JSON body | Log line JSON | Si, como atributo | No |
| `source` | JSON body | Log line JSON + label `source` | Si, como atributo | Si (`source`) |
| `repository` | JSON body | Log line JSON + label `repository` | Si, como atributo | Si (`repository`) |
| `branch` | JSON body | Log line JSON | Si, como atributo | Si (`branch`) |
| `workspace` | JSON body | Log line JSON | Si, como atributo | No |
| `tool_name` | JSON body | Log line JSON | Si, como atributo | Si (`tool_name`, con fallback `none`) |
| `tool_input_summary` | JSON body | Log line JSON | Si, como atributo | No |
| `tool_result_summary` | JSON body | Log line JSON | Si, como atributo | No |
| `prompt_text` | JSON body | Log line JSON | Si, como atributo | No |
| `assistant_response_summary` | JSON body | Log line JSON | Si, como atributo | No |
| `files_touched` | JSON body | Log line JSON | Si, como atributo (serializado JSON string) | No |
| `commands_executed` | JSON body | Log line JSON | Si, como atributo (serializado JSON string) | No |
| `status` | JSON body | Log line JSON | Si, como atributo | Si (`status`, con fallback `unset`) |
| `duration_ms` | JSON body | Log line JSON | Si, como atributo | No |
| `metadata` | JSON body | Log line JSON | Si, como atributo (serializado JSON string) | No |
| `metadata.copilot_user` | Dentro de `metadata` | Dentro de `metadata` | Dentro de `metadata` (JSON string) | No |
| `raw_payload` | JSON body | Log line JSON | Si, como atributo (serializado JSON string) | No |
| `created_at` | JSON body | Log line JSON | Si, como atributo | No |

### Labels Y Campos Tecnicos Adicionales

Valores adicionales que no vienen directamente del contrato normalizado:

| Destino | Campo tecnico | Valor |
| --- | --- | --- |
| Loki | `job` | `session-logger-shell` |
| Loki | `service_name` | `session-logger` |
| Tempo resource | `service.name` | `session-logger` |
| Tempo resource | `service.namespace` | `marvin` |
| Tempo resource | `service.instance.id` | `<session_id>:<event_id>` |
| Tempo span | `name` | `event_type` |
| Tempo span | `kind` | `1` (INTERNAL) |
| Tempo span | `status.code` | `1` |
| Prom metric | `name` | `session_logger_events_total` (exportada como `marvin_session_logger_events_total`) |
| Prom metric | `unit` | `1` |
| Prom metric | `aggregationTemporality` | `2` (CUMULATIVE) |
| Prom metric | `isMonotonic` | `true` |

### Reglas De Tipo En OTLP (Tempo)

- Strings: `stringValue`.
- Booleanos: `boolValue`.
- Numeros enteros: `intValue`.
- Numeros decimales: `doubleValue`.
- Arrays/objetos: se serializan como JSON string en `stringValue`.
- `null`: se envia como `"null"` en `stringValue`.

Esto permite conservar toda la informacion del evento en trazas, minimizando perdida semantica en OTLP JSON desde Bash.

## Backend FastAPI

El backend vive en `backend/` y mantiene Clean Architecture:

```text
entrypoints/api -> usecase -> domain/gateway <- driven_adapters
config/dependency_injection ensambla implementaciones concretas
main.py inicializa FastAPI, middlewares y rutas
```

Endpoints:

- `GET /health`
- `POST /api/v1/events`
- `POST /api/v1/events/batch`
- `GET /api/v1/events`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/prompts/{userPrompt_id}/trace`
- `GET /api/v1/analytics/tool-usage`
- `GET /api/v1/analytics/repository-activity`
- `GET /api/v1/analytics/prompt-impact`
- `GET /api/v1/analytics/session-summary`

Seguridad minima:

- Token por cliente/logger.
- Headers aceptados: `Authorization: Bearer <token>` o `X-Logger-Token: <token>`.
- Sanitizacion en logger y backend.
- Logs sin payload completo.
- CORS/rate limiting deben restringirse al desplegar detras de gateway corporativo.

## Modelo De Datos

PostgreSQL es la base recomendada inicial porque combina campos estructurados para analitica con `JSONB` para `metadata` y `raw_payload`.

Tabla principal: `copilot_events`

Campos clave:

- `id`
- `event_id`
- `session_id`
- `event_type`
- `timestamp`
- `user_id`
- `repository`
- `branch`
- `workspace`
- `userPrompt_id`
- `parent_userPrompt_id`
- `tool_name`
- `prompt_text`
- `assistant_response_summary`
- `tool_input_summary`
- `tool_result_summary`
- `status`
- `duration_ms`
- `files_touched JSONB`
- `commands_executed JSONB`
- `metadata JSONB`
- `raw_payload JSONB`
- `created_at`

Indices incluidos:

- unique `event_id`
- `session_id`
- `timestamp`
- `event_type`
- `repository`
- `userPrompt_id`
- `parent_userPrompt_id`
- `tool_name`
- `(repository, timestamp)`
- `(parent_userPrompt_id, event_type)`
- GIN sobre `metadata`
- GIN sobre `raw_payload`

Vistas recomendadas futuras:

- `session_summary`
- `prompt_activity_summary`
- `tool_usage_summary`
- `repository_usage_daily`
- `user_activity_daily`

## Consultas Analiticas Ejemplo

Prompts por repositorio y dia:

```sql
SELECT repository, date_trunc('day', timestamp) AS day, count(*) AS prompts
FROM copilot_events
WHERE event_type IN ('user_prompt', 'userPromptSubmitted')
GROUP BY repository, day
ORDER BY day DESC, prompts DESC;
```

Tools mas usadas:

```sql
SELECT tool_name, count(*) AS events
FROM copilot_events
WHERE tool_name IS NOT NULL
GROUP BY tool_name
ORDER BY events DESC;
```

Prompts que disparan mas acciones:

```sql
SELECT parent_userPrompt_id, event_type, count(*) AS events
FROM copilot_events
WHERE parent_userPrompt_id IS NOT NULL
GROUP BY parent_userPrompt_id, event_type
ORDER BY events DESC;
```

Archivos mas tocados:

```sql
SELECT file, count(*) AS touches
FROM copilot_events, jsonb_array_elements_text(files_touched) AS file
GROUP BY file
ORDER BY touches DESC;
```

## Ejecutar Backend

```bash
cd backend
python -m pip install -e ".[dev]"
export COPILOT_LOG_BACKEND_API_KEYS=dev-token
export COPILOT_LOG_BACKEND_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/copilot_logs
uvicorn app.main:app --reload --port 8080
```

Docker:

```bash
cd backend
docker compose up --build
```

## Envio End-To-End

Terminal 1:

```bash
cd backend
docker compose up --build
```

Terminal 2:

```bash
export COPILOT_SESSION_LOGGER_HTTP_ENABLED=true
export COPILOT_SESSION_LOGGER_ENDPOINT=http://localhost:8080/api/v1/events
export COPILOT_SESSION_LOGGER_API_KEY=dev-token
export COPILOT_SESSION_LOGGER_LOKI_ENABLED=true
export COPILOT_SESSION_LOGGER_LOKI_ENDPOINT=http://localhost:3100/loki/api/v1/push
export COPILOT_SESSION_LOGGER_OTLP_ENABLED=true
export COPILOT_SESSION_LOGGER_OTLP_ENDPOINT=http://localhost:4318

bash hooks/session-logger.sh --event userPromptSubmitted \
  < examples/payload-user-prompt.json

bash hooks/session-logger.sh --event preToolUse \
  < examples/payload-tool-use.json
```

Consultar traza:

```bash
curl -s -H "X-Logger-Token: dev-token" \
  http://localhost:8080/api/v1/prompts/up_xxx/trace
```

Consultar eventos:

```bash
curl -s -H "X-Logger-Token: dev-token" \
  "http://localhost:8080/api/v1/events?session_id=sess_demo_001&limit=10"
```

Consultar logs directos en Loki:

```bash
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={job="session-logger-shell"}' \
  --data-urlencode "limit=10" \
  --data-urlencode "start=$(($(date +%s)-600))000000000" \
  --data-urlencode "end=$(date +%s)000000000"
```

Consultar trazas en Tempo:

```bash
curl -G -s "http://localhost:3200/api/search" \
  --data-urlencode 'q={ resource.service.name = "session-logger" }' \
  --data-urlencode "limit=10"
```

Consultar metricas en Prometheus:

```bash
curl -G -s "http://localhost:9090/api/v1/query" \
  --data-urlencode 'query=marvin_session_logger_events_total'
```

## Privacidad Y Alcance

- El logger no hace keylogging.
- No intercepta trafico ni inspecciona internals del IDE.
- Solo usa el payload recibido por hooks, variables configuradas y contexto Git disponible.
- `raw_payload` se sanitiza antes de persistirse.
- Se redactan tokens, passwords, private keys, JWT y claves comunes.
- Definir retencion, consentimiento, acceso a tablas y backups antes de despliegue enterprise.
- No guardar variables de entorno completas ni secretos de procesos.

## Tests

Logger Python legacy y pruebas estaticas del Shell logger:

```bash
python -m pytest -q
```

Backend:

```bash
python -m pytest backend/tests -q
```

Shell logger funcional:

```bash
bash scripts/test-session-logger.sh
```

La prueba funcional Shell requiere `jq`. Si falta, instalarlo en el entorno donde corren los hooks.

