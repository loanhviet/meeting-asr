"""Run pinned author code in its own environment, without the baseline imports."""

import argparse
import gc
import importlib.metadata
import json
import random
import subprocess
import sys
import time
from pathlib import Path


def event(stage, progress):
    print("MEETING_DICOW_EVENT " + json.dumps({"stage": stage, "progress": progress}), flush=True)


def run(request):
    import numpy as np
    import torch
    from huggingface_hub import hf_hub_download, snapshot_download
    from pyannote.core import Annotation, Segment

    upstream = Path(request["upstream_dir"])
    sys.path.insert(0, str(upstream / "DiariZen"))
    sys.path.insert(0, str(upstream))
    from diarizen.pipelines.inference import DiariZenPipeline
    from inference import create_lower_uppercase_mapping
    from pipeline import DiCoWPipeline
    from transformers import AutoFeatureExtractor, AutoModelForSpeechSeq2Seq, AutoTokenizer

    random.seed(request["seed"])
    np.random.seed(request["seed"])
    torch.manual_seed(request["seed"])
    device = request["device"]
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in the author runtime")
    started = time.perf_counter()
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    event("M2", 0.2)
    diarization_peak = 0
    if request["oracle_rttm"]:
        annotation = Annotation()
        for index, line in enumerate(Path(request["oracle_rttm"]).read_text().splitlines()):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) != 10 or fields[0] != "SPEAKER":
                raise ValueError("Invalid oracle RTTM")
            start, length = float(fields[3]), float(fields[4])
            annotation[Segment(start, start + length), index] = fields[7]
        backend = "oracle"
    else:
        if request["diarization_backend"] != "diarizen":
            raise ValueError("Author profile requires diarizen, or pass an oracle RTTM")
        model_dir = snapshot_download(
            request["diarization_model"], revision=request["diarization_revision"]
        )
        embedding = hf_hub_download(
            "pyannote/wespeaker-voxceleb-resnet34-LM",
            "pytorch_model.bin",
            revision=request["embedding_revision"],
        )
        from pyannote.audio.core.task import Problem, Resolution, Specifications

        with torch.serialization.safe_globals(
            [torch.torch_version.TorchVersion, Specifications, Problem, Resolution]
        ):
            diarizer = DiariZenPipeline(Path(model_dir), embedding).to(torch.device(device))
        diarizer.embedding_batch_size = request["diarization_batch_size"]
        diarizer.segmentation_batch_size = request["diarization_batch_size"]
        if request["max_speakers"] is not None:
            diarizer.max_speakers = request["max_speakers"]
        annotation = diarizer(request["audio"])
        if device == "cuda":
            diarization_peak = torch.cuda.max_memory_allocated()
        del diarizer
        gc.collect()
        if device == "cuda":
            torch.cuda.empty_cache()
        backend = "diarizen"
    labels = annotation.labels()
    mapping = {label: f"SPEAKER_{index:02d}" for index, label in enumerate(labels)}
    annotation = annotation.rename_labels(mapping=mapping)
    speakers = annotation.labels()
    segments = [
        {"start": span.start, "end": span.end, "speaker": speaker}
        for span, _, speaker in annotation.itertracks(yield_label=True)
    ]
    diarization_elapsed = time.perf_counter() - started
    event("M3", 0.4)
    asr_started = time.perf_counter()
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    dtype = torch.float16 if device == "cuda" else torch.float32
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        request["model_name"],
        revision=request["model_revision"],
        trust_remote_code=True,
        torch_dtype=dtype,
    ).eval()
    if getattr(model.config, "mt_num_speakers", 1) != 1:
        raise ValueError("Sequential target decoding requires a single-target checkpoint")
    if getattr(model.config, "use_enrollments", False):
        raise ValueError("This adapter supports DiCoW FDDT checkpoints, not SE-DiCoW")
    tokenizer = AutoTokenizer.from_pretrained(
        request["model_name"], revision=request["model_revision"]
    )
    features = AutoFeatureExtractor.from_pretrained(
        request["model_name"], revision=request["model_revision"]
    )
    create_lower_uppercase_mapping(tokenizer)
    model.set_tokenizer(tokenizer)

    class FixedDiarizer:
        def __call__(self, unused_path):
            return annotation

    pipeline = DiCoWPipeline(
        model,
        diarization_pipeline=FixedDiarizer(),
        tokenizer=tokenizer,
        feature_extractor=features,
        device=torch.device(device),
    )
    timestamped = []
    raw_outputs = []
    if speakers:
        samples = next(pipeline.preprocess(request["audio"]))
        for index, speaker in enumerate(speakers):
            target = {
                key: value[index : index + 1].to(device=device, dtype=dtype)
                if torch.is_tensor(value) and key in {"input_features", "stno_mask"}
                else value[index : index + 1].to(device)
                if torch.is_tensor(value) and key == "attention_mask"
                else value
                for key, value in samples.items()
            }
            with torch.inference_mode():
                decoded = pipeline._forward(
                    target,
                    return_timestamps=True,
                    language=request["language"],
                    task="transcribe",
                    num_beams=request["num_beams"],
                    ctc_weight=request["ctc_weight"],
                )
            text = tokenizer.batch_decode(
                decoded["tokens"], decode_with_timestamps=True, skip_special_tokens=True
            )[0]
            raw_outputs.append(text)
            timestamped.append(pipeline.postprocess_text(text))
            del decoded
    revisions = {
        "author_commit": request["author_commit"],
        "diarizen_code_commit": subprocess.check_output(
            ["git", "-C", str(upstream / "DiariZen"), "rev-parse", "HEAD"], text=True
        ).strip(),
        "model_name": request["model_name"],
        "model_revision": request["model_revision"],
        "diarization_model": request["diarization_model"],
        "diarization_revision": request["diarization_revision"],
        "embedding_revision": request["embedding_revision"],
        "language": request["language"],
        "device": device,
        "dtype": str(dtype),
        "num_beams": request["num_beams"],
        "ctc_weight": request["ctc_weight"],
        "target_batch_size": 1,
        "diarization_elapsed_sec": diarization_elapsed,
        "asr_elapsed_sec": time.perf_counter() - asr_started,
        "diarization_peak_cuda_allocated_bytes": diarization_peak,
        "asr_peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated()
        if device == "cuda"
        else 0,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ["torch", "torchaudio", "transformers", "pyannote.audio"]
        },
    }
    Path(request["output"]).write_text(
        json.dumps(
            {
                "backend": backend,
                "speakers": speakers,
                "segments": segments,
                "timestamped_outputs": timestamped,
                "raw_outputs": raw_outputs,
                "provenance": revisions,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    run(json.loads(args.request.read_text()))
