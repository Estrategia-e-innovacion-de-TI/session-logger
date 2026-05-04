# copilot-log-backend

Backend FastAPI para centralizar eventos de `copilot-session-logger` en PostgreSQL. La estructura implementa Clean Architecture siguiendo el enfoque descrito por Bancolombia Tech en "Clean Architecture: aislando los detalles": el dominio queda en el centro, los frameworks y motores de datos quedan en los bordes, y las dependencias apuntan hacia contratos.

Referencia: https://medium.com/bancolombia-tech/clean-architecture-aislando-los-detalles-4f9530f35d7a

## Estructura

```text
backend/
  app/
    main.py
    domain/
      model/
        copilot_event.py
        session.py
        user_prompt.py
      gateway/
        event_repository.py
        analytics_repository.py
        sanitizer.py
      exception/
        domain_exceptions.py
    usecase/
      ingest_event_usecase.py
      ingest_batch_events_usecase.py
      get_session_trace_usecase.py
      get_prompt_trace_usecase.py
      get_tool_usage_analytics_usecase.py
      get_repository_activity_usecase.py
      get_prompt_impact_usecase.py
      get_session_summary_usecase.py
      query_events_usecase.py
    entrypoints/
      api/
        v1/
          events_controller.py
          analytics_controller.py
          health_controller.py
        dto/
          event_request.py
          event_response.py
          analytics_response.py
    driven_adapters/
      postgres/
        models.py
        event_repository_adapter.py
        analytics_repository_adapter.py
        database.py
        migrations/
      security/
        api_key_validator.py
        sanitizer.py
      observability/
        logger.py
        metrics.py
    config/
      settings.py
      dependency_injection.py
```

## Reglas de dependencia

```text
entrypoints/api -> usecase -> domain/gateway <- driven_adapters
config/dependency_injection ensambla implementaciones concretas
main.py inicializa FastAPI, middlewares y routers
```

- `domain` contiene entidades, value objects, excepciones y puertos. No importa FastAPI, Pydantic, SQLAlchemy, PostgreSQL ni psycopg.
- `usecase` solo depende de `domain` y de gateways. No recibe `Request`, sesiones SQL ni DTOs HTTP.
- `entrypoints` valida DTOs con Pydantic, convierte a entidades de dominio, invoca casos de uso y convierte respuestas.
- `driven_adapters/postgres` implementa `EventRepository` y `AnalyticsRepository`, traduce dominio a SQLAlchemy y maneja persistencia.
- `driven_adapters/security` implementa detalles de API key y sanitizacion.
- PostgreSQL se puede cambiar por otro adapter sin modificar casos de uso.

## Ejecutar con Docker

```bash
cd backend
docker compose up --build
```

El servicio queda en `http://localhost:8080`.

## Ejecutar local

```bash
cd backend
python -m pip install -e ".[dev]"
export COPILOT_LOG_BACKEND_API_KEYS=dev-token
export COPILOT_LOG_BACKEND_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/copilot_logs
uvicorn app.main:app --reload --port 8080
```

PowerShell:

```powershell
cd backend
python -m pip install -e ".[dev]"
$env:COPILOT_LOG_BACKEND_API_KEYS = "dev-token"
$env:COPILOT_LOG_BACKEND_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/copilot_logs"
uvicorn app.main:app --reload --port 8080
```

Las migraciones SQL se ejecutan al iniciar si `COPILOT_LOG_BACKEND_AUTO_MIGRATE=true`.

## Variables

| Variable | Default | Uso |
| --- | --- | --- |
| `COPILOT_LOG_BACKEND_API_KEYS` | vacio | Tokens Bearer validos separados por comas. |
| `COPILOT_LOG_BACKEND_DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/copilot_logs` | URL SQLAlchemy de PostgreSQL. |
| `COPILOT_LOG_BACKEND_MAX_BODY_MB` | `2` | Tamano maximo del body HTTP. |
| `COPILOT_LOG_BACKEND_ALLOW_UNKNOWN_EVENT_TYPES` | `false` | Permite `event_type` no conocido si es `true`. |
| `COPILOT_LOG_BACKEND_QUERY_LIMIT` | `100` | Limite maximo para `GET /api/v1/events`. |
| `COPILOT_LOG_BACKEND_ANALYTICS_LIMIT` | `100` | Limite por defecto para consultas analiticas. |
| `COPILOT_LOG_BACKEND_AUTO_MIGRATE` | `true` | Ejecuta migraciones SQL al iniciar. |

Autenticacion: los endpoints `/api/v1/*` aceptan `Authorization: Bearer <token>` o `X-Logger-Token: <token>`.

## Endpoints

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

Ejemplo:

```bash
curl -s -X POST http://localhost:8080/api/v1/events \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id":"event-1",
    "session_id":"session-1",
    "event_type":"userPromptSubmitted",
    "timestamp":1704614500000,
    "user_id":"alice",
    "repository":"demo",
    "branch":"main",
    "userPrompt_id":"prompt-1",
    "prompt_text":"Explicame este codigo",
    "metadata":{"source":"hook"},
    "raw_payload":{"prompt":"Explicame este codigo"}
  }'
```

El contrato tambien acepta eventos normalizados producidos por el logger Bash:

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

Respuesta resumida:

```json
{
  "status": "accepted",
  "event_id": "event-1",
  "created": true
}
```

Si se repite el mismo `event_id`, el caso de uso retorna el registro existente con `created=false`. La idempotencia no depende de FastAPI ni de SQLAlchemy.

## Modelo PostgreSQL

Tabla `copilot_events`:

| Campo | Tipo |
| --- | --- |
| `id` | `BIGSERIAL PRIMARY KEY` |
| `event_id` | `TEXT UNIQUE NOT NULL` |
| `session_id` | `TEXT NOT NULL` |
| `event_type` | `TEXT NOT NULL` |
| `timestamp` | `TIMESTAMPTZ NOT NULL` |
| `user_id` | `TEXT NULL` |
| `repository` | `TEXT NULL` |
| `branch` | `TEXT NULL` |
| `workspace` | `TEXT NULL` |
| `userPrompt_id` | `TEXT NULL` |
| `parent_userPrompt_id` | `TEXT NULL` |
| `tool_name` | `TEXT NULL` |
| `prompt_text` | `TEXT NULL` |
| `assistant_response_summary` | `TEXT NULL` |
| `tool_input_summary` | `TEXT NULL` |
| `tool_result_summary` | `TEXT NULL` |
| `status` | `TEXT NULL` |
| `duration_ms` | `INTEGER NULL` |
| `files_touched` | `JSONB NOT NULL` |
| `commands_executed` | `JSONB NOT NULL` |
| `metadata` | `JSONB NOT NULL` |
| `raw_payload` | `JSONB NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL` |

Indices incluidos: `event_id` unico, `session_id`, `timestamp`, `event_type`, `repository`, `userPrompt_id`, `parent_userPrompt_id`, `tool_name`, `(repository, timestamp)`, `(parent_userPrompt_id, event_type)`, `GIN(metadata)` y `GIN(raw_payload)`.

## Tests

Unitarios y API con repositorios fake/in-memory:

```bash
python -m pytest backend/tests -q
```

Integracion real del adapter PostgreSQL:

```bash
$env:COPILOT_LOG_BACKEND_TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/copilot_logs"
python -m pytest backend/tests/integration/test_postgres_adapter.py -q
```

Si `COPILOT_LOG_BACKEND_TEST_DATABASE_URL` no existe, esa prueba se omite para no requerir una base externa durante la suite unitaria.
