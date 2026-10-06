"""Durable SQLite jobs and edits, processed by one local worker."""

from __future__ import annotations

import copy
import json
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

from meeting_asr.io import minutes_from_dict
from meeting_asr.pipeline import project_path, run_pipeline
from meeting_asr.summarize import resolve_evidence


class RevisionConflict(ValueError):
    pass


class JobStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "jobs.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, source TEXT NOT NULL,
                    status TEXT NOT NULL, stage TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
                    error TEXT, created REAL NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
                    summary_revision INTEGER, kind TEXT NOT NULL DEFAULT 'pipeline',
                    summary_json TEXT, summary_error TEXT
                );
                CREATE TABLE IF NOT EXISTS edits (
                    job_id TEXT NOT NULL, turn_id TEXT NOT NULL, text TEXT,
                    reviewed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (job_id, turn_id)
                );
                CREATE TABLE IF NOT EXISTS speaker_assignments (
                    job_id TEXT NOT NULL, turn_id TEXT NOT NULL, speaker TEXT NOT NULL,
                    PRIMARY KEY (job_id, turn_id)
                );
                CREATE TABLE IF NOT EXISTS edit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, kind TEXT NOT NULL, created REAL NOT NULL,
                    changes TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS speakers (
                    job_id TEXT NOT NULL, speaker TEXT NOT NULL, name TEXT NOT NULL,
                    PRIMARY KEY (job_id, speaker)
                );
                CREATE TABLE IF NOT EXISTS ask_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, created REAL NOT NULL,
                    request_key TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(job_id, request_key)
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            if "summary_template" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN summary_template TEXT DEFAULT 'project'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, job_id, filename, source):
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs (id, filename, source, status, stage, created) "
                "VALUES (?, ?, ?, 'queued', 'queued', ?)",
                (job_id, filename, str(source), time.time()),
            )
        return self.get(job_id)

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("job not found")
        return dict(row)

    def list_jobs(self):
        with self.connect() as db:
            return [
                dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 50")
            ]

    def update(self, job_id, **fields):
        allowed = {
            "status",
            "stage",
            "progress",
            "error",
            "summary_revision",
            "kind",
            "summary_json",
            "summary_error",
            "summary_template",
        }
        if not fields or set(fields) - allowed:
            raise ValueError("invalid job update")
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET " + ", ".join(f"{k} = ?" for k in fields) + " WHERE id = ?",
                (*fields.values(), job_id),
            )

    def artifact_dir(self, job_id):
        self.get(job_id)
        return self.root / job_id / "artifacts"

    def result(self, job_id):
        with self.connect() as db:
            # A single read snapshot keeps revision, names and turn edits consistent.
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("job not found")
            job = dict(row)
            path = self.root / job_id / "artifacts" / "minutes.json"
            if not path.is_file():
                raise FileNotFoundError("job result is not ready")
            original = json.loads(path.read_text(encoding="utf-8"))
            edited = copy.deepcopy(original)
            edits = {
                row["turn_id"]: dict(row)
                for row in db.execute("SELECT * FROM edits WHERE job_id = ?", (job_id,))
            }
            assignments = {
                row["turn_id"]: row["speaker"]
                for row in db.execute(
                    "SELECT * FROM speaker_assignments WHERE job_id = ?", (job_id,)
                )
            }
            names = {
                row["speaker"]: row["name"]
                for row in db.execute("SELECT * FROM speakers WHERE job_id = ?", (job_id,))
            }
        for turn in edited["turns"]:
            edit = edits.get(turn["turn_id"], {})
            turn["original_text"] = turn["text"]
            turn["original_speaker"] = turn["speaker"]
            turn["text"] = edit.get("text") if edit.get("text") is not None else turn["text"]
            turn["speaker_id"] = assignments.get(turn["turn_id"], turn["speaker"])
            turn["speaker"] = names.get(turn["speaker_id"], turn["speaker_id"])
            turn["reviewed"] = bool(edit.get("reviewed", False))
        edited["num_speakers"] = len({t["speaker_id"] for t in edited["turns"]})
        if job["summary_json"]:
            edited.update(json.loads(job["summary_json"]))
        stale = bool(
            (original.get("summary") or job["summary_json"])
            and job["summary_revision"] is not None
            and job["summary_revision"] != job["revision"]
        )
        evidence = resolve_evidence(edited, edited["turns"])
        for field in ("summary_points", "decisions", "action_items"):
            edited[field] = evidence.get(field, [])
        # Never present an old summary as current in exported artifacts.
        return {
            "original": original,
            "edited": edited,
            "revision": job["revision"],
            "summary_stale": stale,
            "summary_error": job["summary_error"],
            "speaker_names": names,
            "summary_revision": job["summary_revision"],
            "summary_template": job["summary_template"] or "project",
            "summary_grounded": bool(edited.get("summary_points")),
        }

    def answers(self, job_id, request_key=None):
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT revision FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("job not found")
            revision = row[0]
            query = "SELECT * FROM ask_answers WHERE job_id=?"
            args = [job_id]
            if request_key is not None:
                query += " AND request_key=?"
                args.append(request_key)
            rows = db.execute(query + " ORDER BY created DESC, id DESC LIMIT 20", args).fetchall()
        return [
            {
                **json.loads(row["payload"]),
                "id": row["id"],
                "revision": row["revision"],
                "created": row["created"],
                "stale": row["revision"] != revision,
            }
            for row in rows
        ]

    def save_answer(self, job_id, revision, request_key, payload):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._check_revision(db, job_id, revision)
            db.execute(
                "INSERT INTO ask_answers (job_id, revision, created, request_key, payload) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(job_id, request_key) "
                "DO UPDATE SET created=excluded.created",
                (
                    job_id,
                    revision,
                    time.time(),
                    request_key,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        return self.answers(job_id, request_key)[0]

    def edit(
        self,
        job_id,
        turn_id,
        *,
        text=None,
        reviewed=True,
        speaker_name=None,
        expected_revision=None,
        speaker_id=None,
    ):
        original = self.result(job_id)["original"]
        turn = next((t for t in original["turns"] if t["turn_id"] == turn_id), None)
        if turn is None:
            raise KeyError("turn not found")
        valid_speakers = {t["speaker"] for t in original["turns"]}
        if speaker_id is not None and speaker_id not in valid_speakers:
            raise ValueError("unknown speaker ID")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision = self._check_revision(db, job_id, expected_revision)
            assignment = db.execute(
                "SELECT speaker FROM speaker_assignments WHERE job_id=? AND turn_id=?",
                (job_id, turn_id),
            ).fetchone()
            current_speaker = assignment[0] if assignment else turn["speaker"]
            previous = db.execute(
                "SELECT text, reviewed FROM edits WHERE job_id=? AND turn_id=?", (job_id, turn_id)
            ).fetchone()
            previous_text = previous[0] if previous and previous[0] is not None else turn["text"]
            previous_reviewed = bool(previous[1]) if previous else False
            target = speaker_id or current_speaker
            old_name = db.execute(
                "SELECT name FROM speakers WHERE job_id=? AND speaker=?", (job_id, target)
            ).fetchone()
            if speaker_name is not None:
                if not speaker_name.strip():
                    raise ValueError("speaker name must not be blank")
                speaker_name = speaker_name.strip()
                db.execute(
                    "INSERT INTO speakers VALUES (?, ?, ?) ON CONFLICT(job_id, speaker) "
                    "DO UPDATE SET name=excluded.name",
                    (job_id, target, speaker_name),
                )
            if speaker_id is not None:
                db.execute(
                    "INSERT INTO speaker_assignments VALUES (?, ?, ?) "
                    "ON CONFLICT(job_id, turn_id) DO UPDATE SET speaker=excluded.speaker",
                    (job_id, turn_id, speaker_id),
                )
            db.execute(
                "INSERT INTO edits VALUES (?, ?, ?, ?) ON CONFLICT(job_id, turn_id) "
                "DO UPDATE SET text=COALESCE(excluded.text, edits.text), reviewed=excluded.reviewed",
                (job_id, turn_id, text, int(reviewed)),
            )
            content_changed = (
                (text is not None and text != previous_text)
                or target != current_speaker
                or (
                    speaker_name is not None
                    and speaker_name != (old_name[0] if old_name else target)
                )
            )
            changes = {
                "turn_id": turn_id,
                "before": {
                    "text": previous_text,
                    "speaker_id": current_speaker,
                    "reviewed": previous_reviewed,
                },
                "after": {
                    "text": text if text is not None else previous_text,
                    "speaker_id": target,
                    "reviewed": reviewed,
                },
            }
            if speaker_name is not None:
                changes["speaker_name"] = {
                    "speaker_id": target,
                    "before": old_name[0] if old_name else target,
                    "after": speaker_name,
                }
            self._record_edit(db, job_id, revision, "turn_edit", changes, content_changed)
        return self.result(job_id)

    @staticmethod
    def _check_revision(db, job_id, expected_revision):
        row = db.execute("SELECT revision FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("job not found")
        revision = row[0]
        if expected_revision is not None and expected_revision != revision:
            raise RevisionConflict("transcript changed; reload before saving")
        return revision

    @staticmethod
    def _record_edit(db, job_id, revision, kind, changes, content_changed=True):
        # Review-only changes preserve a current summary, without reviving a stale one.
        if not content_changed:
            db.execute(
                "UPDATE jobs SET summary_revision=? WHERE id=? AND summary_revision=?",
                (revision + 1, job_id, revision),
            )
        db.execute("UPDATE jobs SET revision=revision+1 WHERE id=?", (job_id,))
        db.execute(
            "INSERT INTO edit_events (job_id, revision, kind, created, changes) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, revision + 1, kind, time.time(), json.dumps(changes, ensure_ascii=False)),
        )

    def merge_speakers(self, job_id, source_speaker, target_speaker, expected_revision=None):
        original = self.result(job_id)["original"]
        known = {t["speaker"] for t in original["turns"]}
        if source_speaker == target_speaker or {source_speaker, target_speaker} - known:
            raise ValueError("merge requires two distinct known speaker IDs")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision = self._check_revision(db, job_id, expected_revision)
            assignments = {
                row["turn_id"]: row["speaker"]
                for row in db.execute("SELECT * FROM speaker_assignments WHERE job_id=?", (job_id,))
            }
            affected = [
                t["turn_id"]
                for t in original["turns"]
                if assignments.get(t["turn_id"], t["speaker"]) == source_speaker
            ]
            if not affected:
                raise ValueError("source speaker has no turns")
            for turn_id in affected:
                db.execute(
                    "INSERT INTO speaker_assignments VALUES (?, ?, ?) "
                    "ON CONFLICT(job_id, turn_id) DO UPDATE SET speaker=excluded.speaker",
                    (job_id, turn_id, target_speaker),
                )
            self._record_edit(
                db,
                job_id,
                revision,
                "speaker_merge",
                {
                    "source_speaker": source_speaker,
                    "target_speaker": target_speaker,
                    "turn_ids": affected,
                },
            )
        return self.result(job_id)

    def history(self, job_id):
        self.get(job_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM edit_events WHERE job_id=? ORDER BY revision DESC LIMIT 100",
                (job_id,),
            ).fetchall()
        return [{**dict(row), "changes": json.loads(row["changes"])} for row in rows]

    def retry(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("job not found")
            if row[0] != "failed":
                raise ValueError("only failed jobs can be retried")
            db.execute(
                "UPDATE jobs SET status='queued', stage='queued', progress=0, error=NULL "
                "WHERE id=?",
                (job_id,),
            )


class JobWorker:
    def __init__(self, store: JobStore, config, processor=run_pipeline):
        self.store, self.config, self.processor = store, config, processor
        self.stopped = threading.Event()
        self.lock = FileLock(str(store.root / "worker.lock"))
        self.thread = None

    def start(self):
        self.lock.acquire(timeout=0)
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET status='queued', stage='queued' WHERE status='running'")
        self.thread = threading.Thread(target=self._loop, name="meeting-worker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                return  # Keep the process lock while inference still owns the GPU.
        self.lock.release()

    def _loop(self):
        while not self.stopped.is_set():
            with self.store.connect() as db:
                row = db.execute(
                    "SELECT id FROM jobs WHERE status='queued' ORDER BY created LIMIT 1"
                ).fetchone()
            if row:
                self.process_one(row[0])
            else:
                self.stopped.wait(0.2)

    def process_one(self, job_id):
        job = self.store.get(job_id)
        self.store.update(job_id, status="running", error=None)
        try:
            destination = self.store.artifact_dir(job_id)
            if job["kind"] == "summary":
                from meeting_asr.summarize import Summarizer

                view = self.store.result(job_id)
                edited = copy.deepcopy(view["edited"])
                for turn in edited["turns"]:
                    turn["flagged"] = turn["flagged"] and not turn.get("reviewed", False)
                    for field in ("original_text", "original_speaker", "speaker_id", "reviewed"):
                        turn.pop(field, None)
                minutes = minutes_from_dict(edited)
                self.store.update(job_id, stage="M6", progress=0.9)
                result = Summarizer(
                    {**self.config["llm"], "template": job["summary_template"] or "project"},
                    project_path(self.config["paths"]["cache_dir"]) / "summaries",
                ).summarize(minutes.turns)
                self.store.update(
                    job_id,
                    summary_json=json.dumps(result, ensure_ascii=False),
                    summary_revision=view["revision"],
                    summary_error=None,
                )
            else:
                self.processor(
                    job["source"],
                    self.config,
                    destination,
                    progress=lambda stage, fraction: self.store.update(
                        job_id, stage=stage, progress=fraction
                    ),
                )
                status_path = destination / "summary_status.json"
                summary_status = json.loads(status_path.read_text()) if status_path.exists() else {}
                self.store.update(
                    job_id,
                    summary_revision=job["revision"],
                    summary_error=summary_status.get("error"),
                )
            self.store.update(job_id, status="complete", stage="complete", progress=1)
        except Exception as exc:
            logging.getLogger(__name__).exception("Meeting job %s failed", job_id)
            self.store.update(job_id, status="failed", stage="failed", error=str(exc))


def new_job_id():
    return uuid.uuid4().hex
