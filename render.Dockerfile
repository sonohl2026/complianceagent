# Render deployment image (web/worker/scheduler services -- see render.yaml).
#
# Deliberately separate from backend/Dockerfile: the local docker-compose
# setup bind-mounts ./prompts and ./scripts from the repo root at runtime
# (see docker-compose.yml), which only works with a real host filesystem.
# A hosted deploy has no bind mounts, so prompts/ must be baked into the
# image at build time instead -- which means this Dockerfile needs a build
# context of the repo root, not backend/ alone, to reach both backend/ and
# prompts/ in one COPY. scripts/ is standalone admin/maintenance CLI
# tooling (backup, restore, seed, reindex), never imported by the running
# app, so it's deliberately left out of this image.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# See backend/Dockerfile for why the gdk-pixbuf/postgresql-client package
# names each try two alternatives -- same reasoning applies here.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libffi-dev \
    libcairo2 \
    shared-mime-info \
    fonts-liberation \
    && (apt-get install -y --no-install-recommends libgdk-pixbuf-2.0-0 \
        || apt-get install -y --no-install-recommends libgdk-pixbuf2.0-0) \
    && (apt-get install -y --no-install-recommends postgresql-client-16 \
        || apt-get install -y --no-install-recommends postgresql-client) \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml ./
COPY backend/app ./app

# See backend/Dockerfile for why CPU-only PyTorch is installed first.
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install -e ".[dev]"

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/benchmark_suite.json ./
COPY prompts ./prompts

RUN mkdir -p /app/data/storage/projects /app/data/storage/uploads \
    /app/data/storage/crawls /app/data/storage/exports /app/data/storage/quarantine

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
