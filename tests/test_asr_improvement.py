"""Protect the tuning boundary and downloaded source identity."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"split": "test"}],
        [{"split": "train"}],
        [{"split": "dev", "official_split": "test"}],
        [{"split": "dev", "mode": "diarization"}],
    ],
)
def test_tuning_rejects_non_dev_or_non_pipeline_inputs(rows, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    tuner = load_script("tune_dicow_decoding")
    with pytest.raises(ValueError):
        tuner.validate_dev_rows(rows)


def test_source_verification_rejects_changed_cached_audio(tmp_path):
    preparer = load_script("prepare_asr_improvement")
    sources = tmp_path / "sources"
    sources.mkdir()
    audio = sources / "audio.wav"
    audio.write_bytes(b"original")
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            [
                {
                    "file": "audio.wav",
                    "bytes": 8,
                    "sha256": preparer.digest(audio),
                    "url": "https://example.invalid/audio.wav",
                }
            ]
        )
    )
    preparer.download_sources(tmp_path, lock)
    audio.write_bytes(b"modified")
    with pytest.raises(ValueError, match="existing source"):
        preparer.download_sources(tmp_path, lock)


def test_source_download_budget_is_checked_before_network(tmp_path):
    preparer = load_script("prepare_asr_improvement")
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps([{"bytes": 2_000_000_001}]))
    with pytest.raises(ValueError, match="budget"):
        preparer.download_sources(tmp_path, lock)


def test_candidate_selection_keeps_each_domain_and_temporal_quality_gate(monkeypatch):
    import copy

    monkeypatch.syspath_prepend(str(SCRIPTS))
    tuner = load_script("tune_dicow_decoding")
    baseline = {
        "beam": 1,
        "complete": True,
        "failed": 0,
        "vietnamese_wer_by_dataset": {"fleurs_vi": 0.15, "vietmed": 0.24},
        "vi_macro_wer_objective": 0.195,
        "ami_metrics": {"tcpwer": {"error_rate": 0.24}},
    }
    candidate = copy.deepcopy(baseline)
    candidate.update(beam=3, vi_macro_wer_objective=0.18)
    candidate["vietnamese_wer_by_dataset"] = {"fleurs_vi": 0.14, "vietmed": 0.22}
    assert tuner.choose_candidate([baseline, candidate])["beam"] == 3
    candidate["ami_metrics"]["tcpwer"]["error_rate"] = 0.25
    assert tuner.choose_candidate([baseline, candidate])["beam"] == 1
    candidate["ami_metrics"]["tcpwer"]["error_rate"] = 0.24
    candidate["vietnamese_wer_by_dataset"]["vietmed"] = 0.25
    assert tuner.choose_candidate([baseline, candidate])["beam"] == 1
    candidate["complete"] = False
    assert tuner.choose_candidate([baseline, candidate]) is None
