"""Turn error labels, duration-budget risk curves, ablation, and dev-only calibration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from meeting_asr.confidence import VARIANTS, score_confidence, select_review
from meeting_asr.evaluation.metrics import _annotation, _word_errors, normalize_for_wer
from meeting_asr.io import _atomic_text, minutes_from_dict, read_transcript_json
from meeting_asr.models import Turn


@dataclass
class TurnError:
    turn_id: str
    errors: int
    reference_words: int
    wer: float
    is_bad: bool


def label_turns(turns, reference, threshold=0.3):
    from pyannote.metrics.matcher import HungarianMapper

    mapping = HungarianMapper()(
        _annotation([u for t in turns for u in t.utterances]), _annotation(reference.utterances)
    )
    labels = []
    for turn in turns:
        speaker = mapping.get(turn.speaker)
        matched = [
            u
            for u in sorted(reference.utterances, key=lambda u: u.start)
            if u.speaker == speaker and u.start < turn.end and u.end > turn.start
        ]
        ref = normalize_for_wer(" ".join(u.text for u in matched))
        hyp = normalize_for_wer(" ".join(u.text for u in turn.utterances))
        errors, words = _word_errors(ref, hyp)
        wer = errors / words if words else (1.0 if hyp else 0.0)
        labels.append(
            TurnError(
                turn.turn_id, errors, words, wer, not matched or speaker is None or wer > threshold
            )
        )
    # Speech with no predicted turn of any speaker has no reviewable row.
    missed_duration = 0.0
    for utterance in reference.utterances:
        intervals = sorted(
            (max(utterance.start, t.start), min(utterance.end, t.end))
            for t in turns
            if t.start < utterance.end and t.end > utterance.start
        )
        covered, cursor = 0.0, utterance.start
        for start, end in intervals:
            covered += max(0, end - max(cursor, start))
            cursor = max(cursor, end)
        missed_duration += max(0, utterance.duration - covered)
    total = sum(u.duration for u in reference.utterances)
    return labels, missed_duration / total if total else 0.0


def variant_metrics(turns: list[Turn], labels: list[TurnError], coverage=0.2):
    by_id = {label.turn_id: label for label in labels}
    selected = select_review(turns, coverage)
    positives = {label.turn_id for label in labels if label.is_bad}
    tp = len(selected & positives)
    precision = tp / len(selected) if selected else 0.0
    recall = tp / len(positives) if positives else 0.0
    denominator = sum(label.reference_words for label in labels)
    total_duration = sum(t.end - t.start for t in turns)

    # False alarm words contribute errors but cannot disappear through denominator changes.
    def risk(chosen):
        return (
            sum(label.errors for label in labels if label.turn_id not in chosen) / denominator
            if denominator
            else None
        )

    curve = []
    for requested in np.linspace(0, 1, 101):
        chosen = select_review(turns, float(requested))
        actual = (
            sum(t.end - t.start for t in turns if t.turn_id in chosen) / total_duration
            if total_duration
            else 0.0
        )
        curve.append(
            {
                "requested_coverage": float(requested),
                "actual_coverage": actual,
                "remaining_wer": risk(chosen),
            }
        )
    # Area uses the declared budget axis because whole-turn selection can underfill it.
    auc = (
        float(
            np.trapezoid(
                [p["remaining_wer"] for p in curve], [p["requested_coverage"] for p in curve]
            )
        )
        if denominator
        else None
    )
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "auc": auc,
        "remaining_wer": risk(selected),
        "actual_coverage": sum(t.end - t.start for t in turns if t.turn_id in selected)
        / total_duration
        if total_duration
        else 0.0,
        "curve": curve,
        "reference_words": denominator,
        "labelled_turns": len(by_id),
    }


def evaluate_confidence(minutes, reference, options, seed=42, thresholds=(0.2, 0.3, 0.5)):
    result = {}
    for threshold in thresholds:
        labels, missed = label_turns(minutes.turns, reference, threshold)
        variants = {}
        for variant in VARIANTS:
            config = {**options, "variant": variant, "seed": seed}
            scored = score_confidence(minutes.turns, **config)
            variants[variant] = variant_metrics(scored, labels, options.get("target_coverage", 0.2))
        result[str(threshold)] = {"missed_speech_ratio": missed, "variants": variants}
    return result


def calibrate_margin(manifest, out, percentile=90):
    payload = json.loads(Path(manifest).read_text())
    if payload.get("split") != "dev" or not payload.get("sessions"):
        raise ValueError("calibration requires an explicitly labelled dev manifest")
    base = Path(manifest).resolve().parent
    values = []
    for session in payload["sessions"]:
        if session.get("split") != "dev":
            raise ValueError("calibration cannot include test sessions")
        minutes = minutes_from_dict(json.loads((base / session["minutes"]).read_text()))
        values.extend(
            u.diar.cluster_margin
            for t in minutes.turns
            for u in t.utterances
            if u.diar and u.diar.cluster_margin is not None
        )
    positive = [v for v in values if np.isfinite(v) and v > 0]
    if not positive:
        raise ValueError("dev predictions have no positive ECAPA cluster margins")
    result = {
        "margin_ref": float(np.percentile(positive, percentile)),
        "percentile": percentile,
        "split": "dev",
        "source_manifest": str(Path(manifest).resolve()),
        "observations": len(positive),
    }
    _atomic_text(out, json.dumps(result, indent=2))
    return result


def run_confidence_evaluation(manifest, config, out):
    path = Path(manifest).resolve()
    payload = json.loads(path.read_text())
    if not payload.get("sessions"):
        raise ValueError("requires sessions containing minutes, reference_json and split")
    results = []
    for session in payload["sessions"]:
        minutes = minutes_from_dict(json.loads((path.parent / session["minutes"]).read_text()))
        reference = read_transcript_json(path.parent / session["reference_json"])
        result = evaluate_confidence(
            minutes,
            reference,
            config["confidence"],
            config["seed"],
            config["evaluation"]["turn_wer_threshold"],
        )
        results.append({"session": session, "scores": result})
    destination = Path(out)
    destination.mkdir(parents=True, exist_ok=True)
    _atomic_text(destination / "rq3.json", json.dumps(results, ensure_ascii=False, indent=2))
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    for index, result in enumerate(results):
        for threshold, scores in result["scores"].items():
            fig, ax = plt.subplots(figsize=(6, 4))
            for variant, metrics in scores["variants"].items():
                curve = metrics["curve"]
                ax.plot(
                    [p["requested_coverage"] for p in curve],
                    [p["remaining_wer"] for p in curve],
                    label=variant,
                )
            ax.set(
                xlabel="Review budget (predicted speaker-time)",
                ylabel="Remaining turn WER",
                title=f"Session {index + 1}; error threshold {threshold}",
            )
            ax.legend()
            fig.tight_layout()
            fig.savefig(destination / f"risk_coverage_{index:03d}_{threshold}.png", dpi=160)
            plt.close(fig)
    return results
