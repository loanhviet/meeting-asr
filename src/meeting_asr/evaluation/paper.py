"""Export timestamped transcripts to the isolated, pinned MeetEval scorer."""

from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

from meeting_asr.evaluation.metrics import normalize_for_wer
from meeting_asr.settings import PROJECT_ROOT


def transcript_segments(document, *, session_id="audio"):
    """Keep utterance boundaries; ORC assignment depends on those boundaries."""
    result = []
    for utterance in sorted(document.utterances, key=lambda u: (u.start, u.end, u.speaker)):
        words = normalize_for_wer(utterance.text)
        if words:
            result.append(
                {
                    "session_id": session_id,
                    "speaker": utterance.speaker,
                    "start_time": utterance.start,
                    "end_time": utterance.end,
                    "words": words,
                }
            )
    return result


def validate_segments(segments):
    sessions = set()
    for item in segments:
        if (
            not isinstance(item, dict)
            or not {"session_id", "speaker", "start_time", "end_time", "words"} <= item.keys()
        ):
            raise ValueError("paper metrics require text, speaker, session and timestamps")
        start, end = item["start_time"], item["end_time"]
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not math.isfinite(start)
            or not math.isfinite(end)
            or not 0 <= start <= end
        ):
            raise ValueError("invalid timestamp in paper scoring input")
        if (
            not isinstance(item["words"], str)
            or not isinstance(item["speaker"], str)
            or not item["speaker"]
        ):
            raise ValueError("paper scoring requires string text and nonempty speaker IDs")
        sessions.add(item["session_id"])
    if len(sessions) > 1:
        raise ValueError("score each recording independently")


def score_segments(reference, hypothesis, *, collar=5.0, scorer_python=None, timeout=120):
    """Score one recording; interpolation is explicit and never becomes gold timing."""
    if not math.isfinite(collar) or collar < 0:
        raise ValueError("time collar must be finite and nonnegative")
    validate_segments(reference)
    validate_segments(hypothesis)
    if not any(item["words"].split() for item in reference):
        raise ValueError("reference must contain words")
    ref_sessions = {x["session_id"] for x in reference}
    hyp_sessions = {x["session_id"] for x in hypothesis}
    if hyp_sessions and ref_sessions != hyp_sessions:
        raise ValueError("reference/hypothesis session IDs differ")
    python = Path(
        scorer_python
        or os.getenv("MEETING_EVALUATION_PYTHON")
        or PROJECT_ROOT / ".cache/paper-eval/venv/bin/python"
    )
    if not python.is_file():
        raise RuntimeError(
            "MeetEval runtime missing: install requirements/paper-evaluation.txt "
            "in .cache/paper-eval/venv or set MEETING_EVALUATION_PYTHON"
        )
    runner = Path(__file__).with_name("paper_runner.py")
    with tempfile.TemporaryDirectory(prefix="meeting-paper-") as temporary:
        root = Path(temporary)
        payload = root / "request.json"
        result = root / "result.json"
        payload.write_text(
            json.dumps(
                {"reference": reference, "hypothesis": hypothesis, "collar": collar},
                ensure_ascii=False,
            )
        )
        try:
            completed = subprocess.run(
                [str(python), str(runner), str(payload), str(result)],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("MeetEval scoring timed out") from None
        if completed.returncode:
            raise RuntimeError("MeetEval scoring failed; check the pinned scorer environment")
        return json.loads(result.read_text())


def score_transcripts(reference, hypothesis, **options):
    if abs(reference.duration - hypothesis.duration) > 0.001:
        raise ValueError("reference/hypothesis audio durations differ")
    return score_segments(
        transcript_segments(reference), transcript_segments(hypothesis), **options
    )
