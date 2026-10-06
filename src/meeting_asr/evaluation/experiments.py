"""RQ1/RQ2 execution and paired bootstrap over original conversations."""

from __future__ import annotations

import copy
import csv
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from meeting_asr.evaluation.detection import overlap_detection_score, overlap_regions
from meeting_asr.evaluation.log import append_experiment_rows
from meeting_asr.evaluation.metrics import (
    cp_word_error_rate,
    diarization_error_rate,
    normalize_for_wer,
    word_error_rate,
)
from meeting_asr.io import _atomic_text, read_rttm, read_transcript_json
from meeting_asr.pipeline import run_pipeline
from meeting_asr.runtime import git_commit
from meeting_asr.settings import config_hash


def speaker_text(utterances):
    groups = defaultdict(list)
    for utterance in sorted(utterances, key=lambda u: (u.start, u.end, u.speaker)):
        groups[utterance.speaker].append(utterance.text)
    return {speaker: " ".join(texts) for speaker, texts in groups.items()}


def transcript_scores(reference, hypothesis):
    refs = sorted(reference.utterances, key=lambda u: (u.start, u.end, u.speaker))
    hyps = sorted(hypothesis.utterances, key=lambda u: (u.start, u.end, u.speaker))
    return {
        "wer": word_error_rate(" ".join(u.text for u in refs), " ".join(u.text for u in hyps)),
        "cpwer": cp_word_error_rate(speaker_text(refs), speaker_text(hyps)),
        "reference_words": sum(len(normalize_for_wer(u.text).split()) for u in refs),
    }


def paired_bootstrap(rows, field="delta_cpwer", seed=42, repetitions=2000):
    groups = defaultdict(list)
    for row in rows:
        if row.get(field) is not None:
            groups[row["conversation_id"]].append(row[field])
    if not groups:
        return {"mean": None, "ci_low": None, "ci_high": None, "conversations": 0}
    values = np.array([np.mean(v) for _, v in sorted(groups.items())])
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(repetitions, len(values)), replace=True).mean(axis=1)
    return {
        "mean": float(values.mean()),
        "ci_low": float(np.quantile(samples, 0.025)),
        "ci_high": float(np.quantile(samples, 0.975)),
        "conversations": len(values),
    }


def experiment_manifest(path):
    path = Path(path).resolve()
    payload = json.loads(path.read_text())
    if not payload.get("sessions"):
        raise ValueError("experiment manifest requires nonempty sessions")
    seen = set()
    for session in payload["sessions"]:
        for field in (
            "audio",
            "reference_json",
            "reference_rttm",
            "condition",
            "conversation_id",
            "split",
        ):
            if not session.get(field):
                raise ValueError(f"session requires {field}")
        identity = (session["conversation_id"], session["condition"])
        if identity in seen:
            raise ValueError(f"duplicate experiment session: {identity}")
        seen.add(identity)
        for field in ("audio", "reference_json", "reference_rttm"):
            session[field] = str((path.parent / session[field]).resolve())
        if session.get("oracle_rttm"):
            session["oracle_rttm"] = str((path.parent / session["oracle_rttm"]).resolve())
    return payload


