# ── Stage 1: build dependencies ─────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# System build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=odoo_secure.settings

WORKDIR /app

# Runtime system deps:
#   docker-cli  → allows running "docker restart <container>" on the host socket
#   procps      → provides ps/kill for debugging
RUN apt-get update && apt-get install -y --no-install-recommends \
        docker.io \
        util-linux \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy project source
COPY . .

# Ensure static source dir exists before collectstatic
RUN mkdir -p /app/static

# Collect static files
RUN python manage.py collectstatic --noinput

# Create non-root user (still needs access to docker.sock and /var/log)
RUN groupadd -r appuser && \
    useradd -r -g appuser -G adm appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Gunicorn: 1 worker + 4 threads so APScheduler only starts once
CMD ["gunicorn", "odoo_secure.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
