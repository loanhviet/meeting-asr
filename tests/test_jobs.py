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


def review_fixture(tmp_path):
    store = JobStore(tmp_path)
    job_id = new_job_id()
    store.create(job_id, "meeting.wav", tmp_path / "audio.wav")
    turns = [
        Turn("a", 0, 2, "A", "Xin chào", [], flagged=True),
        Turn("b", 2, 4, "B", "Tôi nhận kiểm thử", []),
        Turn("c", 4, 6, "B", "Gửi báo cáo", []),
    ]
    minutes = MeetingMinutes(
        "x",
        6,
        2,
        turns,
        summary="Kế hoạch",
        summary_points=[{"text": "Kế hoạch", "source_turn_ids": ["a"], "uncertain": True}],
    )
    write_minutes_json(store.artifact_dir(job_id) / "minutes.json", minutes)
    store.update(job_id, status="complete", summary_revision=0)
    return store, job_id


def test_reassign_merge_history_and_revision_conflicts_persist(tmp_path):
    store, job_id = review_fixture(tmp_path)
    view = store.edit(job_id, "a", speaker_id="B", reviewed=False, expected_revision=0)
    assert view["edited"]["turns"][0]["speaker_id"] == "B"
    assert view["original"]["turns"][0]["speaker"] == "A"
    assert view["summary_stale"]
    store.edit(job_id, "a", speaker_name="Bình", reviewed=False, expected_revision=1)
    view = store.merge_speakers(job_id, "B", "A", expected_revision=2)
    assert view["edited"]["num_speakers"] == 1
    assert {t["speaker_id"] for t in view["edited"]["turns"]} == {"A"}
    persisted = JobStore(tmp_path)
    assert persisted.result(job_id)["revision"] == 3
    assert persisted.history(job_id)[0]["changes"]["turn_ids"] == ["a", "b", "c"]
    assert persisted.history(job_id)[1]["changes"]["speaker_name"]["after"] == "Bình"
    with pytest.raises(RevisionConflict):
        store.merge_speakers(job_id, "A", "B", expected_revision=0)
    with pytest.raises(ValueError, match="unknown"):
        store.edit(job_id, "a", speaker_id="invented", expected_revision=3)
    assert store.result(job_id)["revision"] == 3
    assert len(store.history(job_id)) == 3


def test_review_only_edit_updates_evidence_without_invalidating_summary(tmp_path):
    store, job_id = review_fixture(tmp_path)
    view = store.edit(job_id, "a", reviewed=True, expected_revision=0)
    assert not view["summary_stale"]
    assert not view["edited"]["summary_points"][0]["needs_review"]
    store.edit(job_id, "a", text="Đổi nội dung", expected_revision=1)
    assert store.edit(job_id, "a", reviewed=True, expected_revision=2)["summary_stale"]


def test_legacy_database_migration_preserves_jobs(tmp_path):
    import sqlite3

    store, job_id = review_fixture(tmp_path)
    with sqlite3.connect(store.database) as db:
        db.execute("ALTER TABLE jobs DROP COLUMN summary_template")
        db.execute("DROP TABLE edit_events")
        db.execute("DROP TABLE speaker_assignments")
    migrated = JobStore(tmp_path)
    assert migrated.result(job_id)["original"]["turns"][0]["text"] == "Xin chào"
    assert migrated.result(job_id)["summary_template"] == "project"
    assert migrated.history(job_id) == []


def test_summary_worker_uses_corrected_turns_and_keeps_concurrent_edit_stale(tmp_path, monkeypatch):
    store, job_id = review_fixture(tmp_path)
    store.edit(
        job_id, "a", speaker_id="B", text="Bình nhận kiểm thử", reviewed=True, expected_revision=0
    )
    store.update(job_id, kind="summary", status="queued", summary_template="standup")

    class Summarizer:
        def __init__(self, options, cache):
            assert options["template"] == "standup"

        def summarize(self, turns):
            assert turns[0].speaker == "B"
            assert turns[0].text == "Bình nhận kiểm thử"
            assert not turns[0].flagged
            store.edit(job_id, "b", text="Thay đổi trong lúc tóm tắt", expected_revision=1)
            return {
                "summary": "Bình nhận kiểm thử",
                "topics": [],
                "summary_points": [
                    {"text": "Kiểm thử", "source_turn_ids": ["a"], "uncertain": False}
                ],
                "decisions": [],
                "action_items": [],
            }

    monkeypatch.setattr("meeting_asr.summarize.Summarizer", Summarizer)
    JobWorker(store, load_config()).process_one(job_id)
    view = store.result(job_id)
    assert store.get(job_id)["status"] == "complete"
    assert view["summary_stale"]
    assert view["summary_revision"] == 1
    assert view["revision"] == 2
    assert view["edited"]["summary_points"][0]["sources"][0]["speaker"] == "B"
