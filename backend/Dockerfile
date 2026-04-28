FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV COPILOT_LOG_BACKEND_HOME=/data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8080
VOLUME ["/data"]

CMD ["uvicorn", "copilot_log_backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
