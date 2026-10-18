FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/app/.cache/huggingface \
    TORCH_HOME=/app/.cache/torch \
    XDG_CACHE_HOME=/app/.cache/xdg \
    PATH=/app/.venv/bin:$PATH \
    MEETING_DICOW_PYTHON=/opt/dicow/venv/bin/python \
    MEETING_DICOW_UPSTREAM_DIR=/opt/dicow/upstream/DiCoW \
    MEETING_DICOW_RUNTIME_MANIFEST=/opt/dicow/runtime.json

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git ffmpeg libsoxr0 libsndfile1 libgomp1 fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv==0.12.2

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY configs/ ./configs/
COPY requirements/ ./requirements/
COPY scripts/setup_dicow.py ./scripts/setup_dicow.py
# The API environment has no legacy ASR models. The pinned author's packages
# live in /opt so mounting the host's .cache cannot hide the image's runtime.
# Override XDG_CACHE_HOME for uv during builds so wheel caches stay in the
# BuildKit mount rather than being copied into the runtime image layers.
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_CACHE_DIR=/root/.cache/uv uv sync --locked --no-dev --no-install-project --extra api --extra demo --extra annotation
RUN git config --system --add safe.directory /opt/dicow/upstream/DiCoW \
    && git config --system --add safe.directory /opt/dicow/upstream/DiCoW/DiariZen
EXPOSE 8000
CMD ["meeting-asr", "serve", "--host", "0.0.0.0", "--config", "/app/configs/default.yaml"]

FROM base AS gpu-runtime
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_CACHE_DIR=/root/.cache/uv python scripts/setup_dicow.py --root /opt/dicow --torch-backend cu128

FROM base AS cpu-runtime
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_CACHE_DIR=/root/.cache/uv python scripts/setup_dicow.py --root /opt/dicow --torch-backend cpu

FROM gpu-runtime AS gpu
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_CACHE_DIR=/root/.cache/uv uv pip install --python /app/.venv/bin/python --no-deps -e .

FROM cpu-runtime AS cpu
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_CACHE_DIR=/root/.cache/uv uv pip install --python /app/.venv/bin/python --no-deps -e .
