import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_asr.api import create_app
from meeting_asr.ask import AskMeeting, retrieve, validate_answer
from meeting_asr.io import write_minutes_json
from meeting_asr.models import MeetingMinutes, Turn
from meeting_asr.settings import load_config


def point(text="Bình nhận kiểm thử.", ids=None):
    return {
        "status": "found",
        "answer_points": [{"text": text, "source_turn_ids": ids or ["b"], "uncertain": False}],
    }


class Provider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []
        self.on_request = None

    def complete(self, prompt, model):
        self.prompts.append(prompt)
        if self.on_request:
            self.on_request()
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response, ensure_ascii=False)


def make_app(tmp_path, provider, enabled=True):
    config = load_config()
    config["llm"].update(enabled=enabled, provider="http", model="test")
    app = create_app(
        config,
        tmp_path,
        start_worker=False,
        answerer_factory=lambda: AskMeeting(config["llm"], tmp_path / "cache", provider),
    )
    store = app.state.store
    store.create("meeting", "synthetic.wav", tmp_path / "synthetic.wav")
    write_minutes_json(
        store.artifact_dir("meeting") / "minutes.json",
        MeetingMinutes(
            "meeting",
            12,
            2,
            [
                Turn("a", 0, 4, "An", "Ai nhận kiểm thử?", []),
                Turn("b", 5, 9, "Bình", "Bình nhận kiểm thử trước thứ Năm.", [], flagged=True),
                Turn("c", 10, 12, "An", "Đính chính: hạn kiểm thử là thứ Sáu.", []),
            ],
        ),
    )
    store.update("meeting", status="complete")
    return app


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "found", "answer_points": []},
        {"status": "not_found", "answer_points": point()["answer_points"]},
        point(ids=["outside"]),
        point(ids=["b", "b"]),
        {"status": "found", "answer_points": [{**point()["answer_points"][0], "start": 999}]},
        {"status": "found", "answer_points": [{**point()["answer_points"][0], "uncertain": 1}]},
    ],
)
def test_reject_ungrounded_answers(payload):
    with pytest.raises((ValueError, TypeError)):
        validate_answer(payload, {"a", "b", "c"})


def test_retrieval_diacritics_aliases_neighbors_long_turn_and_prompt_budget():
    turns = [
        {
            "turn_id": str(i),
            "text": "Trao đổi giao diện.",
            "speaker": "An",
            "start": i,
            "end": i + 1,
        }
        for i in range(25)
    ]
    turns[10]["text"] = "Trao đổi giao diện. " * 400 + "Hạn kiểm thử là thứ Năm."
    turns[10]["original_text"] = "BÍ MẬT BẢN CŨ"
    turns[11]["text"] = "Đính chính hạn kiểm thử là thứ Sáu."
    result = retrieve("deadline kiem thu?", turns, max_chars=6000)
    assert {"10", "11"} <= {t["turn_id"] for t in result}
    assert "Hạn kiểm thử là thứ Năm" in next(t["text"] for t in result if t["turn_id"] == "10")
    assert "BÍ MẬT" not in json.dumps(result, ensure_ascii=False)
    assert len(json.dumps(result, ensure_ascii=False)) < 6500
    assert retrieve("ngân sách?", turns) == []


def test_api_answers_review_sources_history_persistence_cache_and_edit(tmp_path):
    provider = Provider([point(), point("An nhận kiểm thử.")])
    app = make_app(tmp_path, provider)
    with TestClient(app) as client:
        path = "/api/jobs/meeting/questions"
        body = {"question": "Ai nhận kiểm thử?", "expected_revision": 0}
        answer = client.post(path, json=body).json()
        claim = answer["answer_points"][0]
        assert claim["sources"][0]["start"] == 5
        assert claim["sources"][0]["text"] == "Bình nhận kiểm thử trước thứ Năm."
        assert claim["uncertain"] and claim["needs_review"]
        assert client.post(path, json=body).json()["id"] == answer["id"]
        assert len(provider.prompts) == 1
        app.state.store.edit("meeting", "b", text="An nhận kiểm thử.", expected_revision=0)
        assert client.get(path).json()[0]["stale"]
        assert client.post(path, json=body).status_code == 409
        fresh = client.post(path, json={**body, "expected_revision": 1}).json()
        assert fresh["revision"] == 1 and not fresh["stale"]
        assert "Bình nhận kiểm thử trước thứ Năm" not in provider.prompts[-1]
    restarted = create_app(load_config(), tmp_path, start_worker=False)
    with TestClient(restarted) as client:
        assert len(client.get(path).json()) == 2


