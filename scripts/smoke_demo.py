"""Exercise a running local API using real models and synthetic demo uploads.

Adds three persistent jobs, edits one predicted turn per job, and saves exports.
No mock inference and no external LLM requests. Start `meeting-asr serve` first.
"""

import argparse
import json
import time
from pathlib import Path

import httpx


def checked(response):
    response.raise_for_status()
    return response


def smoke(base_url, samples, out, timeout=900):
    samples, destination = Path(samples), Path(out)
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    with httpx.Client(base_url=base_url, timeout=60) as client:
        health = checked(client.get("/api/health")).json()
        if health.get("llm_enabled"):
            raise RuntimeError("Disable LLM for this smoke test to avoid external provider calls")
        for name in ("demo_clean.wav", "demo_noisy.mp3", "demo_overlap.m4a"):
            with (samples / name).open("rb") as handle:
                response = checked(client.post("/api/jobs", files={"file": (name, handle)}))
            job_id = response.json()["job_id"]
            print(f"Uploaded {name}: {job_id}", flush=True)
            deadline, last_stage = time.monotonic() + timeout, None
            while True:
                job = checked(client.get(f"/api/jobs/{job_id}")).json()
                if job["stage"] != last_stage:
                    print(f"{name}: {job['stage']}", flush=True)
                    last_stage = job["stage"]
                if job["status"] == "failed":
                    raise RuntimeError(f"Demo job failed: {job_id}; inspect local job logs")
                if job["status"] == "complete":
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Job still running: {job_id}; not cancelled")
                time.sleep(1)
            view = checked(client.get(f"/api/jobs/{job_id}/result")).json()
            turns = view["edited"]["turns"]
            if not turns or not any(t["text"].strip() for t in turns):
                raise RuntimeError(f"No speech transcript for {name}")
            turn = turns[0]
            original = turn["text"]
            update = {
                "text": original + " [đã kiểm tra demo]",
                "reviewed": True,
                "speaker_name": "Người nói demo",
                "expected_revision": view["revision"],
            }
            checked(client.patch(f"/api/jobs/{job_id}/turns/{turn['turn_id']}", json=update))
            # Refetch rather than trusting the PATCH response: persistence matters.
            edited = checked(client.get(f"/api/jobs/{job_id}/result")).json()
            first = edited["edited"]["turns"][0]
            assert first["text"] == update["text"] and first["reviewed"]
            assert first["speaker"] == "Người nói demo"
            assert edited["original"]["turns"][0]["text"] == original
            conflict = client.patch(f"/api/jobs/{job_id}/turns/{turn['turn_id']}", json=update)
            assert conflict.status_code == 409
            audio = checked(client.get(f"/api/jobs/{job_id}/audio"))
            assert len(audio.content) > 1000
            exports = {}
            for fmt in ("md", "srt", "pdf"):
                response = checked(client.get(f"/api/jobs/{job_id}/export", params={"fmt": fmt}))
                if fmt == "pdf":
                    assert response.content.startswith(b"%PDF-")
                else:
                    assert update["text"] in response.text
                path = destination / f"{Path(name).stem}.{fmt}"
                path.write_bytes(response.content)
                exports[fmt] = str(path.resolve())
            rows.append(
                {
                    "file": name,
                    "job_id": job_id,
                    "duration_sec": view["edited"]["duration"],
                    "num_speakers": view["edited"]["num_speakers"],
                    "turns": len(turns),
                    "revision": edited["revision"],
                    "exports": exports,
                    "checks": "real inference, audio retrieval, persistent edit/name, immutable original, revision conflict, exports",
                }
            )
            (destination / "smoke.json").write_text(
                json.dumps({"synthetic": True, "jobs": rows}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"PASS {name}", flush=True)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", default="data/demo")
    parser.add_argument("--out", default="results/demo-api-smoke")
    arguments = parser.parse_args()
    smoke(arguments.base_url, arguments.samples, arguments.out)
