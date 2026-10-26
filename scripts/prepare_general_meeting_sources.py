"""Download one AMI room microphone and pair it with existing manual references."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
AMI_URL = (
    "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/ES2004a/audio/ES2004a.Array1-01.wav"
)
AMI_SOURCE_SHA256 = "6936edac5d0904fc5c4ab175546c5cc5366601fdc1b1e5183a6ea2c10f05d150"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=PROJECT / "data/gold/general_meetings_v1")
    args = parser.parse_args()
    root = args.out.resolve()
    sources = root / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    original = sources / "ami_ES2004a.Array1-01.wav"
    if not original.exists():
        temporary = original.with_suffix(".part")
        with (
            urllib.request.urlopen(AMI_URL, timeout=90) as response,
            temporary.open("wb") as target,
        ):
            shutil.copyfileobj(response, target)
        temporary.replace(original)
    if sha256(original) != AMI_SOURCE_SHA256:
        raise ValueError("AMI room source checksum does not match the pinned evaluation audio")
    probe = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(original)], text=True
        )
    )["streams"][0]
    if int(probe["sample_rate"]) != 16000 or probe["channels"] != 1:
        raise ValueError("expected mono 16 kHz AMI source for sample-exact excerpt")
    room = root / "audio/ami_ES2004a_room_3min.wav"
    room.parent.mkdir(parents=True, exist_ok=True)
    if not room.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(original),
                "-af",
                "atrim=start_sample=4819200:end_sample=7684880,asetpts=PTS-STARTPTS",
                "-c:a",
                "pcm_s16le",
                str(room),
            ],
            check=True,
        )
    reference = PROJECT / "data/real/ami_es2004a/sample_3min"
    source = json.loads((reference / "source.json").read_text())
    common = {
        "split": "supplementary_en",
        "language": "en",
        "recording_id": "ES2004a",
        "duration_sec": source["duration_sec"],
        "reference_status": "source_manual",
        "project_review_status": "pending",
        "reference_json": str(reference / "reference.json"),
        "reference_rttm": str(reference / "reference.rttm"),
        "reference_uem": str(reference / "reference.uem"),
        "license": "CC BY 4.0",
        "limitations": [
            "English supplementary check; AMI is named in model training data.",
            "Paired microphones of the same meeting are not independent meetings.",
        ],
    }
    rows = [
        {
            **common,
            "dataset": "ami_headset",
            "id": "ES2004a_headset_excerpt",
            "audio_path": str(reference / "AMI_ES2004a_4_nguoi_3_phut.wav"),
        },
        {**common, "dataset": "ami_room", "id": "ES2004a_room_excerpt", "audio_path": str(room)},
    ]
    # COSV has no timestamps and ambiguous speaker labels: score only full-recording text.
    cosv = PROJECT / "data/real/cosv_duc_ly"
    rows.append(
        {
            "dataset": "cosv",
            "id": "cosv_duc_ly_full",
            "recording_id": "cosv_duc_ly",
            "split": "exploratory",
            "language": "vi",
            "audio_path": str(cosv / "full.mp3"),
            "duration_sec": json.loads((cosv / "source.json").read_text())["duration_sec"],
            "reference_text": (cosv / "reference_text.txt").read_text(),
            "reference_status": "source_manual_no_timestamps",
            "project_review_status": "pending",
            "license": None,
            "limitations": [
                "Spontaneous interview, not a workplace meeting.",
                "Full source transcript only; no DER/cpWER or temporal alignment claims.",
            ],
        }
    )
    (root / "extra_samples.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    metadata = {
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source_url": AMI_URL,
        "source_bytes": original.stat().st_size,
        "source_sha256": sha256(original),
        "excerpt_sha256": sha256(room),
        "excerpt_start_sec": 301.2,
        "excerpt_end_sec": 480.305,
        "excerpt_samples": 2865680,
        "microphone": "Array1-01, single distant microphone, not beamformed",
        "license": "CC BY 4.0",
        "annotation_url": "https://groups.inf.ed.ac.uk/ami/download/",
        "selection": "same pre-existing excerpt as headset, before running either prediction",
    }
    (root / "source_lock.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(
        json.dumps(
            {
                "extra_samples": len(rows),
                "new_download_bytes": original.stat().st_size,
                "source_sha256": metadata["source_sha256"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
