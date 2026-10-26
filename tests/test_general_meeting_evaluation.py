"""Protect diagnostic scoring from denominator and scoring-region mistakes."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from meeting_asr.io import write_transcript_json
from meeting_asr.models import TranscriptDocument, Utterance

_spec = importlib.util.spec_from_file_location(
    "general_meeting_evaluation",
    Path(__file__).resolve().parents[1] / "scripts/evaluate_general_meetings.py",
)
_evaluation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_evaluation)
digest, score = _evaluation.digest, _evaluation.score


def test_failed_inference_counts_as_deletions(tmp_path):
    row = {
        "id": "failed",
        "dataset": "fixture",
        "mode": "pipeline",
        "duration_sec": 10,
        "reference_text": "xin chào",
        "audio_sha256": "fixture",
    }
    result = score(row, tmp_path, status="failed", error="inference failed", elapsed=1)
    assert result["wer"]["errors"] == result["wer"]["reference_units"] == 2
    assert result["wer"]["rate"] == 1
    assert result["cer"]["rate"] == 1
    assert result["status"] == "failed"


def test_diarization_uses_uem_and_keeps_raw_padding(tmp_path):
    reference = tmp_path / "reference.rttm"
    reference.write_text("SPEAKER fixture 1 0.000 5.000 <NA> <NA> A <NA> <NA>\n")
    uem = tmp_path / "reference.uem"
    uem.write_text("fixture 1 0.000 5.000\n")
    hypothesis = tmp_path / "diarization.rttm"
    raw = (
        "SPEAKER fixture 1 0.000 5.000 <NA> <NA> X <NA> <NA>\n"
        "SPEAKER fixture 1 10.000 2.000 <NA> <NA> Y <NA> <NA>\n"
    )
    hypothesis.write_text(raw)
    row = {
        "id": "fixture",
        "dataset": "fixture",
        "mode": "diarization",
        "duration_sec": 10,
        "reference_rttm": str(reference),
        "reference_rttm_sha256": digest(reference),
        "reference_uem": str(uem),
    }
    result = score(row, tmp_path, elapsed=1)
    assert result["der"]["strict"]["rate"] == pytest.approx(0)
    assert result["der"]["strict"]["total_sec"] == pytest.approx(5)
    assert result["predicted_segments_past_audio"] == 1
    assert hypothesis.read_text() == raw
    assert result["wer"] is None


def test_reference_timeline_outside_audio_is_rejected(tmp_path):
    reference = tmp_path / "reference.rttm"
    reference.write_text("SPEAKER fixture 1 0.000 12.000 <NA> <NA> A <NA> <NA>\n")
    (tmp_path / "diarization.rttm").write_text("")
    row = {
        "id": "fixture",
        "dataset": "fixture",
        "mode": "diarization",
        "duration_sec": 10,
        "reference_rttm": str(reference),
        "reference_rttm_sha256": digest(reference),
    }
    with pytest.raises(ValueError, match="exceeds audio duration"):
        score(row, tmp_path, elapsed=1)


def test_full_text_uses_source_hash_and_decoded_duration(tmp_path):
    transcript = TranscriptDocument(
        "fixture", 5.0, 16000, "fixture", [Utterance(0, 5, "X", "xin chào")]
    )
    write_transcript_json(tmp_path / "transcript.json", transcript)
    (tmp_path / "diarization.rttm").write_text(
        "SPEAKER fixture 1 0.000 5.000 <NA> <NA> X <NA> <NA>\n"
    )
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"audio_sha256": "same-source"}))
    row = {
        "id": "fixture",
        "dataset": "fixture",
        "mode": "pipeline",
        "duration_sec": 5.09,
        "audio_sha256": "same-source",
        "reference_text": "xin chào",
    }
    result = score(row, tmp_path, elapsed=1)
    assert result["wer"]["rate"] == 0
    assert result["duration_sec"] == 5.0
    assert result["source_nominal_duration_sec"] == 5.09
    run.write_text(json.dumps({"audio_sha256": "different-source"}))
    with pytest.raises(ValueError, match="checksum mismatch"):
        score(row, tmp_path, elapsed=1)


def test_explicit_dev_manifest_freezes_inputs_and_beam_config(tmp_path, monkeypatch):
    from meeting_asr.settings import config_hash

    # prepare sets these environment overrides; keep them local to this test.
    monkeypatch.setenv("MEETING_LLM_ENABLED", "false")
    monkeypatch.setenv("MEETING_DEVICE", "cuda")
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"audio fixture")
    manifest = tmp_path / "dev.jsonl"
    row = {
        "id": "clip.wav",
        "dataset": "fixture",
        "split": "dev",
        "duration_sec": 6,
        "audio_path": "input.wav",
        "reference_text": "xin chào",
    }
    manifest.write_text(json.dumps(row) + "\n")
    out = tmp_path / "evaluation"
    _evaluation.prepare(tmp_path, out, manifest=manifest, num_beams=3)
    frozen = json.loads((out / "selection.json").read_text())
    assert frozen["rows"][0]["audio_path"] == str(audio)
    assert frozen["rows"][0]["audio_sha256"] == digest(audio)
    assert frozen["config"]["dicow"]["num_beams"] == 3
    assert frozen["config_hash"] == config_hash(frozen["config"])
    assert frozen["manifest_sha256"] == digest(manifest)
    assert not frozen["config"]["llm"]["enabled"]
    assert "development" in frozen["rows"][0]["evaluation_split"]
    frozen["config"]["dicow"]["num_beams"] = 5
    (out / "selection.json").write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="configuration hash changed"):
        _evaluation.run_pipeline_rows(out, None)


def test_completed_inference_is_rescored_without_another_gpu_run(tmp_path, monkeypatch):
    from meeting_asr.settings import config_hash

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fixture")
    config = {"asr": {"language": "vi"}}
    row = {
        "mode": "pipeline",
        "dataset": "fixture",
        "id": "clip.wav",
        "audio_path": str(audio),
        "audio_sha256": digest(audio),
        "language": "vi",
    }
    (tmp_path / "selection.json").write_text(
        json.dumps(
            {
                "config": config,
                "config_hash": config_hash(config),
                "rows": [row],
            }
        )
    )
    folder = _evaluation.folder_for(tmp_path, row)
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps(
            {
                "config_hash": config_hash(config),
                "audio_sha256": digest(audio),
                "result": {"oracle_rttm": None, "elapsed_sec": 12},
            }
        )
    )
    calls = []
    monkeypatch.setattr(_evaluation, "score", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(_evaluation.subprocess, "Popen", lambda *a, **kw: pytest.fail("GPU rerun"))
    _evaluation.run_pipeline_rows(tmp_path, None)
    assert len(calls) == 1 and calls[0][1]["elapsed"] == 12
    audio.write_bytes(b"changed")
    with pytest.raises(ValueError, match="audio changed"):
        _evaluation.run_pipeline_rows(tmp_path, None)
