"""Freeze 40 Vietnamese dev clips and an official AMI dev room-mic excerpt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from meeting_asr.io import read_rttm, write_rttm, write_transcript_json
from meeting_asr.models import Segment, TranscriptDocument, Utterance

PROJECT = Path(__file__).resolve().parents[1]
SEED = 20261026
NITE = "{http://nite.sourceforge.net/}id"
SOURCE_LOCK = PROJECT / "document/asr_improvement_sources.lock.json"


def download_sources(root, lock=SOURCE_LOCK):
    """Fetch the small pinned AMI subset; never accept changed upstream content."""
    items = json.loads(Path(lock).read_text())
    if sum(item["bytes"] for item in items) > 2_000_000_000:
        raise ValueError("source download budget exceeds 2 GB")
    sources = root / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    for item in items:
        if Path(item["file"]).name != item["file"]:
            raise ValueError("source filename must be a path component")
        target = sources / item["file"]
        if not target.exists():
            partial = target.with_suffix(target.suffix + ".part")
            count = 0
            try:
                request = Request(item["url"], headers={"User-Agent": "meeting-asr-evaluation/1"})
                with urlopen(request, timeout=30) as response, partial.open("wb") as stream:
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > item["bytes"]:
                            raise ValueError("source exceeds locked byte count")
                        stream.write(chunk)
                if count != item["bytes"] or digest(partial) != item["sha256"]:
                    raise ValueError("download does not match source lock")
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        if target.stat().st_size != item["bytes"] or digest(target) != item["sha256"]:
            raise ValueError("existing source does not match source lock")
    (sources / "downloads.json").write_text(json.dumps(items, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ordering(row):
    return hashlib.sha256(f"round1:{SEED}:{row['id']}".encode()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pick_clips(root):
    selected = []
    for name in ("pilot/references/dev.jsonl", "manifests/fleurs_vi/dev.jsonl"):
        rows = sorted((r for r in read_rows(root / name) if r["duration_sec"] >= 5), key=ordering)
        if len(rows) < 20 or any(r["split"] != "dev" for r in rows):
            raise ValueError("20 eligible development clips required per source")
        # Round-robin by speaker where known; FLEURS uses distinct prompt IDs.
        groups = {}
        for row in rows:
            groups.setdefault(
                row.get("speaker_id") or row.get("prompt_id") or row["id"], []
            ).append(row)
        chosen = []
        while len(chosen) < 20:
            for key in sorted(groups):
                if groups[key]:
                    chosen.append(groups[key].pop(0))
                    if len(chosen) == 20:
                        break
        for row in chosen:
            for field in ("audio_path", "reference_json", "reference_rttm", "reference_uem"):
                if row.get(field):
                    row[field] = str((root / row[field]).resolve())
            row["audio_sha256"] = digest(row["audio_path"])
            selected.append(row)
    return selected


def ami_excerpt(root):
    sources = root / "sources"
    downloads = json.loads((sources / "downloads.json").read_text())
    for item in downloads:
        if digest(sources / item["file"]) != item["sha256"]:
            raise ValueError("download changed before preparing AMI")
    if "ES2011a" not in (sources / "ami_dev.list").read_text().split():
        raise ValueError("AMI meeting must be in the official development list")
    directory = root / "ami_ES2011a"
    directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(sources / "ami_public_manual_1.6.2.zip") as archive:
        names = [
            n
            for n in archive.namelist()
            if re.fullmatch(
                r"(?:words/ES2011a\.[A-D]\.words.xml|segments/ES2011a\.[A-D]\.segments.xml|corpusResources/meetings.xml)",
                n,
            )
        ]
        for name in names:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    meeting = next(
        m
        for m in ET.parse(directory / "corpusResources/meetings.xml").getroot()
        if m.get("observation") == "ES2011a"
    )
    speaker_map = {s.get("nxt_agent"): s.get("global_name") for s in meeting}
    words = {}
    for agent in "ABCD":
        words[agent] = {}
        for node in ET.parse(directory / f"words/ES2011a.{agent}.words.xml").getroot():
            if (
                node.tag != "w"
                or node.get("punc") == "true"
                or not node.text
                or not node.text.strip()
            ):
                continue
            words[agent][node.get(NITE)] = {
                "start": float(node.get("starttime")),
                "end": float(node.get("endtime")),
                "text": node.text.strip(),
                "speaker": speaker_map[agent],
            }
    all_words = [w for mapping in words.values() for w in mapping.values()]

    def boundary(target):
        candidates = [target] + [
            round(w["end"] + 0.01, 5) for w in all_words if abs(w["end"] - target) <= 10
        ]
        for value in sorted(candidates, key=lambda t: (abs(t - target), t)):
            if not any(w["start"] < value < w["end"] for w in all_words):
                return value
        raise ValueError("no word-safe excerpt boundary within ten seconds")

    start, end = boundary(600.0), boundary(780.0)
    start_sample, end_sample = round(start * 16000), round(end * 16000)
    start, end = start_sample / 16000, end_sample / 16000
    duration = end - start
    audio = directory / "ES2011a_room_excerpt.wav"
    if not audio.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(sources / "ES2011a.Array1-01.wav"),
                "-af",
                f"atrim=start_sample={start_sample}:end_sample={end_sample},asetpts=PTS-STARTPTS",
                "-c:a",
                "pcm_s16le",
                str(audio),
            ],
            check=True,
        )
    utterances, used = [], set()
    for agent in "ABCD":
        for segment in ET.parse(directory / f"segments/ES2011a.{agent}.segments.xml").getroot():
            ids = []
            for child in segment:
                targets = re.findall(r"id\(([^)]+)\)", child.get("href", ""))
                if not targets:
                    continue
                first = int(targets[0].rsplit("words", 1)[1])
                last = int(targets[-1].rsplit("words", 1)[1])
                ids.extend(f"ES2011a.{agent}.words{i}" for i in range(first, last + 1))
            items = [
                (identity, words[agent][identity])
                for identity in ids
                if identity in words[agent]
                and start <= words[agent][identity]["start"]
                and words[agent][identity]["end"] <= end
            ]
            if not items:
                continue
            a, b = min(w["start"] for _, w in items), max(w["end"] for _, w in items)
            if b <= a:
                raise ValueError("zero-duration spoken reference utterance")
            for identity, _ in items:
                if identity in used:
                    raise ValueError("reference word linked more than once")
                used.add(identity)
            utterances.append(
                Utterance(
                    a - start, b - start, speaker_map[agent], " ".join(w["text"] for _, w in items)
                )
            )
    expected = {
        identity
        for mapping in words.values()
        for identity, w in mapping.items()
        if start <= w["start"] and w["end"] <= end
    }
    if used != expected:
        raise ValueError("manual transcriber links do not cover selected words exactly")
    utterances.sort(key=lambda u: (u.start, u.end, u.speaker))
    transcript = directory / "reference.json"
    write_transcript_json(
        transcript,
        TranscriptDocument("ES2011a_excerpt", duration, 16000, "official-manual", utterances),
    )
    segments = [
        Segment(max(s.start, start) - start, min(s.end, end) - start, s.speaker)
        for s in read_rttm(sources / "ES2011a.rttm")
        if s.start < end and s.end > start
    ]
    rttm, uem = directory / "reference.rttm", directory / "reference.uem"
    write_rttm(rttm, "ES2011a_excerpt", segments)
    uem.write_text(f"ES2011a_excerpt 1 0.000000 {duration:.6f}\n")
    if {s.speaker for s in segments} != {u.speaker for u in utterances}:
        raise ValueError("reference word/diarization speaker sets differ")
    source = {
        "dataset": "ami_dev",
        "id": "ES2011a_room_excerpt",
        "recording_id": "ES2011a",
        "split": "dev",
        "language": "en",
        "duration_sec": duration,
        "audio_path": str(audio.resolve()),
        "audio_sha256": digest(audio),
        "reference_json": str(transcript.resolve()),
        "reference_rttm": str(rttm.resolve()),
        "reference_uem": str(uem.resolve()),
        "reference_status": "official_manual",
        "paper_metrics": True,
        "project_review_status": "pending",
        "license": "CC BY 4.0",
        "source_start_sec": start,
        "source_end_sec": end,
        "selected_words": len(used),
        "limitations": "English development check; AMI named in model training; not Vietnamese generalization.",
    }
    (directory / "source.json").write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n")
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse", type=Path, default=PROJECT / "data/gold/vi_asr_v1")
    parser.add_argument("--out", type=Path, default=PROJECT / "data/gold/asr_improvement_v1")
    parser.add_argument(
        "--download-sources", action="store_true", help="fetch pinned public AMI files (58.5 MB)"
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="verify/download sources without selecting clips",
    )
    args = parser.parse_args()
    root = args.out.resolve()
    if args.download_sources or args.download_only:
        download_sources(root)
    if args.download_only:
        return
    if (root / "dev.jsonl").exists():
        raise ValueError("development selection already frozen")
    rows = pick_clips(args.warehouse.resolve()) + [ami_excerpt(root)]
    (root / "dev.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (root / "selection_notes.json").write_text(
        json.dumps(
            {
                "seed": SEED,
                "rows": len(rows),
                "vietnamese_clips": 40,
                "ami_dev_excerpts": 1,
                "policy": "before prediction, speaker round robin and hash order; min 5 sec; development only",
                "audio_sec": sum(r["duration_sec"] for r in rows),
                "test_used_for_selection": False,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"frozen_rows": len(rows), "audio_sec": sum(r["duration_sec"] for r in rows)}))


if __name__ == "__main__":
    main()
