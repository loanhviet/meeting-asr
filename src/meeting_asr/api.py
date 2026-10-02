"""Local demo API: durable jobs, revisioned edits, and one inference worker."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from meeting_asr.jobs import JobStore, JobWorker, RevisionConflict, new_job_id
from meeting_asr.pipeline import project_path, run_pipeline
from meeting_asr.settings import load_config

MAX_UPLOAD = 200 * 1024 * 1024


class TurnEdit(BaseModel):
    text: str | None = Field(default=None, max_length=50000)
    speaker_name: str | None = Field(default=None, min_length=1, max_length=100)
    speaker_id: str | None = Field(default=None, min_length=1, max_length=100)
    reviewed: bool = True
    expected_revision: int | None = Field(default=None, ge=0)


class SpeakerMerge(BaseModel):
    source_speaker: str = Field(min_length=1, max_length=100)
    target_speaker: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)


class SummaryRequest(BaseModel):
    template: Literal["project", "standup", "customer"] = "project"


def public_job(job):
    return {
        key: job[key]
        for key in (
            "id",
            "filename",
            "status",
            "stage",
            "progress",
            "error",
            "created",
            "revision",
            "summary_error",
        )
    }


def create_app(config=None, root=None, *, processor=run_pipeline, start_worker=True):
    config = (
        load_config(os.getenv("MEETING_CONFIG"))
        if config is None and os.getenv("MEETING_CONFIG")
        else (load_config() if config is None else config)
    )
    store = JobStore(root or project_path(config["paths"]["results_dir"]) / "jobs")
    worker = JobWorker(store, config, processor)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            if start_worker:
                worker.stop()

    app = FastAPI(title="Meeting Minutes ASR", lifespan=lifespan)
    app.state.store, app.state.worker = store, worker
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def not_ready(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"detail": "Result is not ready"})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "llm_enabled": bool(config["llm"]["enabled"])}

    @app.get("/api/jobs")
    def list_jobs():
        return [public_job(job) for job in store.list_jobs()]

    @app.post("/api/jobs", status_code=202)
    async def upload(file: Annotated[UploadFile, File()]):
        filename = Path(file.filename or "audio").name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".wav", ".mp3", ".m4a"}:
            raise HTTPException(415, "Supported audio: WAV, MP3, M4A")
        job_id = new_job_id()
        folder = store.root / job_id
        folder.mkdir()
        temporary, source = folder / "upload.part", folder / f"audio{suffix}"
        size = 0
        try:
            with temporary.open("xb") as handle:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, "Maximum upload is 200 MB")
                    handle.write(chunk)
            if size == 0:
                raise HTTPException(400, "Audio file is empty")
            temporary.replace(source)
        finally:
            await file.close()
            if temporary.exists():
                temporary.unlink()
        store.create(job_id, filename, source)
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def status(job_id: str):
        return public_job(store.get(job_id))

    @app.get("/api/jobs/{job_id}/result")
    def result(job_id: str):
        return store.result(job_id)

    @app.get("/api/jobs/{job_id}/audio")
    def audio(job_id: str):
        job = store.get(job_id)
        return FileResponse(job["source"], filename=job["filename"])

    @app.patch("/api/jobs/{job_id}/turns/{turn_id}")
    def edit(job_id: str, turn_id: str, update: TurnEdit):
        try:
            return store.edit(job_id, turn_id, **update.model_dump())
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/jobs/{job_id}/history")
    def history(job_id: str):
        return store.history(job_id)

    @app.post("/api/jobs/{job_id}/speakers/merge")
    def merge(job_id: str, update: SpeakerMerge):
        try:
            return store.merge_speakers(job_id, **update.model_dump())
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry(job_id: str):
        try:
            store.retry(job_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"job_id": job_id}

    @app.post("/api/jobs/{job_id}/summary", status_code=202)
    def regenerate(job_id: str, options: SummaryRequest | None = None):
        job = store.get(job_id)
        store.result(job_id)
        if job["status"] not in {"complete", "failed"}:
            raise HTTPException(409, "Job is already running")
        if not config["llm"]["enabled"]:
            raise HTTPException(409, "Configure and enable LLM summarization first")
        store.update(
            job_id,
            status="queued",
            stage="queued",
            kind="summary",
            progress=0,
            error=None,
            summary_template=options.template if options else "project",
        )
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}/export")
    def export(job_id: str, fmt: str = "md"):
        from meeting_asr.export import export_result

        try:
            content, media_type = export_result(store.result(job_id), fmt)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return Response(
            content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="meeting_{job_id}.{fmt}"',
            },
        )

    return app
