# Production Dockerfile for NoteMaker AI
# Multi-stage build: separates dependency installation from the runtime image
# Uses uvicorn with multiple workers for production concurrency

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system build deps (only in builder, not the final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Default server config (override via docker-compose env or -e flags)
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8052 \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO \
    # URL prefix for reverse-proxy deployment (e.g. /note-marker)
    APPLICATION_ROOT=/note-marker \
    # Number of uvicorn worker processes
    WORKERS=2

WORKDIR /app

# Install curl for healthcheck only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY . .

# Ensure uploads directory exists with correct permissions
RUN mkdir -p /app/uploads

# Create a non-privileged user for secure container execution
RUN useradd -u 1000 -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose the application port
EXPOSE 8052

# Health check using the /health endpoint (works under any APPLICATION_ROOT)
# Uses the bare /health route which is always registered without prefix
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${SERVER_PORT}${APPLICATION_ROOT}/health" || \
        curl -fsS "http://127.0.0.1:${SERVER_PORT}/health" || exit 1

# Production launch:
#   - Multiple workers for concurrency
#   - --proxy-headers: trust X-Forwarded-* from Nginx
#   - --forwarded-allow-ips '*': accept forwarded headers from any upstream
#   - --root-path: SCRIPT_NAME prefix for reverse-proxy subpath deployment
#   - --timeout-keep-alive: keep connections open longer for upload requests
CMD LOG_LVL=$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]') && \
    exec uvicorn app.main:app \
    --host "${SERVER_HOST}" \
    --port "${SERVER_PORT}" \
    --workers "${WORKERS}" \
    --proxy-headers \
    --forwarded-allow-ips '*' \
    --root-path "${APPLICATION_ROOT}" \
    --timeout-keep-alive 65 \
    --log-level "${LOG_LVL}" \
    --access-log
