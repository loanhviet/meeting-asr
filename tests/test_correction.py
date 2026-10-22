import io
import json
from urllib.error import HTTPError

import pytest

from meeting_asr.cli import main
from meeting_asr.correction import KimiProvider, propose_correction, source_hash, validate_proposal


def proposal(before, after, turn_id="t1"):
    return {"turn_id": turn_id, "edits": [{"before": before, "after": after, "reason": "gần âm"}]}


def test_exact_unicode_patch_offsets_and_immutable_source():
    text = "Nhóm dùng đô cơ để triển khai."
    result = validate_proposal(proposal("đô cơ", "Docker"), "t1", text)
    edit = result["edits"][0]
    assert text[edit["start_char"] : edit["end_char"]] == "đô cơ"
    assert result["suggested_text"] == "Nhóm dùng Docker để triển khai."
    assert result["source_text"] == text
    assert result["source_sha256"] == source_hash(text)
    assert result["requires_review"]


@pytest.mark.parametrize(
    "text,before,after,rejection",
    [
        ("đô cơ và đô cơ", "đô cơ", "Docker", "source_span_missing_or_ambiguous"),
        ("dùng Docker", "đô cơ", "Docker", "source_span_missing_or_ambiguous"),
        ("triển khai bản 12", "12", "13", "protected_number_negation_or_commitment"),
        ("nhóm chưa chốt", "chưa", "đã", "protected_number_negation_or_commitment"),
        ("nhóm có thể triển khai", "thể", "để", "protected_context_changed"),
        ("abc", "abc", "xyz", "change_budget_exceeded"),
        ("triển khai Docker", "Docker", "Docker", "no_change"),
        ("triển khai Docker", "ock", "abc", "partial_word"),
    ],
)
def test_unsafe_or_ambiguous_patch_is_kept_for_review(text, before, after, rejection):
    result = validate_proposal(proposal(before, after), "t1", text)
    assert result["suggested_text"] == text
    assert not result["edits"]
    assert result["rejected_edits"][0]["rejection"] == rejection


def test_overlaps_rejected_and_wrong_id_or_metadata_cannot_be_accepted():
    payload = proposal("đô cơ", "Docker")
    payload["edits"].append({"before": "đô", "after": "do", "reason": "x"})
    result = validate_proposal(payload, "t1", "Nhóm dùng đô cơ để triển khai.")
    assert len(result["edits"]) == 1
    assert result["rejected_edits"][0]["rejection"] == "overlapping_spans"
    with pytest.raises(ValueError, match="turn ID"):
        validate_proposal(proposal("đô cơ", "Docker", "invented"), "t1", "đô cơ")
    with pytest.raises(ValueError, match="schema"):
        validate_proposal({"turn_id": "t1", "edits": [], "speaker": "B"}, "t1", "x")


def test_cache_keeps_sources_separate_and_never_sends_reference(tmp_path):
    class Provider:
        model = "fixture"
        base_url = "https://example.invalid/v1"
        max_output_tokens = 4096
        calls = 0

        def complete(self, prompt):
            self.calls += 1
            payload = json.loads(prompt.split("DATA_JSON:\n", 1)[1])
            assert set(payload) == {"target", "context", "glossary"}
            assert payload["target"] == {"turn_id": "t1", "text": "Nhóm dùng đô cơ để triển khai."}
            assert "GOLD SECRET" not in prompt
            return {
                "content": json.dumps(proposal("đô cơ", "Docker")),
                "model": self.model,
                "usage": {"total_tokens": 20},
                "elapsed_sec": 0.01,
            }

    provider = Provider()
    turn = {"turn_id": "t1", "text": "Nhóm dùng đô cơ để triển khai.", "reference": "GOLD SECRET"}
    a = propose_correction(provider, turn, cache_dir=tmp_path)
    b = propose_correction(provider, turn, cache_dir=tmp_path)
    assert not a["cache_hit"] and b["cache_hit"]
    assert provider.calls == 1
    assert turn["text"] == "Nhóm dùng đô cơ để triển khai."
    propose_correction(provider, turn, glossary=["Docker"], cache_dir=tmp_path)
    assert provider.calls == 2


def test_csv_provider_errors_do_not_expose_key_or_private_response(tmp_path, monkeypatch):
    path = tmp_path / "key.csv"
    path.write_text(
        "\ufeffid,42\napiKey,fixture-secret\nopenAiCompatible,https://example.invalid/v1\n"
    )
    provider = KimiProvider.from_csv(path)
    assert "fixture-secret" not in repr(provider)

    def fail(request, timeout):
        raise HTTPError(
            request.full_url, 401, "fixture-secret", {}, io.BytesIO(b"private transcript")
        )

    monkeypatch.setattr("meeting_asr.correction.urlopen", fail)
    with pytest.raises(RuntimeError, match="HTTP 401") as exc:
        provider.complete("private transcript")
    assert "fixture-secret" not in str(exc.value) and "private transcript" not in str(exc.value)


def test_cli_writes_suggestions_preserving_audio_and_speaker_metadata(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "key.csv"
    path.write_text("apiKey,fixture-secret\nopenAiCompatible,https://example.invalid/v1\n")
    source = tmp_path / "transcript.json"
    original = {
        "audio_id": "meeting",
        "utterances": [
            {"start": 1, "end": 5, "speaker": "A", "text": "Nhóm dùng đô cơ để triển khai."}
        ],
    }
    source.write_text(json.dumps(original, ensure_ascii=False))
    original_bytes = source.read_bytes()

    def complete(request, timeout):
        payload = json.loads(request.data)
        assert payload["model"] == "kimi-k3" and payload["enable_thinking"] is True
        assert payload["max_tokens"] == 4096
        data = {
            "model": "kimi-k3",
            "usage": {"total_tokens": 30},
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(proposal("đô cơ", "Docker", "utterance_00000")),
                        "reasoning_content": "discard this private reasoning",
                    },
                }
            ],
        }
        return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr("meeting_asr.correction.urlopen", complete)
    out = tmp_path / "suggestions.json"
    assert (
        main(["correct-transcript", str(source), "--api-key-csv", str(path), "--out", str(out)])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["suggestions"] == 1
    assert source.read_bytes() == original_bytes
    result = json.loads(out.read_text())
    assert result["mode"] == "suggestions_only"
    assert result["suggestions"][0]["suggested_text"] == "Nhóm dùng Docker để triển khai."
    assert "fixture-secret" not in out.read_text() and "private reasoning" not in out.read_text()
    assert (
        main(["correct-transcript", str(source), "--api-key-csv", str(path), "--out", str(source)])
        == 2
    )
    assert source.read_bytes() == original_bytes


def test_partial_provider_response_is_not_a_usable_suggestion(monkeypatch):
    data = {
        "usage": {"total_tokens": 123},
        "choices": [{"finish_reason": "length", "message": {"content": '{"edits":['}}],
    }
    monkeypatch.setattr(
        "meeting_asr.correction.urlopen", lambda *a, **k: io.BytesIO(json.dumps(data).encode())
    )
    with pytest.raises(RuntimeError, match="incomplete") as error:
        KimiProvider("https://example.invalid/v1", "fixture").complete("prompt")
    assert error.value.metadata["usage"]["total_tokens"] == 123
