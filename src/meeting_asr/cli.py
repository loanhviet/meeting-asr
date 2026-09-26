"""Independent command-line entry point for completed pipeline stages."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from meeting_asr.cache import load_audio_bundle, save_audio_bundle, stage_key
from meeting_asr.data_gen.dataset import build_dataset
from meeting_asr.data_gen.prepare import prepare_dataset
from meeting_asr.data_gen.simulate import load_clips, read_mono_wav, simulate_matrix, write_session
from meeting_asr.evaluation.confidence import calibrate_margin, run_confidence_evaluation
from meeting_asr.evaluation.experiments import run_experiments
from meeting_asr.io import read_rttm
from meeting_asr.pipeline import run_pipeline
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
    noise = None if args.noise is None else read_mono_wav(args.noise)[0]
    sessions = simulate_matrix(
        load_clips(args.manifest),
        seed=seed,
        index=args.index,
        noise=noise,
        noise_source="white" if args.noise is None else str(Path(args.noise).resolve()),
    )
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


def _run_prepare(args: argparse.Namespace) -> int:
    excluded = set()
    if args.exclude_hashes:
        excluded = set(Path(args.exclude_hashes).read_text().split())
    result = prepare_dataset(
        args.manifest,
        args.out,
        dev_speakers=args.dev_speakers,
        seed=args.seed,
        excluded_hashes=excluded,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _run_pipeline(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.backend:
        config["diarization"]["backend"] = args.backend
    if args.device:
        config.setdefault("runtime", {})["device"] = args.device
    if args.batch_size is not None:
        config["asr"]["batch_size"] = args.batch_size
    minutes = run_pipeline(
        args.audio, config, args.out, no_cache=args.no_cache, oracle_rttm=args.oracle_rttm
    )
    print(
        json.dumps(
            {
                "audio_id": minutes.audio_id,
                "turns": len(minutes.turns),
                "speakers": minutes.num_speakers,
                "out": str(Path(args.out).resolve()),
            }
        )
    )
    return 0


def _run_dataset(args):
    payload = build_dataset(
        args.manifest,
        args.out,
        conversations=args.conversations,
        clips_per_speaker=args.clips_per_speaker,
        seed=args.seed,
        noise=args.noise,
        session_limit=args.session_limit,
    )
    print(json.dumps({"sessions": len(payload["sessions"]), "out": args.out}))
    return 0


def _run_experiments(args):
    backends = ("pyannote", "ecapa") if args.backend == "all" else (args.backend,)
    rows = run_experiments(args.manifest, load_config(args.config), args.out, backends)
    print(json.dumps({"rows": len(rows), "out": args.out}))
    return 0


def _run_rq3(args):
    results = run_confidence_evaluation(args.manifest, load_config(args.config), args.out)
    print(json.dumps({"sessions": len(results), "out": args.out}))
    return 0


def _run_calibrate(args):
    print(
        json.dumps(
            calibrate_margin(
                args.manifest, args.out, args.percentile, args.fit_weights, args.trials, args.seed
            ),
            indent=2,
        )
    )
    return 0


def _run_doctor(args):
    from meeting_asr.doctor import environment_report
    from meeting_asr.settings import load_environment

    load_environment()
    print(json.dumps(environment_report(), ensure_ascii=False, indent=2))
    return 0


def _run_serve(args):
    try:
        import uvicorn

        from meeting_asr.api import create_app
    except ImportError as exc:
        raise RuntimeError("Install API dependencies: uv sync --extra api") from exc
    uvicorn.run(create_app(load_config(args.config)), host=args.host, port=args.port)
    return 0


def _run_benchmark(args):
    from meeting_asr.benchmark import benchmark

    result = benchmark(
        args.audio, load_config(args.config), args.out, args.repetitions, args.cached
    )
    print(json.dumps(result, indent=2))
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
    simulate_parser.add_argument("--noise", help="mono PCM16 16kHz noise WAV, e.g. MUSAN")
    simulate_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    simulate_parser.set_defaults(handler=_run_simulate)

    rttm_parser = subcommands.add_parser("rttm-validate", help="validate one RTTM file")
    rttm_parser.add_argument("path")
    rttm_parser.add_argument("--file-id")
    rttm_parser.set_defaults(handler=_run_rttm_validate)

    prepare_parser = subcommands.add_parser("prepare-data", help="audit and split local clips")
    prepare_parser.add_argument("manifest")
    prepare_parser.add_argument("--out", required=True)
    prepare_parser.add_argument("--dev-speakers", type=int, default=3)
    prepare_parser.add_argument("--seed", type=int, default=42)
    prepare_parser.add_argument("--exclude-hashes")
    prepare_parser.set_defaults(handler=_run_prepare)

    run_parser = subcommands.add_parser("run", help="run restartable meeting pipeline")
    run_parser.add_argument("audio")
    run_parser.add_argument("--out", required=True)
    run_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    run_parser.add_argument("--backend", choices=["pyannote", "ecapa"])
    run_parser.add_argument("--device", choices=["auto", "cpu", "cuda"])
    run_parser.add_argument("--batch-size", type=int)
    run_parser.add_argument("--oracle-rttm")
    run_parser.add_argument("--no-cache", action="store_true")
    run_parser.set_defaults(handler=_run_pipeline)

    dataset_parser = subcommands.add_parser("build-dataset", help="build pilot or main conditions")
    dataset_parser.add_argument("manifest")
    dataset_parser.add_argument("--out", required=True)
    dataset_parser.add_argument("--conversations", type=int, default=2)
    dataset_parser.add_argument("--clips-per-speaker", type=int, default=6)
    dataset_parser.add_argument("--seed", type=int, default=42)
    dataset_parser.add_argument("--noise")
    dataset_parser.add_argument(
        "--session-limit", type=int, help="e.g. 30 independent dev sessions"
    )
    dataset_parser.set_defaults(handler=_run_dataset)

    experiments_parser = subcommands.add_parser("experiments", help="run RQ1/RQ2 with paired data")
    experiments_parser.add_argument("manifest")
    experiments_parser.add_argument("--out", required=True)
    experiments_parser.add_argument(
        "--backend", choices=["all", "pyannote", "ecapa"], default="all"
    )
    experiments_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    experiments_parser.set_defaults(handler=_run_experiments)

    rq3_parser = subcommands.add_parser("evaluate-confidence", help="RQ3 ablation and risk curves")
    rq3_parser.add_argument("manifest")
    rq3_parser.add_argument("--out", required=True)
    rq3_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    rq3_parser.set_defaults(handler=_run_rq3)

    calibration_parser = subcommands.add_parser(
        "calibrate-confidence", help="fit margin scale on dev"
    )
    calibration_parser.add_argument("manifest")
    calibration_parser.add_argument("--out", required=True)
    calibration_parser.add_argument("--percentile", type=float, default=90)
    calibration_parser.add_argument("--fit-weights", action="store_true")
    calibration_parser.add_argument("--trials", type=int, default=64)
    calibration_parser.add_argument("--seed", type=int, default=42)
    calibration_parser.set_defaults(handler=_run_calibrate)

    doctor_parser = subcommands.add_parser(
        "doctor", help="inspect environment without exposing keys"
    )
    doctor_parser.set_defaults(handler=_run_doctor)

    demo_parser = subcommands.add_parser(
        "demo-audio", help="generate synthetic Vietnamese demo audio"
    )
    demo_parser.add_argument("--out", default="data/demo")
    demo_parser.add_argument("--cache", default=".cache/demo-tts")

    def run_demo(args):
        import asyncio

        from meeting_asr.data_gen.demo import generate_demo

        payload = asyncio.run(generate_demo(_project_path(args.out), _project_path(args.cache)))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    demo_parser.set_defaults(handler=run_demo)

    serve_parser = subcommands.add_parser("serve", help="start the local API and single worker")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    serve_parser.set_defaults(handler=_run_serve)

    benchmark_parser = subcommands.add_parser("benchmark", help="measure uncached RTF and VRAM")
    benchmark_parser.add_argument("audio")
    benchmark_parser.add_argument("--out", required=True)
    benchmark_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    benchmark_parser.add_argument("--repetitions", type=int, default=1)
    benchmark_parser.add_argument("--cached", action="store_true")
    benchmark_parser.set_defaults(handler=_run_benchmark)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, TypeError, ValueError, RuntimeError, KeyError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
