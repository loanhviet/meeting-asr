"""Synthetic Vietnamese demo fixtures, not a research or human-speech corpus."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path

import numpy as np

from meeting_asr.data_gen.simulate import (
    Clip,
    SimulatedSession,
    mix_at_snr,
    read_mono_wav,
    write_session,
)
from meeting_asr.evaluation.overlap import measure_overlap_ratio
from meeting_asr.io import _atomic_text
from meeting_asr.models import Segment

VOICES = {"SPEAKER_00": "vi-VN-NamMinhNeural", "SPEAKER_01": "vi-VN-HoaiMyNeural"}
DEMO_TEXT = (
    (
        "Chào mọi người. Hôm nay chúng ta họp để kiểm tra tiến độ dự án ghi biên bản cuộc họp. "
        "Mục tiêu là hoàn thành bản thử nghiệm trước thứ sáu tuần này."
    ),
    (
        "Em đã hoàn thành giao diện tải âm thanh và hiển thị bản chép lời. "
        "Người dùng có thể nghe lại từng đoạn bằng cách bấm vào thời gian bên cạnh câu nói."
    ),
    (
        "Rất tốt. Phần phân biệt người nói hiện tại đã chạy được chưa? "
        "Chúng ta cần thử với hai người nói luân phiên và cả những đoạn nói chồng lên nhau."
    ),
    (
        "Phần đó đã được kết nối với mô hình. Tuy nhiên, em cần kiểm tra thêm những đoạn có tiếng ồn. "
        "Kết quả từ giọng đọc tổng hợp chỉ dùng để kiểm tra chức năng."
    ),
    (
        "Anh sẽ chuẩn bị ba bản ghi âm thật để so sánh. "
        "Mỗi bản dài khoảng hai phút và không chứa thông tin riêng tư của khách hàng."
    ),
    (
        "Em nhận phần kiểm tra sửa nội dung và đổi tên người nói. "
        "Sau khi tải lại trang, các thay đổi phải được lưu đầy đủ và không làm mất bản gốc."
    ),
    (
        "Chúng ta cũng cần xuất biên bản thành tài liệu và phụ đề. "
        "Bản PDF phải hiển thị đúng dấu tiếng Việt, còn phụ đề phải khớp với thời gian trong âm thanh."
    ),
    (
        "Em sẽ kiểm tra cả ba định dạng xuất. Phần tóm tắt tự động đang tắt, "
        "vì chúng ta chưa chọn dịch vụ và chưa cấu hình khóa truy cập."
    ),
    (
        "Vậy thống nhất nhé. Anh chuẩn bị dữ liệu, em chạy kiểm thử và ghi lại các lỗi. "
        "Chúng ta sẽ xem kết quả vào lúc chín giờ sáng thứ sáu."
    ),
    (
        "Em đồng ý. Sau khi kiểm tra xong, em sẽ gửi danh sách lỗi và kết quả đo thời gian xử lý. "
        "Cảm ơn mọi người, cuộc họp kết thúc tại đây."
    ),
)


def compose_demo(clips: list[Clip], name: str, *, overlap=False, snr_db=None, seed=42):
    if not clips:
        raise ValueError("demo requires clips")
    segments = []
    cursor = 0.5
    for index, clip in enumerate(clips):
        if index:
            cursor += (
                -min(1.0, clips[index - 1].duration / 3, clip.duration / 3)
                if (overlap and index % 2)
                else 0.6
            )
        segments.append(Segment(cursor, cursor + clip.duration, clip.speaker))
        cursor += clip.duration
    waveform = np.zeros(round((cursor + 0.5) * 16000), dtype=np.float32)
    active = np.zeros(len(waveform), dtype=bool)
    for segment, clip in zip(segments, clips, strict=True):
        start = round(segment.start * 16000)
        waveform[start : start + len(clip.waveform)] += clip.waveform
        active[start : start + len(clip.waveform)] = True
    if snr_db is not None:
        noise = np.random.default_rng(seed).normal(size=len(waveform)).astype(np.float32)
        waveform = mix_at_snr(waveform, noise, snr_db, active)
    waveform *= 0.8 / max(float(np.max(np.abs(waveform))), 1e-6)
    actual_overlap = measure_overlap_ratio(segments)
    return SimulatedSession(
        name,
        waveform,
        16000,
        segments,
        clips,
        seed,
        0,
        actual_overlap,
        actual_overlap,
        snr_db,
        snr_db,
        "none" if snr_db is None else "seeded white noise",
        segments,
        "full_clip_unverified",
    )


async def generate_demo(out: str | Path, cache: str | Path, *, texts=DEMO_TEXT):
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError(
            "Install demo extras: uv sync --extra demo --extra inference --extra api"
        ) from exc
    destination, cache = Path(out).resolve(), Path(cache).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    version = importlib.metadata.version("edge-tts")
    clips = []
    for index, text in enumerate(texts):
        speaker = f"SPEAKER_{index % 2:02d}"
        voice = VOICES[speaker]
        key = hashlib.sha256(f"{version}|{voice}|{text}".encode()).hexdigest()
        mp3, wav = cache / f"{key}.mp3", cache / f"{key}.wav"
        if not wav.exists():
            for attempt in range(3):
                try:
                    await asyncio.wait_for(edge_tts.Communicate(text, voice).save(str(mp3)), 60)
                    break
                except (TimeoutError, edge_tts.exceptions.NoAudioReceived):
                    if attempt == 2:
                        raise RuntimeError(f"TTS unavailable for demo turn {index + 1}") from None
                    await asyncio.sleep(1)
            await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(mp3),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(wav),
                ],
                check=True,
            )
        waveform, sr = read_mono_wav(wav)
        audible = np.flatnonzero(np.abs(waveform) > 0.003)
        if not len(audible):
            raise RuntimeError("TTS returned silent audio")
        waveform = waveform[max(0, audible[0] - 800) : min(len(waveform), audible[-1] + 801)]
        clips.append(
            Clip(f"tts_{index:02d}", speaker, text, waveform, f"synthetic Edge TTS: {voice}", sr)
        )
        print(f"TTS turn {index + 1}/{len(texts)} ready", flush=True)
    sessions = []
    for name, options in (
        ("demo_clean", {}),
        ("demo_noisy", {"snr_db": 10}),
        ("demo_overlap", {"overlap": True}),
    ):
        session = compose_demo(clips, name, **options)
        wav = write_session(destination, session)
        sessions.append(
            {
                "audio": wav.name,
                "reference_json": wav.with_suffix(".json").name,
                "reference_rttm": wav.with_suffix(".rttm").name,
                "conversation_id": "tts_demo",
                "condition": name,
                "split": "demo",
                "synthetic": True,
                "duration_sec": session.duration,
                "overlap_ratio": session.overlap_actual,
            }
        )
    for name, suffix in (("demo_noisy", "mp3"), ("demo_overlap", "m4a")):
        await asyncio.to_thread(
            subprocess.run,
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(destination / f"{name}.wav"),
                str(destination / f"{name}.{suffix}"),
            ],
            check=True,
        )
    payload = {
        "synthetic": True,
        "purpose": "local functional smoke test only, NOT research evaluation",
        "reference_timing": "TTS clip envelopes, not hand-labelled human speech boundaries",
        "tts_provider": "Microsoft Edge online TTS",
        "edge_tts_version": version,
        "voices": VOICES,
        "sessions": sessions,
    }
    _atomic_text(destination / "sessions.json", json.dumps(payload, ensure_ascii=False, indent=2))
    _atomic_text(
        destination / "README.md",
        "# Audio demo tổng hợp\n\n"
        "Ba bản cùng nội dung: rõ, nhiễu trắng 10 dB và nói chồng lấn.\n"
        "Upload demo_clean.wav, demo_noisy.mp3 hoặc demo_overlap.m4a vào website.\n"
        "Các file JSON/RTTM là nội dung và mốc ghép TTS để đối chiếu.\n"
        "Không phải dữ liệu người thật; không dùng để kết luận DER/WER nghiên cứu.\n",
    )
    return payload
