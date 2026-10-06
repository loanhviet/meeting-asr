from __future__ import annotations

import json
import shutil
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml

from meeting_asr.cli import main
from meeting_asr.settings import load_config


def test_experiment_count_gate_stops_inference_without_requiring_manual_labels(monkeypatch, capsys):
    def audit(*args, **kwargs):
        assert kwargs["expected_conversations"] == 20
        assert kwargs["require_verified_speech"] is False
        return {"ready": False, "issues": ["expected 20 conversations, found 2"]}

    def unexpected(*args, **kwargs):
        raise AssertionError("inference must not start after a failed data gate")

    monkeypatch.setattr("meeting_asr.evaluation.readiness.audit_experiments", audit)
    monkeypatch.setattr("meeting_asr.cli.run_experiments", unexpected)
    assert (
        main(["experiments", "unused.json", "--out", "unused", "--expected-conversations", "20"])
        == 2
    )
    assert "expected 20" in capsys.readouterr().err


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg and ffprobe are required",
)
def test_cli_reuses_cache_and_writes_run_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sr = 16000
    time = np.arange(sr * 6) / sr
    pcm = (0.2 * np.sin(2 * np.pi * 440 * time) * 32767).astype("<i2")
    source = tmp_path / "input.wav"
    with wave.open(str(source), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(pcm.tobytes())

    config = load_config()
    config["paths"]["cache_dir"] = str(tmp_path / "cache")
    config["paths"]["results_dir"] = str(tmp_path / "results")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    assert main(["preprocess", str(source), "--config", str(config_path)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["cache_hit"] is False
    assert main(["preprocess", str(source), "--config", str(config_path)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["cache_hit"] is True
    assert first["cache_key"] == second["cache_key"]
    manifests = list((tmp_path / "results" / "runs").glob("*.json"))
    assert len(manifests) == 2
    assert all(json.loads(path.read_text())["audio_sha256"] for path in manifests)
