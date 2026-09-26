import json
import threading

import pytest

from meeting_asr.io import write_minutes_json
from meeting_asr.jobs import JobStore, JobWorker, RevisionConflict, new_job_id
from meeting_asr.models import MeetingMinutes, Turn, Utterance
from meeting_asr.settings import load_config


def test_edits_persist_without_overwriting_original_and_mark_summary_stale(tmp_path):
    store = JobStore(tmp_path)
    job_id = new_job_id()
    store.create(job_id, "meeting.wav", tmp_path / "audio.wav")
    u = Utterance(0, 2, "A", "xin chào")
    original = MeetingMinutes(
        "x", 2, 1, [Turn("0", 0, 2, "A", "Xin chào", [u], flagged=True)], summary="Tóm tắt ban đầu"
    )
    write_minutes_json(store.artifact_dir(job_id) / "minutes.json", original)
    store.update(job_id, status="complete", summary_revision=0)
    view = store.edit(job_id, "0", text="đã sửa", speaker_name="An", expected_revision=0)
    assert view["summary_stale"]
    assert view["edited"]["turns"][0]["speaker"] == "An"
    assert view["edited"]["turns"][0]["flagged"]
    assert view["original"]["turns"][0]["text"] == "Xin chào"
    assert JobStore(tmp_path).result(job_id)["revision"] == 1
    with pytest.raises(RevisionConflict):
        store.edit(job_id, "0", text="conflict", expected_revision=0)
    assert (
        json.loads((store.artifact_dir(job_id) / "minutes.json").read_text())["summary"]
        == "Tóm tắt ban đầu"
    )


def test_worker_records_failure_and_retries_from_same_source(tmp_path):
    store = JobStore(tmp_path)
    job_id = new_job_id()
    store.create(job_id, "x.wav", tmp_path / "x.wav")

    def fail(*args, **kwargs):
        raise RuntimeError("fixture failure")

    worker = JobWorker(store, load_config(), fail)
    worker.process_one(job_id)
    assert store.get(job_id)["status"] == "failed"
    store.retry(job_id)
    assert store.get(job_id)["status"] == "queued"


def test_worker_recovers_interrupted_job_on_restart(tmp_path):
    store = JobStore(tmp_path)
    job_id = new_job_id()
    store.create(job_id, "x.wav", tmp_path / "x.wav")
    store.update(job_id, status="running", stage="M3")
    processed = threading.Event()

    def processor(source, config, out, progress):
        write_minutes_json(out / "minutes.json", MeetingMinutes("x", 6, 0, []))
        processed.set()

    worker = JobWorker(store, load_config(), processor)
    worker.start()
    try:
        assert processed.wait(3)
    finally:
        worker.stop()
    assert store.get(job_id)["status"] == "complete"
