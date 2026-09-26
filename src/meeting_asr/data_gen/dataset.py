"""Build an audited experiment manifest from disjoint pools of local clips."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from meeting_asr.data_gen.simulate import load_clips, read_mono_wav, simulate_matrix, write_session
from meeting_asr.io import _atomic_text


def build_dataset(manifest, out, *, conversations=2, clips_per_speaker=6, seed=42, noise=None):
    if conversations < 1 or clips_per_speaker < 1:
        raise ValueError("conversation and clip counts must be positive")
    source = Path(manifest).resolve()
    metadata = json.loads(source.read_text())
    if metadata.get("split") not in {"dev", "test"}:
        raise ValueError("build from audited prepare-data dev/test manifests")
    groups = {}
    for clip in load_clips(source):
        groups.setdefault(clip.speaker, []).append(clip)
    rng = np.random.default_rng(seed)
    for group in groups.values():
        rng.shuffle(group)
    destination = Path(out).resolve()
    noise_wave = read_mono_wav(noise)[0] if noise else None
    sessions = []
    for index in range(1, conversations + 1):
        candidates = [s for s, clips in groups.items() if len(clips) >= clips_per_speaker]
        if len(candidates) < 3:
            raise ValueError(
                f"not enough unused clips for conversation {index}; reduce requested size"
            )
        rng.shuffle(candidates)
        candidates.sort(key=lambda s: len(groups[s]), reverse=True)
        clips = [groups[s].pop() for s in candidates[:3] for _ in range(clips_per_speaker)]
        for session in simulate_matrix(
            clips,
            seed=seed + index,
            index=index,
            noise=noise_wave,
            noise_source=str(Path(noise).resolve()) if noise else "white",
        ):
            wav = write_session(destination, session)
            sessions.append(
                {
                    "audio": str(wav),
                    "reference_json": str(wav.with_suffix(".json")),
                    "reference_rttm": str(wav.with_suffix(".rttm")),
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
        "sessions": sessions,
    }
    _atomic_text(destination / "sessions.json", json.dumps(payload, ensure_ascii=False, indent=2))
    return payload
