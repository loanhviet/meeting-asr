import json
from types import SimpleNamespace

import pytest

from meeting_asr.benchmark import benchmark_suite
from meeting_asr.runtime import git_commit
from meeting_asr.settings import load_config


def test_cpu_benchmark_does_not_report_vram_from_an_idle_gpu(tmp_path, monkeypatch):
    def unexpected_gpu_access(*args):
        raise AssertionError("CPU benchmark must not reset or read CUDA memory stats")

    torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            reset_peak_memory_stats=unexpected_gpu_access,
            max_memory_allocated=unexpected_gpu_access,
            get_device_name=unexpected_gpu_access,
        )
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", torch)
    monkeypatch.setattr("meeting_asr.benchmark.resolve_device", lambda device: "cpu")
    monkeypatch.setattr("meeting_asr.benchmark.dependency_versions", dict)

    def pipeline(audio, options, out, no_cache):
        out.mkdir(parents=True, exist_ok=True)
        (out / "run.json").write_text(
            json.dumps(
                {
                    "result": {
                        "elapsed_sec": 3,
                        "rtf": 0.1,
                        "audio_duration_sec": 30,
                        "stages": [],
                        "stage_elapsed_sec": {"M2": 1, "M3": 2},
                    }
                }
            )
        )

    monkeypatch.setattr("meeting_asr.benchmark.run_pipeline", pipeline)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fixture")
    result = benchmark_suite(
        [audio], load_config("configs/baseline-phowhisper.yaml"), tmp_path / "out"
    )
    report = result["recordings"][0]
    assert report["device"] == "cpu" and report["gpu"] is None
    assert report["runs"][0]["peak_cuda_allocated_gib"] is None
    assert "M3_sec" in (tmp_path / "out/suite.csv").read_text()


def test_provenance_works_without_git_in_runtime_images(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr("meeting_asr.runtime.subprocess.run", missing)
    assert git_commit() is None


@pytest.mark.parametrize("cache_hit", [False, True])
def test_dicow_benchmark_uses_child_gpu_and_does_not_reuse_cached_peaks(
    tmp_path, monkeypatch, cache_hit
):
    def unexpected(*args):
        raise AssertionError("DiCoW benchmark must not measure the parent runtime")

    monkeypatch.setattr("meeting_asr.benchmark.resolve_device", unexpected)

    def pipeline(audio, options, out, no_cache):
        out.mkdir(parents=True, exist_ok=True)
        (out / "run.json").write_text(
            json.dumps(
                {
                    "result": {
                        "elapsed_sec": 2,
                        "rtf": 0.1,
                        "stages": [{"stage": "M3", "cache_hit": cache_hit}],
                    }
                }
            )
        )
        (out / "dicow-provenance.json").write_text(
            json.dumps(
                {
                    "device": "cuda",
                    "gpu": "child GPU",
                    "packages": {"torch": "child"},
                    "diarization_peak_cuda_allocated_bytes": 1024**3,
                    "asr_peak_cuda_allocated_bytes": 2 * 1024**3,
                }
            )
        )

    monkeypatch.setattr("meeting_asr.benchmark.run_pipeline", pipeline)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fixture")
    result = benchmark_suite([audio], load_config(), tmp_path / "out", cached=cache_hit)
    report = result["recordings"][0]
    assert report["device"] == "cuda" and report["gpu"] == "child GPU"
    assert report["versions"]["torch"] == "child"
    assert report["runs"][0]["peak_cuda_allocated_gib"] == (None if cache_hit else 2)
