import json
from dataclasses import replace

import numpy as np
import pytest

from meeting_asr.data_gen.annotations import import_speech_labels, validate_speech_labels
from meeting_asr.data_gen.propose import conservative_intervals
from meeting_asr.data_gen.review import build_speech_review
from meeting_asr.data_gen.simulate import Clip, simulate_matrix, write_mono_wav, write_session
from meeting_asr.evaluation.overlap import measure_overlap_ratio
from meeting_asr.io import read_rttm, read_transcript_json
from meeting_asr.runtime import file_sha256

AUTO = {"status": "automatic_unverified", "method": "test-vad", "version": "v1"}


def test_conservative_proposals_keep_padding_and_short_internal_pauses():
    support = np.zeros(16000, dtype=bool)
    support[4800:6400] = True
    support[7200:9600] = True  # 50 ms pause is kept.
    assert conservative_intervals(support) == [[0.2, 0.7]]
    assert conservative_intervals(np.zeros(16000, dtype=bool)) == [[0, 1]]


@pytest.mark.parametrize(
    "ranges",
    [
        [],
        [[0, float("nan")]],
        [[-1, 1]],
        [[0, 3]],
        [[1, 0]],
        [[0, 1.2], [1, 2]],
        [[False, 1]],
        [[0, 0.0001]],
    ],
)
def test_invalid_speech_intervals_are_rejected(ranges):
    # Sub-millisecond regions cannot survive RTTM timestamp serialization.
    with pytest.raises(ValueError):
        validate_speech_labels(ranges, AUTO, 2)


def test_human_verification_requires_reviewer_provenance():
    with pytest.raises(ValueError, match="reviewed_by"):
        validate_speech_labels([[0, 1]], {**AUTO, "status": "human_verified"}, 2)


def labelled_clips():
    return [
        Clip(
            f"c{i}",
            f"s{i % 3}",
            f"câu {i}",
            (0.2 * np.sin(np.arange(32000) * 0.1)).astype(np.float32),
            "fixture",
            speech_intervals=((0.1, 0.8), (0.9, 1.85)),
            speech_annotation=AUTO.copy(),
        )
        for i in range(9)
    ]


def test_real_speech_overlap_snr_and_oracle_context_are_separate(tmp_path):
    clips = labelled_clips()
    for session in simulate_matrix(clips, seed=12, index=1):
        wav = write_session(tmp_path, session)
        truth = read_rttm(wav.with_suffix(".rttm"))
        oracle = read_rttm(wav.with_suffix(".oracle.rttm"))
        transcript = read_transcript_json(wav.with_suffix(".json"))
        assert abs(measure_overlap_ratio(truth) - session.overlap_target) < 0.03
        assert sum(s.duration for s in truth) < sum(s.duration for s in oracle)
        assert len(oracle) == len(transcript.utterances) == len(clips)
        assert len(truth) == 2 * len(clips)
        assert session.reference_kind == "speech_intervals"
        if session.snr_db is not None:
            assert session.snr_actual_db == pytest.approx(session.snr_db)
    first = simulate_matrix(clips, seed=12, index=1)
    second = simulate_matrix(clips, seed=12, index=1)
    assert all(np.array_equal(a.waveform, b.waveform) for a, b in zip(first, second, strict=True))


def test_infeasible_speech_target_and_mixed_label_modes_fail():
    clips = labelled_clips()
    with pytest.raises(ValueError, match="cannot mix"):
        simulate_matrix(
            [replace(clips[0], speech_intervals=None, speech_annotation=None), *clips[1:]],
            seed=1,
            index=1,
        )
    with pytest.raises(ValueError, match="infeasible"):
        simulate_matrix(
            [replace(c, speech_intervals=((0.9, 1.0),)) for c in clips], seed=1, index=1
        )


def test_import_preserves_text_and_checks_audio_identity(tmp_path):
    wav = tmp_path / "clip.wav"
    write_mono_wav(wav, labelled_clips()[0].waveform, 16000)
    clip = {
        "clip_id": "c0",
        "source": "fixture",
        "speaker": "s0",
        "text": "giữ lời gốc",
        "wav": wav.name,
    }
    manifest, labels = tmp_path / "manifest.json", tmp_path / "labels.json"
    manifest.write_text(json.dumps({"split": "test", "clips": [clip]}))
    label = {
        **clip,
        "sha256": file_sha256(wav),
        "speech_intervals": [[0.1, 1.85]],
        "speech_annotation": AUTO,
    }
    labels.write_text(json.dumps({"clips": [label]}))
    result = import_speech_labels(manifest, labels, tmp_path / "out.json")
    assert result["clips"][0]["text"] == "giữ lời gốc"
    assert result["speech_label_import"]["statuses"] == {"automatic_unverified": 1}
    review = build_speech_review(tmp_path / "out.json", tmp_path / "review")
    assert review["clips"] == 1
    page = (tmp_path / "review/index.html").read_text()
    assert "human_verified" in page
    assert (tmp_path / "review/audio" / f"{file_sha256(wav)}.wav").exists()
    label["sha256"] = "wrong"
    labels.write_text(json.dumps({"clips": [label]}))
    with pytest.raises(ValueError, match="checksum"):
        import_speech_labels(manifest, labels, tmp_path / "bad.json")
