# copilot-log-backend

Backend FastAPI para centralizar eventos de `copilot-session-logger` en PostgreSQL. La implementacion sigue Clean Architecture para separar dominio, casos de uso, API e infraestructura.

## Por que Clean Architecture

El dominio de eventos no debe depender de FastAPI, Pydantic, SQLAlchemy ni PostgreSQL. Esto permite:

- Cambiar PostgreSQL por otro storage implementando `EventRepository`.
- Probar reglas de negocio con repositorios fake sin levantar infraestructura.
- Mantener DTOs, modelos SQLAlchemy y entidades de dominio separados.
- Evitar que detalles de transporte o persistencia contaminen la logica de ingesta.

## Estructura

```text
src/copilot_log_backend/
  application/
    main.py
    config.py
    container.py
    migrate.py
  domain/
    entities/event.py
    gateways/event_repository.py
    exceptions.py
  usecases/
    ingest_event.py
    ingest_event_batch.py
    query_events.py
    health_check.py
  entrypoints/api/
    app.py
    auth.py
    dependencies.py
    routes/
    dto/
  driven_adapters/
    postgres/
      database.py
      models.py
      event_repository.py
      migrations/001_create_events_table.sql
    jsonl/
      event_repository.py
    security/
      sanitizer.py
```

## Dependencias

```text
entrypoints/api -> usecases -> domain gateways <- driven_adapters/postgres
application/container ensambla implementaciones concretas
```

`domain/entities/event.py` es una dataclass pura. No importa FastAPI, Pydantic, SQLAlchemy, psycopg ni frameworks.

## Ejecutar con Docker

```bash
cd backend
docker compose up --build
```

El compose levanta:

- `postgres:16`, base `copilot_logs`, usuario `postgres`, password `postgres`.
- Backend FastAPI en `http://localhost:8080`.
- Migracion SQL basica al iniciar el backend.

## Ejecutar local sin Docker

Requiere PostgreSQL accesible.

```bash
cd backend
pip install -e ".[dev]"
export COPILOT_LOG_BACKEND_API_KEYS=dev-token
export COPILOT_LOG_BACKEND_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/copilot_logs
export COPILOT_LOG_BACKEND_STORAGE=postgres
python -m copilot_log_backend.application.migrate
uvicorn copilot_log_backend.application.main:app --reload --port 8080
```

PowerShell:

```powershell
cd backend
python -m pip install -e ".[dev]"
$env:COPILOT_LOG_BACKEND_API_KEYS = "dev-token"
$env:COPILOT_LOG_BACKEND_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/copilot_logs"
$env:COPILOT_LOG_BACKEND_STORAGE = "postgres"
python -m copilot_log_backend.application.migrate
uvicorn copilot_log_backend.application.main:app --reload --port 8080
```

## Variables

| Variable | Default | Uso |
| --- | --- | --- |
| `COPILOT_LOG_BACKEND_API_KEYS` | vacio | Tokens Bearer validos separados por comas. |
| `COPILOT_LOG_BACKEND_DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/copilot_logs` | URL SQLAlchemy de PostgreSQL. |
| `COPILOT_LOG_BACKEND_STORAGE` | `postgres` | Storage productivo. `jsonl` solo para tests/dev local. |
| `COPILOT_LOG_BACKEND_MAX_BODY_MB` | `2` | Tamano maximo del body HTTP. |
| `COPILOT_LOG_BACKEND_ALLOW_UNKNOWN_EVENT_TYPES` | `false` | Permite `event_type` no conocido si es `true`. |
| `COPILOT_LOG_BACKEND_QUERY_LIMIT` | `100` | Limite maximo para `GET /v1/events`. |
| `COPILOT_LOG_BACKEND_AUTO_MIGRATE` | `true` | Ejecuta migracion SQL al iniciar si storage es `postgres`. |

## Endpoints

### `GET /health`

```bash
curl -s http://localhost:8080/health
```

Respuesta:

```json
{
  "status": "ok",
  "storage": "postgres"
}
```

### `POST /v1/events`

```bash
curl -s -X POST http://localhost:8080/v1/events \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id":"session-1",
    "event_type":"userPromptSubmitted",
    "timestamp":1704614500000,
    "user_prompt":"Explicame este codigo",
    "repo_name":"demo",
    "actor":"alice",
    "raw_payload":{"prompt":"Explicame este codigo"}
  }'
```

Respuesta resumida:

```json
{
  "status": "accepted",
  "event_id": "<uuid>",
  "event": {
    "event_id": "<uuid>",
    "session_id": "session-1",
    "event_type": "userPromptSubmitted"
  }
}
```

### `POST /v1/events/batch`

```bash
curl -s -X POST http://localhost:8080/v1/events/batch \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{"events":[{"session_id":"s1","event_type":"sessionStart"}]}'
```

Respuesta:

```json
{
  "accepted": 1,
  "rejected": 0,
  "errors": []
}
```

### `GET /v1/events`

```bash
curl -s -H "Authorization: Bearer dev-token" \
  "http://localhost:8080/v1/events?event_type=userPromptSubmitted&repo_name=demo&limit=10"
```

Filtros: `session_id`, `event_type`, `repo_name`, `actor`, `from_timestamp`, `to_timestamp`, `limit`.

## Modelo de datos

Tabla `events`:

| Columna | Tipo |
| --- | --- |
| `event_id` | `TEXT PRIMARY KEY` |
| `session_id` | `TEXT NOT NULL` |
| `event_type` | `TEXT NOT NULL` |
| `timestamp` | `TIMESTAMPTZ NOT NULL` |
| `user_prompt` | `TEXT NULL` |
| `prompt_hash` | `TEXT NULL` |
| `repo_path` | `TEXT NULL` |
| `repo_name` | `TEXT NULL` |
| `git_branch` | `TEXT NULL` |
| `git_commit` | `TEXT NULL` |
| `working_directory` | `TEXT NULL` |
| `actor` | `TEXT NULL` |
| `files_changed` | `JSONB NOT NULL` |
| `tool_name` | `TEXT NULL` |
| `command` | `TEXT NULL` |
| `status` | `TEXT NULL` |
| `error` | `TEXT NULL` |
| `raw_payload` | `JSONB NULL` |
| `metadata` | `JSONB NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |

Indices:

- `idx_events_session_id`
- `idx_events_event_type`
- `idx_events_repo_name`
- `idx_events_actor`
- `idx_events_timestamp`
- `idx_events_prompt_hash`

## Cambiar storage

Para agregar otro storage, crea una clase que implemente `domain/gateways/event_repository.py`:

- `save(event)`
- `save_many(events)`
- `find(...)`

Luego registra la implementacion en `application/container.py`. Los use cases y entrypoints no necesitan cambiar.

## Seguridad y privacidad

- Todos los endpoints `/v1/*` requieren `Authorization: Bearer <token>`.
- Tokens se comparan con `secrets.compare_digest` y no se loguean.
- El sanitizer corre en el caso de uso antes de persistir.
- Se sanitizan `user_prompt`, `raw_payload`, `metadata`, `command` y `error`.
- El backend no loguea prompts completos; solo `event_id`, `event_type`, `actor`, `repo_name` y estado.
- Define retencion, acceso a tablas y backups antes de uso organizacional amplio.

## Tests

Unit e integracion API sin Postgres:

```bash
python -m pytest backend/tests -q
```

Prueba manual con Postgres:

```bash
cd backend
docker compose up --build
curl -s http://localhost:8080/health
```

Si se requiere automatizar integracion real con Postgres, el siguiente paso recomendado es agregar `testcontainers` o un job CI que ejecute `docker compose` antes de la suite.
