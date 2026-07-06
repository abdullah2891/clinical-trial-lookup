# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System libraries needed to compile native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install pip-tools then resolve + install deps into a target directory so the
# runtime image only needs to COPY the installed packages, not re-compile them.
COPY pyproject.toml .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install \
        # Core serving deps only — torch/transformers are heavy and optional at
        # API startup when MODAL_ENDPOINT_URL is set (remote GPU path).
        fastapi \
        "uvicorn[standard]" \
        pydantic \
        httpx \
        requests \
        asyncpg \
        pgvector \
        "sqlalchemy[asyncio]" \
        redis \
        openai \
        langsmith \
        langgraph \
        python-dotenv \
        tenacity \
        numpy \
        tqdm \
        huggingface-hub
        # NOTE: transformers/peft/accelerate deliberately excluded — they pull
        # multi-GB CUDA torch wheels, and the API only uses them in the local-
        # inference dev path (screener imports them lazily). Install manually
        # if you need local model inference inside the container.

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Runtime system libs (libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY data_sources/ ./data_sources/
COPY etl/          ./etl/
COPY models/       ./models/
COPY pipeline/     ./pipeline/
COPY serving/      ./serving/
COPY eval/         ./eval/

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "serving.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
