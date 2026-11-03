"""Index collected evaluation data and export a small, source-disjoint ASR pilot.

Run with the isolated pyarrow environment described in the dataset README.
This script does not run ASR/LLMs or promote source labels to local human verification.
Manifest paths are relative to the dataset root, including links to existing local data.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import random
import re
import struct
import subprocess
import tarfile
from collections import Counter, defaultdict, deque
from pathlib import Path

import pyarrow.parquet as pq


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def wav_info(data):
    """Read PCM/float RIFF headers without silently converting float source audio."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("expected RIFF WAVE audio")
    stream = io.BytesIO(data)
    stream.seek(12)
    fmt = size = None
    while header := stream.read(8):
        if len(header) != 8:
            raise ValueError("truncated WAV chunk")
        tag, length = struct.unpack("<4sI", header)
        if tag == b"fmt ":
            fmt = struct.unpack("<HHIIHH", stream.read(16))
            stream.seek(length - 16, 1)
        else:
            if tag == b"data":
                size = length
                if stream.tell() + size > len(data):
                    raise ValueError("truncated WAV samples")
            stream.seek(length, 1)
        if length % 2:
            stream.seek(1, 1)
    if fmt is None or size is None or not fmt[4] or size % fmt[4]:
        raise ValueError("invalid WAV format/data sizes")
    return {
        "sample_rate": fmt[2],
        "channels": fmt[1],
        "sample_count": size // fmt[4],
        "duration_sec": size / fmt[4] / fmt[2],
        "bits_per_sample": fmt[5],
        "wav_format_code": fmt[0],
    }


def pcm_wav(encoded, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            "pipe:0",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        input=encoded,
        capture_output=True,
        check=True,
    )
    return wav_info(output.read_bytes())


