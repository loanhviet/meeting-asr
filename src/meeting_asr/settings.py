"""Configuration loading with stable hashing for result provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_ROOT.parents[1]
PROJECT_ROOT = SOURCE_ROOT if (SOURCE_ROOT / "pyproject.toml").exists() else Path.cwd()
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "default.yaml"
if not DEFAULT_CONFIG.is_file():
    DEFAULT_CONFIG = PACKAGE_ROOT / "configs" / "default.yaml"


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
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
    return value


def config_hash(config: dict[str, Any]) -> str:
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
