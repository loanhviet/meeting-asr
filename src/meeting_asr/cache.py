"""Versioned, non-pickle cache for the preprocessed audio stage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from meeting_asr.models import SCHEMA_VERSION, AudioBundle
from meeting_asr.runtime import file_sha256
from meeting_asr.settings import config_hash


def stage_key(
    audio_path: str | Path,
    config: dict[str, Any],
    stage: str,
    implementation_version: str,
) -> str:
    source_digest = file_sha256(audio_path)
    if stage not in config:
        raise ValueError(f"missing config for stage: {stage}")
    raw = (
        f"{source_digest}:{config_hash(config[stage])}:"
        f"{stage}:{implementation_version}:{SCHEMA_VERSION}"
    )
    return hashlib.sha256(raw.encode("ascii")).hexdigest()[:24]


def save_audio_bundle(directory: str | Path, key: str, audio: AudioBundle) -> None:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    array_path = target / f"{key}.npy"
    meta_path = target / f"{key}.json"
    array_temp = target / f"{key}.npy.tmp"
    meta_temp = target / f"{key}.json.tmp"
    with array_temp.open("wb") as handle:
        np.save(handle, audio.waveform, allow_pickle=False)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "key": key,
        "sr": audio.sr,
        "original_sr": audio.original_sr,
        "source_path": audio.source_path,
        "normalization_method": audio.normalization_method,
        "warnings": audio.warnings,
    }
    meta_temp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    array_temp.replace(array_path)
    meta_temp.replace(meta_path)


def load_audio_bundle(directory: str | Path, key: str) -> AudioBundle | None:
    target = Path(directory)
    array_path = target / f"{key}.npy"
    meta_path = target / f"{key}.json"
    if not array_path.exists() or not meta_path.exists():
        return None
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        waveform = np.load(array_path, allow_pickle=False)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if metadata.get("schema_version") != SCHEMA_VERSION or metadata.get("key") != key:
        return None
    return AudioBundle(
        waveform=waveform,
        sr=metadata["sr"],
        original_sr=metadata["original_sr"],
        source_path=metadata["source_path"],
        normalization_method=metadata["normalization_method"],
        warnings=metadata["warnings"],
    )
