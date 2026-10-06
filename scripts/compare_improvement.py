"""Freeze dev-selected settings, then compare one unchanged pilot with baseline.

Reuses a Whisper decoder within a batch of files. Stored raw inference is
resumable; no LLM calls are made. Pilot results are never used for selection.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import yaml

from meeting_asr.asr import WhisperDecoder, transcribe
from meeting_asr.confidence import review_coverage, score_confidence
from meeting_asr.diarization import DiarizationResult, make_backend
from meeting_asr.evaluation.confidence import calibrate_margin, evaluate_confidence
from meeting_asr.evaluation.experiments import experiment_manifest, transcript_scores
from meeting_asr.evaluation.metrics import score_diarization
from meeting_asr.io import (
    _atomic_text,
    read_rttm,
    read_transcript_json,
    write_minutes_json,
    write_rttm,
    write_transcript_json,
)
from meeting_asr.models import MeetingMinutes, TranscriptDocument
from meeting_asr.postprocess import postprocess
from meeting_asr.preprocess import preprocess
from meeting_asr.runtime import file_sha256, set_seed, write_run_manifest
from meeting_asr.settings import config_hash, load_config

OUT = Path("results/improvement-2026-10-02").resolve()
DEV_MANIFEST = Path("data/simulated/dev/sessions.json")
PILOT_MANIFEST = Path("data/simulated/pilot/sessions.json")
BASELINE_ROWS = Path("results/pilot/rows.json")
DRAFT_REFERENCES = Path("results/pilot-annotations-2026-10-02/references/consensus")
CONFIG_PATH = None


def save(path, value):
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def effective_config():
    config = load_config(CONFIG_PATH) if CONFIG_PATH else load_config()
    config["asr"]["batch_size"] = 1
    config["llm"]["enabled"] = False
    return config


def backend_config(base, selection, backend, gap):
    config = copy.deepcopy(base)
    winner = selection["parameters"][backend]
    config["diarization"]["backend"] = backend
    if backend == "pyannote":
        config["diarization"]["clustering_threshold"] = winner["threshold"]
    else:
        config["diarization"]["ecapa"].update(
            cluster_threshold=winner["threshold"], clean_clustering=winner["clean_clustering"]
        )
    config["asr"]["merge_same_speaker_gap"] = gap
    return config


def infer(session, config, destination, decoder, precomputed=None):
    destination.mkdir(parents=True, exist_ok=True)
    raw = destination / "transcript.json"
    if raw.exists() and (destination / "run.json").exists():
        run = json.loads((destination / "run.json").read_text())
        if run.get("audio_sha256") != file_sha256(session["audio"]):
            raise ValueError(f"audio changed for completed run: {destination}")
        if run["config_hash"] != config_hash(config):
            raise ValueError(f"configuration changed for completed run: {destination}")
        document = read_transcript_json(raw)
        diarization = DiarizationResult.from_dict(
            json.loads((destination / "diarsignals.json").read_text())
        )
    else:
        set_seed(config["seed"])
        audio = preprocess(session["audio"], **config["preprocess"])
        diar_path = destination / "diarsignals.json"
        if diar_path.exists():
            diarization = DiarizationResult.from_dict(json.loads(diar_path.read_text()))
        elif precomputed:
            diarization = DiarizationResult.from_dict(json.loads(Path(precomputed).read_text()))
        else:
            backend = make_backend(config["diarization"], device=config["runtime"]["device"])
            options = {
                k: v
                for k, v in config["diarization"].items()
                if k not in {"backend", "model_name", "ecapa"}
            }
            diarization = backend.diarize(audio, **options)
        save(diar_path, diarization.to_dict())
        write_rttm(
            destination / "diarization.rttm", Path(session["audio"]).stem, diarization.segments
        )
        utterances = transcribe(audio, diarization, decoder=decoder, **config["asr"])
        document = TranscriptDocument(
            Path(session["audio"]).stem, audio.duration, audio.sr, config_hash(config), utterances
        )
        write_transcript_json(raw, document)
        write_run_manifest(
            destination / "run.json",
            config=config,
            audio_path=session["audio"],
            result={"precomputed_dev_prediction": precomputed, "llm_enabled": False},
        )
    turns = postprocess(document.utterances, **config["postprocess"])
    minutes = MeetingMinutes(
        document.audio_id,
        document.duration,
        document.num_speakers,
        score_confidence(turns, seed=config["seed"], **config["confidence"]),
    )
    minutes.flagged_ratio = review_coverage(minutes.turns)
    write_minutes_json(destination / "minutes.json", minutes)
    reference = read_transcript_json(session["reference_json"])
    return document, minutes, reference, diarization


def dev():
    base = effective_config()
    save(OUT / "baseline_config.json", base)
    selection = json.loads((OUT / "tuning/selected.json").read_text())
    data = experiment_manifest(DEV_MANIFEST)
    if any(s["split"] != "dev" for s in data["sessions"]):
        raise ValueError("dev selection cannot read test sessions")
    predictions = json.loads((OUT / "tuning/dev_scores.json").read_text())
    decoder = WhisperDecoder(base["asr"]["model_name"], device=base["runtime"]["device"])
    candidates = []
    try:
        # Two complete 9-condition dev conversations determine ASR context.
        for index, session in enumerate(data["sessions"][:18], 1):
            for backend in ("pyannote", "ecapa"):
                winner = selection["parameters"][backend]
                predicted = next(
                    r
                    for r in predictions
                    if r["audio"] == session["audio"]
                    and r["backend"] == backend
                    and r["threshold"] == winner["threshold"]
                    and r["clean_clustering"] == winner["clean_clustering"]
                )
                for gap in (0.0, 0.3):
                    config = backend_config(base, selection, backend, gap)
                    destination = (
                        OUT
                        / "dev"
                        / session["conversation_id"]
                        / session["condition"]
                        / f"{backend}_gap{gap}"
                    )
                    print(
                        f"ASR DEV {index}/18 {backend} gap={gap} {session['condition']}", flush=True
                    )
                    document, _, reference, _ = infer(
                        session, config, destination, decoder, precomputed=predicted["prediction"]
                    )
                    candidates.append(
                        {
                            "conversation_id": session["conversation_id"],
                            "condition": session["condition"],
                            "backend": backend,
                            "gap": gap,
                            **transcript_scores(reference, document),
                        }
                    )
                    save(OUT / "dev_asr_candidates.json", candidates)
        gaps = {}
        aggregates = []
        for backend in ("pyannote", "ecapa"):
            means = {
                gap: float(
                    np.mean(
                        [
                            r["cpwer"]
                            for r in candidates
                            if r["backend"] == backend and r["gap"] == gap
                        ]
                    )
                )
                for gap in (0.0, 0.3)
            }
            gaps[backend] = min(means, key=lambda g: (means[g], g))
            aggregates.append(
                {"backend": backend, "mean_dev_cpwer": means, "selected_gap": gaps[backend]}
            )
        save(OUT / "dev_asr_selection.json", aggregates)
        sessions = []
        for index, session in enumerate(data["sessions"], 1):
            for backend in ("pyannote", "ecapa"):
                winner = selection["parameters"][backend]
                predicted = next(
                    r
                    for r in predictions
                    if r["audio"] == session["audio"]
                    and r["backend"] == backend
                    and r["threshold"] == winner["threshold"]
                    and r["clean_clustering"] == winner["clean_clustering"]
                )
                config = backend_config(base, selection, backend, gaps[backend])
                destination = (
                    OUT
                    / "dev"
                    / session["conversation_id"]
                    / session["condition"]
                    / f"{backend}_gap{gaps[backend]}"
                )
                print(f"CONFIDENCE DEV {index}/30 {backend}", flush=True)
                infer(session, config, destination, decoder, precomputed=predicted["prediction"])
                sessions.append(
                    {**session, "backend": backend, "minutes": str(destination / "minutes.json")}
                )
        save(OUT / "confidence_dev.json", {"split": "dev", "sessions": sessions})
    finally:
        decoder.close()
    calibration = calibrate_margin(
        OUT / "confidence_dev.json",
        OUT / "confidence-calibration.json",
        fit_weights=True,
        trials=128,
    )
    configurations = {}
    for backend in ("pyannote", "ecapa"):
        config = backend_config(base, selection, backend, gaps[backend])
        config["confidence"].update(
            margin_ref=calibration["margin_ref"],
            weights=calibration["weights"],
            calibration_file=str(OUT / "confidence-calibration.json"),
        )
        configurations[backend] = config
        path = OUT / f"optimized-{backend}.yaml"
        _atomic_text(path, yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    save(
        OUT / "frozen.json",
        {
            "selection_split": "dev",
            "configurations": configurations,
            "dev_manifest_sha256": file_sha256(DEV_MANIFEST),
            "confidence_calibration_sha256": file_sha256(OUT / "confidence-calibration.json"),
        },
    )
    print("FROZEN dev-selected configurations", flush=True)


def validate():
    """Reject DER-selected clustering if baseline has better dev cpWER.

    This gate uses the same two dev conversations as ASR context selection.
    No pilot audio or reference is accessed before the configuration is frozen.
    """
    base = effective_config()
    selection = json.loads((OUT / "tuning/selected.json").read_text())
    initial_selection = copy.deepcopy(selection)
    gap_rows = json.loads((OUT / "dev_asr_selection.json").read_text())
    gaps = {r["backend"]: r["selected_gap"] for r in gap_rows}
    data = experiment_manifest(DEV_MANIFEST)
    if any(s["split"] != "dev" for s in data["sessions"]):
        raise ValueError("validation must use dev only")
    predictions = json.loads((OUT / "tuning/dev_scores.json").read_text())
    baseline_selection = {
        "parameters": {
            "pyannote": {"threshold": 0.7045654963945799, "clean_clustering": False},
            "ecapa": {"threshold": 0.7, "clean_clustering": False},
        }
    }
    decoder = WhisperDecoder(base["asr"]["model_name"], device=base["runtime"]["device"])
    baseline_rows, decisions, sessions = [], [], []
    try:
        for index, session in enumerate(data["sessions"][:18], 1):
            for backend in ("pyannote", "ecapa"):
                winner = baseline_selection["parameters"][backend]
                predicted = next(
                    r
                    for r in predictions
                    if r["audio"] == session["audio"]
                    and r["backend"] == backend
                    and r["threshold"] == winner["threshold"]
                    and r["clean_clustering"] == winner["clean_clustering"]
                )
                config = backend_config(base, baseline_selection, backend, 0.0)
                destination = (
                    OUT
                    / "dev"
                    / session["conversation_id"]
                    / session["condition"]
                    / f"{backend}_baseline"
                )
                print(f"VALIDATE DEV {index}/18 {backend}", flush=True)
                document, _, reference, _ = infer(
                    session, config, destination, decoder, precomputed=predicted["prediction"]
                )
                baseline_rows.append(
                    {
                        "backend": backend,
                        "condition": session["condition"],
                        "conversation_id": session["conversation_id"],
                        **transcript_scores(reference, document),
                    }
                )
                save(OUT / "dev_baseline_asr.json", baseline_rows)
        for backend in ("pyannote", "ecapa"):
            baseline_mean = float(
                np.mean([r["cpwer"] for r in baseline_rows if r["backend"] == backend])
            )
            optimized_mean = float(
                next(r for r in gap_rows if r["backend"] == backend)["mean_dev_cpwer"][
                    str(gaps[backend])
                ]
            )
            keep = optimized_mean < baseline_mean
            decisions.append(
                {
                    "backend": backend,
                    "baseline_dev_cpwer": baseline_mean,
                    "candidate_dev_cpwer": optimized_mean,
                    "use_candidate": keep,
                }
            )
            if not keep:
                selection["parameters"][backend] = baseline_selection["parameters"][backend]
                gaps[backend] = 0.0
        save(
            OUT / "dev_validation.json",
            {
                "decisions": decisions,
                "initial_der_selection": initial_selection,
                "final_selection": selection,
                "gaps": gaps,
            },
        )
        for index, session in enumerate(data["sessions"], 1):
            for backend in ("pyannote", "ecapa"):
                winner = selection["parameters"][backend]
                predicted = next(
                    r
                    for r in predictions
                    if r["audio"] == session["audio"]
                    and r["backend"] == backend
                    and r["threshold"] == winner["threshold"]
                    and r["clean_clustering"] == winner["clean_clustering"]
                )
                use_candidate = next(
                    r["use_candidate"] for r in decisions if r["backend"] == backend
                )
                suffix = f"{backend}_gap{gaps[backend]}" if use_candidate else f"{backend}_baseline"
                destination = (
                    OUT / "dev" / session["conversation_id"] / session["condition"] / suffix
                )
                config = backend_config(base, selection, backend, gaps[backend])
                print(f"FINAL CONFIDENCE DEV {index}/30 {backend}", flush=True)
                infer(session, config, destination, decoder, precomputed=predicted["prediction"])
                sessions.append(
                    {**session, "backend": backend, "minutes": str(destination / "minutes.json")}
                )
        save(OUT / "confidence_dev.json", {"split": "dev", "sessions": sessions})
    finally:
        decoder.close()
    calibration = calibrate_margin(
        OUT / "confidence_dev.json",
        OUT / "confidence-calibration.json",
        fit_weights=True,
        trials=128,
    )
    configurations = {}
    for backend in ("pyannote", "ecapa"):
        config = backend_config(base, selection, backend, gaps[backend])
        config["confidence"].update(
            margin_ref=calibration["margin_ref"],
            weights=calibration["weights"],
            calibration_file=str(OUT / "confidence-calibration.json"),
        )
        configurations[backend] = config
        _atomic_text(
            OUT / f"optimized-{backend}.yaml",
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        )
    save(
        OUT / "frozen.json",
        {
            "selection_split": "dev",
            "validated_by": "mean dev cpWER versus baseline on 18 files",
            "configurations": configurations,
            "dev_manifest_sha256": file_sha256(DEV_MANIFEST),
            "confidence_calibration_sha256": file_sha256(OUT / "confidence-calibration.json"),
            "validation_sha256": file_sha256(OUT / "dev_validation.json"),
        },
    )
    print("VALIDATED AND FROZEN", json.dumps(decisions), flush=True)


def pilot():
    frozen_path = OUT / "frozen.json"
    frozen = json.loads(frozen_path.read_text())
    frozen_hash = file_sha256(frozen_path)
    data = experiment_manifest(PILOT_MANIFEST)
    baseline = json.loads(BASELINE_ROWS.read_text())
    config = frozen["configurations"]["pyannote"]
    decoder = WhisperDecoder(config["asr"]["model_name"], device=config["runtime"]["device"])
    rows, confidence = [], []
    try:
        for index, session in enumerate(data["sessions"], 1):
            for backend in ("pyannote", "ecapa"):
                config = frozen["configurations"][backend]
                destination = (
                    OUT / "pilot" / session["conversation_id"] / session["condition"] / backend
                )
                print(f"PILOT {index}/18 {backend} {session['condition']}", flush=True)
                document, minutes, reference, _ = infer(session, config, destination, decoder)
                prior = next(
                    r
                    for r in baseline
                    if r["audio"] == session["audio"] and r["backend"] == backend
                )
                scores = transcript_scores(reference, document)
                original_truth = read_rttm(session["reference_rttm"])
                row = {
                    **session,
                    "backend": backend,
                    **scores,
                    "before_wer": prior["wer"],
                    "before_cpwer": prior["cpwer"],
                    "before_relaxed_der": prior["relaxed_der"],
                    "before_strict_der": prior["strict_der"],
                    "prediction_dir": str(destination),
                    "config_hash": config_hash(config),
                    "speakers": document.num_speakers,
                }
                scored_segments = read_rttm(destination / "diarization.rttm")
                for label, score in score_diarization(original_truth, scored_segments).items():
                    row.update({f"{label}_{k}": v for k, v in asdict(score).items()})
                # Same draft labels for old and new predictions, reported separately.
                draft = DRAFT_REFERENCES / Path(session["reference_rttm"]).name
                proposed_truth = read_rttm(draft)
                previous_segments = read_rttm(Path(prior["prediction_dir"]) / "diarization.rttm")
                row["draft_before_strict_der"] = score_diarization(
                    proposed_truth, previous_segments
                )["strict"].der
                row["draft_after_strict_der"] = score_diarization(proposed_truth, scored_segments)[
                    "strict"
                ].der
                rows.append(row)
                save(OUT / "pilot_rows.json", rows)
                score = evaluate_confidence(
                    minutes, reference, config["confidence"], seed=config["seed"]
                )
                uncalibrated = evaluate_confidence(
                    minutes, reference, effective_config()["confidence"], seed=config["seed"]
                )
                confidence.append(
                    {
                        "session": {**session, "backend": backend},
                        "scores": score,
                        "uncalibrated_scores": uncalibrated,
                    }
                )
                save(OUT / "confidence_test.json", confidence)
                print(
                    f"  WER {prior['wer']:.3f}->{scores['wer']:.3f} "
                    f"cpWER {prior['cpwer']:.3f}->{scores['cpwer']:.3f}",
                    flush=True,
                )
    finally:
        decoder.close()
    if file_sha256(frozen_path) != frozen_hash:
        raise RuntimeError("frozen parameters changed during pilot evaluation")
    fields = sorted({key for row in rows for key in row})
    with (OUT / "pilot_comparison.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    aggregates = {}
    for backend in ("pyannote", "ecapa"):
        subset = [r for r in rows if r["backend"] == backend]
        aggregates[backend] = {
            key: float(np.mean([r[key] for r in subset]))
            for key in (
                "wer",
                "cpwer",
                "before_wer",
                "before_cpwer",
                "relaxed_der",
                "strict_der",
                "before_relaxed_der",
                "before_strict_der",
                "draft_before_strict_der",
                "draft_after_strict_der",
            )
        }
    save(
        OUT / "pilot_summary.json",
        {
            "sessions": 18,
            "original_conversations": 2,
            "frozen_configuration_sha256": frozen_hash,
            "metrics": aggregates,
        },
    )
    print("PILOT COMPLETE", json.dumps(aggregates), flush=True)


def context_dev():
    """A separate controlled intervention: keep baseline speaker clustering.

    The broader DER-selected approach is retained, including regressions.
    Here the only ASR candidate is joining fragments with a 0.3 second gap.
    """
    out = OUT / "context-only"
    base = effective_config()
    data = experiment_manifest(DEV_MANIFEST)
    if any(s["split"] != "dev" for s in data["sessions"]):
        raise ValueError("context selection must use dev only")
    selection = {
        "parameters": {
            "pyannote": {"threshold": 0.7045654963945799, "clean_clustering": False},
            "ecapa": {"threshold": 0.7, "clean_clustering": False},
        }
    }
    predictions = json.loads((OUT / "tuning/dev_scores.json").read_text())
    decoder = WhisperDecoder(base["asr"]["model_name"], device=base["runtime"]["device"])
    candidates, sessions = [], []
    try:
        for index, session in enumerate(data["sessions"][:18], 1):
            predicted = next(
                r
                for r in predictions
                if r["audio"] == session["audio"]
                and r["backend"] == "ecapa"
                and r["threshold"] == 0.7
                and not r["clean_clustering"]
            )
            for gap in (0.0, 0.3):
                config = backend_config(base, selection, "ecapa", gap)
                destination = (
                    (
                        OUT
                        / "dev"
                        / session["conversation_id"]
                        / session["condition"]
                        / "ecapa_baseline"
                    )
                    if gap == 0
                    else (
                        out
                        / "dev"
                        / session["conversation_id"]
                        / session["condition"]
                        / "ecapa_gap0.3"
                    )
                )
                print(f"CONTEXT DEV {index}/18 gap={gap}", flush=True)
                document, _, reference, _ = infer(
                    session, config, destination, decoder, precomputed=predicted["prediction"]
                )
                candidates.append(
                    {
                        "backend": "ecapa",
                        "gap": gap,
                        "condition": session["condition"],
                        "conversation_id": session["conversation_id"],
                        **transcript_scores(reference, document),
                    }
                )
                save(out / "dev_asr_candidates.json", candidates)
        means = {
            gap: float(np.mean([r["cpwer"] for r in candidates if r["gap"] == gap]))
            for gap in (0.0, 0.3)
        }
        gap = min(means, key=lambda g: (means[g], g))
        save(
            out / "dev_validation.json",
            {
                "protocol": "baseline clustering; ASR context only",
                "decisions": [
                    {
                        "backend": "ecapa",
                        "baseline_dev_cpwer": means[0.0],
                        "candidate_dev_cpwer": means[0.3],
                        "use_candidate": gap > 0,
                    }
                ],
                "gaps": {"ecapa": gap, "pyannote": 0.0},
                "final_selection": selection,
            },
        )
        for index, session in enumerate(data["sessions"], 1):
            predicted = next(
                r
                for r in predictions
                if r["audio"] == session["audio"]
                and r["backend"] == "ecapa"
                and r["threshold"] == 0.7
                and not r["clean_clustering"]
            )
            destination = (
                (OUT / "dev" / session["conversation_id"] / session["condition"] / "ecapa_baseline")
                if gap == 0
                else (
                    out / "dev" / session["conversation_id"] / session["condition"] / "ecapa_gap0.3"
                )
            )
            print(f"CONTEXT CONFIDENCE DEV {index}/30", flush=True)
            infer(
                session,
                backend_config(base, selection, "ecapa", gap),
                destination,
                decoder,
                precomputed=predicted["prediction"],
            )
            sessions.append(
                {**session, "backend": "ecapa", "minutes": str(destination / "minutes.json")}
            )
        save(out / "confidence_dev.json", {"split": "dev", "sessions": sessions})
    finally:
        decoder.close()
    calibration = calibrate_margin(
        out / "confidence_dev.json",
        out / "confidence-calibration.json",
        fit_weights=True,
        trials=128,
    )
    configurations = {}
    for backend in ("pyannote", "ecapa"):
        config = backend_config(base, selection, backend, gap if backend == "ecapa" else 0.0)
        config["confidence"].update(
            margin_ref=calibration["margin_ref"],
            weights=calibration["weights"],
            calibration_file=str(out / "confidence-calibration.json"),
        )
        configurations[backend] = config
        _atomic_text(
            out / f"optimized-{backend}.yaml",
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        )
    save(
        out / "frozen.json",
        {
            "protocol": "context-only",
            "selection_split": "dev",
            "confidence_sessions": 30,
            "configurations": configurations,
            "dev_manifest_sha256": file_sha256(DEV_MANIFEST),
            "validation_sha256": file_sha256(out / "dev_validation.json"),
            "confidence_calibration_sha256": file_sha256(out / "confidence-calibration.json"),
        },
    )
    for name in ("input_audit.json", "pilot-draft-speech-context.json"):
        _atomic_text(out / name, (OUT / name).read_text())
    print("CONTEXT FROZEN", json.dumps(means), "gap", gap, flush=True)


def context_pilot():
    out = OUT / "context-only"
    frozen_path = out / "frozen.json"
    frozen = json.loads(frozen_path.read_text())
    frozen_hash = file_sha256(frozen_path)
    data = experiment_manifest(PILOT_MANIFEST)
    baseline = json.loads(BASELINE_ROWS.read_text())
    config = frozen["configurations"]["ecapa"]
    decoder = WhisperDecoder(config["asr"]["model_name"], device=config["runtime"]["device"])
    rows, confidence = [], []
    try:
        for index, session in enumerate(data["sessions"], 1):
            for backend in ("pyannote", "ecapa"):
                config = frozen["configurations"][backend]
                prior = next(
                    r
                    for r in baseline
                    if r["audio"] == session["audio"] and r["backend"] == backend
                )
                previous = Path(prior["prediction_dir"])
                destination = (
                    out / "pilot" / session["conversation_id"] / session["condition"] / backend
                )
                print(f"CONTEXT PILOT {index}/18 {backend}", flush=True)
                if backend == "ecapa":
                    document, minutes, reference, diarization = infer(
                        session,
                        config,
                        destination,
                        decoder,
                        precomputed=str(previous / "diarsignals.json"),
                    )
                else:
                    destination.mkdir(parents=True, exist_ok=True)
                    document = replace(
                        read_transcript_json(previous / "transcript.json"),
                        config_hash=config_hash(config),
                    )
                    diarization = DiarizationResult.from_dict(
                        json.loads((previous / "diarsignals.json").read_text())
                    )
                    reference = read_transcript_json(session["reference_json"])
                    turns = score_confidence(
                        postprocess(document.utterances, **config["postprocess"]),
                        seed=config["seed"],
                        **config["confidence"],
                    )
                    minutes = MeetingMinutes(
                        document.audio_id,
                        document.duration,
                        document.num_speakers,
                        turns,
                        review_coverage(turns),
                    )
                    write_transcript_json(destination / "transcript.json", document)
                    write_minutes_json(destination / "minutes.json", minutes)
                    save(destination / "diarsignals.json", diarization.to_dict())
                    write_rttm(
                        destination / "diarization.rttm",
                        Path(session["audio"]).stem,
                        diarization.segments,
                    )
                    write_run_manifest(
                        destination / "run.json",
                        config=config,
                        audio_path=session["audio"],
                        result={
                            "reused_baseline_asr": str(previous / "transcript.json"),
                            "llm_enabled": False,
                        },
                    )
                scores = transcript_scores(reference, document)
                row = {
                    **session,
                    "backend": backend,
                    **scores,
                    **{
                        f"before_{k}": prior[k]
                        for k in ("wer", "cpwer", "relaxed_der", "strict_der")
                    },
                    "prediction_dir": str(destination),
                    "speakers": document.num_speakers,
                    "config_hash": config_hash(config),
                    "reused_baseline_diarization": True,
                    "reused_baseline_asr": backend == "pyannote",
                }
                if backend == "pyannote":
                    assert abs(scores["wer"] - prior["wer"]) < 1e-8
                    assert abs(scores["cpwer"] - prior["cpwer"]) < 1e-8
                original_truth = read_rttm(session["reference_rttm"])
                scored_segments = read_rttm(destination / "diarization.rttm")
                for label, score in score_diarization(original_truth, scored_segments).items():
                    row.update({f"{label}_{k}": v for k, v in asdict(score).items()})
                assert abs(row["strict_der"] - row["before_strict_der"]) < 1e-8
                draft = DRAFT_REFERENCES / Path(session["reference_rttm"]).name
                draft_der = score_diarization(read_rttm(draft), scored_segments)["strict"].der
                row.update(draft_before_strict_der=draft_der, draft_after_strict_der=draft_der)
                rows.append(row)
                save(out / "pilot_rows.json", rows)
                confidence.append(
                    {
                        "session": {**session, "backend": backend},
                        "scores": evaluate_confidence(
                            minutes, reference, config["confidence"], seed=config["seed"]
                        ),
                        "uncalibrated_scores": evaluate_confidence(
                            minutes,
                            reference,
                            effective_config()["confidence"],
                            seed=config["seed"],
                        ),
                    }
                )
                save(out / "confidence_test.json", confidence)
                print(
                    f"  WER {prior['wer']:.3f}->{scores['wer']:.3f} cpWER {prior['cpwer']:.3f}->{scores['cpwer']:.3f}",
                    flush=True,
                )
    finally:
        decoder.close()
    assert file_sha256(frozen_path) == frozen_hash
    with (out / "pilot_comparison.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted({key for r in rows for key in r}))
        writer.writeheader()
        writer.writerows(rows)
    metrics = {
        backend: {
            key: float(np.mean([r[key] for r in rows if r["backend"] == backend]))
            for key in (
                "wer",
                "cpwer",
                "before_wer",
                "before_cpwer",
                "relaxed_der",
                "strict_der",
                "before_relaxed_der",
                "before_strict_der",
                "draft_before_strict_der",
                "draft_after_strict_der",
            )
        }
        for backend in ("pyannote", "ecapa")
    }
    save(
        out / "pilot_summary.json",
        {
            "sessions": 18,
            "original_conversations": 2,
            "protocol": "context-only",
            "note": "Diarization cached from baseline for both backends; ECAPA ASR rerun, pyannote ASR cached. Confidence re-evaluated for both.",
            "frozen_configuration_sha256": frozen_hash,
            "metrics": metrics,
        },
    )
    print("CONTEXT PILOT COMPLETE", json.dumps(metrics), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    phases = {
        "dev": dev,
        "validate": validate,
        "pilot": pilot,
        "context-dev": context_dev,
        "context-pilot": context_pilot,
    }
    parser.add_argument("phase", choices=tuple(phases))
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--dev-manifest", type=Path, default=DEV_MANIFEST)
    parser.add_argument("--pilot-manifest", type=Path, default=PILOT_MANIFEST)
    parser.add_argument("--baseline-rows", type=Path, default=BASELINE_ROWS)
    parser.add_argument("--draft-references", type=Path, default=DRAFT_REFERENCES)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    OUT, DEV_MANIFEST, PILOT_MANIFEST = (
        args.out.resolve(),
        args.dev_manifest.resolve(),
        args.pilot_manifest.resolve(),
    )
    BASELINE_ROWS, DRAFT_REFERENCES, CONFIG_PATH = (
        args.baseline_rows.resolve(),
        args.draft_references.resolve(),
        args.config,
    )
    phases[args.phase]()