class Collection:
    def __init__(self, root):
        self.root = root.resolve()
        self.project = Path(__file__).resolve().parents[1]
        self.rows = defaultdict(list)
        self.audit = {
            "model_inference_run": False,
            "local_human_verification": False,
            "issues": [],
            "pilot": {},
        }

    def relative(self, path):
        return os.path.relpath(Path(path).resolve(), self.root)

    def add(self, dataset, split, row):
        self.rows[(dataset, split)].append(
            {
                "dataset": dataset,
                "split": split,
                "language": "vi",
                "reference_status": "source_provided",
                "project_review_status": "pending",
                **row,
            }
        )

    def parquet_audio(self, dataset, split, path):
        index = 0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=8):
            for original in batch.to_pylist():
                row = dict(original)
                audio = row.pop("audio")
                data = audio["bytes"]
                if not data:
                    raise ValueError(f"missing embedded audio: {path}:{index}")
                if dataset == "vietmed":
                    identity = row["utterance_id"]
                    output = self.root / "audio" / dataset / split / f"{identity}.ogg"
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(data)
                    record = {
                        "id": identity,
                        "audio_path": self.relative(output),
                        "duration_sec": row["duration"],
                        "reference_text": row["text"],
                        "speaker_id": row["speaker_name"],
                        "recording_id": row["audio_name"],
                        "accent": row["accent"],
                        "gender": row["gender"],
                        "role": row["role"],
                        "recording_condition": row["rec_condition"],
                        "source_sequence": row["seq_name"],
                        "source_audio_name": audio["path"],
                        "license": "MIT (dataset card)",
                    }
                elif dataset == "vimd":
                    info = wav_info(data)
                    record = {
                        "id": row["filename"],
                        "audio_path": None,
                        **info,
                        "reference_text": row["text"],
                        "speaker_id": row["speakerID"],
                        "recording_id": None,
                        "province_code": str(row["province_code"]),
                        "province_name": row["province_name"],
                        "region": row["region"],
                        "gender": str(row["gender"]),
                        "license": "CC BY-NC-ND 4.0",
                        "audio_locator": {"parquet": self.relative(path), "row": index},
                    }
                else:
                    identity = row["audio_id"]
                    if not re.fullmatch(r"[\w-]+", identity):
                        raise ValueError("unsafe audio ID")
                    info = wav_info(data)
                    output = self.root / "audio" / dataset / f"{identity}.wav"
                    converted = pcm_wav(data, output)
                    if converted["sample_count"] != info["sample_count"]:
                        raise ValueError("ViYT sample count changed during PCM conversion")
                    starts, ends, speakers = (
                        row[k] for k in ("timestamps_start", "timestamps_end", "speaker")
                    )
                    if not len(starts) == len(ends) == len(speakers):
                        raise ValueError("diarization label lengths disagree")
                    labels, invalid = [], []
                    for start, end, speaker in zip(starts, ends, speakers, strict=True):
                        if (
                            not math.isfinite(start)
                            or not math.isfinite(end)
                            or not 0 <= start < end <= info["duration_sec"] + 0.001
                        ):
                            invalid.append([start, end, speaker])
                        labels.append(
                            f"SPEAKER {identity} 1 {start:.6f} {end - start:.6f} "
                            f"<NA> <NA> {speaker} <NA> <NA>"
                        )
                    label_path = self.root / "references" / dataset / f"{identity}.rttm"
                    label_path.parent.mkdir(parents=True, exist_ok=True)
                    label_path.write_text("\n".join(labels) + "\n")
                    label_path.with_suffix(".uem").write_text(
                        f"{identity} 1 0.000000 {info['duration_sec']:.6f}\n"
                    )
                    record = {
                        "id": identity,
                        "recording_id": identity,
                        **converted,
                        "audio_path": self.relative(output),
                        "reference_text": None,
                        "reference_rttm": self.relative(label_path),
                        "reference_uem": self.relative(label_path.with_suffix(".uem")),
                        "num_speakers": len(set(speakers)),
                        "segments": len(speakers),
                        "label_bounds_valid": not invalid,
                        "license": "Apache-2.0 (card)",
                    }
                    if invalid:
                        self.audit["issues"].append(
                            {"dataset": dataset, "id": identity, "invalid_intervals": invalid}
                        )
                record["source_audio_sha256"] = digest(data)
                record["source_annotation"] = {"file": self.relative(path), "row": index}
                self.add(dataset, split, record)
                index += 1

    def fleurs(self, split):
        source = self.root / "sources/fleurs_vi/data/vi_vn"
        target = self.root / "audio/fleurs_vi" / split
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(source / "audio" / f"{split}.tar.gz", "r:gz") as archive:
            for member in archive:
                if not member.isfile() or not member.name.endswith(".wav"):
                    continue
                if Path(member.name).parent.as_posix() not in {split, "."}:
                    raise ValueError("unexpected FLEURS archive path")
                with archive.extractfile(member) as stream:
                    (target / Path(member.name).name).write_bytes(stream.read())
        with (source / f"{split}.tsv").open(encoding="utf-8") as stream:
            # FLEURS uses literal tabs; quotation marks belong to spoken text.
            for line, fields in enumerate(
                csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
            ):
                prompt, name, raw, text, _, samples, gender = fields
                audio = target / name
                data = audio.read_bytes()
                info = wav_info(data)
                if info["sample_count"] != int(samples) or info["sample_rate"] != 16000:
                    raise ValueError("FLEURS audio differs from TSV sample count")
                self.add(
                    "fleurs_vi",
                    split,
                    {
                        "id": name,
                        "audio_path": self.relative(audio),
                        **info,
                        "reference_text": text,
                        "raw_reference_text": raw,
                        "prompt_id": prompt,
                        "speaker_id": None,
                        "recording_id": None,
                        "gender": gender,
                        "source_audio_sha256": digest(data),
                        "license": "CC BY 4.0",
                        "source_annotation": {
                            "file": self.relative(source / f"{split}.tsv"),
                            "row": line,
                        },
                    },
                )

    def existing(self):
        source = self.project / "data/raw/vivos/test"
        downloaded = self.root / "sources/vivos/data/prompts-test.txt.gz"
        if gzip.decompress(downloaded.read_bytes()) != (source / "prompts.txt").read_bytes():
            raise ValueError("local VIVOS prompts differ from pinned official test prompts")
        original_splits = {}
        for split in ("dev", "test"):
            manifest = self.project / f"data/audited/{split}.json"
            for row in json.loads(manifest.read_text())["clips"]:
                original_splits[row["clip_id"]] = split
        for line in (source / "prompts.txt").read_text(encoding="utf-8").splitlines():
            identity, text = line.split(maxsplit=1)
            speaker = identity.split("_")[0]
            audio = source / "waves" / speaker / f"{identity}.wav"
            data = audio.read_bytes()
            self.add(
                "vivos",
                "official_test",
                {
                    "id": identity,
                    "audio_path": self.relative(audio),
                    **wav_info(data),
                    "reference_text": text,
                    "speaker_id": speaker,
                    "recording_id": None,
                    "license": "CC BY-NC-SA 4.0",
                    "project_previous_split": original_splits.get(identity),
                    "source_audio_sha256": digest(data),
                    "source_annotation": {"file": self.relative(source / "prompts.txt")},
                },
            )
        for name in ("cosv_dung_an", "cosv_duc_ly"):
            folder = self.project / "data/real" / name
            meta = json.loads((folder / "source.json").read_text())
            audio = folder / "full.mp3"
            self.add(
                "cosv",
                "exploratory",
                {
                    "id": name,
                    "recording_id": name,
                    "audio_path": self.relative(audio),
                    "duration_sec": meta["duration_sec"],
                    "reference_text": (folder / "reference_text.txt").read_text(),
                    "reference_turns": self.relative(folder / "reference_turns.json"),
                    "source_audio_sha256": file_digest(audio),
                    "license": None,
                    "source_url": meta["source_url"],
                    "timestamp_annotation": None,
                    "speaker_reference_complete": False,
                    "available_metrics": ["WER", "CER"],
                    "limitation": "Full reference matches full audio only; no DER or verified cpWER.",
                },
            )
        folder = self.project / "data/real/ami_es2004a/sample_3min"
        meta = json.loads((folder / "source.json").read_text())
        self.add(
            "ami",
            "supplementary_en",
            {
                "id": "ES2004a_excerpt",
                "language": "en",
                "recording_id": "ES2004a",
                "duration_sec": meta["duration_sec"],
                "audio_path": self.relative(folder / meta["audio"]),
                "reference_text": (folder / "reference_text.txt").read_text(),
                "reference_json": self.relative(folder / "reference.json"),
                "reference_rttm": self.relative(folder / "reference.rttm"),
                "source_audio_sha256": meta["audio_sha256"],
                "license": "CC BY 4.0",
                "limitation": "English; AMI named in DiCoW training; report separately.",
            },
        )

    def text_datasets(self):
        folder = self.root / "sources/vietmed_sum/data"
        for path in sorted(folder.glob("*.parquet")):
            variant = path.name.split("-00000")[0]
            split = variant.split(".")[0]
            rows = pq.read_table(path).to_pylist()
            for index, raw in enumerate(rows):
                self.add(
                    "vietmed_sum",
                    variant,
                    {
                        "id": f"{variant}_{index:05d}",
                        "official_split": split,
                        "source_annotation": {"file": self.relative(path), "row": index},
                        "source_fields": raw,
                        "license": None,
                        "reference_status": "source_gold_human_edited_llm_assisted",
                        "input_kind": "asr" if "_asr" in variant else "reference_transcript",
                    },
                )
        for split in ("train", "val", "test"):
            path = self.root / "sources/qmsum/data/ALL/jsonl" / f"{split}.jsonl"
            for line, text in enumerate(path.read_text(encoding="utf-8").splitlines()):
                raw = json.loads(text)
                meeting_hash = digest(
                    json.dumps(raw["meeting_transcripts"], sort_keys=True).encode()
                )
                self.add(
                    "qmsum",
                    split,
                    {
                        "id": meeting_hash[:20],
                        "language": "en",
                        "recording_id": meeting_hash,
                        "source_fields": raw,
                        "license": "MIT repository; retain original corpus terms",
                        "source_annotation": {"file": self.relative(path), "row": line},
                    },
                )

    def make_pilot(self):
        dev = self.rows[("vietmed", "dev")]
        test = self.rows[("vietmed", "test")]
        shared = sorted({r["recording_id"] for r in dev} & {r["recording_id"] for r in test})
        self.audit["vietmed_shared_official_recordings"] = shared
        self.audit["vietmed_official_speaker_overlap"] = sorted(
            {r["speaker_id"] for r in dev} & {r["speaker_id"] for r in test}
        )
        for split, rows in (("dev", dev), ("test", test)):
            buckets = defaultdict(list)
            for row in rows:
                if split == "dev" and row["recording_id"] in shared:
                    continue
                buckets[row["speaker_id"]].append(row)
            rng = random.Random(42)
            for group in buckets.values():
                rng.shuffle(group)
            groups = deque(deque(buckets[k]) for k in sorted(buckets))
            selected, duration = [], 0.0
            while groups and duration < 1800:
                group = groups.popleft()
                row = dict(group.popleft())
                selected.append(row)
                duration += row["duration_sec"]
                if group:
                    groups.append(group)
            for row in selected:
                source = self.root / row["audio_path"]
                output = self.root / "pilot/audio" / split / f"{row['id']}.wav"
                info = pcm_wav(source.read_bytes(), output)
                if abs(info["duration_sec"] - row["duration_sec"]) > 0.05:
                    raise ValueError("VietMed decoded duration mismatch")
                row.update(audio_path=self.relative(output), **info)
            write_jsonl(self.root / f"pilot/references/{split}.jsonl", selected)
            write_jsonl(
                self.root / f"pilot/inputs/{split}.jsonl",
                [
                    {k: row[k] for k in ("id", "audio_path", "language", "duration_sec", "dataset")}
                    for row in selected
                ],
            )
            self.audit["pilot"][split] = {
                "clips": len(selected),
                "duration_sec": duration,
                "recordings": sorted({r["recording_id"] for r in selected}),
                "speakers": sorted({r["speaker_id"] for r in selected}),
                "accents": dict(Counter(r["accent"] for r in selected)),
                "gender": dict(Counter(r["gender"] for r in selected)),
                "role": dict(Counter(r["role"] for r in selected)),
            }
            csv_path = self.root / f"pilot/review_{split}.csv"
            if not csv_path.exists():
                with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
                    fields = [
                        "id",
                        "audio_path",
                        "source_reference",
                        "reviewed_text",
                        "reviewed_by",
                        "reviewed_at",
                        "status",
                        "notes",
                    ]
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    for row in selected:
                        writer.writerow(
                            {
                                "id": row["id"],
                                "audio_path": row["audio_path"],
                                "source_reference": row["reference_text"],
                                "status": "pending",
                            }
                        )

    def save(self):
        stats = []
        for (dataset, split), rows in sorted(self.rows.items()):
            ids = [r["id"] for r in rows]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate IDs in {dataset}/{split}")
            write_jsonl(self.root / f"manifests/{dataset}/{split}.jsonl", rows)
            inputs, targets = [], []
            for row in rows:
                identity = {k: row[k] for k in ("id", "dataset", "split", "language")}
                if dataset == "vietmed_sum":
                    inputs.append({**identity, "transcript": row["source_fields"]["transcript"]})
                    targets.append({**identity, "summary": row["source_fields"]["summary"]})
                elif dataset == "qmsum":
                    raw = row["source_fields"]
                    queries = raw["general_query_list"] + raw["specific_query_list"]
                    for index, query in enumerate(queries):
                        key = {**identity, "id": f"{row['id']}_q{index:03d}"}
                        inputs.append(
                            {
                                **key,
                                "query": query["query"],
                                "meeting_transcripts": raw["meeting_transcripts"],
                            }
                        )
                        targets.append(
                            {
                                **key,
                                "answer": query["answer"],
                                "relevant_text_span": query.get("relevant_text_span"),
                            }
                        )
                else:
                    inputs.append(
                        {
                            **identity,
                            **{
                                k: row[k]
                                for k in ("audio_path", "audio_locator", "duration_sec")
                                if k in row
                            },
                        }
                    )
            write_jsonl(self.root / f"inputs/{dataset}/{split}.jsonl", inputs)
            if targets:
                write_jsonl(self.root / f"references/{dataset}/{split}.jsonl", targets)
            stats.append(
                {
                    "dataset": dataset,
                    "split": split,
                    "rows": len(rows),
                    "duration_sec": sum(r.get("duration_sec", 0) for r in rows),
                    "speakers": len({r["speaker_id"] for r in rows if r.get("speaker_id")}),
                    "provinces": len({r["province_code"] for r in rows if r.get("province_code")}),
                }
            )
        # QMSum overlaps AMI/ICSI by construction, so it is a separate text benchmark.
        qmsum_sets = {
            s: {r["recording_id"] for r in self.rows[("qmsum", s)]}
            for s in ("train", "val", "test")
        }
        self.audit["qmsum_transcript_overlap"] = {
            f"{a}/{b}": len(qmsum_sets[a] & qmsum_sets[b])
            for a, b in (("train", "val"), ("train", "test"), ("val", "test"))
        }
        self.audit["pilot_recording_disjoint"] = not bool(
            set(self.audit["pilot"]["dev"]["recordings"])
            & set(self.audit["pilot"]["test"]["recordings"])
        )
        self.audit["pilot_speaker_disjoint"] = not bool(
            set(self.audit["pilot"]["dev"]["speakers"])
            & set(self.audit["pilot"]["test"]["speakers"])
        )
        if not self.audit["pilot_recording_disjoint"] or not self.audit["pilot_speaker_disjoint"]:
            raise ValueError("pilot split leakage")
        self.audit["statistics"] = stats
        write_json(self.root / "audit.json", self.audit)
        print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    collection = Collection(args.root)
    for dataset, split, pattern in (
        ("vietmed", "dev", "dev-*.parquet"),
        ("vietmed", "test", "test-*.parquet"),
        ("vimd", "test", "data/test-*.parquet"),
        ("viyt_diar", "test", "data/test-*.parquet"),
    ):
        for path in sorted((collection.root / "sources" / dataset).glob(pattern)):
            collection.parquet_audio(dataset, split, path)
            print(f"Indexed {dataset}/{path.name}", flush=True)
    for split in ("dev", "test"):
        collection.fleurs(split)
        print(f"Indexed fleurs_vi/{split}", flush=True)
    collection.existing()
    collection.text_datasets()
    collection.make_pilot()
    collection.save()


if __name__ == "__main__":
    main()
