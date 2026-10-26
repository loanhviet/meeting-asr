"""Local readiness checks and explicit live probes; never include credentials."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def probe_llm(options):
    """One explicit, bounded request; no user transcript or credential in the report."""
    from meeting_asr.evaluation.acceptance import llm_readiness
    from meeting_asr.summarize import LLMRequestError, Summarizer

    report = llm_readiness(options)
    report.update(mode="live_probe", api_accessible=False, configuration_ready=report["ready"])
    if not report["ready"]:
        return report
    probe_options = dict(options)
    probe_options["max_output_tokens"] = 512
    probe_options["timeout_sec"] = min(options.get("timeout_sec", 90), 20)
    adapter = Summarizer(probe_options, Path(".cache") / "llm-probe-unused")
    report["model"] = adapter.model
    report["endpoint_sha256"] = hashlib.sha256(adapter.identity["base_url"].encode()).hexdigest()
    report["max_output_tokens"] = 512
    report["requests_sent"] = 1
    try:
        raw = adapter.provider.complete(
            'Trả đúng JSON {"ok":true}. Không thêm nội dung khác.', adapter.model
        )
        report["api_accessible"] = True
        report["ready"] = json.loads(raw) == {"ok": True}
        report["category"] = "ok" if report["ready"] else "unexpected_probe_response"
    except LLMRequestError as exc:
        report.update(
            ready=False,
            category=exc.category,
            http_status=exc.status_code,
            provider_code=exc.provider_code,
        )
    except (ValueError, TypeError, KeyError, IndexError):
        report.update(ready=False, category="invalid_provider_response")
    return report


def environment_report(config=None):
    from meeting_asr.settings import load_config

    config = load_config() if config is None else config
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
    report = {
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
        "asr_engine": config["asr"].get("engine", "whisper"),
        "asr_model": config["asr"]["model_name"],
        "diarization_backend": config["diarization"]["backend"],
    }
    if report["asr_engine"] == "dicow":
        from meeting_asr.dicow import author_runtime

        try:
            python, upstream = author_runtime(config)
            inspection = subprocess.run(
                [str(python), str(Path(__file__).with_name("dicow_runner.py")), "--inspect"],
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            runtime = json.loads(inspection.stdout)
            report["dicow_runtime"] = {
                "ready": True,
                "executable": str(python),
                "upstream_dir": str(upstream),
                **runtime,
            }
            report["gpu"] = runtime["gpu"]
            report["gpu_error"] = None
            report["hf_token_present"] = token or runtime["hf_token_present"]
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            report["dicow_runtime"] = {"ready": False, "error": type(exc).__name__}
    return report
