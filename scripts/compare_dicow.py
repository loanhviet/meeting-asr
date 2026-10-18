"""Compare real baseline/DiCoW artifacts without treating predictions as gold."""

import argparse
import json
from pathlib import Path


def describe(folder):
    run = json.loads((folder / "run.json").read_text())
    minutes = json.loads((folder / "minutes.json").read_text())
    author_path = folder / "dicow-provenance.json"
    author = json.loads(author_path.read_text()) if author_path.exists() else None
    return {
        "output_dir": str(folder.resolve()),
        "audio_sha256": run["audio_sha256"],
        "config_hash": run["config_hash"],
        "duration_sec": minutes["duration"],
        "predicted_speakers": minutes["num_speakers"],
        "predicted_turns": len(minutes["turns"]),
        "elapsed_sec": run["result"]["elapsed_sec"],
        "rtf": run["result"]["rtf"],
        "stages": run["result"]["stages"],
        "author_provenance": author,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("dicow", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    baseline, dicow = describe(args.baseline), describe(args.dicow)
    if baseline["audio_sha256"] != dicow["audio_sha256"]:
        parser.error("Both runs must use identical source audio")
    if abs(baseline["duration_sec"] - dicow["duration_sec"]) > 0.01:
        parser.error("Preprocessed audio durations differ")
    report = {
        "baseline": baseline,
        "dicow": dicow,
        "wer": None,
        "cpwer": None,
        "der": None,
        "quality_status": "not_scored_no_verified_reference_for_this_excerpt",
        "limitations": [
            "Model predictions and automatically generated captions are not ground truth.",
            "This changes both diarization and ASR; it is a system comparison, not an isolated FDDT ablation.",
            "Timing includes model loading; check cache_hit fields before comparing speed.",
            "Speaker counts and turn counts do not measure transcription accuracy.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
