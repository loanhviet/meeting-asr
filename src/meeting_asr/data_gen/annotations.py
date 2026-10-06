"""Versioned speech labels, kept separate from utterance text and audio context."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from meeting_asr.io import _atomic_text
from meeting_asr.runtime import file_sha256

STATUSES = {"automatic_unverified", "human_verified"}


def validate_speech_labels(intervals, annotation, duration):
    if not isinstance(intervals, (list, tuple)) or not intervals:
        raise ValueError("speech_intervals must contain at least one interval")
    previous = -1.0
    normalized = []
    for interval in intervals:
        if not isinstance(interval, (list, tuple)) or len(interval) != 2:
            raise ValueError("speech intervals must be [start, end] pairs")
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) for value in interval
        ):
            raise ValueError("speech times must be numeric")
        start, end = map(float, interval)
        if not all(map(math.isfinite, (start, end))) or not 0 <= start < end <= duration:
            raise ValueError("speech interval is outside the clip")
        if round(end, 3) <= round(start, 3):
            raise ValueError("speech interval is shorter than RTTM timestamp precision")
        if start < previous:
            raise ValueError("speech intervals must be sorted and nonoverlapping")
        previous = end
        normalized.append((start, end))
    if not isinstance(annotation, dict) or annotation.get("status") not in STATUSES:
        raise ValueError("speech_annotation requires an explicit verification status")
    for field in ("method", "version"):
        if not isinstance(annotation.get(field), str) or not annotation[field].strip():
            raise ValueError(f"speech_annotation requires {field}")
    if annotation["status"] == "human_verified":
        for field in ("reviewed_by", "reviewed_at"):
            if not isinstance(annotation.get(field), str) or not annotation[field].strip():
                raise ValueError(f"human_verified labels require {field}")
    return tuple(normalized)


def import_speech_labels(manifest, labels, out):
    """Attach labels by source/clip ID and checksum; never change text or speaker."""
    source, label_path = Path(manifest).resolve(), Path(labels).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    proposed = json.loads(label_path.read_text(encoding="utf-8"))
    index = {}
    for entry in proposed["clips"]:
        key = (entry["source"], entry["clip_id"])
        if key in index:
            raise ValueError(f"duplicate speech annotation: {key}")
        index[key] = entry
    seen = set()
    statuses = Counter()
    for clip in payload["clips"]:
        key = (clip["source"], clip["clip_id"])
        if key in seen:
            raise ValueError(f"duplicate manifest clip: {key}")
        seen.add(key)
        wav = (source.parent / clip["wav"]).resolve()
        clip["wav"] = str(wav)
        if key not in index:
            continue
        label = index[key]
        checksum = file_sha256(wav)
        if label.get("sha256") != checksum or clip.get("sha256", checksum) != checksum:
            raise ValueError(f"speech annotation checksum mismatch: {key}")
        from meeting_asr.data_gen.simulate import read_mono_wav

        waveform, sr = read_mono_wav(wav)
        intervals = label.get("speech_intervals", label.get("proposed_intervals"))
        annotation = label.get("speech_annotation") or {
            "status": label.get("annotation_status", proposed.get("annotation_status")),
            "method": "conservative-vad-consensus",
            "version": "pilot-audit-v1",
        }
        normalized = validate_speech_labels(intervals, annotation, len(waveform) / sr)
        clip.update(speech_intervals=normalized, speech_annotation=annotation, sha256=checksum)
        statuses[annotation["status"]] += 1
    if index.keys() - seen:
        raise ValueError("speech annotations include clips absent from the manifest")
    payload["speech_label_import"] = {
        "labels_sha256": file_sha256(label_path),
        "statuses": dict(statuses),
        "unlabelled_clips": sum("speech_intervals" not in c for c in payload["clips"]),
    }
    _atomic_text(Path(out), json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload
