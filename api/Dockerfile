# syntax=docker/dockerfile:1.7
# Two-stage build: wheels in stage 1, slim runtime in stage 2.

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# System deps required to build lxml + reportlab cleanly.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt \
    && pip wheel --wheel-dir /wheels "psycopg[binary]>=3.1"


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    PYTHONPATH=/app

WORKDIR /app

# Lean runtime libs for lxml and sqlite
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY api/requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt "psycopg[binary]>=3.1" \
    && rm -rf /wheels

# Copy the Python app
COPY api ./api

# Directory for SQLite + branding assets when no managed DB is attached
RUN mkdir -p /app/api/data /app/api/data/branding

EXPOSE 8000

# Use shell form so ${PORT} expands at runtime (Fly.io injects it).
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
