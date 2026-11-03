"""Live checks must be explicit, bounded and safe to share."""

import io
import json
from urllib.error import HTTPError

import pytest

from meeting_asr.cli import main
from meeting_asr.doctor import probe_llm
from meeting_asr.summarize import HTTPProvider, LLMRequestError


@pytest.fixture
def options(monkeypatch):
    for name in ("PROVIDER", "MODEL", "BASE_URL"):
        monkeypatch.delenv(f"MEETING_LLM_{name}", raising=False)
    monkeypatch.setenv("PROBE_FIXTURE_KEY", "private-fixture-key")
    return {
        "provider": "http",
        "model": "fixture",
        "base_url": "https://example.invalid/v1",
        "api_key_env": "PROBE_FIXTURE_KEY",
        "enabled": True,
        "timeout_sec": 90,
    }


def test_probe_is_one_bounded_request_without_transcript(options, monkeypatch):
    calls = []

    def open_request(request, timeout):
        calls.append(request)
        payload = json.loads(request.data)
        assert payload["max_tokens"] == 512
        assert payload["model"] == "fixture"
        assert timeout == 20
        assert len(payload["messages"]) == 1
        return io.BytesIO(
            json.dumps({"choices": [{"message": {"content": '{"ok":true}'}}]}).encode()
        )

    monkeypatch.setattr("meeting_asr.summarize.urlopen", open_request)
    report = probe_llm(options)
    assert report["ready"] and report["api_accessible"]
    assert report["requests_sent"] == len(calls) == 1
    assert "private-fixture-key" not in json.dumps(report)
    assert "example.invalid" not in json.dumps(report)


def test_permission_failure_exposes_only_status_and_code(options, monkeypatch):
    def forbidden(request, timeout):
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            io.BytesIO(
                b'{"error":{"code":"model_access_denied","message":"private-fixture-key private transcript"}}'
            ),
        )

    monkeypatch.setattr("meeting_asr.summarize.urlopen", forbidden)
    report = probe_llm(options)
    assert report["configuration_ready"]
    assert not report["ready"] and not report["api_accessible"]
    assert report["requests_sent"] == 1
    assert report["http_status"] == 403
    assert report["provider_code"] == "model_access_denied"
    assert report["category"] == "permission_denied"
    assert "private" not in json.dumps(report)
    with pytest.raises(LLMRequestError, match="HTTP 403") as exc:
        HTTPProvider("http", "https://example.invalid", "private-fixture-key").complete(
            "private", "fixture"
        )
    assert "private" not in str(exc.value)


def test_missing_configuration_never_sends_request(options, monkeypatch):
    monkeypatch.delenv("PROBE_FIXTURE_KEY")
    monkeypatch.setattr(
        "meeting_asr.summarize.urlopen", lambda *a, **kw: pytest.fail("network called")
    )
    report = probe_llm(options)
    assert not report["ready"]
    assert report["requests_sent"] == 0


def test_invalid_json_is_not_ready_even_when_api_responds(options, monkeypatch):
    monkeypatch.setattr("meeting_asr.summarize.HTTPProvider.complete", lambda *a: "not json")
    report = probe_llm(options)
    assert report["api_accessible"]
    assert not report["ready"]
    assert report["category"] == "invalid_provider_response"


def test_cli_default_is_configuration_only_and_probe_writes_failure(
    options, monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr("meeting_asr.cli.load_config", lambda _: {"llm": options})
    monkeypatch.setattr(
        "meeting_asr.summarize.urlopen", lambda *a, **kw: pytest.fail("network called")
    )
    assert main(["llm-check"]) == 0
    assert json.loads(capsys.readouterr().out)["requests_sent"] == 0
    report = {"ready": False, "category": "permission_denied", "requests_sent": 1}
    monkeypatch.setattr("meeting_asr.doctor.probe_llm", lambda _: report)
    target = tmp_path / "probe.json"
    assert main(["llm-check", "--probe", "--out", str(target)]) == 2
    assert json.loads(target.read_text()) == report
