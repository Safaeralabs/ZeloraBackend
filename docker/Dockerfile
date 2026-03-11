# ─── Vendly API — Production Dockerfile ────────────────────────────────────────
# Runs the Django ASGI app via Gunicorn + UvicornWorker (supports WebSockets).
# Build context: repository root (backendv2/).

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ─── System dependencies ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# ─── Python dependencies ────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ─── Application code ──────────────────────────────────────────────────────────
COPY . .

# ─── Entrypoint ────────────────────────────────────────────────────────────────
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ─── Non-root user for security ────────────────────────────────────────────────
RUN addgroup --system vendly && adduser --system --ingroup vendly vendly
RUN chown -R vendly:vendly /app
USER vendly

# ─── Logs directory ────────────────────────────────────────────────────────────
RUN mkdir -p /app/logs

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]

# Gunicorn + UvicornWorker for ASGI (HTTP + WebSocket via Daphne fallback)
CMD ["gunicorn", \
     "config.asgi:application", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--threads", "2", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
