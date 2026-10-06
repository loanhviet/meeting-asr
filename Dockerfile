FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/app/.cache/huggingface \
    TORCH_HOME=/app/.cache/torch \
    XDG_CACHE_HOME=/app/.cache/xdg \
    PATH=/app/.venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg libsoxr0 libsndfile1 libgomp1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv==0.12.2

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY configs/ ./configs/
COPY src/ ./src/
EXPOSE 8000
CMD ["meeting-asr", "serve", "--host", "0.0.0.0"]

FROM base AS gpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra api --extra inference --extra demo --extra annotation

FROM base AS cpu
# Retain locked application dependencies, replacing only Torch/Torchaudio with
# the matching official CPU wheels and omitting CUDA-only runtime packages.
RUN --mount=type=cache,target=/root/.cache/uv python - <<'PY'
import subprocess
import tomllib

with open("uv.lock", "rb") as handle:
    packages = tomllib.load(handle)["package"]
skip = {"torch", "torchaudio", "triton"} | {
    p["name"] for p in packages if p["name"].startswith("nvidia-")
}
command = ["uv", "sync", "--locked", "--no-dev", "--extra", "api",
           "--extra", "inference", "--extra", "demo", "--extra", "annotation"]
for name in sorted(skip):
    command.extend(["--no-install-package", name])
subprocess.run(command, check=True)
versions = {p["name"]: p["version"] for p in packages if p["name"] in {"torch", "torchaudio"}}
subprocess.run(["uv", "pip", "install", "--python", "/app/.venv/bin/python", "--no-deps",
                "--index-url", "https://download.pytorch.org/whl/cpu",
                *[f"{name}=={version}" for name, version in sorted(versions.items())]], check=True)
PY