def _prediction_rtf(prediction_dir):
    try:
        payload = json.loads((Path(prediction_dir) / "run.json").read_text())
        return payload["result"]["rtf"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def experiment_log_rows(rows, config, created=None, commit=None):
    """One spec log row per cascaded session. Miss, FA and confusion are relaxed."""
    stamp = created or datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    recorded = commit if commit is not None else git_commit()
    logged = []
    for index, row in enumerate(rows):
        logged.append(
            {
                "run_id": f"{stamp}_{index:03d}",
                "git_commit": recorded,
                "config_hash": row.get("config_hash"),
                "dataset": row.get("condition"),
                "diar_backend": row.get("backend"),
                "masking": config["asr"].get("masking", "none"),
                "der_lenient": row.get("relaxed_der"),
                "der_strict": row.get("strict_der"),
                "miss": row.get("relaxed_miss"),
                "fa": row.get("relaxed_false_alarm"),
                "confusion": row.get("relaxed_confusion"),
                "wer": row.get("wer"),
                "cpwer_oracle": row.get("oracle_cpwer"),
                "cpwer_cascaded": row.get("cpwer"),
                "rtf": _prediction_rtf(row["prediction_dir"])
                if row.get("prediction_dir")
                else None,
                "notes": (f"conversation={row.get('conversation_id')}; miss/fa/confusion=relaxed"),
            }
        )
    return logged


def run_experiments(manifest, config, out, backends=("pyannote", "ecapa"), log_path=None):
    if config["asr"].get("masking", "none") != "none":
        raise ValueError("RQ2 requires masking=none for oracle and cascaded")
    payload = experiment_manifest(manifest)
    destination = Path(out)
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    for session in payload["sessions"]:
        reference = read_transcript_json(session["reference_json"])
        truth = read_rttm(session["reference_rttm"])
        session_dir = destination / config_hash(session)
        options = copy.deepcopy(config)
        options["llm"]["enabled"] = False
        oracle_dir = session_dir / "oracle"
        run_pipeline(
            session["audio"],
            options,
            oracle_dir,
            oracle_rttm=session.get("oracle_rttm", session["reference_rttm"]),
        )
        oracle = read_transcript_json(oracle_dir / "transcript.json")
        oracle_score = transcript_scores(reference, oracle)
        for backend in backends:
            options["diarization"]["backend"] = backend
            predicted_dir = session_dir / backend
            run_pipeline(session["audio"], options, predicted_dir)
            transcript = read_transcript_json(predicted_dir / "transcript.json")
            predicted = read_rttm(predicted_dir / "diarization.rttm")
            row = {
                **session,
                "backend": backend,
                **transcript_scores(reference, transcript),
                "prediction_dir": str(predicted_dir.resolve()),
                "oracle_cpwer": oracle_score["cpwer"],
                "config_hash": config_hash(options),
            }
            signals = json.loads((predicted_dir / "diarsignals.json").read_text())
            regions = signals.get("overlap_regions")
            row.update(
                overlap_detection_score(
                    truth, regions if regions is not None else overlap_regions(predicted)
                )
            )
            for label, collar, skip in (("relaxed", 0.25, True), ("strict", 0.0, False)):
                try:
                    score = diarization_error_rate(
                        truth, predicted, collar=collar, skip_overlap=skip
                    )
                    for key, value in asdict(score).items():
                        row[f"{label}_{key}"] = value
                except ValueError as exc:
                    if "reference speech duration is zero" not in str(exc):
                        raise
                    row[f"{label}_der"] = None
                    row[f"{label}_undefined_reason"] = "no reference speech in scoring region"
            row["delta_cpwer"] = row["cpwer"] - row["oracle_cpwer"]
            row["relative_gap"] = row["delta_cpwer"] / row["cpwer"] if row["cpwer"] else None
            rows.append(row)
            _atomic_text(destination / "rows.json", json.dumps(rows, ensure_ascii=False, indent=2))
    fields = sorted({key for row in rows for key in row})
    with (destination / "rq1_rq2.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        backend: paired_bootstrap([r for r in rows if r["backend"] == backend], seed=config["seed"])
        for backend in backends
    }
    _atomic_text(destination / "paired_summary.json", json.dumps(summary, indent=2))
    for split in {row["split"] for row in rows}:
        sessions = [
            {**row, "minutes": str(Path(row["prediction_dir"]) / "minutes.json")}
            for row in rows
            if row["split"] == split
        ]
        _atomic_text(
            destination / f"confidence_{split}.json",
            json.dumps(
                {
                    "split": split,
                    "sessions": sessions,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    append_experiment_rows(experiment_log_rows(rows, config), log_path)
    return rows
