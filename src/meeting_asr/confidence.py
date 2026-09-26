"""Explainable confidence and a deterministic budget in predicted speaker-time."""

from __future__ import annotations

import copy
import math
import random

from meeting_asr.models import Turn, Utterance

DEFAULT_WEIGHTS = {"asr": 0.3, "speech": 0.1, "rep": 0.1, "ovl": 0.25, "spk": 0.15, "dur": 0.1}
VARIANTS = ("baseline_random", "baseline_asr_only", "no_diar", "full")
BLACKLIST = (
    "cảm ơn các bạn đã xem",
    "hãy đăng ký kênh",
    "phụ đề được thực hiện bởi",
    "hẹn gặp lại các bạn",
)
REASONS = {
    "asr": "độ tin cậy ASR thấp",
    "speech": "nghi không có tiếng nói",
    "rep": "nghi lặp/ảo giác",
    "spk": "khó phân biệt người nói",
    "dur": "đoạn quá ngắn",
}


def clip(value):
    return max(0.0, min(1.0, value))


def normalized_signals(utterance: Utterance, margin_ref=None) -> dict:
    asr, diar = utterance.asr, utterance.diar
    return {
        "asr": clip((asr.avg_logprob + 1) / 0.9) if asr.avg_logprob is not None else None,
        "speech": clip(1 - asr.no_speech_prob) if asr.no_speech_prob is not None else None,
        "rep": min(1.0, 2.4 / asr.compression_ratio)
        if asr.compression_ratio
        else (1.0 if asr.compression_ratio == 0 else None),
        "ovl": 1 - diar.overlap_ratio if diar else None,
        "spk": clip(diar.cluster_margin / margin_ref)
        if diar and diar.cluster_margin is not None and margin_ref
        else None,
        "dur": clip(utterance.duration / 1.5),
    }


def select_review(turns: list[Turn], target_coverage=0.2) -> set[str]:
    if not math.isfinite(target_coverage) or not 0 <= target_coverage <= 1:
        raise ValueError("target_coverage must be in [0, 1]")
    budget = target_coverage * sum(t.end - t.start for t in turns)
    chosen = set()
    for turn in sorted(
        turns, key=lambda t: (t.confidence if t.confidence is not None else 0.5, t.turn_id)
    ):
        duration = turn.end - turn.start
        if duration <= 0:
            raise ValueError("turn duration must be positive")
        if duration <= budget + 1e-9:
            chosen.add(turn.turn_id)
            budget -= duration
    return chosen


def score_confidence(
    turns: list[Turn],
    weights=None,
    target_coverage=0.2,
    variant="full",
    margin_ref=None,
    seed=42,
    **unused,
) -> list[Turn]:
    if variant not in VARIANTS:
        raise ValueError(f"unknown confidence variant: {variant}")
    weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
    if (
        set(weights) - set(DEFAULT_WEIGHTS)
        or any(not math.isfinite(v) or v < 0 for v in weights.values())
        or sum(weights.values()) <= 0
    ):
        raise ValueError("confidence weights must be finite, nonnegative and have positive sum")
    if margin_ref is not None and (not math.isfinite(margin_ref) or margin_ref <= 0):
        raise ValueError("margin_ref must be positive; calibrate on dev only")
    if variant == "baseline_asr_only":
        weights = {"asr": 1.0}
    elif variant == "no_diar":
        weights = {k: v for k, v in weights.items() if k not in {"ovl", "spk"}}
    result = copy.deepcopy(turns)
    rng = random.Random(seed)
    for turn in result:
        available = {}
        for key in weights:
            signals = [
                (normalized_signals(u, margin_ref)[key], u.duration) for u in turn.utterances
            ]
            signals = [(v, d) for v, d in signals if v is not None]
            if signals:
                available[key] = sum(v * d for v, d in signals) / sum(d for _, d in signals)
        total = sum(weights[k] for k in available)
        turn.confidence = (
            sum(weights[k] * v for k, v in available.items()) / total if total else 0.5
        )
        turn.flag_reasons = []
        for key, value in available.items():
            if value < 0.5:
                turn.flag_reasons.append(
                    f"chồng lấn {1 - value:.0%}" if key == "ovl" else REASONS[key]
                )
        if not total:
            turn.flag_reasons.append("không có tín hiệu tin cậy khả dụng")
        if variant == "full" and any(
            phrase in " ".join(u.text.casefold() for u in turn.utterances) for phrase in BLACKLIST
        ):
            turn.confidence = min(turn.confidence, 0.05)
            turn.flag_reasons.append("hallucination_blacklist")
        if variant == "baseline_random":
            turn.confidence = rng.random()
            turn.flag_reasons = ["chọn ngẫu nhiên để đối chiếu"]
    selected = select_review(result, target_coverage)
    for turn in result:
        turn.flagged = turn.turn_id in selected
    return result


def review_coverage(turns: list[Turn]) -> float:
    duration = sum(t.end - t.start for t in turns)
    return sum(t.end - t.start for t in turns if t.flagged) / duration if duration else 0.0
