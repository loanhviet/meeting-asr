from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from meeting_asr.cache import load_audio_bundle, save_audio_bundle, stage_key
from meeting_asr.models import AudioBundle
from meeting_asr.settings import load_config


def test_cache_roundtrip_and_content_invalidation(tmp_path: Path) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"first version")
    config = load_config()
    key = stage_key(source, config, "preprocess", "1")
    audio = AudioBundle(
        waveform=np.array([0.1, -0.2], dtype=np.float32),
        sr=16000,
        original_sr=44100,
        source_path=str(source),
    )

    save_audio_bundle(tmp_path / "cache", key, audio)

    loaded = load_audio_bundle(tmp_path / "cache", key)
    assert loaded is not None
    np.testing.assert_array_equal(loaded.waveform, audio.waveform)
    assert loaded.original_sr == 44100

    source.write_bytes(b"second version")
    assert stage_key(source, config, "preprocess", "1") != key


def test_preprocess_cache_ignores_later_stage_weights(tmp_path: Path) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"recording")
    config = load_config()
    original_key = stage_key(source, config, "preprocess", "1")

    config["confidence"]["weights"]["asr"] = 0.9
    assert stage_key(source, config, "preprocess", "1") == original_key
    config["preprocess"]["normalize"] = False
    assert stage_key(source, config, "preprocess", "1") != original_key


def test_broken_cache_metadata_is_a_miss(tmp_path):
    audio = AudioBundle(np.array([0.1], dtype=np.float32), 16000, 16000, "fixture")
    save_audio_bundle(tmp_path, "fixture", audio)
    (tmp_path / "fixture.json").write_text(json.dumps({"schema_version": 1, "key": "fixture"}))
    assert load_audio_bundle(tmp_path, "fixture") is None
