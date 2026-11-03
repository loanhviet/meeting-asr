"""Create review tables and figures from saved general-meeting predictions only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from meeting_asr.evaluation.overlap import measure_overlap_ratio
from meeting_asr.io import read_rttm


def percentage(value):
    return "—" if value is None else f"{100 * value:.2f}%"


def bootstrap_der(rows, policy):
    """Resample recordings, retaining speech-time weighting within each draw."""
    rng = np.random.default_rng(20261026)
    total = np.array([r["der"][policy]["total_sec"] for r in rows])
    errors = np.array(
        [
            sum(r["der"][policy][k] for k in ("miss_sec", "false_alarm_sec", "confusion_sec"))
            for r in rows
        ]
    )
    indices = rng.integers(0, len(rows), size=(2000, len(rows)))
    rates = errors[indices].sum(axis=1) / total[indices].sum(axis=1)
    return {
        "low": float(np.quantile(rates, 0.025)),
        "high": float(np.quantile(rates, 0.975)),
        "repetitions": 2000,
        "unit": "source recording; not guaranteed independent of model training",
    }


def main(out):
    summary = json.loads((out / "summary.json").read_text())
    if not summary["complete"]:
        raise ValueError("evaluation incomplete; collect all frozen rows before final report")
    selection = json.loads((out / "selection.json").read_text())
    rows = [json.loads(line) for line in (out / "scores.jsonl").read_text().splitlines()]
    groups = {(g["mode"], g["dataset"]): g for g in summary["groups"]}
    pipeline = [r for r in rows if r["mode"] == "pipeline"]
    diarization = [r for r in rows if r["mode"] == "diarization"]
    diagnostics = {
        "pipeline_clips": len(pipeline),
        "pipeline_audio_sec": sum(r["duration_sec"] for r in pipeline),
        "pipeline_elapsed_sec": sum(r["elapsed_sec"] for r in pipeline),
        "pipeline_failed": sum(r["status"] != "ok" for r in pipeline),
        "empty_successful_transcripts": sum(
            not r["hypothesis"].strip() for r in pipeline if r["status"] == "ok"
        ),
        "viyt": {
            "recordings": len(diarization),
            "correct_speaker_count": sum(
                r["predicted_speakers"] == r["reference_speakers"] for r in diarization
            ),
            "strict_95ci": bootstrap_der(diarization, "strict"),
            "relaxed_95ci": bootstrap_der(diarization, "relaxed"),
        },
    }
    overlap = [
        measure_overlap_ratio(read_rttm(r["reference_rttm"]))
        for r in selection["rows"]
        if r["mode"] == "diarization"
    ]
    diagnostics["viyt"].update(
        reference_files_with_overlap=sum(v > 0 for v in overlap),
        mean_file_speech_overlap_ratio=sum(overlap) / len(overlap),
        maximum_file_speech_overlap_ratio=max(overlap),
    )
    strata = {}
    for count in sorted({r["reference_speakers"] for r in diarization}):
        items = [r for r in diarization if r["reference_speakers"] == count]
        strata[str(count)] = {"files": len(items)}
        for policy in ("strict", "relaxed"):
            total = sum(r["der"][policy]["total_sec"] for r in items)
            errors = sum(
                sum(r["der"][policy][k] for k in ("miss_sec", "false_alarm_sec", "confusion_sec"))
                for r in items
            )
            strata[str(count)][policy] = errors / total if total else None
    diagnostics["viyt"]["reference_speaker_count_strata"] = strata
    review_candidates = []
    for row in selection["rows"]:
        if row["mode"] == "diarization" and row["num_speakers"] == 1:
            segments = read_rttm(row["reference_rttm"])
            review_candidates.append(
                {
                    "id": row["id"],
                    "audio_path": row["audio_path"],
                    "duration_sec": row["duration_sec"],
                    "reference_segments": len(segments),
                    "reference_speech_sec": sum(s.duration for s in segments),
                    "reference_first_speech_sec": min(s.start for s in segments),
                    "source_annotation": row["source_annotation"],
                    "review_status": "pending",
                    "note": "Source has one speaker label late in the recording; audio review required. "
                    "Not removed from primary all-100 score.",
                }
            )
    diagnostics["viyt"]["reference_review_candidates"] = review_candidates
    with (out / "viyt-reference-review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "id",
            "audio_path",
            "duration_sec",
            "reference_speech_sec",
            "reference_first_speech_sec",
            "review_status",
            "reviewed_by",
            "notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for candidate in review_candidates:
            writer.writerow(candidate)
    parity = []
    for r in pipeline:
        if r["dataset"] != "viyt_diar":
            continue
        name = Path(r["id"]).stem
        a = out / "pipeline/viyt_diar" / name / "diarization.rttm"
        b = out / "diarization/viyt_diar" / name / "diarization.rttm"

        def canonical(path):
            # Compare speaker partitions while allowing arbitrary label names.
            by_speaker = defaultdict(list)
            for segment in read_rttm(path):
                by_speaker[segment.speaker].append((round(segment.start, 3), round(segment.end, 3)))
            return sorted(tuple(sorted(spans)) for spans in by_speaker.values())

        parity.append({"id": r["id"], "same_m2_prediction": canonical(a) == canonical(b)})
    diagnostics["m2_parity"] = parity
    regions = defaultdict(list)
    for row in pipeline:
        if row["dataset"] == "vimd":
            regions[row["region"]].append(row)
    diagnostics["vimd_regions"] = {
        name: {
            "clips": len(items),
            "errors": sum(r["wer"]["errors"] for r in items),
            "reference_units": sum(r["wer"]["reference_units"] for r in items),
            "wer": sum(r["wer"]["errors"] for r in items)
            / sum(r["wer"]["reference_units"] for r in items),
        }
        for name, items in sorted(regions.items())
    }
    diagnostics["multi_speaker_predictions_on_short_asr_clips"] = {
        dataset: sum(r["predicted_speakers"] > 1 for r in pipeline if r["dataset"] == dataset)
        for dataset in ("fleurs_vi", "vimd", "vietmed")
    }
    diagnostics["analysis_implementation_sha256"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    (out / "diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n"
    )
    with (out / "review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "dataset",
            "id",
            "audio_path",
            "duration_sec",
            "status",
            "wer",
            "cer",
            "reference",
            "hypothesis",
            "review_status",
            "reviewed_by",
            "notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        paths = {(r["dataset"], r["id"]): r["audio_path"] for r in selection["rows"]}
        for row in sorted(
            pipeline, key=lambda r: r["wer"]["rate"] if r["wer"] else -1, reverse=True
        ):
            if row["wer"] is None:
                continue
            writer.writerow(
                {
                    **{
                        k: row.get(k)
                        for k in (
                            "dataset",
                            "id",
                            "duration_sec",
                            "status",
                            "reference",
                            "hypothesis",
                        )
                    },
                    "audio_path": paths[(row["dataset"], row["id"])],
                    "wer": row["wer"]["rate"],
                    "cer": row["cer"]["rate"],
                    "review_status": "pending",
                    "reviewed_by": "",
                    "notes": "",
                }
            )
    lines = [
        "# General meeting evaluation — 26/10/2026",
        "",
        "Frozen baseline, no model tuning, no oracle RTTM, no LLM in audio inference.",
        "Source-provided manual references have not been independently listened to by this project.",
        "",
        "| Mode | Dataset | Files | Audio min | WER | CER | DER strict | DER relaxed | Failed |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in summary["groups"]:
        der = group["der"] or {}
        lines.append(
            f"| {group['mode']} | {group['dataset']} | {group['clips']} | "
            f"{group['audio_sec'] / 60:.2f} | {percentage(group['wer']['rate'] if group['wer'] else None)} | "
            f"{percentage(group['cer']['rate'] if group['cer'] else None)} | "
            f"{percentage(der.get('strict', {}).get('rate'))} | "
            f"{percentage(der.get('relaxed', {}).get('rate'))} | {group['failed']} |"
        )
    lines.extend(
        [
            "",
            "## AMI paired microphone check",
            "",
            "Same recording and manual words; the two microphones are not independent meetings.",
            "",
            "| Microphone | WER | cpWER | Predicted / reference speakers |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in pipeline:
        if row["dataset"].startswith("ami_"):
            lines.append(
                f"| {row['dataset']} | {percentage(row['wer']['rate'])} | "
                f"{percentage(row['cpwer'])} | "
                f"{row['predicted_speakers']} / {row['reference_speakers']} |"
            )
    lines.extend(
        [
            "",
            "## ViYT protocol sensitivity",
            "",
            "| Collar / overlap | DER | Miss sec | False alarm sec | Confusion sec |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, detail in groups[("diarization", "viyt_diar")]["der"].items():
        lines.append(
            f"| {name} | {percentage(detail['rate'])} | {detail['miss_sec']:.2f} | "
            f"{detail['false_alarm_sec']:.2f} | {detail['confusion_sec']:.2f} |"
        )
    lines.extend(
        [
            "",
            "### Sensitivity by number of reference speaker labels",
            "",
            (
                "Primary results above retain all 100 files. Three source files have only Speaker_2 labels "
                "late in the audio; independently listening to them is still required. "
                "The original parquet contains the same labels, so this is not an RTTM conversion omission."
            ),
            "",
            "| Reference labels | Files | Strict DER | Relaxed DER |",
            "|---|---:|---:|---:|",
        ]
    )
    for count, detail in strata.items():
        lines.append(
            f"| {count} | {detail['files']} | {percentage(detail['strict'])} | "
            f"{percentage(detail['relaxed'])} |"
        )
    lines.extend(
        [
            "",
            "## ViMD diagnostic region groups",
            "",
            "One selected clip per source province code; not full test or population estimates.",
            "",
            "| Source region | Clips | WER |",
            "|---|---:|---:|",
        ]
    )
    for name, detail in diagnostics["vimd_regions"].items():
        lines.append(f"| {name} | {detail['clips']} | {percentage(detail['wer'])} |")
    lines.extend(["", "## QMSum retrieval and configured LLM", ""])
    retrieval = json.loads((out / "qmsum_retrieval_summary.json").read_text())
    for name, detail in retrieval["variants"].items():
        lines.append(
            f"- {name}: any annotated evidence hit "
            f"{percentage(detail['any_evidence_hit_rate'])}; "
            f"mean context text {detail['mean_context_text_chars']:.0f} chars."
        )
    canary = json.loads((out / "llm-canary.json").read_text())
    lines.append(
        f"- Configured summary canary: {canary['status']}; "
        f"{canary.get('error', 'semantic quality not scored')}."
    )
    control_path = out / "phowhisper_comparison_summary.json"
    controls = json.loads(control_path.read_text()) if control_path.exists() else None
    if controls:
        lines.extend(
            [
                "",
                "## Same predicted DiariZen timeline, alternative ASR",
                "",
                (
                    "Both preprocessing and the predicted speaker timeline are reused. "
                    "PhoWhisper uses cuts; DiCoW uses full audio with STNO. This does not isolate FDDT."
                ),
                "",
                "| Dataset | Clips | DiCoW WER | DiariZen + PhoWhisper WER |",
                "|---|---:|---:|---:|",
            ]
        )
        for name, detail in controls["groups"].items():
            lines.append(
                f"| {name} | {detail['clips']} | "
                f"{percentage(detail['dicow_wer']['rate'])} | "
                f"{percentage(detail['phowhisper_wer']['rate'])} |"
            )
    lines.extend(
        [
            "",
            "## Limits",
            "",
            "- Vietnamese WER uses normalized whitespace units, approximately syllables; CER removes spaces.",
            "- DER strict: collar 0, overlap kept; relaxed: collar 0.25 s, overlap skipped. Official UEM retained.",
            "- COSV text is full-recording only, without reliable speaker timestamps; DER/cpWER unavailable.",
            "- AMI is English and named in model training; supplemental engineering evidence only.",
            "- ViYT mainly covers one/two speakers and low overlap, not crowded Vietnamese meetings.",
            "- ViMD is one clip per 63 source province codes; FLEURS subset has male metadata only.",
            "- No single score is pooled across languages, domains or tasks.",
            "- Pipeline time includes repeated process/model startup; M2 resident timing excludes startup.",
            "- M2 and the PhoWhisper control overlap on the GPU; their timings are not isolated throughput measurements.",
            "- QMSum span hits are retrieval diagnostics, not answer correctness or completeness.",
            "",
            "Detailed machine-readable results: summary.json, diagnostics.json, scores.jsonl; listening queue: review.csv.",
        ]
    )
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), constrained_layout=True)
    text_groups = [groups[("pipeline", d)] for d in ("fleurs_vi", "vimd", "vietmed", "cosv")]
    labels = ["FLEURS\n40 clips", "ViMD\n63 clips", "VietMed\n27 clips", "COSV\n1 full interview"]
    bars = axes[0].bar(labels, [100 * g["wer"]["rate"] for g in text_groups], color="#326b9c")
    axes[0].bar_label(bars, fmt="%.2f%%", padding=3)
    axes[0].set(title="Vietnamese text error (separate corpora)", ylabel="WER (%)")
    axes[0].set_ylim(0, max(b.get_height() for b in bars) * 1.25)
    diar_groups = [
        groups[(m, d)]
        for m, d in [
            ("diarization", "viyt_diar"),
            ("pipeline", "ami_headset"),
            ("pipeline", "ami_room"),
        ]
    ]
    x = np.arange(3)
    for offset, policy, color in [(-0.2, "strict", "#b96e32"), (0.2, "relaxed", "#3b8a70")]:
        bars = axes[1].bar(
            x + offset,
            [100 * g["der"][policy]["rate"] for g in diar_groups],
            width=0.4,
            label=policy,
            color=color,
        )
        axes[1].bar_label(bars, fmt="%.1f", padding=3, fontsize=8)
    axes[1].set_xticks(
        x,
        [
            "ViYT-Diar\n100 files (VI)",
            "AMI headset\n1 excerpt (EN)",
            "AMI room mic\npaired excerpt (EN)",
        ],
    )
    axes[1].set(title="Speaker activity error", ylabel="DER (%)")
    axes[1].legend(frameon=False)
    axes[1].margins(y=0.2)
    fig.savefig(out / "quality-overview.png", dpi=180)
    fig.savefig(out / "quality-overview.svg")
    plt.close(fig)
    if controls:
        names = ["fleurs_vi", "vimd", "vietmed"]
        fig, axis = plt.subplots(figsize=(7, 4), constrained_layout=True)
        x = np.arange(len(names))
        for shift, field, label, color in [
            (-0.2, "dicow_wer", "DiCoW", "#326b9c"),
            (0.2, "phowhisper_wer", "PhoWhisper on same DiariZen", "#b96e32"),
        ]:
            bars = axis.bar(
                x + shift,
                [100 * controls["groups"][d][field]["rate"] for d in names],
                width=0.4,
                label=label,
                color=color,
            )
            axis.bar_label(bars, fmt="%.2f", padding=3)
        axis.set_xticks(x, ["FLEURS (40)", "ViMD (63)", "VietMed (27)"])
        axis.set(ylabel="WER (%)", title="Vietnamese short clips: matched ASR control")
        axis.legend(frameon=False)
        axis.margins(y=0.3)
        fig.savefig(out / "asr-control-comparison.png", dpi=180)
        fig.savefig(out / "asr-control-comparison.svg")
        plt.close(fig)
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    main(arguments.out.resolve())
