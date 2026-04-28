# copilot-log-backend

Backend minimo FastAPI para centralizar eventos generados por `copilot-session-logger`.

## Ejecutar local

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

## Docker

```bash
cd backend
docker compose up --build
```

Los eventos quedan en `backend/data/events/YYYY-MM-DD/events.jsonl`.

## Variables

- `COPILOT_LOG_BACKEND_API_KEYS`: lista separada por comas de tokens validos.
- `COPILOT_LOG_BACKEND_STORAGE`: `jsonl` o `sqlite`. Por defecto: `jsonl`.
- `COPILOT_LOG_BACKEND_HOME`: directorio base. Por defecto: `~/.copilot-log-backend`.
- `COPILOT_LOG_BACKEND_MAX_BODY_MB`: tamano maximo de request. Por defecto: `2`.
- `ALLOW_UNKNOWN_EVENT_TYPES`: permite `event_type` no conocido si es `true`.

## Endpoints

- `GET /health`: no requiere token.
- `POST /v1/events`: requiere `Authorization: Bearer <token>`.
- `POST /v1/events/batch`: acepta `{ "events": [...] }`.
- `GET /v1/events`: consulta local/dev con filtros `session_id`, `event_type`, `repo_name`, `actor`, `from_timestamp`, `to_timestamp` y `limit`.

## Prueba manual

```bash
curl -s http://localhost:8080/health
```

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

Respuesta esperada:

```json
{
  "status": "accepted",
  "event_id": "<uuid>"
}
```
