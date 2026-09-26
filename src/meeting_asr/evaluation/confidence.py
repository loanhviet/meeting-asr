"""Turn error labels, duration-budget risk curves, ablation, and dev-only calibration."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.integrate import trapezoid

from meeting_asr.confidence import DEFAULT_WEIGHTS, VARIANTS, score_confidence, select_review
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
            trapezoid([p["remaining_wer"] for p in curve], [p["requested_coverage"] for p in curve])
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
        "true_positives": tp,
        "false_positives": len(selected - positives),
        "false_negatives": len(positives - selected),
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


def calibrate_margin(manifest, out, percentile=90, fit_weights=False, trials=64, seed=42):
    if not 0 <= percentile <= 100 or trials < 1:
        raise ValueError("invalid percentile or calibration trials")
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
    if fit_weights:
        examples = []
        for session in payload["sessions"]:
            minutes = minutes_from_dict(json.loads((base / session["minutes"]).read_text()))
            reference = read_transcript_json(base / session["reference_json"])
            labels, _ = label_turns(minutes.turns, reference)
            examples.append((minutes.turns, {label.turn_id for label in labels if label.is_bad}))
        keys = list(DEFAULT_WEIGHTS)
        rng = np.random.default_rng(seed)
        candidates = [DEFAULT_WEIGHTS] + [
            dict(zip(keys, row.tolist(), strict=True))
            for row in rng.dirichlet(np.ones(len(keys)), size=trials)
        ]
        best, best_f1 = DEFAULT_WEIGHTS, -1.0
        for weights in candidates:
            f1s = []
            for turns, positives in examples:
                scored = score_confidence(turns, weights=weights, margin_ref=result["margin_ref"])
                chosen = {t.turn_id for t in scored if t.flagged}
                tp = len(chosen & positives)
                f1s.append(2 * tp / (len(chosen) + len(positives)) if chosen or positives else 0)
            mean_f1 = float(np.mean(f1s))
            if mean_f1 > best_f1:
                best, best_f1 = weights, mean_f1
        result.update(
            weights=best,
            dev_mean_f1=best_f1,
            seed=seed,
            trials=trials,
            error_threshold=0.3,
            target_coverage=0.2,
        )
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
    rows = []
    for result in results:
        session = result["session"]
        for threshold, score in result["scores"].items():
            for variant, metrics in score["variants"].items():
                rows.append(
                    {
                        "conversation_id": session.get("conversation_id"),
                        "condition": session.get("condition"),
                        "backend": session.get("backend"),
                        "threshold": threshold,
                        "variant": variant,
                        "missed_speech_ratio": score["missed_speech_ratio"],
                        **{k: v for k, v in metrics.items() if k != "curve"},
                    }
                )
    with (destination / "rq3.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
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
