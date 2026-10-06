"""Propose speech intervals on source clips and audit stored pilot predictions.

All output labels are automatic and unverified. The original audio, RTTM,
transcript, prediction, and configuration files are never overwritten.
WebRTC is an independent check; Silero also appears in the evaluated ECAPA
backend, so scores under Silero-derived labels are sensitivity checks only.
"""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from meeting_asr.data_gen.simulate import read_mono_wav
from meeting_asr.evaluation.metrics import score_diarization
from meeting_asr.evaluation.overlap import measure_overlap_ratio
from meeting_asr.io import _atomic_text, read_rttm, read_transcript_json, write_rttm
from meeting_asr.models import Segment
from meeting_asr.runtime import file_sha256

SR = 16000
FRAME = 160  # 10 ms
PAD = 1600  # 100 ms
MIN_QUIET = 4000  # 250 ms; do not remove brief pauses
METHODS = ("webrtc_energy", "consensus", "silero_035", "silero_050", "silero_065")


def runs(mask):
    """Half-open sample intervals for true runs, including either endpoint."""
    edges = np.diff(np.r_[False, np.asarray(mask, dtype=bool), False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def conservative_ranges(support, min_quiet=MIN_QUIET, pad=PAD):
    """Remove long unsupported regions, retaining padding beside supported audio."""
    support = np.asarray(support, dtype=bool)
    if not support.any():
        raise ValueError("no supported speech; clip requires review")
    retained = np.ones(len(support), dtype=bool)
    for start, end in runs(~support):
        if end - start < min_quiet:
            continue
        cut_start = start + (pad if start else 0)
        cut_end = end - (pad if end < len(support) else 0)
        if cut_end > cut_start:
            retained[cut_start:cut_end] = False
    return runs(retained)


def mask_for(intervals, length):
    mask = np.zeros(length, dtype=bool)
    for start, end in intervals:
        mask[max(0, start) : min(length, end)] = True
    return mask


def project_ranges(turn, intervals, sample_rate=SR):
    result = []
    for start, end in intervals:
        a = turn["start"] + start / sample_rate
        b = min(turn["end"], turn["start"] + end / sample_rate)
        if b - a >= 0.001:
            result.append(Segment(a, b, turn["speaker"]))
    return result


def write_json(path, value):
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analyze_clip(entry, silero, webrtcvad):
    import torch
    from silero_vad import get_speech_timestamps

    waveform, sr = read_mono_wav(entry["wav"])
    assert sr == SR and file_sha256(entry["wav"]) == entry["sha256"]
    length = len(waveform)
    pcm = np.clip(np.round(waveform * 32768), -32768, 32767).astype("<i2")
    detector = webrtcvad.Vad(0)
    web_mask = np.zeros(length, dtype=bool)
    for start in range(0, length, 2 * FRAME):
        chunk = pcm[start : start + 2 * FRAME]
        if len(chunk) < 2 * FRAME:
            chunk = np.pad(chunk, (0, 2 * FRAME - len(chunk)))
        if detector.is_speech(chunk.tobytes(), SR):
            web_mask[start : start + 2 * FRAME] = True
    frames = np.pad(waveform, (0, (-length) % FRAME)).reshape(-1, FRAME)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    energy = np.repeat(rms >= float(np.max(np.abs(waveform))) * 0.01, FRAME)[:length]
    intervals, masks = {}, {}
    for threshold in (0.35, 0.5, 0.65):
        spans = get_speech_timestamps(
            torch.from_numpy(waveform),
            silero,
            threshold=threshold,
            sampling_rate=SR,
            speech_pad_ms=100,
            min_silence_duration_ms=200,
            min_speech_duration_ms=100,
            return_seconds=False,
        )
        name = f"silero_{round(threshold * 100):03d}"
        intervals[name] = [(s["start"], s["end"]) for s in spans]
        masks[name] = mask_for(intervals[name], length)
    intervals["webrtc_energy"] = conservative_ranges(web_mask | energy)
    # A Silero-positive region vetoes removal but never changes speaker identity.
    intervals["consensus"] = conservative_ranges(web_mask | energy | masks["silero_035"])
    candidate = mask_for(intervals["consensus"], length)
    independent = mask_for(intervals["webrtc_energy"], length)
    disagreements = web_mask ^ masks["silero_050"]
    result = {
        **entry,
        "annotation_status": "automatic_unverified",
        "duration_sec": length / SR,
        "proposed_intervals": [[a / SR, b / SR] for a, b in intervals["consensus"]],
        "removed_sec": float((~candidate).sum() / SR),
        "leading_removed_sec": intervals["consensus"][0][0] / SR,
        "trailing_removed_sec": (length - intervals["consensus"][-1][1]) / SR,
        "internal_removed_sec": sum(b - a for a, b in runs(~candidate) if a > 0 and b < length)
        / SR,
        "detector_disagreement_sec": float(disagreements.sum() / SR),
        "silero_veto_kept_sec": float((candidate & ~independent).sum() / SR),
        "ranges_samples": intervals,
    }
    return result


def audit(args):
    if args.vad_deps:
        sys.path.insert(0, str(Path(args.vad_deps).resolve()))
    import silero_vad
    import webrtcvad
    from silero_vad import load_silero_vad

    destination = Path(args.out).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path(args.manifest).read_text())
    predictions = json.loads(Path(args.predictions).read_text())
    entries = {e["clip_id"]: e for e in json.loads(Path(args.clips).read_text())["clips"]}
    metadata = {
        s["audio"]: json.loads(Path(s["audio"]).with_suffix(".meta.json").read_text())
        for s in manifest["sessions"]
    }
    ids = sorted({clip for meta in metadata.values() for clip in meta["clip_ids"]})
    silero = load_silero_vad()
    annotations = {}
    for index, clip_id in enumerate(ids, 1):
        result = analyze_clip(entries[clip_id], silero, webrtcvad)
        annotations[clip_id] = result
        print(
            f"CLIP {index}/{len(ids)} {clip_id}: remove {result['removed_sec']:.2f}s, "
            f"disagreement {result['detector_disagreement_sec']:.2f}s",
            flush=True,
        )
    write_json(
        destination / "clip_annotations.proposed.json",
        {
            "annotation_status": "automatic_unverified",
            "clips": list(annotations.values()),
        },
    )
    write_csv(
        destination / "clip_review.csv",
        [
            {k: v for k, v in e.items() if k not in ("ranges_samples", "proposed_intervals")}
            for e in annotations.values()
        ],
    )
    scores, overlaps, speaker_rows = [], [], []
    for session in manifest["sessions"]:
        meta = metadata[session["audio"]]
        truth = read_rttm(session["reference_rttm"])
        refs = {"original": truth}
        for method in METHODS:
            refs[method] = sorted(
                [
                    seg
                    for turn in meta["turns"]
                    for seg in project_ranges(
                        turn, annotations[turn["clip_id"]]["ranges_samples"][method]
                    )
                ],
                key=lambda s: (s.start, s.end, s.speaker),
            )
            if not refs[method] or {s.speaker for s in refs[method]} != {s.speaker for s in truth}:
                raise ValueError(f"empty/missing-speaker proposal: {session['audio']} {method}")
            write_rttm(
                destination / "references" / method / f"{Path(session['audio']).stem}.rttm",
                Path(session["audio"]).stem,
                refs[method],
            )
        overlaps.append(
            {
                "conversation_id": session["conversation_id"],
                "condition": session["condition"],
                "target": meta["overlap_target"],
                **{f"overlap_{k}": measure_overlap_ratio(v) for k, v in refs.items()},
            }
        )
        selected = [p for p in predictions if p["audio"] == session["audio"]]
        assert len(selected) == 2
        for prediction in selected:
            predicted = read_rttm(Path(prediction["prediction_dir"]) / "diarization.rttm")
            for method, reference in refs.items():
                row = {
                    "conversation_id": session["conversation_id"],
                    "condition": session["condition"],
                    "backend": prediction["backend"],
                    "reference_method": method,
                    "annotation_status": "automatic_unverified",
                    "wer_unchanged": prediction["wer"],
                    "cpwer_unchanged": prediction["cpwer"],
                }
                for label, detail in score_diarization(reference, predicted).items():
                    row.update({f"{label}_{k}": v for k, v in asdict(detail).items()})
                if method == "original":
                    assert abs(row["relaxed_der"] - prediction["relaxed_der"]) < 1e-12
                scores.append(row)
            if session["condition"] == "ovl0_clean":
                from pyannote.metrics.matcher import HungarianMapper

                from meeting_asr.evaluation.metrics import _annotation

                mapping = HungarianMapper()(_annotation(predicted), _annotation(refs["consensus"]))
                hypothesis = read_transcript_json(
                    Path(prediction["prediction_dir"]) / "transcript.json"
                )
                for turn in meta["turns"]:
                    spans = project_ranges(
                        turn, annotations[turn["clip_id"]]["ranges_samples"]["consensus"]
                    )
                    duration_by_speaker = defaultdict(float)
                    for h in predicted:
                        duration_by_speaker[h.speaker] += sum(
                            max(0, min(h.end, s.end) - max(h.start, s.start)) for s in spans
                        )
                    positive = {s: d for s, d in duration_by_speaker.items() if d > 0}
                    dominant = max(positive, key=positive.get) if positive else None
                    mapped = mapping.get(dominant)
                    texts = [
                        u.text
                        for u in hypothesis.utterances
                        if min(u.end, turn["end"]) > max(u.start, turn["start"])
                    ]
                    speaker_rows.append(
                        {
                            "conversation_id": session["conversation_id"],
                            "backend": prediction["backend"],
                            "clip_id": turn["clip_id"],
                            "start": turn["start"],
                            "end": turn["end"],
                            "reference_speaker": turn["speaker"],
                            "reference_text": turn["text"],
                            "dominant_predicted_speaker": dominant,
                            "mapped_speaker": mapped,
                            "speaker_mismatch": mapped != turn["speaker"],
                            "predicted_text": " ".join(texts),
                            "proposed_intervals": json.dumps([[s.start, s.end] for s in spans]),
                        }
                    )
    write_csv(destination / "der_sensitivity.csv", scores)
    write_csv(destination / "overlap_sensitivity.csv", overlaps)
    write_csv(destination / "speaker_review.csv", speaker_rows)
    summary = {
        "created_at": datetime.now(UTC).isoformat(),
        "annotation_status": "automatic_unverified",
        "clips": len(ids),
        "sessions": len(manifest["sessions"]),
        "score_rows": len(scores),
        "total_source_duration_sec": sum(e["duration_sec"] for e in annotations.values()),
        "total_proposed_removed_sec": sum(e["removed_sec"] for e in annotations.values()),
        "speaker_mismatches": {
            b: sum(r["speaker_mismatch"] for r in speaker_rows if r["backend"] == b)
            for b in ("pyannote", "ecapa")
        },
        "versions": {
            "webrtcvad": webrtcvad.__version__,
            "silero_vad": importlib.metadata.version("silero-vad"),
        },
        "silero_model_sha256": file_sha256(
            Path(silero_vad.__file__).parent / "data/silero_vad.jit"
        ),
        "parameters": {
            "webrtc_mode": 0,
            "webrtc_frame_ms": 20,
            "energy_peak_fraction": 0.01,
            "min_removed_gap_ms": 250,
            "kept_edge_pad_ms": 100,
            "silero_thresholds": [0.35, 0.5, 0.65],
            "silero_pad_ms": 100,
            "silero_min_silence_ms": 200,
            "silero_min_speech_ms": 100,
        },
        "inputs": {str(p): file_sha256(p) for p in [args.manifest, args.clips, args.predictions]},
        "limitations": [
            "No human listening or verified ground truth",
            "Silero-derived labels share a detector with the ECAPA backend",
            "No audio or ASR prediction changed; DER changes reflect reference changes",
        ],
    }
    write_json(destination / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/simulated/pilot/sessions.json")
    parser.add_argument("--clips", default="data/audited/test.json")
    parser.add_argument("--predictions", default="results/pilot/rows.json")
    parser.add_argument("--out", default="results/pilot-annotations-2026-10-02")
    parser.add_argument(
        "--vad-deps", default=None, help="Optional isolated WebRTC dependency directory"
    )
    audit(parser.parse_args())


if __name__ == "__main__":
    main()
