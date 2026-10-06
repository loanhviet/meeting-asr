"""Conservative independent VAD candidates; never label them human verified."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import numpy as np

from meeting_asr.data_gen.simulate import read_mono_wav
from meeting_asr.io import _atomic_text
from meeting_asr.runtime import file_sha256


def conservative_intervals(support, *, sr=16000, min_quiet_sec=0.25, pad_sec=0.1):
    support = np.asarray(support, dtype=bool)
    if support.ndim != 1 or not len(support):
        raise ValueError("speech support must be a nonempty mask")
    if not support.any():
        return [[0, len(support) / sr]]
    edges = np.diff(np.r_[False, ~support, False].astype(np.int8))
    retained = np.ones(len(support), dtype=bool)
    for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True):
        if end - start < round(min_quiet_sec * sr):
            continue
        left = start + (round(pad_sec * sr) if start else 0)
        right = end - (round(pad_sec * sr) if end < len(support) else 0)
        if right > left:
            retained[left:right] = False
    edges = np.diff(np.r_[False, retained, False].astype(np.int8))
    return [
        [int(a) / sr, int(b) / sr]
        for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True)
    ]


def propose_speech(manifest, out):
    try:
        import webrtcvad
    except ImportError as exc:
        raise RuntimeError("install the annotation extra to propose speech labels") from exc
    source = Path(manifest).resolve()
    if source == Path(out).resolve():
        raise ValueError("write proposals to a new manifest; preserve the original")
    payload = json.loads(source.read_text(encoding="utf-8"))
    seen = set()
    for clip in payload["clips"]:
        identity = (clip["source"], clip["clip_id"])
        if identity in seen:
            raise ValueError(f"duplicate clip: {identity}")
        seen.add(identity)
        wav = (source.parent / clip["wav"]).resolve()
        checksum = file_sha256(wav)
        if clip.get("sha256", checksum) != checksum:
            raise ValueError(f"audio checksum mismatch: {clip['clip_id']}")
        clip["wav"], clip["sha256"] = str(wav), checksum
        if clip.get("speech_annotation", {}).get("status") == "human_verified":
            continue
        waveform, sr = read_mono_wav(wav)
        pcm = np.clip(np.round(waveform * 32768), -32768, 32767).astype("<i2")
        vad = webrtcvad.Vad(0)
        support = np.zeros(len(waveform), dtype=bool)
        for start in range(0, len(pcm), 320):
            frame = np.pad(pcm[start : start + 320], (0, max(0, start + 320 - len(pcm))))
            if vad.is_speech(frame.tobytes(), sr):
                support[start : start + 320] = True
        frames = np.pad(waveform, (0, (-len(waveform)) % 160)).reshape(-1, 160)
        rms = np.sqrt(np.mean(frames**2, axis=1))
        support |= np.repeat(rms >= max(float(np.max(np.abs(waveform))) * 0.01, 1e-6), 160)[
            : len(waveform)
        ]
        clip["speech_intervals"] = conservative_intervals(support)
        clip["speech_annotation"] = {
            "status": "automatic_unverified",
            "method": "webrtc-energy-conservative",
            "version": "v1",
            "vad_version": importlib.metadata.version("webrtcvad-wheels"),
            "parameters": {
                "vad_mode": 0,
                "frame_ms": 20,
                "energy_peak_ratio": 0.01,
                "min_quiet_ms": 250,
                "padding_ms": 100,
            },
            "needs_listening": True,
            "no_supported_speech": not bool(support.any()),
        }
    payload["speech_proposal"] = {
        "source_manifest_sha256": file_sha256(source),
        "status": "automatic_unverified",
        "limitations": "VAD/energy may miss quiet speech or retain noise. Listen before treating labels as ground truth.",
    }
    _atomic_text(Path(out), json.dumps(payload, ensure_ascii=False, indent=2))
    return {"clips": len(payload["clips"]), "out": str(Path(out).resolve())}
