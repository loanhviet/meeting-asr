"""Read-only local readiness checks; never include credential values."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import sys


def environment_report():
    versions = {}
    for package in (
        "torch",
        "torchaudio",
        "transformers",
        "pyannote.audio",
        "speechbrain",
        "silero-vad",
        "fastapi",
        "uvicorn",
        "reportlab",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    gpu, gpu_error = None, None
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            gpu = {"name": props.name, "memory_gib": round(props.total_memory / 1024**3, 2)}
    except (ImportError, RuntimeError, OSError) as exc:
        gpu_error = type(exc).__name__
    token = bool(os.getenv("HF_TOKEN"))
    try:
        from huggingface_hub import get_token

        token = token or bool(get_token())
    except ImportError:
        pass
    return {
        "python": sys.version.split()[0],
        "executables": {
            name: shutil.which(name) is not None for name in ("ffmpeg", "ffprobe", "node", "npm")
        },
        "packages": versions,
        "gpu": gpu,
        "gpu_error": gpu_error,
        "hf_token_present": token,
        "model_access": "not verified",
        "llm_key_present": bool(os.getenv("MEETING_LLM_API_KEY")),
        "llm_model_configured": bool(os.getenv("MEETING_LLM_MODEL")),
    }
