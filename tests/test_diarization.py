import pytest

from meeting_asr.diarization import DiarizationResult, make_backend
from meeting_asr.models import DiarSignals, Segment


def test_diarization_signal_roundtrip_preserves_identical_boundaries():
    result = DiarizationResult(
        [Segment(0, 2, "A"), Segment(0, 2, "B")], [DiarSignals(1), DiarSignals(1)], "fixture"
    )
    restored = DiarizationResult.from_dict(result.to_dict())
    assert restored == result
    with pytest.raises(ValueError, match="align"):
        DiarizationResult(result.segments, [], "fixture")
    with pytest.raises(ValueError, match="unknown"):
        make_backend({"backend": "missing"})
