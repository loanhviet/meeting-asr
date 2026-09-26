from fastapi.testclient import TestClient

from meeting_asr.api import create_app
from meeting_asr.io import write_minutes_json
from meeting_asr.models import MeetingMinutes, Turn, Utterance
from meeting_asr.settings import load_config


def test_upload_result_edit_conflict_and_retry(tmp_path):
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
        response = client.post("/api/jobs", files={"file": ("../../x.wav", b"audio fixture")})
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert client.get(f"/api/jobs/{job_id}").json()["filename"] == "x.wav"
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
