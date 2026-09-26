"""DER, WER, and cpWER used by the research questions.

DER uses pyannote.metrics in the two modes required by the spec: relaxed
(collar 0.25s, overlap regions skipped) and strict (collar 0, overlap kept).
WER and cpWER share one Vietnamese normalization. cpWER sums per-speaker
errors after the best speaker permutation, so an alignment cannot cross from
one speaker's words into another's.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import permutations

from meeting_asr.evaluation.overlap import measure_overlap_ratio
from meeting_asr.models import Segment

RELAXED_COLLAR = 0.25
STRICT_COLLAR = 0.0
_PUNCTUATION = str.maketrans("", "", ".,!?;:\"'")

__all__ = [
    "DerScore",
    "cp_word_error_rate",
    "diarization_error_rate",
    "measure_overlap_ratio",
    "normalize_for_wer",
    "score_diarization",
    "word_error_rate",
]


def normalize_for_wer(text: str) -> str:
    text = text.lower().translate(_PUNCTUATION)
    text = " ".join(text.split())
    return unicodedata.normalize("NFC", text).strip()


def word_error_rate(reference: str, hypothesis: str) -> float:
    errors, total = _word_errors(normalize_for_wer(reference), normalize_for_wer(hypothesis))
    if total == 0:
        return 0.0 if errors == 0 else 1.0
    return errors / total


def cp_word_error_rate(reference: Mapping[str, str], hypothesis: Mapping[str, str]) -> float:
    ref_texts = [normalize_for_wer(text) for text in reference.values()]
    hyp_texts = [normalize_for_wer(text) for text in hypothesis.values()]
    ref_total = sum(len(text.split()) for text in ref_texts)
    if ref_total == 0:
        hyp_total = sum(len(text.split()) for text in hyp_texts)
        return 0.0 if hyp_total == 0 else 1.0
    width = max(len(ref_texts), len(hyp_texts), 1)
    ref_texts.extend([""] * (width - len(ref_texts)))
    hyp_texts.extend([""] * (width - len(hyp_texts)))
    best: int | None = None
    for order in permutations(range(width)):
        errors = 0
        for index in range(width):
            word_errors, _ = _word_errors(ref_texts[index], hyp_texts[order[index]])
            errors += word_errors
        if best is None or errors < best:
            best = errors
    assert best is not None
    return best / ref_total


@dataclass(frozen=True, slots=True)
class DerScore:
    der: float
    miss: float
    false_alarm: float
    confusion: float
    collar: float
    skip_overlap: bool


def score_diarization(reference: list[Segment], hypothesis: list[Segment]) -> dict[str, DerScore]:
    return {
        "relaxed": diarization_error_rate(
            reference, hypothesis, collar=RELAXED_COLLAR, skip_overlap=True
        ),
        "strict": diarization_error_rate(
            reference, hypothesis, collar=STRICT_COLLAR, skip_overlap=False
        ),
    }


def diarization_error_rate(
    reference: list[Segment],
    hypothesis: list[Segment],
    *,
    collar: float,
    skip_overlap: bool,
) -> DerScore:
    from pyannote.core import Timeline
    from pyannote.metrics.diarization import DiarizationErrorRate

    reference_annotation = _annotation(reference)
    hypothesis_annotation = _annotation(hypothesis)
    # The scored map is the union of both extents. Passing it explicitly is the
    # same region pyannote uses when no map is given.
    extent = reference_annotation.get_timeline().extent()
    extent |= hypothesis_annotation.get_timeline().extent()
    uem = Timeline(segments=[extent] if extent else [], uri=reference_annotation.uri)
    metric = DiarizationErrorRate(collar=collar, skip_overlap=skip_overlap)
    detail = metric(reference_annotation, hypothesis_annotation, uem=uem, detailed=True)
    total = float(detail["total"])
    if total <= 0:
        raise ValueError("reference speech duration is zero")
    return DerScore(
        der=float(detail["diarization error rate"]),
        miss=float(detail["missed detection"]) / total,
        false_alarm=float(detail["false alarm"]) / total,
        confusion=float(detail["confusion"]) / total,
        collar=collar,
        skip_overlap=skip_overlap,
    )


def _annotation(segments: list[Segment]):
    from pyannote.core import Annotation
    from pyannote.core import Segment as PySegment

    annotation = Annotation(uri="audio")
    for track, segment in enumerate(segments):
        annotation[PySegment(segment.start, segment.end), track] = segment.speaker
    return annotation


def _word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    import jiwer

    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words and not hyp_words:
        return 0, 0
    if not ref_words:
        return len(hyp_words), 0
    if not hyp_words:
        return len(ref_words), len(ref_words)
    output = jiwer.process_words(
        reference,
        hypothesis,
        reference_transform=jiwer.transforms.ReduceToListOfListOfWords(),
        hypothesis_transform=jiwer.transforms.ReduceToListOfListOfWords(),
    )
    errors = output.substitutions + output.deletions + output.insertions
    total = output.hits + output.substitutions + output.deletions
    return errors, total
