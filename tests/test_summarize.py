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
        assert payload["max_tokens"] == 1800
        assert payload["messages"][0]["content"] == "JSON prompt"
        assert "enable_thinking" not in payload
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


def test_provider_timeout_is_sanitized_and_output_limit_is_configurable(monkeypatch):
    def timeout(request, timeout):
        assert json.loads(request.data)["max_tokens"] == 500
        raise TimeoutError("private request information")

    monkeypatch.setattr("meeting_asr.summarize.urlopen", timeout)
    with pytest.raises(RuntimeError, match="endpoint is unreachable") as exc:
        HTTPProvider(
            "http", "https://example.invalid/v1", "secret", max_output_tokens=500
        ).complete("private transcript", "fixture")
    assert "private" not in str(exc.value)


@pytest.mark.parametrize("thinking", [False, True])
def test_http_thinking_option_is_sent_explicitly(monkeypatch, thinking):
    def open_request(request, timeout):
        payload = json.loads(request.data)
        assert payload["enable_thinking"] is thinking
        assert payload["max_tokens"] == 1800
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode())

    monkeypatch.setattr("meeting_asr.summarize.urlopen", open_request)
    provider = HTTPProvider("http", "https://example.invalid/v1", None, enable_thinking=thinking)
    assert provider.complete("JSON", "deepseek-v4.1-flash") == "{}"


def test_thinking_environment_overrides_config_and_changes_cache_identity(monkeypatch, tmp_path):
    from meeting_asr.evaluation.ask import provider_provenance

    monkeypatch.setenv("MEETING_LLM_MODEL", "deepseek-v4.1-flash")
    monkeypatch.setenv("MEETING_LLM_PROVIDER", "http")
    monkeypatch.setenv("MEETING_LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.delenv("MEETING_LLM_ENABLE_THINKING", raising=False)
    options = {"enable_thinking": True, "api_key_env": None}
    original = Summarizer(options, tmp_path)
    monkeypatch.setenv("MEETING_LLM_ENABLE_THINKING", "false")
    adapted = Summarizer(options, tmp_path)
    assert original.identity != adapted.identity
    assert adapted.identity["enable_thinking"] is False
    assert adapted.provider.enable_thinking is False
    assert provider_provenance(adapted)["enable_thinking"] is False
    monkeypatch.setenv("MEETING_LLM_ENABLE_THINKING", "invalid")
    with pytest.raises(ValueError, match="MEETING_LLM_ENABLE_THINKING"):
        Summarizer(options, tmp_path)


@pytest.mark.parametrize("thinking", ["false", 0, 1])
def test_thinking_requires_boolean(thinking):
    with pytest.raises(ValueError, match="boolean"):
        HTTPProvider("http", "https://example.invalid/v1", None, enable_thinking=thinking)


def test_thinking_option_does_not_apply_to_anthropic_protocol():
    with pytest.raises(ValueError, match="http provider"):
        HTTPProvider("claude", "https://example.invalid/v1", None, enable_thinking=False)


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


def test_fenced_json_replies_are_accepted_for_minutes_and_answers():
    from meeting_asr.ask import validate_answer

    minutes = {"summary": "Họp.", "topics": [], "action_items": []}
    fenced = "```json\n" + json.dumps(minutes, ensure_ascii=False) + "\n```"
    assert validate_summary(fenced) == minutes
    answer = {"status": "not_found", "answer_points": []}
    assert validate_answer("```\n" + json.dumps(answer) + "\n```", set()) == answer
    with pytest.raises(json.JSONDecodeError):
        validate_summary("```json\nnot json\n```")
