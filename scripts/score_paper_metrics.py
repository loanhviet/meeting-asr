"""Offline cpWER/tcpWER/tcORC-WER via the pinned MeetEval environment."""

import argparse
import json
from pathlib import Path

from meeting_asr.evaluation.paper import score_transcripts
from meeting_asr.io import read_transcript_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("hypothesis", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--collar", type=float, default=5.0)
    parser.add_argument("--scorer-python", type=Path)
    args = parser.parse_args()
    if args.out.resolve() in {args.reference.resolve(), args.hypothesis.resolve()}:
        parser.error("output must differ from input transcripts")
    result = score_transcripts(
        read_transcript_json(args.reference),
        read_transcript_json(args.hypothesis),
        collar=args.collar,
        scorer_python=args.scorer_python,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
