"""Read-only gates for dataset capacity, paired conditions, labels and leakage."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from meeting_asr.data_gen.simulate import CONDITIONS, load_clips, read_mono_wav
from meeting_asr.evaluation.experiments import experiment_manifest
from meeting_asr.evaluation.overlap import measure_overlap_ratio
from meeting_asr.io import _atomic_text, read_rttm, read_transcript_json
from meeting_asr.runtime import file_sha256

EXPECTED_CONDITIONS = {f"{c.overlap_label}_{c.noise_label}" for c in CONDITIONS}


def write_report(out, report):
    _atomic_text(Path(out), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def plan_data(manifest, *, conversations=20, clips_per_speaker=6, minimum_duration_sec=180):
    if conversations < 1 or clips_per_speaker < 1 or minimum_duration_sec < 0:
        raise ValueError("invalid dataset planning counts or duration")
    clips = load_clips(manifest)
    groups = defaultdict(list)
    for clip in clips:
        groups[clip.speaker].append(clip)
    remaining = {s: len(group) for s, group in groups.items()}
    possible = 0
    while True:
        eligible = sorted(
            (s for s, n in remaining.items() if n >= clips_per_speaker),
            key=lambda s: (-remaining[s], s),
        )
        if len(eligible) < 3:
            break
        for speaker in eligible[:3]:
            remaining[speaker] -= clips_per_speaker
        possible += 1
    total_sec = sum(c.duration for c in clips)
    statuses = Counter(
        c.speech_annotation["status"] if c.speech_annotation else "unlabelled" for c in clips
    )
    issues = []
    if possible < conversations:
        issues.append(
            f"only {possible} disjoint conversations fit {clips_per_speaker} clips/speaker"
        )
    # This is a necessary aggregate bound, not a scheduling guarantee.
    # At most one second of nonoverlap gap is added per adjacent utterance.
    upper_bound = total_sec + max(0, conversations * (3 * clips_per_speaker - 1))
    if upper_bound < conversations * minimum_duration_sec:
        issues.append(
            "audio pool cannot meet the requested minimum duration without reusing clips or adding data"
        )
    if statuses.get("human_verified", 0) != len(clips):
        issues.append("speech labels are not all human verified")
    return {
        "manifest_sha256": file_sha256(manifest),
        "clips": len(clips),
        "speakers": len(groups),
        "audio_minutes": total_sec / 60,
        "requested_conversations": conversations,
        "clips_per_speaker": clips_per_speaker,
        "capacity_conversations": possible,
        "minimum_duration_sec": minimum_duration_sec,
        "speech_annotation_statuses": dict(statuses),
        "issues": issues,
        "ready": not issues,
        "limitations": "Capacity is clip-count based. Scheduling feasibility and actual duration must be checked after generation.",
    }


def audit_experiments(
    manifest,
    *,
    other_manifest=None,
    expected_conversations=None,
    minimum_duration_sec=0,
    require_verified_speech=False,
):
    payload = experiment_manifest(manifest)
    issues, rows = [], []
    grouped = defaultdict(list)
    provenance = {}
    for session in payload["sessions"]:
        audio = Path(session["audio"])
        waveform, sr = read_mono_wav(audio)
        reference = read_transcript_json(session["reference_json"])
        speech = read_rttm(session["reference_rttm"], expected_file_id=audio.stem)
        oracle = read_rttm(
            session.get("oracle_rttm", session["reference_rttm"]), expected_file_id=audio.stem
        )
        duration = len(waveform) / sr
        label = f"{session['conversation_id']}/{session['condition']}"
        if not np.isfinite(waveform).all() or np.max(np.abs(waveform)) >= 0.999:
            issues.append(f"{label}: invalid/clipping audio")
        if duration < minimum_duration_sec:
            issues.append(f"{label}: duration {duration:.2f}s below {minimum_duration_sec}s")
        if abs(reference.duration - duration) > 0.01 or any(
            s.end > duration + 0.01 for s in [*speech, *oracle]
        ):
            issues.append(f"{label}: reference exceeds audio duration")
        if len({s.speaker for s in speech}) != 3:
            issues.append(f"{label}: expected three reference speakers")
        target = int(session["condition"].split("_")[0][3:]) / 100
        actual = measure_overlap_ratio(speech)
        if abs(actual - target) >= 0.03:
            issues.append(f"{label}: speech overlap {actual:.4f} differs from {target:.2f}")
        meta_path = audio.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        statuses = {
            t.get("speech_annotation", {}).get("status", "unlabelled")
            if t.get("speech_annotation")
            else "unlabelled"
            for t in meta.get("turns", [])
        }
        if require_verified_speech and (not statuses or statuses != {"human_verified"}):
            issues.append(f"{label}: speech labels have not been human verified")
        if not meta.get("turns"):
            issues.append(f"{label}: missing clip provenance metadata")
        identity = tuple(
            (t["source"], t["clip_id"], t["speaker"], t["text"]) for t in meta.get("turns", [])
        )
        conversation = session["conversation_id"]
        if conversation in provenance and provenance[conversation] != identity:
            issues.append(f"{label}: utterance order/content differs across conditions")
        provenance[conversation] = identity
        grouped[conversation].append(session)
        rows.append(
            {
                "conversation_id": conversation,
                "condition": session["condition"],
                "duration_sec": duration,
                "overlap_actual": actual,
                "reference_kind": meta.get("reference_kind", "full_clip_unverified"),
                "speech_annotation_statuses": sorted(statuses),
                "audio_sha256": file_sha256(audio),
            }
        )
    for conversation, sessions in grouped.items():
        conditions = {s["condition"] for s in sessions}
        if conditions != EXPECTED_CONDITIONS:
            issues.append(f"{conversation}: incomplete or unknown condition matrix")
    clip_owner = {}
    for conversation, identity in provenance.items():
        for source, clip, _, _ in identity:
            key = (source, clip)
            if key in clip_owner and clip_owner[key] != conversation:
                issues.append(f"clip {key} reused across original conversations")
            clip_owner[key] = conversation
    if expected_conversations is not None and len(grouped) != expected_conversations:
        issues.append(
            f"expected {expected_conversations} independent conversations, found {len(grouped)}"
        )
    if other_manifest:
        other = experiment_manifest(other_manifest)
        other_speakers, other_clips, other_hashes = set(), set(), set()
        for session in other["sessions"]:
            meta = json.loads(Path(session["audio"]).with_suffix(".meta.json").read_text())
            for turn in meta["turns"]:
                other_speakers.add((turn["source"], turn["speaker"]))
                other_clips.add((turn["source"], turn["clip_id"]))
                if turn.get("audio_sha256"):
                    other_hashes.add(turn["audio_sha256"])
        for identity in provenance.values():
            for source, clip, speaker, _ in identity:
                if (source, clip) in other_clips or (source, speaker) in other_speakers:
                    issues.append("speaker or clip leakage across dev/test manifests")
        for session in payload["sessions"]:
            meta = json.loads(Path(session["audio"]).with_suffix(".meta.json").read_text())
            if any(t.get("audio_sha256") in other_hashes for t in meta["turns"]):
                issues.append("source audio checksum leakage across dev/test manifests")
    return {
        "ready": not issues,
        "manifest_sha256": file_sha256(manifest),
        "sessions": len(rows),
        "independent_conversations": len(grouped),
        "condition_counts": dict(Counter(r["condition"] for r in rows)),
        "require_verified_speech": require_verified_speech,
        "issues": sorted(set(issues)),
        "rows": rows,
    }
