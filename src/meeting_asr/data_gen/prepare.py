"""Audit local speech manifests and split by original speaker, before simulation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from meeting_asr.data_gen.simulate import read_mono_wav
from meeting_asr.io import _atomic_text
from meeting_asr.runtime import file_sha256
from meeting_asr.settings import config_hash


def prepare_dataset(
    manifest: str | Path,
    out: str | Path,
    *,
    dev_speakers: int = 3,
    seed: int = 42,
    excluded_hashes: set[str] | None = None,
) -> dict:
    """Require provenance, reject duplicate audio/IDs, and keep speakers disjoint.

    This audits supplied data; it cannot prove absence from pretrained model training.
    Speaker IDs must identify original people, not per-conversation display labels.
    """
    path = Path(manifest).resolve()
    entries = json.loads(path.read_text(encoding="utf-8"))["clips"]
    if not entries:
        raise ValueError("manifest contains no clips")
    ids, hashes = set(), set()
    accepted, excluded = [], []
    for entry in entries:
        for field in ("clip_id", "speaker", "text", "source", "license", "wav"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"every clip requires {field}")
        identity = (entry["source"], entry["clip_id"])
        if "vivos" in entry["source"].casefold() and "train" in entry["source"].casefold():
            raise ValueError("VIVOS train is excluded from PhoWhisper evaluation")
        if identity in ids:
            raise ValueError(f"duplicate clip ID: {identity}")
        ids.add(identity)
        wav = (path.parent / entry["wav"]).resolve()
        checksum = file_sha256(wav)
        if checksum in hashes:
            raise ValueError(f"duplicate audio checksum: {entry['clip_id']}")
        hashes.add(checksum)
        waveform, sr = read_mono_wav(wav)
        if not np.isfinite(waveform).all() or np.max(np.abs(waveform)) < 1e-4:
            raise ValueError(f"invalid or silent clip: {entry['clip_id']}")
        record = {
            **entry,
            "wav": str(wav),
            "sha256": checksum,
            "duration": len(waveform) / sr,
        }
        if checksum in (excluded_hashes or set()):
            excluded.append(record)
        else:
            accepted.append(record)
    speakers = sorted({(entry["source"], entry["speaker"]) for entry in accepted})
    if dev_speakers < 3 or len(speakers) - dev_speakers < 3:
        raise ValueError("need at least three disjoint speakers in each of dev and test")
    rng = np.random.default_rng(seed)
    rng.shuffle(speakers)
    dev = set(speakers[:dev_speakers])
    destination = Path(out)
    splits = {}
    for name in ("dev", "test"):
        clips = [e for e in accepted if ((e["source"], e["speaker"]) in dev) == (name == "dev")]
        # Qualify original speaker identity so two corpora's speaker_001 cannot collide.
        clips = [
            {**e, "speaker": f"src_{config_hash({'source': e['source']})[:8]}:{e['speaker']}"}
            for e in clips
        ]
        payload = {"seed": seed, "split": name, "clips": clips}
        _atomic_text(
            destination / f"{name}.json", json.dumps(payload, ensure_ascii=False, indent=2)
        )
        splits[name] = {"clips": len(clips), "speakers": len({e["speaker"] for e in clips})}
    report = {
        "seed": seed,
        "splits": splits,
        "excluded_clips": len(excluded),
        "training_overlap_status": "requires source-level audit; checksum exclusions only",
    }
    _atomic_text(destination / "audit.json", json.dumps(report, ensure_ascii=False, indent=2))
    return report
