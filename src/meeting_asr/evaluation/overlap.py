"""Overlap ratio measured from speaker segments.

The ratio is the time in which at least two speakers are active divided by the
time in which at least one speaker is active. Touching endpoints do not count
as overlap, and two segments from the same speaker do not count as overlap.
"""

from __future__ import annotations

from meeting_asr.models import Segment


def measure_overlap_ratio(segments: list[Segment]) -> float:
    multi, union = _overlap_times(segments)
    if union == 0:
        return 0.0
    return multi / union


def utterance_overlap_fractions(segments: list[Segment]) -> list[float]:
    """Fraction of each segment that overlaps a different speaker."""
    fractions = []
    for index, segment in enumerate(segments):
        others = [
            other
            for other_index, other in enumerate(segments)
            if other_index != index and other.speaker != segment.speaker
        ]
        covered = _covered_duration(segment, others)
        fractions.append(min(1.0, covered / segment.duration))
    return fractions


def _overlap_times(segments: list[Segment]) -> tuple[float, float]:
    events: list[tuple[float, int, str]] = []
    for segment in segments:
        events.append((segment.start, 1, segment.speaker))
        events.append((segment.end, -1, segment.speaker))
    # Ends sort before starts at the same instant, so a shared boundary is silence.
    events.sort(key=lambda item: (item[0], item[1]))
    active: dict[str, int] = {}
    multi = 0.0
    union = 0.0
    previous: float | None = None
    for time, delta, speaker in events:
        if previous is not None and time > previous:
            speaking = sum(count > 0 for count in active.values())
            span = time - previous
            if speaking >= 1:
                union += span
            if speaking >= 2:
                multi += span
        count = active.get(speaker, 0) + delta
        if count == 0:
            active.pop(speaker, None)
        else:
            active[speaker] = count
        previous = time
    return multi, union


def _covered_duration(segment: Segment, others: list[Segment]) -> float:
    pieces = []
    for other in others:
        start = max(segment.start, other.start)
        end = min(segment.end, other.end)
        if end > start:
            pieces.append((start, end))
    if not pieces:
        return 0.0
    pieces.sort()
    covered = 0.0
    current_start, current_end = pieces[0]
    for start, end in pieces[1:]:
        if start > current_end:
            covered += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    return covered + (current_end - current_start)
