"""Generate spoken Vietnamese fixtures, evaluate retrieval, or serve an isolated demo.

Fixture mode reads scripted gold answers and NEVER claims to evaluate an LLM.
Configured mode uses the project's selected LLM provider on synthetic data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from fastapi.responses import JSONResponse

from meeting_asr.api import create_app
from meeting_asr.ask import AskMeeting
from meeting_asr.data_gen.demo import generate_demo
from meeting_asr.evaluation.ask import evaluate_questions
from meeting_asr.io import read_transcript_json, write_minutes_json
from meeting_asr.models import MeetingMinutes, Turn
from meeting_asr.settings import load_config

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "tests/fixtures/askmeeting.json"


def scripted_turns(dataset):
    return [
        {
            "turn_id": f"t{i:02d}",
            "start": i * 10.0,
            "end": i * 10.0 + 8,
            "speaker": dataset["speakers"][i % 2],
            "text": text,
            "flagged": i == 5,
            "reviewed": False,
        }
        for i, text in enumerate(dataset["script"])
    ]


class FixtureProvider:
    def __init__(self, dataset):
        self.cases = {case["question"]: case for case in dataset["questions"]}
        self.script = {f"t{i:02d}": text for i, text in enumerate(dataset["script"])}

    def complete(self, prompt, model):
        data = json.loads(prompt.split("\n")[-1])
        case = self.cases.get(data["question"])
        context = {turn["turn_id"]: turn["text"] for turn in data["transcript"]}
        if (
            case is None
            or case["status"] == "not_found"
            or any(context.get(source) != self.script[source] for source in case["source_turn_ids"])
        ):
            return json.dumps({"status": "not_found", "answer_points": []})
        return json.dumps(
            {
                "status": "found",
                "answer_points": [
                    {
                        "text": case["answer"],
                        "source_turn_ids": case["source_turn_ids"],
                        "uncertain": False,
                    }
                ],
            },
            ensure_ascii=False,
        )


def load_turns(dataset, directory):
    reference = directory / "audio/demo_clean.json"
    if not reference.exists():
        return scripted_turns(dataset)
    document = read_transcript_json(reference)
    if [u.text for u in document.utterances] != dataset["script"]:
        raise ValueError("Generated audio reference does not match the selected script")
    return [
        {**turn, "start": utterance.start, "end": utterance.end}
        for turn, utterance in zip(scripted_turns(dataset), document.utterances, strict=True)
    ]


def demo_app(dataset, directory, mode):
    audio = directory / "audio/demo_clean.wav"
    if not audio.exists():
        raise FileNotFoundError("Run generate first; spoken audio is required to serve the demo")
    turns = load_turns(dataset, directory)
    config = load_config()
    factory = None
    if mode == "fixture":
        config["llm"].update(enabled=True, model="scripted-functional-fixture", provider="http")
        factory = lambda: AskMeeting(config["llm"], directory / "cache", FixtureProvider(dataset))
    elif not config["llm"]["enabled"]:
        raise ValueError("Configure and enable the real LLM provider before using configured mode")
    app = create_app(config, directory / "jobs", start_worker=False, answerer_factory=factory)

    @app.middleware("http")
    async def isolated_demo(request, call_next):
        if request.url.path == "/api/health":
            return JSONResponse(
                {"status": "ok", "llm_enabled": False, "ask_enabled": True, "demo_provider": mode}
            )
        if request.method == "POST" and (
            request.url.path == "/api/jobs" or request.url.path.endswith(("/summary", "/retry"))
        ):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Demo hỏi đáp dùng bản ghi tổng hợp có sẵn. Dùng API chính để tải và xử lý bản ghi mới."
                },
            )
        return await call_next(request)

    store = app.state.store
    if not store.list_jobs():
        store.create("ask-demo", f"Họp tổng hợp — AskMeeting ({mode}).wav", audio)
        write_minutes_json(
            store.artifact_dir("ask-demo") / "minutes.json",
            MeetingMinutes(
                "ask-demo",
                turns[-1]["end"] + 0.5,
                2,
                [
                    Turn(
                        t["turn_id"],
                        t["start"],
                        t["end"],
                        t["speaker"],
                        t["text"],
                        [],
                        flagged=t["flagged"],
                    )
                    for t in turns
                ],
            ),
        )
        store.update("ask-demo", status="complete", stage="complete", progress=1)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "evaluate", "serve"])
    parser.add_argument("--directory", type=Path, default=ROOT / "results/askmeeting-demo")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--provider", choices=["none", "fixture", "configured"], default="none")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    args.directory.mkdir(parents=True, exist_ok=True)
    if args.command == "generate":
        asyncio.run(
            generate_demo(
                args.directory / "audio", ROOT / ".cache/ask-tts", texts=dataset["script"]
            )
        )
        (args.directory / "dataset.json").write_text(
            json.dumps(
                {**dataset, "turns": load_turns(dataset, args.directory)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    elif args.command == "evaluate":
        answerer = None
        if args.provider != "none":
            options = load_config()["llm"]
            provider = None
            if args.provider == "fixture":
                options = {"provider": "http", "model": "scripted-functional-fixture"}
                provider = FixtureProvider(dataset)
            elif not options["enabled"]:
                raise ValueError("Configure and enable LLM before running provider evaluation")
            answerer = AskMeeting(options, args.directory / "cache", provider)
        report = evaluate_questions(dataset, load_turns(dataset, args.directory), answerer)
        report["provider_mode"] = args.provider
        report["timing"] = (
            "generated TTS envelopes"
            if (args.directory / "audio/demo_clean.json").exists()
            else "placeholder scripted timestamps"
        )
        (args.directory / f"evaluation-{args.provider}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False, indent=2
            )
        )
    else:
        import uvicorn

        if args.provider == "none":
            raise ValueError("Serve requires explicit --provider fixture or configured")
        uvicorn.run(
            demo_app(dataset, args.directory, args.provider), host="127.0.0.1", port=args.port
        )


if __name__ == "__main__":
    main()
