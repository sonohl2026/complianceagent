FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# libgdk-pixbuf's package name changed between Debian releases (bookworm:
# libgdk-pixbuf2.0-0, trixie: libgdk-pixbuf-2.0-0) as the base python:3.11-slim
# image moves to newer Debian versions over time. Try the current name first
# and fall back to the older one, so this Dockerfile doesn't silently break
# again the next time the upstream base image's Debian release changes.
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

COPY pyproject.toml ./
COPY app ./app

# Install CPU-only PyTorch first, from PyTorch's own CPU wheel index. The
# default PyPI torch build bundles full NVIDIA CUDA support (~2-3GB of
# nvidia-*/triton packages) even on this CPU-only, non-GPU deployment
# (config.embedding_device defaults to "cpu" -- see docs/architecture.md).
# Installing the CPU wheel first satisfies sentence-transformers' torch
# requirement without pip ever reaching for the CUDA build.
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install -e ".[dev]"

COPY alembic.ini ./
COPY migrations ./migrations
COPY tests ./tests

# scripts/ lives at the repo root (shared across services) and is mounted at
# runtime via docker-compose; create the mount point here for local `docker build` use.
RUN mkdir -p /app/scripts

RUN mkdir -p /app/data/storage/projects /app/data/storage/uploads \
    /app/data/storage/crawls /app/data/storage/exports /app/data/storage/quarantine

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
