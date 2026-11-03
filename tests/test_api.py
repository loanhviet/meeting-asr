import pytest
from fastapi.testclient import TestClient

from meeting_asr.api import create_app
from meeting_asr.io import write_minutes_json
from meeting_asr.models import MeetingMinutes, Turn, Utterance
from meeting_asr.settings import load_config


@pytest.mark.parametrize("extension", ["wav", "mp3", "m4a"])
def test_upload_result_edit_conflict_and_retry(tmp_path, extension):
    config = load_config()

    def processor(source, config, out, progress):
        u = Utterance(0, 6, "A", "xin chào")
        write_minutes_json(
            out / "minutes.json",
            MeetingMinutes("x", 6, 1, [Turn("0", 0, 6, "A", "Xin chào", [u], flagged=True)]),
        )

    app = create_app(config, tmp_path, processor=processor, start_worker=False)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/jobs", files={"file": ("x.txt", b"x")}).status_code == 415
        assert client.post("/api/jobs", files={"file": ("x.wav", b"")}).status_code == 400
        response = client.post(
            "/api/jobs", files={"file": (f"../../x.{extension}", b"audio fixture")}
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert client.get(f"/api/jobs/{job_id}").json()["filename"] == f"x.{extension}"
        assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
        app.state.worker.process_one(job_id)
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "complete"
        response = client.patch(
            f"/api/jobs/{job_id}/turns/0", json={"text": "đã sửa", "expected_revision": 0}
        )
        assert response.json()["edited"]["turns"][0]["text"] == "đã sửa"
        assert response.json()["original"]["turns"][0]["text"] == "Xin chào"
        assert (
            client.patch(
                f"/api/jobs/{job_id}/turns/0", json={"text": "conflict", "expected_revision": 0}
            ).status_code
            == 409
        )
        assert client.post(f"/api/jobs/{job_id}/retry").status_code == 409
        assert client.get("/api/jobs/missing").status_code == 404
        exported = client.get(f"/api/jobs/{job_id}/export?fmt=srt")
        assert exported.status_code == 200
        assert "đã sửa" in exported.text


def test_oversized_upload_does_not_leave_partial_audio(tmp_path, monkeypatch):
    monkeypatch.setattr("meeting_asr.api.MAX_UPLOAD", 4)
    app = create_app(load_config(), tmp_path, start_worker=False)
    with TestClient(app) as client:
        assert client.post("/api/jobs", files={"file": ("x.wav", b"12345")}).status_code == 413
    assert not list(tmp_path.rglob("upload.part"))
    assert app.state.store.list_jobs() == []


def test_speaker_review_api_and_template_validation(tmp_path):
    app = create_app(load_config(), tmp_path, start_worker=False)
    with TestClient(app) as client:
        job_id = client.post("/api/jobs", files={"file": ("x.wav", b"audio")}).json()["job_id"]
        write_minutes_json(
            app.state.store.artifact_dir(job_id) / "minutes.json",
            MeetingMinutes(
                "x", 6, 2, [Turn("a", 0, 3, "A", "xin chào", []), Turn("b", 3, 6, "B", "chào", [])]
            ),
        )
        app.state.store.update(job_id, status="complete")
        response = client.patch(
            f"/api/jobs/{job_id}/turns/a", json={"speaker_id": "B", "expected_revision": 0}
        )
        assert response.status_code == 200
        assert response.json()["edited"]["num_speakers"] == 1
        assert (
            client.patch(f"/api/jobs/{job_id}/turns/a", json={"speaker_id": "X"}).status_code == 422
        )
        response = client.post(
            f"/api/jobs/{job_id}/speakers/merge",
            json={
                "source_speaker": "B",
                "target_speaker": "A",
                "expected_revision": 1,
            },
        )
        assert response.status_code == 200
        assert client.get(f"/api/jobs/{job_id}/history").json()[0]["kind"] == "speaker_merge"
        assert (
            client.post(
                f"/api/jobs/{job_id}/speakers/merge",
                json={
                    "source_speaker": "A",
                    "target_speaker": "B",
                    "expected_revision": 0,
                },
            ).status_code
            == 409
        )
        assert (
            client.post(f"/api/jobs/{job_id}/summary", json={"template": "unknown"}).status_code
            == 422
        )


def test_titles_finalize_action_edits_overview_and_moved_audio(tmp_path):
    def processor(source, config, out, progress):
        turns = [
            Turn("t0", 0, 5, "A", "An viết báo cáo trước thứ Sáu", [], flagged=True),
            Turn("t1", 5, 9, "B", "ừ ừ ừ ừ", [], flagged=True, flag_reasons=["nghi lặp/ảo giác"]),
            Turn("t2", 9, 12, "B", "Không liên quan", [], flagged=True),
        ]
        minutes = MeetingMinutes("x", 12, 2, turns, summary="Họp")
        minutes.summary_points = [{"text": "Họp", "source_turn_ids": ["t0"], "uncertain": False}]
        minutes.action_items = [
            {
                "speaker": None,
                "task": "Viết báo cáo",
                "deadline": None,
                "source_turn_ids": ["t0"],
                "uncertain": False,
            }
        ]
        write_minutes_json(out / "minutes.json", minutes)

    app = create_app(load_config(), tmp_path, processor=processor, start_worker=False)
    store = app.state.store
    with TestClient(app) as client:
        job_id = client.post("/api/jobs", files={"file": ("hop_nhom_2.wav", b"RIFF")}).json()[
            "job_id"
        ]
        app.state.worker.process_one(job_id)
        # A job created inside Docker keeps an /app/... path; the audio is still found locally.
        with store.connect() as db:
            db.execute(
                "UPDATE jobs SET source=? WHERE id=?", (f"/app/x/{job_id}/audio.wav", job_id)
            )
        assert client.get(f"/api/jobs/{job_id}/audio").status_code == 200

        job = client.get("/api/jobs").json()[0]
        assert job["title"] == "hop nhom 2" and not job["finalized"]
        assert job["overview"] == {
            "duration": 12,
            "speakers": 2,
            "unnamed_speakers": 2,
            "decisions": 0,
            "actions": 1,
            "actions_done": 0,
            "to_review": 2,
            "has_minutes": True,
            "summary_stale": False,
        }
        view = client.get(f"/api/jobs/{job_id}/result").json()
        # Cited turn and decoding loop need a listen; an uncited ordinary flag does not.
        assert view["review_turn_ids"] == ["t0", "t1"]

        renamed = client.patch(
            f"/api/jobs/{job_id}", json={"title": "Họp nhóm 2", "finalized": True}
        )
        assert renamed.json()["title"] == "Họp nhóm 2" and renamed.json()["finalized"]
        view = client.patch(
            f"/api/jobs/{job_id}/actions/0",
            json={"speaker": "An", "deadline": "Thứ Sáu", "done": True},
        ).json()
        assert view["edited"]["action_items"][0] | {"sources": None} == {
            "speaker": "An",
            "task": "Viết báo cáo",
            "deadline": "Thứ Sáu",
            "done": True,
            "source_turn_ids": ["t0"],
            "uncertain": False,
            "sources": None,
            "evidence_missing": False,
            "needs_review": True,
        }
        assert client.patch(f"/api/jobs/{job_id}/actions/5", json={"done": True}).status_code == 404
        exported = client.get(f"/api/jobs/{job_id}/export?fmt=md").text
        assert "# Biên bản họp — Họp nhóm 2" in exported and "- [x] An: Viết báo cáo" in exported

        # Editing the transcript after finalizing reopens the meeting.
        client.patch(f"/api/jobs/{job_id}/turns/t0", json={"text": "sửa", "expected_revision": 0})
        assert not client.get(f"/api/jobs/{job_id}").json()["finalized"]
        # Re-running the pipeline produces new minutes, so the action edits are dropped.
        store.update(job_id, status="failed")
        store.retry(job_id)
        app.state.worker.process_one(job_id)
        assert not client.get(f"/api/jobs/{job_id}/result").json()["edited"]["action_items"][0][
            "done"
        ]
