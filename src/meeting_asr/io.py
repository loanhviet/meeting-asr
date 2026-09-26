"""RTTM and transcript JSON readers/writers."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from meeting_asr.models import (
    SCHEMA_VERSION,
    ASRSignals,
    DiarSignals,
    MeetingMinutes,
    Segment,
    TranscriptDocument,
    Turn,
    Utterance,
)


def _atomic_text(path: str | Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(destination)


def write_rttm(path: str | Path, file_id: str, segments: list[Segment]) -> None:
    if not file_id or any(char.isspace() for char in file_id):
        raise ValueError("file_id must be a nonempty token")
    lines = []
    for segment in segments:
        start = round(segment.start, 3)
        duration = round(segment.duration, 3)
        if duration <= 0:
            raise ValueError("segment duration becomes zero after RTTM millisecond rounding")
        lines.append(
            f"SPEAKER {file_id} 1 {start:.3f} {duration:.3f} <NA> <NA> {segment.speaker} <NA> <NA>"
        )
    _atomic_text(path, "\n".join(lines) + ("\n" if lines else ""))


def read_rttm(path: str | Path, expected_file_id: str | None = None) -> list[Segment]:
    segments = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 10 or fields[0] != "SPEAKER" or fields[2] != "1":
            raise ValueError(f"invalid RTTM line {line_number}: {path}")
        if expected_file_id is not None and fields[1] != expected_file_id:
            raise ValueError(f"unexpected file_id on RTTM line {line_number}: {fields[1]}")
        if fields[5:7] != ["<NA>", "<NA>"] or fields[8:] != ["<NA>", "<NA>"]:
            raise ValueError(f"invalid RTTM placeholders on line {line_number}: {path}")
        start, duration = float(fields[3]), float(fields[4])
        if duration <= 0:
            raise ValueError(f"nonpositive RTTM duration on line {line_number}: {path}")
        segments.append(Segment(start=start, end=start + duration, speaker=fields[7]))
    return segments


def write_transcript_json(path: str | Path, transcript: TranscriptDocument) -> None:
    payload = asdict(transcript)
    payload["schema_version"] = SCHEMA_VERSION
    payload["num_speakers"] = transcript.num_speakers
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_transcript_json(path: str | Path) -> TranscriptDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported transcript schema: {payload.get('schema_version')}")
    utterances = [
        Utterance(
            start=item["start"],
            end=item["end"],
            speaker=item["speaker"],
            text=item["text"],
            asr=ASRSignals(**item["asr"]),
            diar=DiarSignals(**item["diar"]) if item.get("diar") is not None else None,
        )
        for item in payload["utterances"]
    ]
    result = TranscriptDocument(
        audio_id=payload["audio_id"],
        duration=payload["duration"],
        sample_rate=payload["sample_rate"],
        config_hash=payload["config_hash"],
        utterances=utterances,
    )
    if result.num_speakers != payload["num_speakers"]:
        raise ValueError("transcript num_speakers disagrees with utterances")
    return result


def minutes_from_dict(payload: dict) -> MeetingMinutes:
    payload = dict(payload)
    payload.pop("schema_version", None)
    turns = []
    for item in payload.pop("turns"):
        item = dict(item)
        utterances = []
        for raw in item.pop("utterances"):
            raw = dict(raw)
            raw["asr"] = ASRSignals(**raw["asr"])
            raw["diar"] = DiarSignals(**raw["diar"]) if raw.get("diar") else None
            utterances.append(Utterance(**raw))
        turns.append(Turn(**item, utterances=utterances))
    return MeetingMinutes(**payload, turns=turns)


def write_minutes_json(path: str | Path, minutes: MeetingMinutes) -> None:
    _atomic_text(
        path,
        json.dumps(
            {"schema_version": SCHEMA_VERSION, **asdict(minutes)}, ensure_ascii=False, indent=2
        ),
    )
