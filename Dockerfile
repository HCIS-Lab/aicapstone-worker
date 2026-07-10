FROM python:3.11-slim

# Runtime deps for Isaac Sim mode would go here (nvidia-container-runtime,
# vulkan-tools, etc.) — mock mode needs nothing beyond Python.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./worker_agent/

# Storage + state dirs. Mount volumes over these on the host so the
# machine JWT survives container recreation.
RUN mkdir -p /var/lib/worker-agent/storage /var/lib/worker-agent/state

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    WORKER_STORAGE_ROOT=/var/lib/worker-agent/storage \
    WORKER_STATE_DIR=/var/lib/worker-agent/state \
    WORKER_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "-m", "worker_agent.main"]
