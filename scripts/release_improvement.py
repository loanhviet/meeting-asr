"""Keep the accepted ASR context change; retain baseline confidence weights.

These are exploratory pilot results. The clustering and calibration trials
remain available in separate reports, including their regressions.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import yaml

from meeting_asr.confidence import review_coverage, score_confidence
from meeting_asr.io import (
    _atomic_text,
    read_transcript_json,
    write_minutes_json,
    write_transcript_json,
)
from meeting_asr.models import MeetingMinutes
from meeting_asr.postprocess import postprocess
from meeting_asr.settings import config_hash

OUT = Path("results/improvement-2026-10-02").resolve()


def read(path):
    return json.loads(Path(path).read_text())


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=OUT)
    parser.add_argument(
        "--baseline-confidence",
        type=Path,
        default=Path("results/pilot-review-2026-10-02/rq3_summary.json"),
    )
    parser.add_argument("--profile", type=Path, default=Path("configs/improved-ecapa.yaml"))
    args = parser.parse_args()
    OUT = args.directory.resolve()
    context = OUT / "context-only"
    destination = OUT / "recommended"
    base = read(OUT / "baseline_config.json")
    frozen = read(context / "frozen.json")
    rows = read(context / "pilot_rows.json")
    assert len(rows) == 36
    metrics = read(context / "pilot_summary.json")["metrics"]
    ecapa = metrics["ecapa"]
    assert ecapa["wer"] < ecapa["before_wer"] and ecapa["cpwer"] < ecapa["before_cpwer"]
    confidence = read(context / "confidence_test.json")
    old_confidence = read(args.baseline_confidence)["rows"]
    configurations = copy.deepcopy(frozen["configurations"])
    for backend, config in configurations.items():
        config["confidence"] = copy.deepcopy(base["confidence"])
        _atomic_text(
            destination / f"{backend}.yaml",
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        )
    profile = args.profile
    _atomic_text(
        profile, yaml.safe_dump(configurations["ecapa"], allow_unicode=True, sort_keys=False)
    )
    manifest = []
    for row in rows:
        source = Path(row["prediction_dir"])
        config = configurations[row["backend"]]
        target = destination / "pilot" / row["conversation_id"] / row["condition"] / row["backend"]
        target.mkdir(parents=True, exist_ok=True)
        document = replace(
            read_transcript_json(source / "transcript.json"), config_hash=config_hash(config)
        )
        write_transcript_json(target / "transcript.json", document)
        for filename in ("diarsignals.json", "diarization.rttm"):
            shutil.copyfile(source / filename, target / filename)
        turns = score_confidence(
            postprocess(document.utterances, **config["postprocess"]),
            seed=config["seed"],
            **config["confidence"],
        )
        minutes = MeetingMinutes(
            document.audio_id,
            document.duration,
            document.num_speakers,
            turns,
            review_coverage(turns),
        )
        write_minutes_json(target / "minutes.json", minutes)
        _atomic_text(
            target / "provenance.json",
            json.dumps(
                {
                    "cached_asr_source": str(source / "transcript.json"),
                    "config_hash": config_hash(config),
                    "confidence": "baseline weights; recomputed on new turns",
                    "llm_enabled": False,
                },
                indent=2,
            ),
        )
        manifest.append({**row, "prediction_dir": str(target), "config_hash": config_hash(config)})
    review = {}
    for backend in ("pyannote", "ecapa"):
        subset = [
            r["uncalibrated_scores"]["0.3"]["variants"]["full"]
            for r in confidence
            if r["session"]["backend"] == backend
        ]
        prior = next(
            r for r in old_confidence if r["backend"] == backend and r["variant"] == "full"
        )
        review[backend] = {
            "before_f1": prior["f1"],
            "f1": float(np.mean([r["f1"] for r in subset])),
            "before_remaining_wer": prior["remaining_wer"],
            "remaining_wer": float(np.mean([r["remaining_wer"] for r in subset])),
        }
    summary = {
        "sessions": 18,
        "original_conversations": 2,
        "protocol": "baseline diarization; dev-selected ECAPA ASR merge gap 0.3s; baseline confidence",
        "selection_note": "Software acceptance after exploratory pilot comparison; not a fresh final held-out evaluation.",
        "metrics": metrics,
        "review_budget": 0.2,
        "turn_wer_threshold": 0.3,
        "confidence": review,
        "profile": str(profile.resolve()),
    }
    _atomic_text(destination / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    _atomic_text(
        destination / "pilot_rows.json", json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    lines = [
        "# Cấu hình khuyến nghị sau kiểm tra — 02/10/2026",
        "",
        "Chỉ giữ thay đổi **nối mảnh cùng speaker trước ASR với gap tối đa 0,3 s cho ECAPA**. Khoảng nối chọn bằng cpWER trên dev. Diarization, trọng số confidence và text ASR gốc được giữ đúng theo phương án so sánh; không sửa lời theo transcript tham chiếu. LLM tắt.",
        "",
        "## Kết quả trên cùng 18 audio pilot",
        "",
        "Trung bình không trọng số theo file; chỉ có **2 hội thoại gốc**. Các chỉ số lỗi càng thấp càng tốt.",
        "",
        "| Backend | WER trước → sau | cpWER trước → sau | DER relaxed | DER strict |",
        "|---|---:|---:|---:|---:|",
    ]
    for backend, m in metrics.items():
        lines.append(
            f"| {backend} | {100 * m['before_wer']:.2f}% → {100 * m['wer']:.2f}% | {100 * m['before_cpwer']:.2f}% → {100 * m['cpwer']:.2f}% | {100 * m['relaxed_der']:.2f}% | {100 * m['strict_der']:.2f}% |"
        )
    lines += [
        "",
        "ECAPA giảm WER **0,75 điểm phần trăm** (khoảng 4,0% tương đối), cpWER **0,61 điểm phần trăm**. Pyannote giữ nguyên ASR/diarization baseline. DER không thay đổi vì dự đoán phân người nói được dùng lại trong phép so sánh can thiệp ASR. DER chấm trên RTTM xuất file để độ chính xác timestamp giống baseline.",
        "",
        "![So sánh](../context-only/comparison.svg)",
        "",
        "## Những thử nghiệm không được bật",
        "",
        "- [Đổi clustering](../report.md) giảm lỗi trên dev nhưng tăng lỗi trên pilot: pyannote cpWER 44,29% → 82,82%, ECAPA 27,57% → 43,07%. Ngưỡng này không được bật mặc định.",
        "- [Hiệu chỉnh confidence](../context-only/report.md) chưa cho lợi ích nhất quán. Bản khuyến nghị giữ trọng số baseline; không tuyên bố confidence cải thiện.",
        "",
        "F1 lượt sai ở ngưỡng WER > 0,3, ngân sách soát 20% speaker-time:",
        "",
        "| Backend | F1 trước → sau | Tỷ lệ từ còn sai trước → sau |",
        "|---|---:|---:|",
    ]
    for backend, r in review.items():
        lines.append(
            f"| {backend} | {r['before_f1']:.3f} → {r['f1']:.3f} | {100 * r['before_remaining_wer']:.2f}% → {100 * r['remaining_wer']:.2f}% |"
        )
    lines += [
        "",
        "Tỷ lệ từ còn sai giả định các lượt được chọn được sửa hoàn toàn, **không phải WER cả file**. Nối mảnh đổi cấu trúc lượt và nhãn lượt sai, nên F1 không phải phép so sánh calibration trên cố định lượt.",
        "",
        "## Chạy cấu hình mới",
        "",
        "```bash",
        "MEETING_LLM_ENABLED=false uv run --no-sync meeting-asr run /duong/dan/meeting.wav --config configs/improved-ecapa.yaml --out results/improved-demo",
        "```",
        "",
        "- [summary.json](summary.json): số liệu tổng hợp.",
        "- [pilot_rows.json](pilot_rows.json): 36 kết quả và đường dẫn transcript/minutes khuyến nghị.",
        "- [Nghe trước/sau](../context-only/listen.html): transcript ASR giống bản khuyến nghị; trang dùng hai hội thoại sạch.",
        "- [Audit đầu vào](../input_audit.json): dev/test không trùng speaker, clip, checksum; audio và nhãn pilot không đổi.",
        "- [Chọn khoảng nối trên dev](../context-only/dev_validation.json): cpWER dev 84,80% → 83,40%.",
        "",
        "69 bài pytest đạt; Ruff check và format đạt. Báo cáo [CLI smoke](cli-smoke.json) xác nhận cấu hình công khai tạo lại WER/cpWER của file sạch.",
        "",
        "Đây là pilot thăm dò. Cấu hình được khuyến nghị sau khi xem các phép thử trên cùng pilot, nên cần một tập hội thoại độc lập để xác nhận trước khi viết kết luận tổng quát. Nhãn speech gốc vẫn chứa khoảng yên lặng trong clip; nhãn speech tự động đề xuất cần nghe kiểm tra. Bước tiếp theo là mở rộng dev theo speaker và số hội thoại, kiểm tra nhãn speech và đánh giá họp thật.",
        "",
    ]
    _atomic_text(destination / "report.md", "\n".join(lines))
    print(
        json.dumps(
            {"profile": str(profile), "metrics": metrics, "confidence": review}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
