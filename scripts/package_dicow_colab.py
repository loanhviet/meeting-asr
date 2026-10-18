"""Bundle this working branch and optional sample audio for a Colab trial."""

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/dicow-author/colab-bundle.zip")
    parser.add_argument("--include-samples", action="store_true")
    args = parser.parse_args()
    files = set()
    for pattern in ["src/**/*.py", "configs/*.yaml", "requirements/dicow*.txt"]:
        files.update(ROOT.glob(pattern))
    for name in [
        "pyproject.toml",
        "README.md",
        "DICOW.md",
        "DICOW_COMPARISON.md",
        "uv.lock",
        "scripts/setup_dicow.py",
        "scripts/compare_dicow.py",
        "scripts/score_dicow_quality.py",
    ]:
        files.add(ROOT / name)
    if args.include_samples:
        for name, filename in [
            ("cosv_duc_ly", "sample_first_5min.wav"),
            ("cosv_dung_an", "sample_first_5min.wav"),
            ("haveasip_13_giang_oi", "sample_5min.wav"),
        ]:
            files.add(ROOT / "data/real" / name / filename)
            files.add(ROOT / "data/real" / name / "source.json")
    missing = [str(p.relative_to(ROOT)) for p in files if not p.is_file()]
    if missing:
        parser.error("Missing bundle inputs: " + ", ".join(missing))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for p in sorted(files):
            bundle.write(p, Path("meeting_asr") / p.relative_to(ROOT))
    print(f"Saved {args.out} ({args.out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
