"""Time-based overlap detector precision/recall independent of speaker assignment."""

from __future__ import annotations

from itertools import pairwise


def overlap_regions(segments):
    times = sorted({t for s in segments for t in (s.start, s.end)})
    return [
        (a, b)
        for a, b in pairwise(times)
        if len({s.speaker for s in segments if s.start < b and s.end > a}) >= 2
    ]


def overlap_detection_score(reference, predicted_regions):
    truth = overlap_regions(reference)
    times = sorted({t for region in truth + list(predicted_regions) for t in region})
    actual, predicted, intersection = 0.0, 0.0, 0.0
    for a, b in pairwise(times):
        ref = any(x < b and y > a for x, y in truth)
        hyp = any(x < b and y > a for x, y in predicted_regions)
        actual += (b - a) * ref
        predicted += (b - a) * hyp
        intersection += (b - a) * (ref and hyp)
    precision = intersection / predicted if predicted else 0.0
    recall = intersection / actual if actual else 0.0
    return {
        "overlap_precision": precision,
        "overlap_recall": recall,
        "overlap_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        "false_overlap_sec": predicted - intersection,
        "reference_overlap_sec": actual,
        "predicted_overlap_sec": predicted,
    }