def test_api_missing_answers_and_invalid_retry(tmp_path):
    provider = Provider([point(ids=["invented"]), {"status": "not_found", "answer_points": []}])
    app = make_app(tmp_path, provider)
    with TestClient(app) as client:
        path = "/api/jobs/meeting/questions"
        # Zero lexical matches avoids a provider request.
        answer = client.post(path, json={"question": "ngân sách?", "expected_revision": 0}).json()
        assert answer["status"] == "not_found" and not provider.prompts
        answer = client.post(
            path, json={"question": "Hạn kiểm thử?", "expected_revision": 0}
        ).json()
        assert answer["status"] == "not_found" and len(provider.prompts) == 2
        assert client.post(path, json={"question": " ", "expected_revision": 0}).status_code == 422
        assert (
            client.post(path, json={"question": "x" * 1001, "expected_revision": 0}).status_code
            == 422
        )
        assert client.get("/api/jobs/missing/questions").status_code == 404


def test_concurrent_edit_discards_answer_and_does_not_store_wrong_revision(tmp_path):
    provider = Provider([point()])
    app = make_app(tmp_path, provider)
    provider.on_request = lambda: app.state.store.edit("meeting", "b", text="Nội dung đã sửa")
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs/meeting/questions",
            json={"question": "Ai nhận kiểm thử?", "expected_revision": 0},
        )
        assert response.status_code == 409
        assert client.get("/api/jobs/meeting/questions").json() == []


def test_provider_failure_is_sanitized_and_disabled_service_remains_readable(tmp_path):
    provider = Provider([RuntimeError("private transcript provider response")])
    app = make_app(tmp_path, provider)
    with TestClient(app) as client:
        path = "/api/jobs/meeting/questions"
        response = client.post(path, json={"question": "kiểm thử", "expected_revision": 0})
        assert response.status_code == 502 and "private" not in response.text
        assert client.get(path).json() == []
    app = make_app(tmp_path / "disabled", Provider([]), enabled=False)
    with TestClient(app) as client:
        assert not client.get("/api/health").json()["ask_enabled"]
        assert (
            client.post(path, json={"question": "kiểm thử", "expected_revision": 0}).status_code
            == 409
        )


def test_invalid_provider_response_twice_is_not_saved(tmp_path):
    app = make_app(tmp_path, Provider([point(ids=["fake"]), point(ids=["fake"])]))
    with TestClient(app) as client:
        path = "/api/jobs/meeting/questions"
        assert (
            client.post(path, json={"question": "kiểm thử", "expected_revision": 0}).status_code
            == 502
        )
        assert client.get(path).json() == []


def test_result_revision_and_edits_share_one_database_snapshot(tmp_path, monkeypatch):
    store = make_app(tmp_path, Provider([])).state.store
    read_text = Path.read_text
    pending = True

    def competing_edit(path, *args, **kwargs):
        nonlocal pending
        if pending and path.name == "minutes.json":
            pending = False
            store.edit("meeting", "b", text="An nhận kiểm thử", expected_revision=0)
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", competing_edit)
    old = store.result("meeting")
    assert old["revision"] == 0 and old["edited"]["turns"][1]["text"].startswith("Bình")
    new = store.result("meeting")
    assert new["revision"] == 1 and new["edited"]["turns"][1]["text"].startswith("An")


def test_repeated_question_reuses_provider_and_moves_to_recent_history(tmp_path):
    provider = Provider([point()])
    app = make_app(tmp_path, provider)
    with TestClient(app) as client:
        path = "/api/jobs/meeting/questions"
        body = {"question": "Ai nhận kiểm thử?", "expected_revision": 0}
        first = client.post(path, json=body).json()
        missing = client.post(path, json={**body, "question": "ngân sách?"}).json()
        assert client.get(path).json()[0]["id"] == missing["id"]
        repeat = client.post(path, json=body).json()
        assert repeat["id"] == first["id"] and repeat["created"] > missing["created"]
        assert client.get(path).json()[0]["id"] == first["id"]
        assert len(provider.prompts) == 1
