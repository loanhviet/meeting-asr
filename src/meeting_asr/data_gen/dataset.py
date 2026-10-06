"""Build an audited experiment manifest from disjoint pools of local clips."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from meeting_asr.data_gen.simulate import load_clips, read_mono_wav, simulate_matrix, write_session
from meeting_asr.io import _atomic_text
from meeting_asr.runtime import file_sha256


def build_dataset(
    manifest,
    out,
    *,
    conversations=2,
    clips_per_speaker=6,
    seed=42,
    noise=None,
    session_limit=None,
    require_verified_speech=False,
):
    if conversations < 1 or clips_per_speaker < 1:
        raise ValueError("conversation and clip counts must be positive")
    if session_limit is not None and not 1 <= session_limit <= conversations * 9:
        raise ValueError("session_limit must be within the requested matrix size")
    source = Path(manifest).resolve()
    metadata = json.loads(source.read_text())
    if metadata.get("split") not in {"dev", "test"}:
        raise ValueError("build from audited prepare-data dev/test manifests")
    groups = {}
    excluded_unverified = 0
    for clip in load_clips(source):
        if require_verified_speech and (
            clip.speech_annotation is None or clip.speech_annotation["status"] != "human_verified"
        ):
            excluded_unverified += 1
            continue
        groups.setdefault(clip.speaker, []).append(clip)
    if require_verified_speech and not groups:
        raise ValueError("verified speech labels required: no eligible clips")
    rng = np.random.default_rng(seed)
    for group in groups.values():
        rng.shuffle(group)
    destination = Path(out).resolve()
    if (destination / "sessions.json").exists():
        raise ValueError(
            "dataset already exists; choose a new output directory to preserve provenance"
        )
    noise_wave = read_mono_wav(noise)[0] if noise else None
    conversations_clips = []
    for index in range(1, conversations + 1):
        candidates = [s for s, clips in groups.items() if len(clips) >= clips_per_speaker]
        if len(candidates) < 3:
            raise ValueError(
                f"not enough unused clips for conversation {index}; reduce requested size"
            )
        rng.shuffle(candidates)
        candidates.sort(key=lambda s: len(groups[s]), reverse=True)
        clips = [groups[s].pop() for s in candidates[:3] for _ in range(clips_per_speaker)]
        conversations_clips.append(clips)
    sessions = []
    for index, clips in enumerate(conversations_clips, 1):
        for session in simulate_matrix(
            clips,
            seed=seed + index,
            index=index,
            noise=noise_wave,
            noise_source=str(Path(noise).resolve()) if noise else "white",
        ):
            if session_limit is not None and len(sessions) >= session_limit:
                break
            wav = write_session(destination, session)
            sessions.append(
                {
                    "audio": str(wav),
                    "reference_json": str(wav.with_suffix(".json")),
                    "reference_rttm": str(wav.with_suffix(".rttm")),
                    "oracle_rttm": str(wav.with_suffix(".oracle.rttm")),
                    "reference_kind": session.reference_kind,
                    "speech_annotation_statuses": sorted(
                        {
                            c.speech_annotation["status"]
                            if c.speech_annotation
                            else "full_clip_unverified"
                            for c in session.clips
                        }
                    ),
                    "overlap_target": session.overlap_target,
                    "overlap_actual": session.overlap_actual,
                    "conversation_id": f"{metadata['split']}_{index:03d}",
                    "condition": f"ovl{round(session.overlap_target * 100)}_"
                    f"{'clean' if session.snr_db is None else 'snr' + str(int(session.snr_db))}",
                    "split": metadata["split"],
                }
            )
    payload = {
        "seed": seed,
        "split": metadata["split"],
        "source_manifest": str(source),
        "source_sha256": file_sha256(source),
        "excluded_unverified_clips": excluded_unverified,
        "sessions": sessions,
    }
    _atomic_text(destination / "sessions.json", json.dumps(payload, ensure_ascii=False, indent=2))
    return payload
