"""Bridge the pinned author's DiariZen/DiCoW runtime to the meeting contracts."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
import zlib
from itertools import pairwise
from pathlib import Path

from meeting_asr.diarization import DiarizationResult
from meeting_asr.evaluation.overlap import utterance_overlap_fractions
from meeting_asr.models import ASRSignals, DiarSignals, Segment, Utterance
from meeting_asr.settings import PROJECT_ROOT

AUTHOR_COMMIT = "801e2130d00142a7da5845754f87b97550053a75"
DIARIZEN_COMMIT = "4d1009d4a3f1bc41777623e9d74b8081564cddf9"
DICOW_REVISION = "99c64e8dc409a158816e808a1ee556cdfd0af51c"
DIARIZEN_REVISION = "6285693ddd5b38e8229acb93f864f3d04a82bee1"
EVENT_PREFIX = "MEETING_DICOW_EVENT "
_TIMESTAMP = re.compile(r"<\|([0-9]+(?:\.[0-9]+)?)\|>")


def timestamped_utterances(outputs, speakers, duration):
    """Keep genuine generated timestamps; never invent a whole-file text span."""
    if len(outputs) != len(speakers) or len(set(speakers)) != len(speakers):
        raise ValueError("DiCoW outputs must align with distinct diarization speakers")
    utterances = []
    rejected = []
    for speaker, text in zip(speakers, outputs, strict=True):
        matches = list(_TIMESTAMP.finditer(text))
        usable = 0
        for left, right in pairwise(matches):
            words = text[left.end() : right.start()].strip()
            words = re.sub(r"<\|[^>]+\|>", "", words).strip()
            if not words:
                continue
            start, end = float(left[1]), float(right[1])
            if not all(math.isfinite(v) for v in (start, end)) or end <= start:
                rejected.append({"speaker": speaker, "start": start, "end": end})
                continue
            if start >= duration or end > duration + 1:
                rejected.append({"speaker": speaker, "start": start, "end": end})
                continue
            raw = words.encode("utf-8")
            utterances.append(
                Utterance(
                    start,
                    min(end, duration),
                    speaker,
                    words,
                    ASRSignals(compression_ratio=len(raw) / len(zlib.compress(raw))),
                )
            )
            usable += 1
        if text.strip() and not usable:
            raise ValueError(f"DiCoW returned no usable generated timestamps for {speaker}")
    utterances.sort(key=lambda item: (item.start, item.end, item.speaker))
    ratios = utterance_overlap_fractions(utterances)
    for utterance, ratio in zip(utterances, ratios, strict=True):
        utterance.diar = DiarSignals(ratio)
    return utterances, rejected


def author_runtime(config):
    options = config.get("dicow", {})
    python = Path(options.get("python", ".cache/dicow/venv/bin/python"))
    upstream = Path(options.get("upstream_dir", ".cache/dicow/upstream/DiCoW"))
    python = python if python.is_absolute() else PROJECT_ROOT / python
    upstream = upstream if upstream.is_absolute() else PROJECT_ROOT / upstream
    if not python.is_file() or not (upstream / "pipeline.py").is_file():
        raise RuntimeError("DiCoW runtime is missing; run: python scripts/setup_dicow.py")
    revision = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != AUTHOR_COMMIT:
        raise RuntimeError("DiCoW author checkout differs from the pinned supported commit")
    child_revision = subprocess.check_output(
        ["git", "-C", str(upstream / "DiariZen"), "rev-parse", "HEAD"], text=True
    ).strip()
    if child_revision != DIARIZEN_COMMIT:
        raise RuntimeError("DiariZen checkout differs from the author's pinned submodule")
    changed = subprocess.check_output(
        ["git", "-C", str(upstream), "diff", "HEAD", "--", "pipeline.py", "inference.py"],
        text=True,
    )
    if changed:
        raise RuntimeError("Pinned DiCoW inference source has local modifications")
    return python, upstream


def recognize_author(audio, config, destination, *, oracle_rttm=None, progress=None):
    python, upstream = author_runtime(config)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    options = config.get("dicow", {})
    payload = {
        "upstream_dir": str(upstream),
        "author_commit": AUTHOR_COMMIT,
        "model_name": config["asr"]["model_name"],
        "model_revision": options.get("model_revision", DICOW_REVISION),
        "diarization_model": config["diarization"]["model_name"],
        "diarization_revision": options.get("diarization_revision", DIARIZEN_REVISION),
        "embedding_revision": options.get(
            "embedding_revision", "837717ddb9ff5507820346191109dc79c958d614"
        ),
        "diarization_backend": config["diarization"]["backend"],
        "language": config["asr"].get("language", "vi"),
        "device": config.get("runtime", {}).get("device", "auto"),
        "diarization_batch_size": options.get("diarization_batch_size", 1),
        "max_speakers": config["diarization"].get("max_speakers", 6),
        "num_beams": options.get("num_beams", 1),
        "ctc_weight": options.get("ctc_weight", 0.0),
        "seed": config["seed"],
        "oracle_rttm": str(Path(oracle_rttm).resolve()) if oracle_rttm else None,
    }
    # The author preprocessor creates resampled.wav beside its input. Use a private
    # directory so it cannot overwrite user audio or collide with another run.
    with tempfile.TemporaryDirectory(prefix="dicow-", dir=destination) as scratch:
        from scipy.io.wavfile import write

        scratch = Path(scratch)
        prepared = scratch / "prepared.wav"
        write(prepared, audio.sr, audio.waveform)
        payload.update(audio=str(prepared), output=str(scratch / "author-output.json"))
        request = scratch / "request.json"
        request.write_text(json.dumps(payload), encoding="utf-8")
        log = destination / "dicow-runtime.log"
        runner = Path(__file__).with_name("dicow_runner.py")
        env = os.environ.copy()
        env["TOKENIZERS_PARALLELISM"] = "false"
        with log.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                [str(python), str(runner), "--request", str(request)],
                cwd=PROJECT_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=handle,
                text=True,
            )
            try:
                for line in process.stdout:
                    handle.write(line)
                    handle.flush()
                    if line.startswith(EVENT_PREFIX) and progress:
                        event = json.loads(line[len(EVENT_PREFIX) :])
                        progress(event["stage"], event["progress"])
                code = process.wait()
            except BaseException:
                process.terminate()
                process.wait()
                raise
        if code:
            # Detailed dependency/model diagnostics stay in the local log.
            raise RuntimeError(f"DiCoW author inference failed (exit {code}); see {log}")
        result = json.loads((scratch / "author-output.json").read_text())
    segments = [Segment(**segment) for segment in result["segments"]]
    diar = DiarizationResult(
        segments,
        [DiarSignals(r) for r in utterance_overlap_fractions(segments)],
        "oracle" if oracle_rttm else result["backend"],
    )
    utterances, rejected = timestamped_utterances(
        result["timestamped_outputs"], result["speakers"], audio.duration
    )
    metadata = {**result["provenance"], "rejected_timestamp_spans": rejected}
    metadata["limitations"] = [
        "Pretrained author checkpoint, not a retraining of the v1 paper.",
        "Target speakers decoded sequentially, greedy by default, to fit local GPU memory.",
        "Token log probabilities and diarization margins are unavailable; confidence is not calibrated.",
    ]
    return diar, utterances, metadata, result
