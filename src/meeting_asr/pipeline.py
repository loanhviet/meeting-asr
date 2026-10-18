"""Sequential stages with upstream-aware caches and restartable artifacts."""

from __future__ import annotations

import importlib.metadata
import json
import time
from collections.abc import Callable
from pathlib import Path

from meeting_asr.asr import transcribe
from meeting_asr.cache import load_audio_bundle, save_audio_bundle, stage_key
from meeting_asr.confidence import review_coverage, score_confidence
from meeting_asr.diarization import DiarizationResult, make_backend
from meeting_asr.evaluation.overlap import utterance_overlap_fractions
from meeting_asr.io import (
    _atomic_text,
    read_rttm,
    read_transcript_json,
    write_minutes_json,
    write_rttm,
    write_transcript_json,
)
from meeting_asr.models import DiarSignals, MeetingMinutes, TranscriptDocument
from meeting_asr.postprocess import postprocess
from meeting_asr.preprocess import preprocess
from meeting_asr.runtime import file_sha256, set_seed, write_run_manifest
from meeting_asr.settings import PROJECT_ROOT, config_hash

Progress = Callable[[str, float], None]


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def dependency_versions() -> dict:
    result = {}
    for name in ("torch", "transformers", "pyannote.audio", "speechbrain"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def run_pipeline(
    source: str | Path,
    config: dict,
    out: str | Path,
    *,
    no_cache=False,
    oracle_rttm: str | Path | None = None,
    progress: Progress | None = None,
) -> MeetingMinutes:
    missing = {"diarization", "asr", "postprocess", "confidence"} - set(config)
    if missing:
        raise ValueError(f"pipeline config is missing sections: {sorted(missing)}")
    source, destination = Path(source).resolve(), Path(out)
    destination.mkdir(parents=True, exist_ok=True)
    cache = project_path(config["paths"]["cache_dir"])
    device = config.get("runtime", {}).get("device", "auto")
    started = time.perf_counter()
    stages = []
    stage_elapsed_sec = {}
    timing_stage, timing_started = None, started
    set_seed(int(config["seed"]))

    def notify(stage, fraction):
        nonlocal timing_stage, timing_started
        now = time.perf_counter()
        if timing_stage is not None:
            stage_elapsed_sec[timing_stage] = now - timing_started
        timing_stage, timing_started = stage, now
        if progress:
            progress(stage, fraction)

    notify("M1", 0.05)
    key1 = stage_key(source, config, "preprocess", "1")
    audio = None if no_cache else load_audio_bundle(cache / "preprocess", key1)
    hit = audio is not None
    if audio is None:
        audio = preprocess(source, **config["preprocess"])
        save_audio_bundle(cache / "preprocess", key1, audio)
    stages.append({"stage": "M1", "cache_hit": hit, "key": key1})
    versions = dependency_versions()
    common = {"seed": config["seed"], "device": device, "versions": versions}
    engine = config["asr"].get("engine", "whisper")
    if engine not in {"whisper", "dicow"}:
        raise ValueError(f"unknown ASR engine: {engine}")
    recognize = _recognize_dicow if engine == "dicow" else _recognize_cascaded
    _diar, transcript = recognize(
        source,
        audio,
        config,
        cache,
        key1,
        common,
        destination,
        stages,
        notify,
        no_cache,
        oracle_rttm,
    )
    notify("M4", 0.75)
    turns = postprocess(transcript.utterances, **config["postprocess"])
    minutes = MeetingMinutes(source.stem, audio.duration, transcript.num_speakers, turns)
    notify("M5", 0.85)
    minutes.turns = score_confidence(turns, seed=int(config["seed"]), **config["confidence"])
    minutes.flagged_ratio = review_coverage(minutes.turns)
    summary_error = None
    if config.get("llm", {}).get("enabled"):
        from meeting_asr.summarize import Summarizer

        notify("M6", 0.92)
        try:
            summary = Summarizer(config["llm"], cache / "summaries").summarize(minutes.turns)
            minutes.summary, minutes.topics, minutes.action_items = (
                summary["summary"],
                summary["topics"],
                summary["action_items"],
            )
            minutes.summary_points = summary["summary_points"]
            minutes.decisions = summary["decisions"]
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            summary_error = str(exc)
    _atomic_text(
        destination / "summary_status.json",
        json.dumps(
            {
                "enabled": bool(config.get("llm", {}).get("enabled")),
                "error": summary_error,
            }
        ),
    )
    write_minutes_json(destination / "minutes.json", minutes)
    elapsed = time.perf_counter() - started
    if timing_stage is not None:
        stage_elapsed_sec[timing_stage] = time.perf_counter() - timing_started
    write_run_manifest(
        destination / "run.json",
        config=config,
        audio_path=source,
        result={
            "stages": stages,
            "asr_engine": engine,
            "stage_elapsed_sec": stage_elapsed_sec,
            "audio_duration_sec": audio.duration,
            "elapsed_sec": elapsed,
            "rtf": elapsed / audio.duration,
            "versions": versions,
            "warnings": audio.warnings,
            "review_coverage": minutes.flagged_ratio,
            "summary_error": summary_error,
            "oracle_rttm": str(oracle_rttm) if oracle_rttm else None,
        },
    )
    notify("complete", 1.0)
    return minutes


def _recognize_cascaded(
    source, audio, config, cache, key1, common, destination, stages, notify, no_cache, oracle_rttm
):
    notify("M2", 0.2)
    key2 = config_hash(
        {
            "audio": key1,
            "config": config["diarization"],
            **common,
            "oracle": file_sha256(oracle_rttm) if oracle_rttm else None,
            "implementation": 3,
        }
    )
    diar_path = cache / "diarization" / f"{key2}.json"
    diar = None
    if not no_cache and diar_path.exists():
        try:
            diar = DiarizationResult.from_dict(json.loads(diar_path.read_text()))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    hit = diar is not None
    if diar is None:
        if oracle_rttm:
            segments = read_rttm(oracle_rttm)
            diar = DiarizationResult(
                segments, [DiarSignals(r) for r in utterance_overlap_fractions(segments)], "oracle"
            )
        else:
            backend = make_backend(config["diarization"], common["device"])
            options = {
                k: v
                for k, v in config["diarization"].items()
                if k not in {"backend", "model_name", "ecapa"}
            }
            diar = backend.diarize(audio, **options)
        _atomic_text(diar_path, json.dumps(diar.to_dict(), ensure_ascii=False))
    write_rttm(destination / "diarization.rttm", source.stem, diar.segments)
    _atomic_text(destination / "diarsignals.json", json.dumps(diar.to_dict(), ensure_ascii=False))
    stages.append({"stage": "M2", "cache_hit": hit, "key": key2, "backend": diar.backend})
    notify("M3", 0.4)
    key3 = config_hash({"diarization": key2, "asr": config["asr"], **common, "implementation": 2})
    transcript_path = cache / "asr" / f"{key3}.json"
    transcript = None
    if not no_cache and transcript_path.exists():
        try:
            transcript = read_transcript_json(transcript_path)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    hit = transcript is not None
    if transcript is None:
        utterances = transcribe(
            audio,
            diar,
            device=common["device"],
            **{k: v for k, v in config["asr"].items() if k != "engine"},
        )
        transcript = TranscriptDocument(
            source.stem, audio.duration, audio.sr, config_hash(config), utterances
        )
        write_transcript_json(transcript_path, transcript)
    # Identical audio under a different filename may reuse the same cached inference.
    transcript.audio_id = source.stem
    transcript.config_hash = config_hash(config)
    write_transcript_json(destination / "transcript.json", transcript)
    stages.append({"stage": "M3", "cache_hit": hit, "key": key3})
    return diar, transcript


def _recognize_dicow(
    source, audio, config, cache, key1, common, destination, stages, notify, no_cache, oracle_rttm
):
    from meeting_asr.dicow import AUTHOR_COMMIT, recognize_author

    notify("M2", 0.2)
    runtime_manifest = project_path(
        config.get("dicow", {}).get("runtime_manifest", ".cache/dicow/runtime.json")
    )
    key = config_hash(
        {
            "audio": key1,
            "asr": config["asr"],
            "diarization": config["diarization"],
            "dicow": config.get("dicow", {}),
            "author_commit": AUTHOR_COMMIT,
            "runtime_sha256": file_sha256(runtime_manifest) if runtime_manifest.exists() else None,
            "oracle": file_sha256(oracle_rttm) if oracle_rttm else None,
            **common,
            "implementation": 1,
        }
    )
    joint_path = cache / "dicow" / f"{key}.json"
    saved = None
    if not no_cache and joint_path.exists():
        try:
            saved = json.loads(joint_path.read_text())
            diar = DiarizationResult.from_dict(saved["diarization"])
            transcript = read_transcript_json(cache / "dicow" / f"{key}.transcript.json")
        except (OSError, ValueError, KeyError, TypeError):
            saved = None
    hit = saved is not None
    if saved is None:
        diar, utterances, metadata, raw = recognize_author(
            audio,
            config,
            destination,
            oracle_rttm=oracle_rttm,
            progress=notify,
        )
        transcript = TranscriptDocument(
            source.stem,
            audio.duration,
            audio.sr,
            config_hash(config),
            utterances,
        )
        saved = {"diarization": diar.to_dict(), "provenance": metadata, "raw": raw}
        write_transcript_json(cache / "dicow" / f"{key}.transcript.json", transcript)
        _atomic_text(joint_path, json.dumps(saved, ensure_ascii=False))
    if hit:
        notify("M3", 0.4)
    transcript.audio_id = source.stem
    transcript.config_hash = config_hash(config)
    write_rttm(destination / "diarization.rttm", source.stem, diar.segments)
    _atomic_text(destination / "diarsignals.json", json.dumps(diar.to_dict(), ensure_ascii=False))
    write_transcript_json(destination / "transcript.json", transcript)
    _atomic_text(
        destination / "dicow-provenance.json",
        json.dumps(saved["provenance"], ensure_ascii=False, indent=2),
    )
    _atomic_text(
        destination / "dicow-author-output.json",
        json.dumps(saved["raw"], ensure_ascii=False, indent=2),
    )
    stages.extend(
        [
            {"stage": "M2", "cache_hit": hit, "key": key, "backend": diar.backend},
            {"stage": "M3", "cache_hit": hit, "key": key, "engine": "dicow"},
        ]
    )
    return diar, transcript
