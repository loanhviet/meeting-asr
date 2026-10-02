import io
import json

import pytest

from meeting_asr.models import Turn
from meeting_asr.summarize import HTTPProvider, Summarizer, validate_summary


def test_json_retry_and_cache_preserve_uncertain_action_items(tmp_path):
    payload = {
        "summary": "Đã thống nhất kế hoạch.",
        "topics": ["kế hoạch"],
        "summary_points": [
            {"text": "Đã thống nhất kế hoạch.", "source_turn_ids": ["1"], "uncertain": True}
        ],
        "decisions": [],
        "action_items": [
            {
                "speaker": "A",
                "task": "gửi báo cáo",
                "deadline": None,
                "uncertain": True,
                "source_turn_ids": ["1"],
            }
        ],
    }

    class Provider:
        calls = 0

        def complete(self, prompt, model):
            assert "[?]" in prompt
            self.calls += 1
            return "bad JSON" if self.calls == 1 else json.dumps(payload)

    provider = Provider()
    summarizer = Summarizer({"model": "fixture", "provider": "http"}, tmp_path, provider)
    turns = [Turn("1", 0, 3, "A", "tôi sẽ gửi báo cáo", [], flagged=True)]
    assert summarizer.summarize(turns) == payload
    assert summarizer.summarize(turns) == payload
    assert provider.calls == 2
    with pytest.raises(ValueError):
        validate_summary({"summary": "x", "topics": [], "action_items": [{"task": "x"}]})


@pytest.mark.parametrize("provider", ["http", "claude"])
def test_provider_request_and_response_protocol(provider, monkeypatch):
    expected = '{"summary":"x","topics":[],"action_items":[]}'

    def open_request(request, timeout):
        payload = json.loads(request.data)
        assert payload["model"] == "fixture"
        assert payload["messages"][0]["content"] == "JSON prompt"
        if provider == "http":
            assert request.full_url.endswith("/chat/completions")
            assert payload["response_format"] == {"type": "json_object"}
            response = {"choices": [{"message": {"content": expected}}]}
        else:
            assert request.full_url.endswith("/messages")
            assert request.get_header("Anthropic-version") == "2023-06-01"
            response = {"content": [{"type": "text", "text": expected}]}
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr("meeting_asr.summarize.urlopen", open_request)
    assert (
        HTTPProvider(provider, "https://example.invalid/v1", "fixture-key").complete(
            "JSON prompt", "fixture"
        )
        == expected
    )


def grounded(ids, task="gửi báo cáo"):
    return {
        "summary": "Thống nhất gửi báo cáo.",
        "topics": ["báo cáo"],
        "summary_points": [{"text": "Gửi báo cáo", "source_turn_ids": ids, "uncertain": False}],
        "decisions": [{"text": "Chốt báo cáo", "source_turn_ids": ids, "uncertain": False}],
        "action_items": [
            {
                "speaker": None,
                "task": task,
                "deadline": None,
                "source_turn_ids": ids,
                "uncertain": False,
            }
        ],
    }


def test_unknown_or_empty_evidence_is_rejected_and_not_cached(tmp_path):
    class Provider:
        calls = 0

        def complete(self, prompt, model):
            self.calls += 1
            return json.dumps(grounded(["invented"]))

    provider = Provider()
    summarizer = Summarizer({"model": "fixture"}, tmp_path, provider)
    with pytest.raises(ValueError, match="evidence twice"):
        summarizer.summarize([Turn("real", 0, 2, "A", "báo cáo", [])])
    assert provider.calls == 2
    assert not list(tmp_path.glob("*.json"))
    with pytest.raises(ValueError, match="evidence"):
        validate_summary(grounded([]), allowed_turn_ids={"real"}, require_grounded=True)


def test_long_transcript_keeps_source_ids_and_decisions_across_chunks(tmp_path):
    import re

    class Provider:
        calls = 0

        def complete(self, prompt, model):
            self.calls += 1
            ids = re.findall(r"\[ID=([^\]]+)\]", prompt)
            assert ids
            return json.dumps(grounded(list(dict.fromkeys(ids)), task=f"task {self.calls}"))

    provider = Provider()
    turns = [
        Turn(str(i), i * 3, i * 3 + 2, "A", "nội dung " * 500, [], flagged=i == 1) for i in range(3)
    ]
    result = Summarizer(
        {"model": "fixture", "max_input_chars": 2000}, tmp_path, provider
    ).summarize(turns)
    assert provider.calls > 3
    assert {i for d in result["decisions"] for i in d["source_turn_ids"]} == {"0", "1", "2"}
    assert all(d["uncertain"] for d in result["decisions"] if "1" in d["source_turn_ids"])
    assert all(a["speaker"] is None for a in result["action_items"])


def test_evidence_timestamps_and_review_status_come_from_transcript():
    from meeting_asr.summarize import resolve_evidence

    result = resolve_evidence(
        grounded(["1"]),
        [
            {
                "turn_id": "1",
                "start": 12,
                "end": 18,
                "speaker": "An",
                "flagged": True,
                "reviewed": False,
            }
        ],
    )
    item = result["action_items"][0]
    assert item["sources"][0]["start"] == 12
    assert item["needs_review"]
    assert not item["evidence_missing"]
