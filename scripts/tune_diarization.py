"""Select diarization settings on speaker-disjoint dev; cache neural features.

Threshold sweeps use only dev reference RTTM. Test/pilot labels are not loaded
by this script. Pyannote's `training` flag enables its feature cache; no model
training, gradient computation, or weight updates take place.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path

import numpy as np

from meeting_asr.checkpoints import pyannote_checkpoint_context
from meeting_asr.diarization import DiarizationResult, release_gpu
from meeting_asr.ecapa import EcapaBackend, Window, diarization_from_features
from meeting_asr.evaluation.experiments import experiment_manifest
from meeting_asr.evaluation.metrics import score_diarization
from meeting_asr.evaluation.overlap import utterance_overlap_fractions
from meeting_asr.io import _atomic_text, read_rttm
from meeting_asr.models import DiarSignals, Segment
from meeting_asr.preprocess import preprocess
from meeting_asr.runtime import file_sha256, set_seed
from meeting_asr.settings import config_hash, load_config


def save(path, payload):
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def continuous_result(annotation, duration, minimum):
    segments = sorted(
        [
            Segment(max(0, s.start), min(duration, s.end), str(speaker))
            for s, _, speaker in annotation.itertracks(yield_label=True)
            if min(duration, s.end) - max(0, s.start) >= minimum
        ],
        key=lambda s: (s.start, s.end, s.speaker),
    )
    return DiarizationResult(
        segments, [DiarSignals(r) for r in utterance_overlap_fractions(segments)], "pyannote"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    config = load_config()
    config["asr"]["batch_size"] = 1
    config["llm"]["enabled"] = False
    manifest = experiment_manifest(args.manifest)
    if any(s["split"] != "dev" for s in manifest["sessions"]):
        raise ValueError("only dev sessions are allowed for parameter selection")
    set_seed(config["seed"])
    import torch
    from pyannote.audio import Model, Pipeline
    from silero_vad import load_silero_vad
    from speechbrain.inference.classifiers import EncoderClassifier

    device = "cuda" if torch.cuda.is_available() else "cpu"
    # The models remain in inference mode; the pipeline flag caches features.
    with pyannote_checkpoint_context():
        pya = Pipeline.from_pretrained(
            config["diarization"]["model_name"], use_auth_token=os.getenv("HF_TOKEN")
        )
    pya.to(torch.device(device))
    pya.training = True
    original_parameters = pya.parameters(instantiated=True)
    pya_default = float(original_parameters["clustering"]["threshold"])
    pya_thresholds = sorted({0.45, 0.55, 0.65, pya_default, 0.75, 0.85})
    ecapa_thresholds = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    save(
        out / "search_space.json",
        {
            "split": "dev",
            "objective": "mean strict DER",
            "pyannote_thresholds": pya_thresholds,
            "ecapa_thresholds": ecapa_thresholds,
            "ecapa_clean_clustering": [False, True],
            "manifest_sha256": file_sha256(args.manifest),
        },
    )
    # Reuse feature extractors across files. Model methods and outputs are unchanged.
    silero = load_silero_vad()
    encoder = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        run_opts={"device": device},
        savedir=".cache/models/ecapa",
    )
    with pyannote_checkpoint_context():
        overlap_model = Model.from_pretrained(
            "pyannote/segmentation-3.0", use_auth_token=os.getenv("HF_TOKEN")
        )
    actual_vad_factory = __import__("silero_vad").load_silero_vad
    actual_encoder_factory = EncoderClassifier.from_hparams
    actual_overlap_factory = Model.from_pretrained
    __import__("silero_vad").load_silero_vad = lambda *a, **k: silero
    EncoderClassifier.from_hparams = lambda *a, _model=encoder, **k: _model
    Model.from_pretrained = lambda *a, _model=overlap_model, **k: _model
    rows = []
    try:
        for index, session in enumerate(manifest["sessions"], 1):
            identity = config_hash(session)
            directory = out / "predictions" / identity
            truth = read_rttm(session["reference_rttm"])
            audio = preprocess(session["audio"], **config["preprocess"])
            file = {
                "waveform": torch.from_numpy(audio.waveform).unsqueeze(0),
                "sample_rate": audio.sr,
                "uri": Path(session["audio"]).stem,
            }
            print(
                f"DEV {index}/{len(manifest['sessions'])} {session['conversation_id']} "
                f"{session['condition']}",
                flush=True,
            )
            for threshold in pya_thresholds:
                path = directory / f"pyannote_{threshold:.8f}.json"
                if path.exists():
                    result = DiarizationResult.from_dict(json.loads(path.read_text()))
                else:
                    params = copy.deepcopy(original_parameters)
                    params["clustering"]["threshold"] = threshold
                    pya.instantiate(params)
                    annotation = pya(file, max_speakers=config["diarization"]["max_speakers"])
                    result = continuous_result(
                        annotation, audio.duration, config["diarization"]["min_segment_duration"]
                    )
                    save(path, result.to_dict())
                scores = score_diarization(truth, result.segments)
                rows.append(
                    {
                        **session,
                        "backend": "pyannote",
                        "threshold": threshold,
                        "clean_clustering": False,
                        "prediction": str(path),
                        "strict_der": scores["strict"].der,
                        "strict_confusion": scores["strict"].confusion,
                        "speakers": len({s.speaker for s in result.segments}),
                    }
                )
            feature_path = out / "features" / f"{identity}.npz"
            meta_path = feature_path.with_suffix(".json")
            if feature_path.exists() and meta_path.exists():
                meta = json.loads(meta_path.read_text())
                assert meta["audio_sha256"] == file_sha256(session["audio"])
                windows = [Window(**w) for w in meta["windows"]]
                vectors = np.load(feature_path, allow_pickle=False)["vectors"]
                regions = meta["regions"]
            else:
                ecapa = EcapaBackend(device=device, **config["diarization"]["ecapa"])
                windows, vectors, regions = ecapa.extract_features(audio)
                feature_path.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(feature_path, vectors=vectors)
                save(
                    meta_path,
                    {
                        "windows": [vars(w) for w in windows],
                        "regions": regions,
                        "audio_sha256": file_sha256(session["audio"]),
                    },
                )
            for clean in (False, True):
                for threshold in ecapa_thresholds:
                    path = directory / f"ecapa_{threshold:.2f}_clean{int(clean)}.json"
                    result = diarization_from_features(
                        windows,
                        vectors,
                        regions,
                        cluster_threshold=threshold,
                        clean_clustering=clean,
                    )
                    save(path, result.to_dict())
                    scores = score_diarization(truth, result.segments)
                    rows.append(
                        {
                            **session,
                            "backend": "ecapa",
                            "threshold": threshold,
                            "clean_clustering": clean,
                            "prediction": str(path),
                            "strict_der": scores["strict"].der,
                            "strict_confusion": scores["strict"].confusion,
                            "speakers": len({s.speaker for s in result.segments}),
                        }
                    )
            save(out / "dev_scores.json", rows)
            print("  saved feature sweep", flush=True)
    finally:
        __import__("silero_vad").load_silero_vad = actual_vad_factory
        EncoderClassifier.from_hparams = actual_encoder_factory
        Model.from_pretrained = actual_overlap_factory
        del encoder, overlap_model, pya
        release_gpu()
    aggregates = []
    for backend in ("pyannote", "ecapa"):
        combinations = sorted(
            {(r["threshold"], r["clean_clustering"]) for r in rows if r["backend"] == backend}
        )
        for threshold, clean in combinations:
            selected = [
                r
                for r in rows
                if r["backend"] == backend
                and r["threshold"] == threshold
                and r["clean_clustering"] == clean
            ]
            aggregates.append(
                {
                    "backend": backend,
                    "threshold": threshold,
                    "clean_clustering": clean,
                    "sessions": len(selected),
                    "strict_der": float(np.mean([r["strict_der"] for r in selected])),
                    "strict_confusion": float(np.mean([r["strict_confusion"] for r in selected])),
                }
            )
    save(out / "dev_aggregates.json", aggregates)
    winners = {
        backend: min(
            (r for r in aggregates if r["backend"] == backend),
            key=lambda r: (r["strict_der"], r["clean_clustering"], r["threshold"]),
        )
        for backend in ("pyannote", "ecapa")
    }
    save(
        out / "selected.json",
        {
            "split": "dev",
            "manifest": str(Path(args.manifest).resolve()),
            "objective": "mean strict DER",
            "parameters": winners,
        },
    )
    print("SELECTED", json.dumps(winners), flush=True)


if __name__ == "__main__":
    main()
