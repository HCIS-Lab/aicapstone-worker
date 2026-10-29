# Mock-mode image: the UI and run queue without Isaac Sim or a GPU.
# Runs return synthetic scores — for trying out the UI, never for grading.
# Real evaluations use Dockerfile.real.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./worker_agent/
COPY ui/ ./worker_agent/ui/

RUN mkdir -p /var/lib/worker-agent/storage /var/lib/worker-agent/state

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    WORKER_STORAGE_ROOT=/var/lib/worker-agent/storage \
    WORKER_STATE_DIR=/var/lib/worker-agent/state \
    WORKER_PORT=8080 \
    EVAL_MODE=mock

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "worker_agent.main:app", "--host", "0.0.0.0", "--port", "8080"]
