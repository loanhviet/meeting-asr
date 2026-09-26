"""Independent command-line entry point for completed pipeline stages."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from meeting_asr.cache import load_audio_bundle, save_audio_bundle, stage_key
from meeting_asr.data_gen.simulate import load_clips, simulate_matrix, write_session
from meeting_asr.io import read_rttm
from meeting_asr.preprocess import preprocess
from meeting_asr.runtime import set_seed, write_run_manifest
from meeting_asr.settings import DEFAULT_CONFIG, PROJECT_ROOT, load_config


def _project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _run_preprocess(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    set_seed(int(config["seed"]))
    audio_path = Path(args.audio).resolve()
    options = config["preprocess"]
    cache_dir = _project_path(config["paths"]["cache_dir"]) / "preprocess"
    key = stage_key(audio_path, config, "preprocess", "1")
    start = time.perf_counter()
    audio = None if args.no_cache else load_audio_bundle(cache_dir, key)
    cache_hit = audio is not None
    if audio is None:
        audio = preprocess(audio_path, **options)
        save_audio_bundle(cache_dir, key, audio)
    result = {
        "stage": "preprocess",
        "source": str(audio_path),
        "cache_hit": cache_hit,
        "cache_key": key,
        "sample_rate": audio.sr,
        "original_sample_rate": audio.original_sr,
        "duration_sec": round(audio.duration, 3),
        "normalization_method": audio.normalization_method,
        "warnings": audio.warnings,
        "elapsed_sec": round(time.perf_counter() - start, 3),
    }
    run_dir = _project_path(config["paths"]["results_dir"]) / "runs"
    run_id = f"{int(time.time_ns())}_{key[:8]}"
    write_run_manifest(
        run_dir / f"{run_id}.json", config=config, audio_path=audio_path, result=result
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _run_simulate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    seed = int(config["seed"] if args.seed is None else args.seed)
    set_seed(seed)
    sessions = simulate_matrix(load_clips(args.manifest), seed=seed, index=args.index)
    out_dir = _project_path(args.out)
    written = []
    for session in sessions:
        wav_path = write_session(out_dir, session)
        written.append(
            {
                "stem": session.stem,
                "wav": str(wav_path),
                "overlap_target": session.overlap_target,
                "overlap_actual": round(session.overlap_actual, 4),
                "snr_db": session.snr_db,
                "snr_actual_db": None
                if session.snr_actual_db is None
                else round(session.snr_actual_db, 3),
            }
        )
    print(json.dumps({"seed": seed, "sessions": written}, ensure_ascii=False, indent=2))
    return 0


def _run_rttm_validate(args: argparse.Namespace) -> int:
    segments = read_rttm(args.path, expected_file_id=args.file_id)
    print(json.dumps({"segments": len(segments)}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meeting-asr")
    subcommands = parser.add_subparsers(dest="command", required=True)

    preprocess_parser = subcommands.add_parser("preprocess", help="run the M1 audio stage")
    preprocess_parser.add_argument("audio")
    preprocess_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    preprocess_parser.add_argument("--no-cache", action="store_true")
    preprocess_parser.set_defaults(handler=_run_preprocess)

    simulate_parser = subcommands.add_parser(
        "simulate", help="mix clean clips into the nine acoustic conditions"
    )
    simulate_parser.add_argument("manifest")
    simulate_parser.add_argument("--out", required=True)
    simulate_parser.add_argument("--index", type=int, required=True)
    simulate_parser.add_argument("--seed", type=int)
    simulate_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    simulate_parser.set_defaults(handler=_run_simulate)

    rttm_parser = subcommands.add_parser("rttm-validate", help="validate one RTTM file")
    rttm_parser.add_argument("path")
    rttm_parser.add_argument("--file-id")
    rttm_parser.set_defaults(handler=_run_rttm_validate)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, TypeError, ValueError, RuntimeError, NotImplementedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
