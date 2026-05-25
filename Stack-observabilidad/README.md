# Stack Observabilidad para Session Logger

Este stack recibe telemetria OTLP por HTTP en el puerto 4318 y la enruta asi:

- trazas -> Tempo
- logs -> Loki
- metricas -> Prometheus

## 1) Levantar servicios

Comando:

```bash
docker-compose -f "/Users/jomaver/Downloads/Stack-observabilidad/docker-compose.observability 1.yml" up -d
```

Validar estado:

```bash
docker-compose -f "/Users/jomaver/Downloads/Stack-observabilidad/docker-compose.observability 1.yml" ps
```

Endpoints:

- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Tempo API: http://localhost:3200
- Loki API: http://localhost:3100
- OTEL Collector OTLP HTTP: http://localhost:4318

## 2) Enviar desde Traceloop a OTLP 4318

Variables sugeridas para el proceso que instrumenta Traceloop:

```bash
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://localhost:4318/v1/logs
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://localhost:4318/v1/metrics
```

Nota:

- Si tu SDK ya usa endpoint base, bastan PROTOCOL y ENDPOINT.
- Si quieres control fino por senal, usa los endpoints especificos de traces/logs/metrics.

## 3) Clasificacion de datos del hook

El hook normaliza eventos como user_prompt, tool_use, tool_result, session_start, session_end y error.

Mapeo recomendado:

- Trazas:
  - user_prompt inicia span raiz de la interaccion.
  - tool_use crea span hijo (nombre de herramienta en tool_name).
  - tool_result cierra span hijo y agrega resultado/status/duration_ms.
  - session_start/session_end delimitan span de sesion.
- Logs:
  - payload normalizado por evento (raw_payload sanitizado).
  - errores (errorOccurred/event_type=error) como log de severidad error.
  - resumenes textuales como prompt_text, tool_input_summary, tool_result_summary.
- Metricas:
  - contador de eventos por tipo: events_total{event_type=...}.
  - latencia de herramienta desde duration_ms.
  - tasa de error: errores / total eventos.
  - volumen por herramienta: events_total{tool_name=...}.

## 4) Verificacion rapida

1. Publica un evento de prueba desde tu app instrumentada con Traceloop.
2. En Grafana, revisa Explore:
   - Tempo: busca por service.name.
   - Loki: filtra por labels de servicio/sesion.
   - Prometheus: consulta metricas con prefijo marvin_.

## 5) Si falla pull de imagenes

Si aparece error TLS tipo x509 certificate signed by unknown authority al hacer pull desde docker.io, debes agregar el certificado raiz corporativo al daemon de Docker Desktop (Settings > Certificates) o permitir acceso por un mirror de registry confiable en tu red.
