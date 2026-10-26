"""Frozen diagnostic evaluation of general meetings and complementary speech corpora.

References stay in the scoring process. The normal CLI runs the unmodified
production pipeline. A separate worker evaluates M2 over all ViYT-Diar files,
with the same pinned author code, preprocessing, model and batch settings.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SEED = 20261026
DER_POLICIES = [
    ("strict", 0.0, False),
    ("relaxed", 0.25, True),
    ("no_collar_skip_overlap", 0.0, True),
    ("collar_keep_overlap", 0.25, False),
]


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def ordering(row):
    return hashlib.sha256(f"{SEED}:{row['id']}".encode()).hexdigest()


def prepare(root, out, *, manifest=None, num_beams=None):
    from meeting_asr.settings import config_hash, load_config

    os.environ["MEETING_LLM_ENABLED"] = "false"
    os.environ["MEETING_DEVICE"] = "cuda"
    config = load_config()
    config["llm"]["enabled"] = False
    config["runtime"]["device"] = "cuda"
    config["paths"]["cache_dir"] = str(out / "cache")
    config["paths"]["results_dir"] = str(out)
    if num_beams is not None:
        if isinstance(num_beams, bool) or not isinstance(num_beams, int) or num_beams < 1:
            raise ValueError("num_beams must be a positive integer")
        config["dicow"]["num_beams"] = num_beams
    if manifest is not None:
        manifest = Path(manifest).resolve()
        root = manifest.parent
    selected = []

    def add(row, mode="pipeline"):
        row = copy.deepcopy(row)
        if (
            Path(row["dataset"]).name != row["dataset"]
            or row["dataset"] in {".", ".."}
            or Path(row["id"]).name != row["id"]
            or Path(row["id"]).stem in {"", ".", ".."}
        ):
            raise ValueError("dataset and sample IDs must be safe path components")
        if row["duration_sec"] < 5:
            raise ValueError("evaluation inputs must meet the five-second audio contract")
        for key in ("audio_path", "reference_rttm", "reference_uem", "reference_json"):
            if row.get(key):
                row[key] = str((root / row[key]).resolve())
        row["mode"] = mode
        row["evaluation_split"] = (
            "development; configuration selection permitted"
            if manifest and row.get("split") == "dev"
            else "frozen_diagnostic; do not tune on these results"
        )
        row["audio_sha256"] = digest(row["audio_path"])
        selected.append(row)

    if manifest is not None:
        for row in read_rows(manifest):
            add(row, row.get("mode", "pipeline"))
    else:
        _add_legacy_sources(root, add)
    identities = [(r["mode"], r["dataset"], Path(r["id"]).stem) for r in selected]
    if len(set(identities)) != len(identities):
        raise ValueError("sample output identities must be unique")
    for row in selected:
        if row.get("reference_json"):
            row["reference_json_sha256"] = digest(row["reference_json"])
        if row.get("reference_rttm"):
            row["reference_rttm_sha256"] = digest(row["reference_rttm"])
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "Vietnamese general meetings; IT is one optional domain",
        "selection_seed": SEED,
        "selection_policy": (
            "explicit frozen manifest"
            if manifest
            else "hash order before prediction; one ViMD clip/province, "
            "one VietMed pilot test clip/speaker, 40 distinct FLEURS test prompts, "
            "all ViYT M2 and first 10 ViYT production pipeline; minimum input 5s"
        ),
        "manifest_sha256": digest(manifest) if manifest else None,
        "llm_enabled": False,
        "config": config,
        "config_hash": config_hash(config),
        "code_sha256": {
            str(p.relative_to(PROJECT)): digest(p)
            for p in [
                Path(__file__),
                PROJECT / "src/meeting_asr/dicow_runner.py",
                PROJECT / "src/meeting_asr/pipeline.py",
                PROJECT / "src/meeting_asr/preprocess.py",
            ]
        },
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        "rows": selected,
    }
    target = out / "selection.json"
    if target.exists():
        raise ValueError("selection already frozen; choose a new output directory")
    write_json(target, payload)
    import yaml

    (out / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True))
    print(json.dumps({"selected": len(selected), "out": str(out)}), flush=True)


def _add_legacy_sources(root, add):
    viyt = read_rows(root / "manifests/viyt_diar/test.jsonl")
    for row in sorted(viyt, key=ordering):
        add(row, "diarization")
    for row in sorted(viyt, key=ordering)[:10]:
        add(row)
    fleurs = read_rows(root / "manifests/fleurs_vi/test.jsonl")
    seen = set()
    for row in sorted(fleurs, key=ordering):
        if row["duration_sec"] >= 5 and row["prompt_id"] not in seen:
            add(row)
            seen.add(row["prompt_id"])
            if len(seen) == 40:
                break
    for manifest, field in [
        ("exports/vimd_diagnostic/manifest.jsonl", "province_code"),
        ("pilot/references/test.jsonl", "speaker_id"),
    ]:
        seen = set()
        for row in sorted(read_rows(root / manifest), key=ordering):
            if row["duration_sec"] >= 5 and row[field] not in seen:
                add(row)
                seen.add(row[field])
    extras = PROJECT / "data/gold/general_meetings_v1/extra_samples.json"
    if extras.is_file():
        for row in json.loads(extras.read_text()):
            add(row)


def folder_for(out, row):
    return out / row["mode"] / row["dataset"] / Path(row["id"]).stem


def annotation(segments, duration, *, check_bounds=True):
    from pyannote.core import Annotation, Segment

    result = Annotation(uri="audio")
    for i, segment in enumerate(segments):
        if check_bounds and segment.end > duration + 0.001:
            raise ValueError("RTTM exceeds audio duration")
        result[Segment(segment.start, segment.end), i] = segment.speaker
    return result


def score(row, folder, status="ok", error=None, elapsed=None):
    from pyannote.core import Segment, Timeline
    from pyannote.metrics.diarization import DiarizationErrorRate

    from meeting_asr.evaluation.experiments import transcript_scores
    from meeting_asr.io import read_rttm, read_transcript_json

    sys.path.insert(0, str(PROJECT / "scripts"))
    from run_asr_dev_baseline import error_counts

    hypothesis, predicted = "", []
    document = None
    if status == "ok":
        predicted = read_rttm(folder / "diarization.rttm")
        if row["mode"] == "pipeline":
            document = read_transcript_json(folder / "transcript.json")
            run = json.loads((folder / "run.json").read_text())
            if run["audio_sha256"] != row["audio_sha256"]:
                raise ValueError("prediction/source audio checksum mismatch")
            if (row.get("reference_rttm") or row.get("reference_json")) and abs(
                document.duration - row["duration_sec"]
            ) > 0.001:
                raise ValueError("transcript/audio duration mismatch")
            hypothesis = " ".join(
                u.text
                for u in sorted(document.utterances, key=lambda u: (u.start, u.end, u.speaker))
            )
    result = {
        key: row.get(key)
        for key in (
            "id",
            "dataset",
            "mode",
            "duration_sec",
            "audio_sha256",
            "recording_id",
            "speaker_id",
            "province_code",
            "province_name",
            "region",
            "accent",
            "gender",
            "reference_status",
            "project_review_status",
        )
    }
    result.update(status=status, error=error, elapsed_sec=elapsed, hypothesis=hypothesis)
    if document is not None:
        # Container duration (especially MP3 encoder padding) can differ from
        # decoded audio. The source SHA identifies full-text samples; timestamped
        # references still require sample-compatible durations above.
        result["source_nominal_duration_sec"] = row["duration_sec"]
        result["duration_sec"] = document.duration
    result["predicted_speakers"] = len({s.speaker for s in predicted})
    result.update(wer=None, cer=None, cpwer=None, der=None)
    reference = row.get("reference_text")
    if row.get("reference_json"):
        if digest(row["reference_json"]) != row["reference_json_sha256"]:
            raise ValueError("reference transcript changed after selection")
        gold = read_transcript_json(row["reference_json"])
        reference = " ".join(
            u.text for u in sorted(gold.utterances, key=lambda u: (u.start, u.end, u.speaker))
        )
        if document:
            result["cpwer"] = transcript_scores(gold, document)["cpwer"]
        elif status != "ok":
            result["cpwer"] = 1.0
    if reference is not None and row["mode"] == "pipeline":
        result["reference"] = reference
        result["wer"] = error_counts(reference, hypothesis)
        result["cer"] = error_counts(reference, hypothesis, characters=True)
    if row.get("paper_metrics") and row.get("reference_json"):
        from meeting_asr.evaluation.paper import score_segments, transcript_segments

        result["paper_metrics"] = score_segments(
            transcript_segments(gold), transcript_segments(document) if document else [], collar=5.0
        )
    if row.get("reference_rttm"):
        if digest(row["reference_rttm"]) != row["reference_rttm_sha256"]:
            raise ValueError("reference RTTM changed after selection")
        truth = annotation(read_rttm(row["reference_rttm"]), row["duration_sec"])
        # Model frame padding may extend past EOF. Official UEM, rather than
        # modifying model RTTM or rejecting the file, defines the scoring region.
        prediction = annotation(predicted, row["duration_sec"], check_bounds=False)
        result["predicted_segments_past_audio"] = sum(
            s.end > row["duration_sec"] for s in predicted
        )
        intervals = [(0, row["duration_sec"])]
        if row.get("reference_uem"):
            intervals = [
                (float(parts[2]), float(parts[3]))
                for line in Path(row["reference_uem"]).read_text().splitlines()
                if (parts := line.split()) and not line.startswith("#")
            ]
        uem = Timeline([Segment(a, b) for a, b in intervals], uri="audio")
        result["reference_speakers"] = len(truth.labels())
        result["der"] = {}
        for name, collar, skip_overlap in DER_POLICIES:
            detail = DiarizationErrorRate(collar=collar, skip_overlap=skip_overlap)(
                truth, prediction, uem=uem, detailed=True
            )
            total = float(detail["total"])
            result["der"][name] = {
                "rate": float(detail["diarization error rate"]) if total else None,
                "total_sec": total,
                "miss_sec": float(detail["missed detection"]),
                "false_alarm_sec": float(detail["false alarm"]),
                "confusion_sec": float(detail["confusion"]),
                "collar_sec": collar,
                "skip_overlap": skip_overlap,
                "uem": intervals,
            }
    write_json(folder / "score.json", result)
    return result


def run_pipeline_rows(out, datasets):
    from meeting_asr.settings import config_hash

    selection = json.loads((out / "selection.json").read_text())
    if config_hash(selection["config"]) != selection["config_hash"]:
        raise ValueError("frozen configuration hash changed")
    rows = [r for r in selection["rows"] if r["mode"] == "pipeline"]
    if datasets:
        rows = [r for r in rows if r["dataset"] in datasets]
    for index, row in enumerate(rows, 1):
        folder = folder_for(out, row)
        folder.mkdir(parents=True, exist_ok=True)
        if digest(row["audio_path"]) != row["audio_sha256"]:
            raise ValueError("audio changed after selection")
        config = copy.deepcopy(selection["config"])
        config["asr"]["language"] = row.get("language", "vi")
        import yaml

        config_path = folder / "config.yaml"
        config_path.write_text(yaml.safe_dump(config, allow_unicode=True))
        run_path = folder / "run.json"
        if run_path.exists():
            previous_run = json.loads(run_path.read_text())
            if (
                previous_run["config_hash"] == config_hash(config)
                and previous_run["audio_sha256"] == row["audio_sha256"]
                and previous_run["result"]["oracle_rttm"] is None
            ):
                score(row, folder, elapsed=previous_run["result"]["elapsed_sec"])
                print(json.dumps({"rescored_completed_inference": row["id"]}), flush=True)
                continue
        env = os.environ.copy()
        env.update(
            MEETING_LLM_ENABLED="false",
            MEETING_DEVICE="cuda",
            OMP_NUM_THREADS="2",
            MKL_NUM_THREADS="2",
        )
        started = time.perf_counter()
        status, error = "ok", None
        with (folder / "pipeline.log").open("w") as handle:
            process = subprocess.Popen(
                [
                    str(PROJECT / ".venv/bin/meeting-asr"),
                    "run",
                    row["audio_path"],
                    "--config",
                    str(config_path),
                    "--out",
                    str(folder),
                    "--no-cache",
                ],
                cwd=PROJECT,
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                code = process.wait(timeout=1200 if row["duration_sec"] > 1800 else 600)
                if code:
                    status, error = "failed", f"pipeline exited {code}; see pipeline.log"
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                status, error = "failed", "pipeline timeout"
        elapsed = time.perf_counter() - started
        result = score(row, folder, status, error, elapsed)
        print(
            json.dumps(
                {
                    "completed": index,
                    "of": len(rows),
                    "dataset": row["dataset"],
                    "id": row["id"],
                    "status": status,
                    "wer": result["wer"]["rate"] if result["wer"] else None,
                    "elapsed_sec": round(elapsed, 2),
                }
            ),
            flush=True,
        )
        if index >= 3:
            previous = [folder_for(out, r) / "score.json" for r in rows[index - 3 : index]]
            if all(json.loads(p.read_text())["status"] != "ok" for p in previous):
                raise RuntimeError("three consecutive pipeline failures; inspect logs")


def prepare_diarization(out):
    from scipy.io.wavfile import write

    from meeting_asr.preprocess import preprocess

    selection = json.loads((out / "selection.json").read_text())
    inputs = []
    for row in selection["rows"]:
        if row["mode"] != "diarization":
            continue
        if digest(row["audio_path"]) != row["audio_sha256"]:
            raise ValueError("audio changed after selection")
        folder = folder_for(out, row)
        folder.mkdir(parents=True, exist_ok=True)
        prepared = folder / "prepared.wav"
        if not prepared.exists():
            audio = preprocess(row["audio_path"], **selection["config"]["preprocess"])
            write(prepared, audio.sr, audio.waveform)
        inputs.append({"id": row["id"], "audio": str(prepared), "out": str(folder)})
    # This request contains no references, true speaker counts, or transcripts.
    write_json(
        out / "diarization_inputs.json",
        {
            "config": {k: selection["config"][k] for k in ("seed", "dicow", "diarization")},
            "inputs": inputs,
        },
    )


def diarization_worker(request):
    import importlib.metadata
    import random

    import numpy as np
    import torch
    from huggingface_hub import hf_hub_download, snapshot_download

    config = request["config"]
    upstream = PROJECT / config["dicow"]["upstream_dir"]
    sys.path.insert(0, str(upstream / "DiariZen"))
    from diarizen.pipelines.inference import DiariZenPipeline
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    model_dir = snapshot_download(
        config["diarization"]["model_name"], revision=config["dicow"]["diarization_revision"]
    )
    embedding = hf_hub_download(
        "pyannote/wespeaker-voxceleb-resnet34-LM",
        "pytorch_model.bin",
        revision=config["dicow"]["embedding_revision"],
    )
    with torch.serialization.safe_globals(
        [torch.torch_version.TorchVersion, Specifications, Problem, Resolution]
    ):
        model = DiariZenPipeline(Path(model_dir), embedding).to(torch.device("cuda"))
    model.embedding_batch_size = config["dicow"]["diarization_batch_size"]
    model.segmentation_batch_size = config["dicow"]["diarization_batch_size"]
    model.max_speakers = config["diarization"]["max_speakers"]
    provenance = {
        "device": "cuda",
        "gpu": torch.cuda.get_device_name(0),
        "packages": {
            k: importlib.metadata.version(k) for k in ("torch", "torchaudio", "pyannote.audio")
        },
        "mode": "M2 only; model resident across files",
        "config": config,
    }
    for index, row in enumerate(request["inputs"], 1):
        folder = Path(row["out"])
        marker = folder / "worker_result.json"
        if marker.exists() and json.loads(marker.read_text())["status"] == "ok":
            continue
        random.seed(config["seed"])
        np.random.seed(config["seed"])
        torch.manual_seed(config["seed"])
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        status, error = "ok", None
        try:
            prediction = model(row["audio"])
            labels = prediction.labels()
            prediction = prediction.rename_labels(
                mapping={label: f"SPEAKER_{i:02d}" for i, label in enumerate(labels)}
            )
            prediction.uri = row["id"]
            with (folder / "diarization.rttm").open("w") as handle:
                prediction.write_rttm(handle)
        except (RuntimeError, ValueError, OSError, TypeError) as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        result = {
            "status": status,
            "error": error,
            "elapsed_sec": time.perf_counter() - started,
            "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(),
            "provenance": provenance,
        }
        write_json(marker, result)
        print(
            json.dumps(
                {
                    "M2": index,
                    "of": len(request["inputs"]),
                    "id": row["id"],
                    "status": status,
                    "elapsed_sec": round(result["elapsed_sec"], 2),
                }
            ),
            flush=True,
        )


def collect(out):
    selection = json.loads((out / "selection.json").read_text())
    for row in selection["rows"]:
        if row["mode"] == "diarization":
            folder = folder_for(out, row)
            marker = folder / "worker_result.json"
            if marker.exists():
                result = json.loads(marker.read_text())
                score(row, folder, result["status"], result["error"], result["elapsed_sec"])
        else:
            folder = folder_for(out, row)
            saved = folder / "score.json"
            if saved.exists():
                previous = json.loads(saved.read_text())
                elapsed = previous["elapsed_sec"]
                if previous["status"] == "ok":
                    elapsed = json.loads((folder / "run.json").read_text())["result"]["elapsed_sec"]
                score(row, folder, previous["status"], previous["error"], elapsed)
    rows = []
    for row in selection["rows"]:
        path = folder_for(out, row) / "score.json"
        if path.exists():
            rows.append(json.loads(path.read_text()))
    groups = defaultdict(list)
    for row in rows:
        groups[(row["mode"], row["dataset"])].append(row)
    summary = []
    for (mode, dataset), items in sorted(groups.items()):
        group = {
            "mode": mode,
            "dataset": dataset,
            "clips": len(items),
            "failed": sum(r["status"] != "ok" for r in items),
            "audio_sec": sum(r["duration_sec"] for r in items),
            "elapsed_sec": sum(r["elapsed_sec"] for r in items),
        }
        for metric in ("wer", "cer"):
            valid = [r[metric] for r in items if r[metric] is not None]
            group[metric] = None
            if valid:
                errors = sum(v["errors"] for v in valid)
                units = sum(v["reference_units"] for v in valid)
                group[metric] = {
                    "rate": errors / units if units else None,
                    "errors": errors,
                    "reference_units": units,
                }
        group["der"] = None
        if any(r["der"] for r in items):
            group["der"] = {}
            for policy, _, _ in DER_POLICIES:
                valid = [r["der"][policy] for r in items if r["der"]]
                total = sum(v["total_sec"] for v in valid)
                components = {
                    k: sum(v[k] for v in valid)
                    for k in ("miss_sec", "false_alarm_sec", "confusion_sec")
                }
                group["der"][policy] = {
                    **components,
                    "total_sec": total,
                    "rate": sum(components.values()) / total if total else None,
                }
        summary.append(group)
    write_json(
        out / "summary.json",
        {
            "complete": len(rows) == len(selection["rows"]),
            "planned": len(selection["rows"]),
            "completed": len(rows),
            "groups": summary,
            "notes": [
                "No single pooled quality score across languages/domains/tasks.",
                "Source-provided labels; not independently listened to by this project.",
                "Failed files remain in metric denominators with empty predictions.",
                "M2 timings exclude model load and are not production pipeline throughput.",
                "No LLM or oracle RTTM used in these inference runs.",
            ],
        },
    )
    with (out / "scores.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {"planned": len(selection["rows"]), "completed": len(rows), "groups": summary},
            ensure_ascii=False,
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "prepare",
            "run",
            "prepare-diarization",
            "run-diarization",
            "collect",
            "diarization-worker",
        ],
    )
    parser.add_argument("--root", type=Path, default=PROJECT / "data/gold/vi_asr_v1")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--datasets", nargs="*")
    parser.add_argument(
        "--manifest", type=Path, help="explicit JSONL inputs; paths relative to manifest"
    )
    parser.add_argument("--num-beams", type=int, help="freeze a DiCoW decoding beam count")
    args = parser.parse_args()
    out = args.out.resolve()
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    if args.command == "prepare":
        prepare(args.root.resolve(), out, manifest=args.manifest, num_beams=args.num_beams)
    elif args.command == "run":
        run_pipeline_rows(out, args.datasets)
    elif args.command == "prepare-diarization":
        prepare_diarization(out)
    elif args.command == "diarization-worker":
        diarization_worker(json.loads((out / "diarization_inputs.json").read_text()))
    elif args.command == "run-diarization":
        from meeting_asr.settings import load_environment

        load_environment()
        selection = json.loads((out / "selection.json").read_text())
        config = selection["config"]
        write_json(
            out / "worker_execution.json",
            {
                "script_sha256": digest(__file__),
                "started_at": datetime.now(UTC).isoformat(),
                "note": "Worker launched by app environment; credentials inherited in memory only.",
            },
        )
        subprocess.run(
            [
                str(PROJECT / config["dicow"]["python"]),
                str(Path(__file__).resolve()),
                "diarization-worker",
                "--out",
                str(out),
            ],
            cwd=PROJECT,
            check=True,
        )
    else:
        collect(out)


if __name__ == "__main__":
    main()
