"""Default upload/CLI routing must never silently use the legacy recognizer."""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from meeting_asr.api import create_app
from meeting_asr.cli import main
from meeting_asr.data_gen.simulate import write_mono_wav
from meeting_asr.diarization import DiarizationResult
from meeting_asr.models import DiarSignals, Segment, Utterance
from meeting_asr.settings import load_config


@pytest.mark.parametrize("runtime_ready", [True, False])
def test_default_upload_uses_dicow_and_preserves_pipeline_artifacts(
    tmp_path, monkeypatch, runtime_ready
):
    config = load_config()
    config["paths"]["cache_dir"] = str(tmp_path / "cache")
    config["llm"]["enabled"] = False
    calls = []

    def author(audio, options, destination, *, oracle_rttm, progress):
        calls.append((options["asr"]["engine"], options["diarization"]["backend"]))
        if not runtime_ready:
            raise RuntimeError("DiCoW runtime is missing")
        progress("M3", 0.4)
        return (
            DiarizationResult([Segment(0, 6, "A")], [DiarSignals(0)], "diarizen"),
            [Utterance(1, 4, "A", "xin chào")],
            {"fixture": True},
            {"raw": "fixture"},
        )

    def legacy(*args, **kwargs):
        raise AssertionError("Default uploads must not call the baseline")

    monkeypatch.setattr("meeting_asr.dicow.recognize_author", author)
    monkeypatch.setattr("meeting_asr.pipeline.make_backend", legacy)
    monkeypatch.setattr("meeting_asr.pipeline.transcribe", legacy)
    source = tmp_path / "audio.wav"
    write_mono_wav(source, np.sin(np.arange(96000) / 16000).astype(np.float32), 16000)
    app = create_app(config, tmp_path / "jobs", start_worker=False)
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert (health["asr_engine"], health["diarization_backend"]) == ("dicow", "diarizen")
        job_id = client.post(
            "/api/jobs", files={"file": ("meeting.wav", source.read_bytes())}
        ).json()["job_id"]
        app.state.worker.process_one(job_id)
        if not runtime_ready:
            assert client.get(f"/api/jobs/{job_id}").json()["status"] == "failed"
            assert calls == [("dicow", "diarizen")]
            return
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "complete"
        result = client.get(f"/api/jobs/{job_id}/result").json()
        assert result["original"]["turns"][0]["text"] == "Xin chào"
        out = app.state.store.artifact_dir(job_id)
        assert json.loads((out / "run.json").read_text())["result"]["asr_engine"] == "dicow"
        assert (out / "dicow-provenance.json").is_file()
    assert calls == [("dicow", "diarizen")]


def test_runtime_paths_override_dicow_without_changing_baseline(monkeypatch):
    monkeypatch.setenv("MEETING_DICOW_PYTHON", "/opt/dicow/venv/bin/python")
    monkeypatch.setenv("MEETING_DICOW_UPSTREAM_DIR", "/opt/dicow/upstream/DiCoW")
    monkeypatch.setenv("MEETING_DICOW_RUNTIME_MANIFEST", "/opt/dicow/runtime.json")
    config = load_config()
    assert config["dicow"]["python"] == "/opt/dicow/venv/bin/python"
    assert config["dicow"]["runtime_manifest"] == "/opt/dicow/runtime.json"
    assert config["dicow"]["upstream_dir"] == "/opt/dicow/upstream/DiCoW"
    baseline = load_config("configs/baseline-phowhisper.yaml")
    assert baseline["asr"]["engine"] == "whisper"
    assert baseline["asr"]["model_name"] == "vinai/PhoWhisper-medium"
    assert "dicow" not in baseline


def test_cli_rejects_baseline_backend_with_default_dicow(capsys):
    assert main(["run", "unused.wav", "--out", "unused", "--backend", "ecapa"]) == 2
    assert "configs/baseline-phowhisper.yaml" in capsys.readouterr().err
