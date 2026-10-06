import json

import pytest
from test_speech_labels import labelled_clips

from meeting_asr.data_gen.dataset import build_dataset
from meeting_asr.data_gen.simulate import write_mono_wav
from meeting_asr.evaluation.readiness import audit_experiments, plan_data


def dataset(tmp_path):
    entries = []
    for clip in labelled_clips():
        path = tmp_path / f"{clip.clip_id}.wav"
        write_mono_wav(path, clip.waveform, 16000)
        entries.append(
            {
                "clip_id": clip.clip_id,
                "source": clip.source,
                "speaker": clip.speaker,
                "text": clip.text,
                "wav": str(path),
                "speech_intervals": clip.speech_intervals,
                "speech_annotation": clip.speech_annotation,
            }
        )
    manifest = tmp_path / "clips.json"
    manifest.write_text(json.dumps({"split": "test", "clips": entries}))
    return manifest


def test_capacity_reports_missing_labels_and_duration_before_inference(tmp_path):
    report = plan_data(dataset(tmp_path), conversations=20, clips_per_speaker=3)
    assert not report["ready"]
    assert report["capacity_conversations"] == 1
    assert len(report["issues"]) == 3


def test_matrix_audit_checks_verification_leakage_and_missing_conditions(tmp_path):
    manifest = dataset(tmp_path)
    out = tmp_path / "out"
    build_dataset(manifest, out, conversations=1, clips_per_speaker=3)
    session_manifest = out / "sessions.json"
    report = audit_experiments(session_manifest, expected_conversations=1)
    assert report["ready"], report["issues"]
    assert not audit_experiments(session_manifest, require_verified_speech=True)["ready"]
    assert not audit_experiments(session_manifest, other_manifest=session_manifest)["ready"]
    payload = json.loads(session_manifest.read_text())
    payload["sessions"].pop()
    session_manifest.write_text(json.dumps(payload))
    assert "incomplete" in audit_experiments(session_manifest)["issues"][0]
    with pytest.raises(ValueError, match="already exists"):
        build_dataset(manifest, out, conversations=1, clips_per_speaker=3)


def test_verified_dataset_gate_rejects_automatic_labels(tmp_path):
    with pytest.raises(ValueError, match="verified speech"):
        build_dataset(
            dataset(tmp_path),
            tmp_path / "out",
            conversations=1,
            clips_per_speaker=3,
            require_verified_speech=True,
        )


def test_verified_build_selects_reviewed_clips_and_excludes_pending_pool(tmp_path):
    manifest = dataset(tmp_path)
    payload = json.loads(manifest.read_text())
    for clip in payload["clips"]:
        clip["speech_annotation"].update(
            status="human_verified",
            reviewed_by="fixture reviewer",
            reviewed_at="2026-10-06T00:00:00Z",
        )
    pending = {
        **payload["clips"][0],
        "clip_id": "pending",
        "speech_annotation": {
            "status": "automatic_unverified",
            "method": "fixture",
            "version": "v1",
        },
    }
    payload["clips"].append(pending)
    manifest.write_text(json.dumps(payload))
    result = build_dataset(
        manifest,
        tmp_path / "verified",
        conversations=1,
        clips_per_speaker=3,
        require_verified_speech=True,
    )
    assert result["excluded_unverified_clips"] == 1
    assert audit_experiments(tmp_path / "verified/sessions.json", require_verified_speech=True)[
        "ready"
    ]
