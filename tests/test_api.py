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
