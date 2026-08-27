FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DATABASE_URL=sqlite:////app/runtime/maintenance_copilot.db \
    LANGGRAPH_CHECKPOINT_PATH=/app/runtime/langgraph_checkpoints.sqlite \
    ENGINEERING_DOCS_PATH=/app/data/engineering_docs \
    VECTOR_STORE_PATH=/app/runtime/chroma \
    HF_HOME=/app/runtime/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
    ca-certificates \
    libgomp1 \
    && rm --recursive --force /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

ARG TORCH_VERSION=2.11.0

RUN python -m pip install \
    --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    "torch==${TORCH_VERSION}"

RUN python -m pip install --no-cache-dir --requirement requirements.txt

RUN groupadd --system maintenance \
    && useradd \
    --system \
    --gid maintenance \
    --home-dir /home/maintenance \
    --create-home \
    maintenance \
    && mkdir --parents /app/runtime \
    && chown --recursive maintenance:maintenance /app/runtime

COPY --chown=maintenance:maintenance . .

USER maintenance

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]