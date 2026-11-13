"""Publish portable round-one evidence after all local experiments complete."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from evaluate_general_meetings import digest, folder_for, read_rows, write_json

from meeting_asr.settings import PROJECT_ROOT


def build_evidence(out):
    experiment = json.loads((out / "experiment.json").read_text())
    comparison = json.loads((out / "comparison.json").read_text())
    if not comparison["complete"] or comparison["recommended_beam"] is None:
        raise ValueError("a complete decoding grid is required")
    if digest(out / "inputs.dev.jsonl") != experiment["manifest_sha256"]:
        raise ValueError("development inputs changed after freezing")
    inputs = read_rows(out / "inputs.dev.jsonl")
    if len(inputs) != 41 or any(r.get("split") != "dev" for r in inputs):
        raise ValueError("round one requires the frozen 41-recording development selection")
    ami = [r for r in inputs if r["dataset"] == "ami_dev"]
    if len(ami) != 1 or ami[0].get("recording_id") != "ES2011a":
        raise ValueError("round one requires the official AMI development control")
    ami = ami[0]
    expected = {(r["dataset"], r["id"]): r for r in inputs}
    baseline = out / "beam-1"
    paired = {
        key: {
            "dataset": key[0],
            "id": key[1],
            "audio_sha256": r["audio_sha256"],
            "errors_by_beam": {},
        }
        for key, r in expected.items()
    }
    groups, revision, repetition = {}, None, []
    matched_diarization = True
    for beam in experiment["beams"]:
        folder = out / f"beam-{beam}"
        selection = json.loads((folder / "selection.json").read_text())
        if {(r["dataset"], r["id"]) for r in selection["rows"]} != set(expected):
            raise ValueError("grid recording sets differ")
        for row in selection["rows"]:
            source = expected[(row["dataset"], row["id"])]
            if row["audio_sha256"] != source["audio_sha256"]:
                raise ValueError("grid input checksums differ")
            sample = folder_for(folder, row)
            run = json.loads((sample / "run.json").read_text())
            if run["result"]["oracle_rttm"] is not None:
                raise ValueError("oracle diarization is not an eligible production trial")
            provenance = json.loads((sample / "dicow-provenance.json").read_text())
            if provenance["num_beams"] != beam:
                raise ValueError("actual decoding differs from the planned beam count")
            if revision is None:
                revision = {
                    k: provenance[k]
                    for k in (
                        "author_commit",
                        "diarizen_code_commit",
                        "model_name",
                        "model_revision",
                        "diarization_model",
                        "diarization_revision",
                        "embedding_revision",
                        "packages",
                        "gpu",
                        "dtype",
                        "ctc_weight",
                        "target_batch_size",
                    )
                }
            if any(provenance[k] != v for k, v in revision.items()):
                raise ValueError("model/runtime changed across the grid")
            matched_diarization &= digest(sample / "diarization.rttm") == digest(
                folder_for(baseline, row) / "diarization.rttm"
            )
        rows = read_rows(folder / "scores.jsonl")
        for row in rows:
            if row["status"] != "ok":
                raise ValueError("failed inference requires explicit analysis before publication")
            pair = paired[(row["dataset"], row["id"])]
            if (
                pair.get("reference_units", row["wer"]["reference_units"])
                != row["wer"]["reference_units"]
            ):
                raise ValueError("reference denominator changed across beams")
            pair["reference_units"] = row["wer"]["reference_units"]
            pair["errors_by_beam"][str(beam)] = row["wer"]["errors"]
            if row["dataset"] == "ami_dev":
                words = row["hypothesis"].split()
                ngrams = Counter(tuple(words[i : i + 5]) for i in range(max(0, len(words) - 4)))
                common = ngrams.most_common(1)
                repetition.append(
                    {
                        "beam": beam,
                        "dataset": row["dataset"],
                        "id": row["id"],
                        "hypothesis_words": len(words),
                        "insertions": row["wer"]["insertions"],
                        "most_repeated_5gram": " ".join(common[0][0]) if common else None,
                        "occurrences": common[0][1] if common else 0,
                        "note": "Text repetition diagnostic; not an independent listening judgment.",
                    }
                )
        groups[str(beam)] = json.loads((folder / "summary.json").read_text())["groups"]
    controls = json.loads((baseline / "phowhisper_comparison_summary.json").read_text())
    control_rows = read_rows(baseline / "phowhisper_comparison_rows.jsonl")
    expected_vi = {key for key, row in expected.items() if row.get("language", "vi") == "vi"}
    if {(r["dataset"], r["id"]) for r in control_rows} != expected_vi:
        raise ValueError("PhoWhisper controls must cover every Vietnamese development clip")
    if any(r["status"] != "ok" for r in control_rows):
        raise ValueError("PhoWhisper control failed")
    for row in control_rows:
        pair = paired[(row["dataset"], row["id"])]
        if row["dicow_wer"]["errors"] != pair["errors_by_beam"]["1"]:
            raise ValueError("control baseline does not match beam 1")
        pair["phowhisper_errors"] = row["phowhisper_wer"]["errors"]
    probe = json.loads((out / "llm-probe.json").read_text())
    return {
        "experiment": experiment,
        "data": {
            "clips": len(inputs),
            "audio_sec": sum(r["duration_sec"] for r in inputs),
            "all_split_dev": all(r["split"] == "dev" for r in inputs),
            "ami_recording": ami["recording_id"],
            "ami_source_start_sec": ami["source_start_sec"],
            "ami_source_end_sec": ami["source_end_sec"],
            "ami_words": ami["selected_words"],
            "new_download_bytes": sum(
                r["bytes"]
                for r in json.loads(
                    (PROJECT_ROOT / "docs/experiments/asr_improvement_sources.lock.json").read_text()
                )
            ),
        },
        "runtime": revision,
        "predicted_rttm_identical_across_beams": matched_diarization,
        "comparison": comparison,
        "groups_by_beam": groups,
        "phowhisper_controls": controls,
        "llm_probe": probe,
        "paired_counts": list(paired.values()),
        "ami_repetition_diagnostic": repetition,
        "limitations": [
            "Development selection, not an independent final test or paper reproduction.",
            "Short VI clips are supplementary domains, not full multi-speaker Vietnamese meetings.",
            "Public reference annotations have not been independently listened to by this project.",
            "AMI is English and named in model training; temporal scores use interpolated word times.",
            "GPU peaks are PyTorch allocated bytes, not total device memory requirements.",
            "PhoWhisper reuses M1/M2 with resident ASR weights; its latency is not comparable to a full pipeline run.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="completed experiment directory")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = build_evidence(args.out.resolve())
    write_json(args.evidence, evidence)
    print(
        json.dumps(
            {
                "evidence": str(args.evidence),
                "recommended_beam": evidence["comparison"]["recommended_beam"],
            }
        )
    )


if __name__ == "__main__":
    main()
