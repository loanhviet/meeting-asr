"""Evaluate supplied meeting transcripts and collect explicit semantic reviews."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

from meeting_asr.ask import AskMeeting
from meeting_asr.evaluation.ask import evaluate_questions
from meeting_asr.io import _atomic_text, minutes_from_dict
from meeting_asr.pipeline import run_pipeline
from meeting_asr.runtime import file_sha256, git_commit
from meeting_asr.settings import config_hash
from meeting_asr.summarize import TEMPLATES, Summarizer


def llm_readiness(options):
    """Validate selected provider configuration without sending requests or keys."""
    fields = {
        "provider": os.getenv("MEETING_LLM_PROVIDER") or options.get("provider"),
        "model": os.getenv("MEETING_LLM_MODEL") or options.get("model"),
        "base_url": os.getenv("MEETING_LLM_BASE_URL") or options.get("base_url"),
    }
    missing = []
    if fields["provider"] not in {"http", "claude"}:
        missing.append("provider (http or claude)")
    if not fields["model"]:
        missing.append("model")
    if fields["provider"] != "claude" and not fields["base_url"]:
        missing.append("base_url")
    key_env = options.get("api_key_env", "MEETING_LLM_API_KEY")
    if key_env and not os.getenv(key_env):
        missing.append("api_key")
    return {
        "ready": not missing,
        "enabled": bool(options.get("enabled")),
        "provider": fields["provider"],
        "model_configured": bool(fields["model"]),
        "endpoint_configured": bool(fields["base_url"]) or fields["provider"] == "claude",
        "missing": missing,
        "requests_sent": 0,
    }


def meeting_manifest(path):
    path = Path(path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    meetings = payload.get("meetings")
    if not isinstance(meetings, list) or not meetings:
        raise ValueError("acceptance manifest requires meetings")
    seen = set()
    for meeting in meetings:
        identity = meeting.get("id")
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError("meeting IDs must be unique nonempty strings")
        seen.add(identity)
        for field in ("source_url", "license", "audio"):
            if not isinstance(meeting.get(field), str) or not meeting[field].strip():
                raise ValueError(f"meeting {identity} requires {field}")
        for field in ("audio", "minutes", "reference_json", "reference_rttm"):
            if meeting.get(field):
                meeting[field] = str((path.parent / meeting[field]).resolve())
                if not Path(meeting[field]).is_file():
                    raise ValueError(f"meeting {identity}: missing {field} file")
        questions = meeting.get("questions", [])
        if not isinstance(questions, list):
            raise TypeError("meeting questions must be a list")
        ids = set()
        for i, question in enumerate(questions):
            case_id = question.get("id", f"q{i:03d}")
            if not isinstance(case_id, str) or not case_id or case_id in ids:
                raise ValueError("question IDs must be unique nonempty strings")
            ids.add(case_id)
            if question.get("status") not in {"found", "not_found"}:
                raise ValueError("question requires expected status found/not_found")
            if not isinstance(question.get("question"), str) or not question["question"].strip():
                raise ValueError("question requires nonempty question text")
            if question["status"] == "found" and (
                not isinstance(question.get("answer"), str) or not question["answer"].strip()
            ):
                raise ValueError("answerable question requires expected answer text")
            if question["status"] == "not_found" and question.get("answer") not in (None, ""):
                raise ValueError("unanswerable question must have null/empty expected answer")
            sources = question.get("source_turn_ids")
            if not isinstance(sources, list) or not all(isinstance(s, str) and s for s in sources):
                raise ValueError("question requires source_turn_ids")
            if len(set(sources)) != len(sources) or bool(sources) != (
                question["status"] == "found"
            ):
                raise ValueError("expected sources must agree with question status")
    return payload


def evaluate_meetings(
    manifest,
    config,
    out,
    *,
    provider_mode="none",
    run_asr=False,
    answerer_factory=None,
    summarizer_factory=None,
):
    """Default mode runs retrieval only. Configured mode explicitly calls an LLM."""
    if provider_mode not in {"none", "configured"}:
        raise ValueError("provider must be none or configured")
    payload = meeting_manifest(manifest)
    if provider_mode == "configured" and not answerer_factory:
        readiness = llm_readiness(config["llm"])
        if not readiness["ready"]:
            raise ValueError("LLM configuration incomplete: " + ", ".join(readiness["missing"]))
    if not run_asr and any(not m.get("minutes") for m in payload["meetings"]):
        raise ValueError("provide minutes files or pass --run-asr to process the recordings")
    destination = Path(out)
    results, reviews = [], []
    for index, meeting in enumerate(payload["meetings"]):
        folder = destination / f"meeting_{index:03d}"
        if run_asr:
            options = copy.deepcopy(config)
            options["llm"]["enabled"] = False
            run_pipeline(meeting["audio"], options, folder / "pipeline")
            minutes_path = folder / "pipeline/minutes.json"
        else:
            minutes_path = Path(meeting["minutes"])
        raw = json.loads(minutes_path.read_text(encoding="utf-8"))
        raw = raw.get("edited", raw)  # Also accept a saved GET /api/jobs/{id}/result snapshot.
        summary_input = copy.deepcopy(raw)
        for turn in summary_input["turns"]:
            turn["flagged"] = turn["flagged"] and not turn.get("reviewed", False)
            for field in ("original_text", "original_speaker", "speaker_id", "reviewed"):
                turn.pop(field, None)
        minutes = minutes_from_dict(summary_input)
        turns = raw["turns"]
        allowed = {t["turn_id"] for t in turns}
        if any(set(q["source_turn_ids"]) - allowed for q in meeting.get("questions", [])):
            raise ValueError(
                f"meeting {meeting['id']}: gold source IDs do not exist in this transcript"
            )
        answerer = None
        if provider_mode == "configured":
            answerer = (
                answerer_factory()
                if answerer_factory
                else AskMeeting(config["llm"], folder / "ask-cache")
            )
        question_report = evaluate_questions(
            {
                "synthetic": meeting.get("synthetic", False),
                "questions": meeting.get("questions", []),
            },
            turns,
            answerer,
        )
        summaries = {}
        if provider_mode == "configured":
            for template in TEMPLATES:
                try:
                    summarizer = (
                        summarizer_factory(template)
                        if summarizer_factory
                        else Summarizer(
                            {**config["llm"], "template": template}, folder / "summary-cache"
                        )
                    )
                    summaries[template] = {
                        "response": summarizer.summarize(minutes.turns),
                        "semantic_accuracy": None,
                    }
                except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
                    summaries[template] = {"error": type(exc).__name__, "semantic_accuracy": None}
        result = {
            "id": meeting["id"],
            "synthetic": bool(meeting.get("synthetic")),
            "source_url": meeting["source_url"],
            "license": meeting["license"],
            "audio_sha256": file_sha256(meeting["audio"]),
            "minutes_sha256": file_sha256(minutes_path),
            "turns": turns,
            "questions": question_report,
            "summaries": summaries,
        }
        for case in question_report["cases"]:
            if "response" in case:
                reviews.append(
                    review_case(f"{meeting['id']}/question/{case['case_id']}", case["response"])
                )
        for template, summary in summaries.items():
            if "response" in summary:
                reviews.append(
                    review_case(f"{meeting['id']}/summary/{template}", summary["response"])
                )
        if meeting.get("reference_json"):
            from meeting_asr.evaluation.experiments import transcript_scores
            from meeting_asr.io import read_transcript_json

            if not run_asr:
                result["asr_scores"] = None
            else:
                result["asr_scores"] = transcript_scores(
                    read_transcript_json(meeting["reference_json"]),
                    read_transcript_json(folder / "pipeline/transcript.json"),
                )
        if meeting.get("reference_rttm") and run_asr:
            from dataclasses import asdict

            from meeting_asr.evaluation.metrics import diarization_error_rate
            from meeting_asr.io import read_rttm

            result["diarization_scores"] = {
                label: asdict(
                    diarization_error_rate(
                        read_rttm(meeting["reference_rttm"]),
                        read_rttm(folder / "pipeline/diarization.rttm"),
                        collar=collar,
                        skip_overlap=skip,
                    )
                )
                for label, collar, skip in (("relaxed", 0.25, True), ("strict", 0, False))
            }
        results.append(result)
        report = {
            "schema_version": 1,
            "git_commit": git_commit(),
            "manifest_sha256": file_sha256(manifest),
            "config_hash": config_hash(config),
            "provider_mode": provider_mode,
            "run_asr": run_asr,
            "semantic_accuracy": None,
            "meetings": results,
            "limitations": "Transcript correctness and semantic support require human review. Synthetic meetings cannot validate real meeting quality.",
        }
        _atomic_text(destination / "report.json", json.dumps(report, ensure_ascii=False, indent=2))
        _atomic_text(
            destination / "review-template.json",
            json.dumps({"reviews": reviews}, ensure_ascii=False, indent=2),
        )
    return report


def review_case(case_id, response):
    return {
        "case_id": case_id,
        "response_sha256": response_hash(response),
        "correct": None,
        "complete": None,
        "supported": None,
        "reviewed_by": "",
        "reviewed_at": "",
        "notes": "",
    }


def response_hash(response):
    canonical = json.dumps(response, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def score_semantic_reviews(report_path, reviews_path):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    reviews = json.loads(Path(reviews_path).read_text(encoding="utf-8"))["reviews"]
    expected = {}
    for meeting in report["meetings"]:
        for case in meeting["questions"]["cases"]:
            if "response" in case:
                expected[f"{meeting['id']}/question/{case['case_id']}"] = response_hash(
                    case["response"]
                )
        for template, summary in meeting["summaries"].items():
            if "response" in summary:
                expected[f"{meeting['id']}/summary/{template}"] = response_hash(summary["response"])
    seen, scored = set(), []
    for review in reviews:
        identity = review["case_id"]
        if (
            identity not in expected
            or identity in seen
            or review.get("response_sha256") != expected[identity]
        ):
            raise ValueError("unknown, duplicate or stale semantic review")
        seen.add(identity)
        values = [review.get(k) for k in ("correct", "complete", "supported")]
        if all(v is None for v in values):
            continue
        if not all(isinstance(v, bool) for v in values):
            raise ValueError("semantic review requires three explicit boolean ratings")
        if not review.get("reviewed_by", "").strip() or not review.get("reviewed_at", "").strip():
            raise ValueError("semantic review requires reviewer and timestamp")
        scored.append(review)
    return {
        "report_sha256": file_sha256(report_path),
        "expected_cases": len(expected),
        "reviewed_cases": len(scored),
        "coverage": len(scored) / len(expected) if expected else 0,
        **{
            f"{k}_rate": sum(r[k] for r in scored) / len(scored) if scored else None
            for k in ("correct", "complete", "supported")
        },
        "reviews": scored,
    }
