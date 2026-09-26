"""Silero VAD + ECAPA/AHC with predicted overlap and nearby speaker evidence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from meeting_asr.diarization import DiarizationResult, release_gpu, resolve_device
from meeting_asr.evaluation.overlap import utterance_overlap_fractions
from meeting_asr.models import DiarSignals, Segment


@dataclass
class Window:
    start: float
    end: float
    region: int


def cluster_embeddings(embeddings, threshold=0.7, min_speakers=None, max_speakers=6):
    from scipy.cluster.hierarchy import cut_tree, fcluster, linkage

    matrix = np.asarray(embeddings, dtype=np.float64)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("embeddings must be a finite matrix")
    matrix = matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
    if len(matrix) == 1:
        labels = np.zeros(1, dtype=int)
    else:
        tree = linkage(matrix, method="average", metric="cosine")
        labels = fcluster(tree, threshold, criterion="distance") - 1
        count = len(set(labels))
        wanted = max(min_speakers or 1, min(count, max_speakers or count))
        wanted = min(len(matrix), wanted)
        if wanted != count:
            labels = cut_tree(tree, n_clusters=wanted).ravel()
    unique = sorted(set(labels))
    labels = np.array([unique.index(label) for label in labels])
    centroids = np.stack([matrix[labels == label].mean(axis=0) for label in range(len(unique))])
    centroids /= np.maximum(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-12)
    distances = 1 - matrix @ centroids.T
    margins = []
    for row, label in zip(distances, labels, strict=True):
        other = np.delete(row, label)
        margins.append(max(0.0, float(other.min() - row[label])) if len(other) else None)
    return labels, margins


def assign_overlaps(segments, windows, labels, margins, regions):
    """Add the closest different speaker supported outside each overlap region.

    Only predictions are used. Regions without single-speaker evidence cannot be
    assigned reliably and are deliberately left without a fabricated speaker.
    """
    result = list(segments)
    extras = []
    for start, end in regions:
        boundaries = sorted(
            {start, end, *[max(start, min(end, t)) for s in segments for t in (s.start, s.end)]}
        )
        anchors = [
            (w, int(label), margin)
            for w, label, margin in zip(windows, labels, margins, strict=True)
            if all(w.end <= a or w.start >= b for a, b in regions)
        ]
        for a, b in pairwise(boundaries):
            if b <= a:
                continue
            active = {s.speaker for s in segments if s.start < b and s.end > a}
            if len(active) != 1:
                continue
            candidates = [
                (w, label, margin)
                for w, label, margin in anchors
                if f"SPEAKER_{label:02d}" not in active
            ]
            if not candidates:
                continue
            _window, label, margin = min(
                candidates,
                key=lambda item: (abs((item[0].start + item[0].end) / 2 - (a + b) / 2), item[1]),
            )
            segment = Segment(a, b, f"SPEAKER_{label:02d}")
            result.append(segment)
            extras.append((segment, margin))
    return result, extras


class EcapaBackend:
    def __init__(
        self,
        device="auto",
        vad_threshold=0.5,
        window_size=1.5,
        hop_size=0.75,
        cluster_threshold=0.7,
        overlap_detector="pyannote/segmentation-3.0",
    ):
        if not 0 < hop_size <= window_size or not 0 < vad_threshold < 1:
            raise ValueError("invalid ECAPA window or VAD options")
        self.device, self.vad_threshold = device, vad_threshold
        self.window_size, self.hop_size = window_size, hop_size
        self.cluster_threshold, self.overlap_detector = cluster_threshold, overlap_detector

    def diarize(
        self, audio, *, min_speakers=None, max_speakers=6, min_segment_duration=0.3, **unused
    ):
        try:
            import torch
            from pyannote.audio import Model
            from pyannote.audio.pipelines import OverlappedSpeechDetection
            from silero_vad import get_speech_timestamps, load_silero_vad
            from speechbrain.inference.classifiers import EncoderClassifier
        except ImportError as exc:
            raise RuntimeError("Install inference dependencies: uv sync --extra inference") from exc
        device = resolve_device(self.device)
        waveform = torch.from_numpy(audio.waveform)
        vad = load_silero_vad()
        speech = get_speech_timestamps(
            waveform, vad, sampling_rate=audio.sr, threshold=self.vad_threshold, return_seconds=True
        )
        del vad
        windows = []
        for region, span in enumerate(speech):
            if span["end"] - span["start"] < min_segment_duration:
                continue
            start = span["start"]
            while True:
                end = min(span["end"], start + self.window_size)
                windows.append(Window(start, end, region))
                if end >= span["end"]:
                    break
                start += self.hop_size
        if not windows:
            return DiarizationResult([], [], "ecapa+overlap")
        encoder = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb", run_opts={"device": device}
        )
        vectors = []
        try:
            for window in windows:
                clip = waveform[int(window.start * audio.sr) : int(window.end * audio.sr)]
                with torch.inference_mode():
                    vector = encoder.encode_batch(clip.unsqueeze(0).to(device))
                vectors.append(vector.detach().cpu().numpy().reshape(-1))
        finally:
            del encoder
            release_gpu()
        labels, margins = cluster_embeddings(
            vectors, self.cluster_threshold, min_speakers, max_speakers
        )
        pieces = []
        for index, window in enumerate(windows):
            start, end = window.start, window.end
            if index and windows[index - 1].region == window.region:
                start = (windows[index - 1].start + windows[index - 1].end + start + end) / 4
            if index + 1 < len(windows) and windows[index + 1].region == window.region:
                other = windows[index + 1]
                end = (window.start + window.end + other.start + other.end) / 4
            segment = Segment(start, end, f"SPEAKER_{labels[index]:02d}")
            if (
                pieces
                and pieces[-1][0].speaker == segment.speaker
                and (abs(pieces[-1][0].end - segment.start) < 1e-6)
            ):
                previous, values = pieces[-1]
                previous.end = segment.end
                values.append(margins[index])
            else:
                pieces.append((segment, [margins[index]]))
        model = Model.from_pretrained(self.overlap_detector, use_auth_token=os.getenv("HF_TOKEN"))
        if model is None:
            raise RuntimeError("Accept segmentation model conditions and configure HF_TOKEN")
        detector = OverlappedSpeechDetection(segmentation=model)
        detector.instantiate({"min_duration_on": 0.0, "min_duration_off": 0.0})
        detector.to(torch.device(device))
        try:
            overlap = detector({"waveform": waveform.unsqueeze(0), "sample_rate": audio.sr})
            regions = [
                (max(0, s.start), min(audio.duration, s.end))
                for s in overlap.get_timeline().support()
            ]
        finally:
            del detector, model
            release_gpu()
        base = [segment for segment, _ in pieces]
        _, extras = assign_overlaps(base, windows, labels, margins, regions)
        pieces.extend((s, [m]) for s, m in extras)
        pieces = sorted(
            [(s, values) for s, values in pieces if s.duration >= min_segment_duration],
            key=lambda item: (item[0].start, item[0].end, item[0].speaker),
        )
        segments = [s for s, _ in pieces]
        ratios = utterance_overlap_fractions(segments)
        signals = []
        for (_, values), ratio in zip(pieces, ratios, strict=True):
            valid = [v for v in values if v is not None]
            signals.append(
                DiarSignals(ratio, float(np.mean(valid)) if valid else None, len(values))
            )
        return DiarizationResult(segments, signals, "ecapa+overlap")
