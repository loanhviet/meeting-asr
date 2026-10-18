"""Score paired pilot artifacts against source transcripts, with reference caveats."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import jiwer
import numpy as np
from scipy.optimize import linear_sum_assignment

from meeting_asr.evaluation.metrics import normalize_for_wer, score_diarization
from meeting_asr.io import read_rttm


def texts(turns):
    ordered = sorted(turns, key=lambda u: (u["start"], u["end"], u["speaker"]))
    groups = defaultdict(list)
    for turn in ordered:
        groups[turn["speaker"]].append(normalize_for_wer(turn["text"]))
    return " ".join(normalize_for_wer(u["text"]) for u in ordered), {
        speaker: " ".join(parts) for speaker, parts in groups.items()
    }


def errors(ref, hyp):
    result = jiwer.process_words(ref, hyp)
    return {
        "reference_words": result.hits + result.substitutions + result.deletions,
        "substitutions": result.substitutions,
        "deletions": result.deletions,
        "insertions": result.insertions,
        "errors": result.substitutions + result.deletions + result.insertions,
        "wer": result.wer,
    }


def permuted_score(reference, hypothesis):
    refs, hyps = list(reference.items()), list(hypothesis.items())
    width = max(len(refs), len(hyps))
    refs += [(None, "")] * (width - len(refs))
    hyps += [(None, "")] * (width - len(hyps))
    costs = np.array([[errors(r, h)["errors"] for _, h in hyps] for _, r in refs])
    rows, cols = linear_sum_assignment(costs)
    mapping = []
    totals = {
        "reference_words": 0,
        "substitutions": 0,
        "deletions": 0,
        "insertions": 0,
        "errors": 0,
    }
    for i, j in zip(rows, cols, strict=True):
        score = errors(refs[i][1], hyps[j][1])
        mapping.append({"reference_speaker": refs[i][0], "hypothesis_speaker": hyps[j][0], **score})
        for key in totals:
            totals[key] += score[key]
    return {
        **totals,
        "cpwer": totals["errors"] / max(1, totals["reference_words"]),
        "mapping": mapping,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", type=Path, help="Batch directory with manifest.json and paired outputs"
    )
    args = parser.parse_args()
    manifest = json.loads((args.root / "manifest.json").read_text())
    rows = []
    for session in manifest["sessions"]:
        reference = json.loads(Path(session["reference_json"]).read_text())
        ref_text, ref_speakers = texts(reference["utterances"])
        audio_sha = hashlib.sha256(Path(session["audio"]).read_bytes()).hexdigest()
        row = {
            "conversation_id": session["conversation_id"],
            "condition": session["condition"],
            "overlap_actual": session["overlap_actual"],
            "duration": reference["duration"],
            "reference_words": len(ref_text.split()),
            "audio_sha256": audio_sha,
            "reference_speech_status": session["speech_annotation_statuses"],
        }
        for engine in ("baseline", "dicow"):
            folder = args.root / session["conversation_id"] / session["condition"] / engine
            run = json.loads((folder / "run.json").read_text())
            if run["audio_sha256"] != audio_sha:
                raise ValueError(f"Audio mismatch: {folder}")
            hypothesis = json.loads((folder / "transcript.json").read_text())
            if abs(hypothesis["duration"] - reference["duration"]) > 0.01:
                raise ValueError(f"Reference/hypothesis duration mismatch: {folder}")
            hyp_text, hyp_speakers = texts(hypothesis["utterances"])
            diar = score_diarization(
                read_rttm(session["reference_rttm"]), read_rttm(folder / "diarization.rttm")
            )
            row[engine] = {
                "chronological": errors(ref_text, hyp_text),
                "cer": jiwer.cer(ref_text, hyp_text),
                "speaker_permuted": permuted_score(ref_speakers, hyp_speakers),
                "predicted_speakers": len(hyp_speakers),
                "elapsed_sec": run["result"]["elapsed_sec"],
                "rtf": run["result"]["rtf"],
                "cache": run["result"]["stages"],
                "config_hash": run["config_hash"],
                "draft_der": {
                    mode: {
                        "der": v.der,
                        "miss": v.miss,
                        "false_alarm": v.false_alarm,
                        "confusion": v.confusion,
                    }
                    for mode, v in diar.items()
                },
                "output_dir": str(folder.resolve()),
                "text": hyp_text,
                "speaker_texts": hyp_speakers,
            }
            oracle_folder = folder.with_name(engine + "-oracle")
            if (oracle_folder / "run.json").exists():
                oracle_run = json.loads((oracle_folder / "run.json").read_text())
                if oracle_run["audio_sha256"] != audio_sha:
                    raise ValueError(f"Oracle audio mismatch: {oracle_folder}")
                oracle_hyp = json.loads((oracle_folder / "transcript.json").read_text())
                oracle_text, oracle_speakers = texts(oracle_hyp["utterances"])
                row[engine]["placement_oracle"] = {
                    "chronological": errors(ref_text, oracle_text),
                    "speaker_permuted": permuted_score(ref_speakers, oracle_speakers),
                    "elapsed_sec": oracle_run["result"]["elapsed_sec"],
                    "text": oracle_text,
                    "speaker_texts": oracle_speakers,
                    "reference_rttm": session["oracle_rttm"],
                    "reference_kind": "known whole source-clip placement, including within-clip silence",
                }
        row["reference_text"] = ref_text
        row["reference_speaker_texts"] = ref_speakers
        rows.append(row)
    totals = {}
    for condition in ["all", *sorted({r["condition"] for r in rows})]:
        selected = [r for r in rows if condition == "all" or r["condition"] == condition]
        nwords = sum(r["reference_words"] for r in selected)
        totals[condition] = {"sessions": len(selected), "reference_words": nwords}
        for engine in ("baseline", "dicow"):
            totals[condition][engine] = {
                "wer": sum(r[engine]["chronological"]["errors"] for r in selected) / nwords,
                "cpwer": sum(r[engine]["speaker_permuted"]["errors"] for r in selected) / nwords,
                "substitutions": sum(r[engine]["chronological"]["substitutions"] for r in selected),
                "deletions": sum(r[engine]["chronological"]["deletions"] for r in selected),
                "insertions": sum(r[engine]["chronological"]["insertions"] for r in selected),
                "elapsed_sec": sum(r[engine]["elapsed_sec"] for r in selected),
            }
            oracle_rows = [r for r in selected if "placement_oracle" in r[engine]]
            if oracle_rows:
                oracle_words = sum(r["reference_words"] for r in oracle_rows)
                totals[condition][engine]["placement_oracle"] = {
                    "sessions": len(oracle_rows),
                    "reference_words": oracle_words,
                    "cpwer": sum(
                        r[engine]["placement_oracle"]["speaker_permuted"]["errors"]
                        for r in oracle_rows
                    )
                    / oracle_words,
                    "wer": sum(
                        r[engine]["placement_oracle"]["chronological"]["errors"]
                        for r in oracle_rows
                    )
                    / oracle_words,
                }
    report = {
        "scope": manifest["scope"],
        "implementation_sha256": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in [
                "src/meeting_asr/pipeline.py",
                "src/meeting_asr/dicow.py",
                "src/meeting_asr/dicow_runner.py",
                "configs/default.yaml",
                "configs/baseline-phowhisper.yaml",
                "configs/dicow-author.yaml",
                "scripts/score_dicow_quality.py",
            ]
        },
        "limitations": [
            "Only two original VIVOS conversations, each reused in three conditions; not six independent meetings.",
            "Text comes from VIVOS prompts; audio is a constructed mixture of read speech, not spontaneous meetings.",
            "Chronological WER/CER are affected by overlapping utterance ordering; cpWER preserves per-speaker order.",
            "DER is exploratory: reference speech intervals are automatic_unverified, not human-confirmed boundaries.",
            "Comparing complete systems with different backbones and diarizers does not isolate FDDT.",
            "Timing includes model loading and is not a repeated latency benchmark.",
        ],
        "normalization": "Existing normalize_for_wer: NFC, lowercase, punctuation removal, whitespace collapse; Vietnamese syllable tokens; no synonym/filler/number rewriting.",
        "aggregates": totals,
        "rows": rows,
    }
    (args.root / "scores.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
