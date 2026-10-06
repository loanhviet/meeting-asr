# Vietnamese Meeting Minutes ASR

A local application that turns Vietnamese meeting recordings into speaker-attributed transcripts, prioritizes segments for review, and creates cited minutes and meeting answers. It combines pretrained models with a CLI, research evaluation tools, a FastAPI/SQLite backend and a Next.js interface.

## Features

- Pyannote and ECAPA + overlap detector backends, followed by PhoWhisper-medium.
- Confidence scoring with ASR-only, no-diarization, full and random ablations.
- Audio playback, per-turn transcript/speaker edits, speaker merging, review history and revision conflict detection.
- Cited summaries, decisions and action items; meeting questions with audio sources. Changed transcripts make previous outputs stale.
- Markdown, SRT and Unicode PDF exports; stage caching and restartable jobs.
- Versioned speech annotations, an offline listening/review page, speech-based simulation and dataset readiness checks.
- RQ1–RQ3 evaluation and benchmark reports including per-stage time and peak allocated GPU memory.

See the [architecture](ARCHITECTURE.md), [acceptance workflow](ACCEPTANCE.md) and [current evidence and limitations](RELEASE_STATUS.md).

## Run locally

Python 3.11/3.12, uv and FFmpeg are required. Configure `.env` from `.env.example`; accept the gated Pyannote model terms and supply a Hugging Face read token. LLM summaries/questions require a separately selected provider, model, endpoint and key.

```bash
uv sync --locked --extra dev --extra inference --extra api --extra demo --extra annotation
uv run --no-sync meeting-asr doctor
uv run --no-sync meeting-asr serve
# In a second terminal:
cd web
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`. On a 4 GB GPU, start with ASR batch size 1. For containers, run `docker compose up --build -d`; the default image uses CPU Torch wheels. NVIDIA GPU deployment uses `docker compose -f compose.yaml -f compose.gpu.yaml up --build -d` and requires NVIDIA Container Toolkit. Model downloads and the GPU image require additional disk space.

## Validation and scope

```bash
MEETING_LLM_ENABLED=false uv run --no-sync pytest -q
uv run --no-sync ruff check src/meeting_asr tests
uv build
cd web
npm run format:check
npm run typecheck
npm run build
npm run test:e2e
```

Software tests use deterministic fixtures; they do not establish model quality. The speech labels and main experimental matrices generated locally are drafts pending listening review and adequate recording durations. Synthetic conversations support functional evaluation, while real meeting acceptance remains necessary. The project uses pretrained inference rather than model fine-tuning; it currently serves a local, single-worker demo without multi-user authentication.

Audio, model caches, credentials and generated reports remain outside Git. Local `docs/` also requires a separate backup. The Vietnamese [testing guide](TESTING.md) provides environment and reproduction details.
