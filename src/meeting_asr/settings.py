"""Configuration loading with stable hashing for result provenance."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_ROOT.parents[1]
PROJECT_ROOT = SOURCE_ROOT if (SOURCE_ROOT / "pyproject.toml").exists() else Path.cwd()
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "default.yaml"
if not DEFAULT_CONFIG.is_file():
    DEFAULT_CONFIG = PACKAGE_ROOT / "configs" / "default.yaml"


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    load_environment()
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"config must contain a YAML mapping: {config_path}")
    for section in ("seed", "preprocess", "paths"):
        if section not in value:
            raise ValueError(f"config is missing {section}: {config_path}")
    if value["preprocess"].get("target_sr") != 16000:
        raise ValueError("the current pipeline contract requires target_sr=16000")
    if os.getenv("MEETING_LLM_ENABLED") is not None:
        enabled = os.environ["MEETING_LLM_ENABLED"].lower()
        if enabled not in {"true", "false", "1", "0"}:
            raise ValueError("MEETING_LLM_ENABLED must be true or false")
        value.setdefault("llm", {})["enabled"] = enabled in {"true", "1"}
    if os.getenv("MEETING_DEVICE"):
        value.setdefault("runtime", {})["device"] = os.environ["MEETING_DEVICE"]
    if os.getenv("MEETING_ASR_BATCH_SIZE"):
        value["asr"]["batch_size"] = int(os.environ["MEETING_ASR_BATCH_SIZE"])
    calibration_path = os.getenv("MEETING_CONFIDENCE_CALIBRATION") or value.get(
        "confidence", {}
    ).get("calibration_file")
    if calibration_path:
        calibration_path = Path(calibration_path)
        if not calibration_path.is_absolute():
            calibration_path = PROJECT_ROOT / calibration_path
        raw = calibration_path.read_text(encoding="utf-8")
        calibration = json.loads(raw)
        if calibration.get("split") != "dev":
            raise ValueError("confidence calibration must come from dev")
        value["confidence"]["margin_ref"] = calibration["margin_ref"]
        if "weights" in calibration:
            value["confidence"]["weights"] = calibration["weights"]
        value["confidence"]["calibration_hash"] = hashlib.sha256(raw.encode()).hexdigest()
    return value


def load_environment():
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def config_hash(config: dict[str, Any]) -> str:
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
