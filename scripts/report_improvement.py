"""Build the complete before/after report after dev selection and pilot inference."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path

import matplotlib
import numpy as np

from meeting_asr.runtime import file_sha256

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path("results/improvement-2026-10-02").resolve()


def read(path):
    return json.loads(Path(path).read_text())


def mean(rows, field):
    return float(np.mean([r[field] for r in rows]))


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=OUT)
    parser.add_argument(
        "--pilot-manifest", type=Path, default=Path("data/simulated/pilot/sessions.json")
    )
    parser.add_argument(
        "--dev-manifest", type=Path, default=Path("data/simulated/dev/sessions.json")
    )
    parser.add_argument("--baseline-rows", type=Path, default=Path("results/pilot/rows.json"))
    parser.add_argument(
        "--baseline-confidence",
        type=Path,
        default=Path("results/pilot-review-2026-10-02/rq3_summary.json"),
    )
    args = parser.parse_args()
    OUT = args.directory.resolve()
    rows = read(OUT / "pilot_rows.json")
    assert len(rows) == 36
    audit = read(OUT / "input_audit.json")
    for session in audit["pilot_inputs"]:
        for entry in session.values():
            assert file_sha256(entry["path"]) == entry["sha256"], entry["path"]
    assert file_sha256(args.pilot_manifest) == audit["pilot_manifest_sha256"]
    summary = read(OUT / "pilot_summary.json")
    assert file_sha256(OUT / "frozen.json") == summary["frozen_configuration_sha256"]
    confidence = read(OUT / "confidence_test.json")
    assert len(confidence) == 36
    old_confidence = read(args.baseline_confidence)["rows"]
    frozen = read(OUT / "frozen.json")
    assert (
        file_sha256(OUT / "confidence-calibration.json") == frozen["confidence_calibration_sha256"]
    )
    assert file_sha256(OUT / "dev_validation.json") == frozen["validation_sha256"]
    assert file_sha256(args.dev_manifest) == frozen["dev_manifest_sha256"]
    decisions = read(OUT / "dev_validation.json")
    rq3 = []
    for backend in ("pyannote", "ecapa"):
        subset = [r for r in confidence if r["session"]["backend"] == backend]
        for variant in ("baseline_random", "baseline_asr_only", "no_diar", "full"):
            before = next(
                r for r in old_confidence if r["backend"] == backend and r["variant"] == variant
            )
            values = [r["scores"]["0.3"]["variants"][variant] for r in subset]
            uncalibrated = [r["uncalibrated_scores"]["0.3"]["variants"][variant] for r in subset]
            rq3.append(
                {
                    "backend": backend,
                    "variant": variant,
                    **{
                        f"before_{k}": before[k]
                        for k in ("f1", "remaining_wer", "actual_coverage", "auc")
                    },
                    **{
                        k: mean(values, k)
                        for k in ("f1", "remaining_wer", "actual_coverage", "auc")
                    },
                    "uncalibrated_f1_on_new_transcripts": mean(uncalibrated, "f1"),
                    "uncalibrated_remaining_wer_on_new_transcripts": mean(
                        uncalibrated, "remaining_wer"
                    ),
                }
            )
    (OUT / "confidence_summary.json").write_text(
        json.dumps(
            {"threshold": 0.3, "review_budget": 0.2, "rows": rq3}, ensure_ascii=False, indent=2
        )
        + "\n"
    )
    lines = [
        "# Kết quả cải thiện và kiểm tra lại — 02/10/2026",
        "",
        "Đã chạy lại cả hai backend trên cùng 18 audio pilot. Các bảng dưới đây là trung bình không trọng số theo file; 18 điều kiện chỉ đến từ **2 hội thoại gốc**. Chưa đủ để khẳng định khả năng tổng quát cho họp thật.",
        "",
        "## So sánh trên nhãn gốc",
        "",
        "WER đo lỗi từ; cpWER còn tính việc gán lời cho đúng người nói. DER đo lỗi phân người nói theo thời gian. Các chỉ số này càng thấp càng tốt.",
        "",
        "| Backend | WER cũ → mới | cpWER cũ → mới | DER relaxed cũ → mới | DER strict cũ → mới |",
        "|---|---:|---:|---:|---:|",
    ]
    for backend, values in summary["metrics"].items():
        cells = [
            f"{100 * values['before_' + k]:.2f}% → {100 * values[k]:.2f}%"
            for k in ("wer", "cpwer", "relaxed_der", "strict_der")
        ]
        lines.append(f"| {backend} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "![So sánh trước và sau](comparison.svg)",
        "",
        "Relaxed DER: collar 0,25 s, bỏ overlap. Strict DER: collar 0 s, tính overlap. Nhãn gốc vẫn chứa khoảng yên lặng bên trong clip; vì vậy DER có giới hạn về độ chính xác của annotation.",
        "",
        "## Cách chọn cấu hình",
        "",
        "Sinh 30 phiên dev từ 4 hội thoại ghép bằng clip VIVOS thuộc tập dev đã audit. Dev và test không trùng speaker, clip hay checksum nguồn. Các hội thoại dev chỉ có 3 speaker, nên phạm vi hiệu chỉnh còn hẹp.",
        "",
        "Quét ngưỡng clustering bằng DER trên cả 30 phiên, sau đó so sánh cpWER của cấu hình được chọn với baseline trên 18 phiên dev (2 hội thoại đủ 9 điều kiện). Khoảng nối mảnh ASR chọn giữa 0 và 0,3 s trên cùng dev. Chỉ giữ cấu hình ứng viên khi cpWER dev thấp hơn baseline. Không dùng pilot để chọn ngưỡng hoặc trọng số.",
        "",
        "| Backend | cpWER baseline trên dev | cpWER ứng viên trên dev | Giữ ứng viên |",
        "|---|---:|---:|---|",
    ]
    for decision in decisions["decisions"]:
        lines.append(
            f"| {decision['backend']} | {100 * decision['baseline_dev_cpwer']:.2f}% | {100 * decision['candidate_dev_cpwer']:.2f}% | {'Có' if decision['use_candidate'] else 'Không; giữ clustering baseline'} |"
        )
    lines += [
        "",
        "Cấu hình cuối và calibration được chốt trong [frozen.json](frozen.json) trước khi chạy pilot; checksum không đổi sau đánh giá. Confidence dùng 60 kết quả dev (30 phiên × 2 backend), percentile margin 90 và 128 bộ trọng số ngẫu nhiên cộng baseline. Không fine-tune trọng số neural model, không ép số speaker theo nhãn test.",
        "",
        "```json",
        json.dumps(
            {
                backend: {
                    "diarization": config["diarization"],
                    "asr_merge_same_speaker_gap": config["asr"].get("merge_same_speaker_gap", 0),
                }
                for backend, config in frozen["configurations"].items()
            },
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "## Confidence và soát lỗi",
        "",
        "F1 xác định lượt có WER > 0,3, với ngân sách soát 20% speaker-time. Tỷ lệ từ còn sai giả định các lượt đã chọn được sửa hoàn toàn; **không phải WER cả file**. Bảng dùng trung bình theo file.",
        "",
        "| Backend / variant | F1 cũ → mới | Tỷ lệ từ còn sai cũ → mới | Coverage thực mới |",
        "|---|---:|---:|---:|",
    ]
    for r in rq3:
        lines.append(
            f"| {r['backend']} / {r['variant']} | {r['before_f1']:.3f} → {r['f1']:.3f} | {100 * r['before_remaining_wer']:.2f}% → {100 * r['remaining_wer']:.2f}% | {100 * r['actual_coverage']:.2f}% |"
        )
    lines += [
        "",
        "[confidence_summary.json](confidence_summary.json) còn tách hiệu quả calibration trên cùng transcript mới: so sánh `uncalibrated_*_on_new_transcripts` với kết quả đã hiệu chỉnh. Các biến thể no_diar/asr_only cũng dùng trọng số chọn trên dev, nên số trước/sau phản ánh toàn bộ cấu hình.",
        "",
        "## Theo điều kiện",
        "",
        "| Backend | Điều kiện | WER cũ → mới | cpWER cũ → mới |",
        "|---|---|---:|---:|",
    ]
    for backend in ("pyannote", "ecapa"):
        for condition in sorted({r["condition"] for r in rows}):
            subset = [r for r in rows if r["backend"] == backend and r["condition"] == condition]
            lines.append(
                f"| {backend} | {condition} | {100 * mean(subset, 'before_wer'):.2f}% → {100 * mean(subset, 'wer'):.2f}% | {100 * mean(subset, 'before_cpwer'):.2f}% → {100 * mean(subset, 'cpwer'):.2f}% |"
            )
    lines += [
        "",
        "## Nhãn speech đề xuất",
        "",
        "[pilot-draft-speech-context.json](pilot-draft-speech-context.json) tách speech RTTM tự động đề xuất và oracle RTTM ngữ cảnh câu. Đây là **auto_unverified**, không dùng cho bảng kết quả chính. Trong `pilot_rows.json`, `draft_before_strict_der` và `draft_after_strict_der` chấm cả hai dự đoán trên cùng nhãn đề xuất; không so với DER cũ trên nhãn khác để tuyên bố model cải thiện.",
        "",
        "## Tái lập và artifact",
        "",
        "```bash",
        "uv run --no-sync meeting-asr build-dataset data/audited/dev.json --out data/simulated/dev --conversations 4 --session-limit 30 --seed 42",
        "MEETING_LLM_ENABLED=false MEETING_ASR_BATCH_SIZE=1 uv run --no-sync python scripts/tune_diarization.py data/simulated/dev/sessions.json --out results/improvement-2026-10-02/tuning",
        "MEETING_LLM_ENABLED=false MEETING_ASR_BATCH_SIZE=1 uv run --no-sync python scripts/compare_improvement.py dev",
        "MEETING_LLM_ENABLED=false MEETING_ASR_BATCH_SIZE=1 uv run --no-sync python scripts/compare_improvement.py validate",
        "MEETING_LLM_ENABLED=false MEETING_ASR_BATCH_SIZE=1 uv run --no-sync python scripts/compare_improvement.py pilot",
        "uv run --no-sync python scripts/report_improvement.py",
        "```",
        "",
        "- [pilot_comparison.csv](pilot_comparison.csv): 36 dòng so sánh.",
        "- [pilot_rows.json](pilot_rows.json): từng chỉ số và thư mục transcript/RTTM/minutes mới.",
        "- [listen.html](listen.html): nghe và đối chiếu transcript sạch trước/sau.",
        "- [input_audit.json](input_audit.json): SHA-256 xác nhận audio, transcript tham chiếu và RTTM pilot giữ nguyên.",
        "- [dev_validation.json](dev_validation.json), [confidence-calibration.json](confidence-calibration.json): bằng chứng chọn tham số trên dev.",
        "- [optimized-ecapa.yaml](optimized-ecapa.yaml), [optimized-pyannote.yaml](optimized-pyannote.yaml): cấu hình của lần chạy này.",
        "",
        "Kiểm tra code: 69 bài pytest đạt; Ruff check và format đạt. Có kiểm thử việc nối mảnh ASR, loại cửa sổ ngắn/chồng lấn khỏi bước tạo cụm, fallback khi không đủ cửa sổ sạch và tách oracle RTTM khỏi speech RTTM. Transcript mới được tạo bằng model pretrained chạy thật trên GPU, không dùng decoder giả trong bảng trên.",
        "",
        "LLM tắt trong toàn bộ thử nghiệm. Đây là đánh giá chất lượng, không đo tốc độ hoặc VRAM. Bước tiếp theo là kiểm tra nhãn speech bằng nghe, mở rộng số hội thoại độc lập và đánh giá họp thật; không chỉnh lại tham số dựa trên lỗi pilot vừa thấy.",
        "",
    ]
    report = "\n".join(lines)
    if frozen.get("protocol") != "context-only" and any(
        v["cpwer"] > v["before_cpwer"] for v in summary["metrics"].values()
    ):
        report = report.replace(
            "## So sánh trên nhãn gốc",
            "**Không khuyến nghị bật các ngưỡng clustering này làm mặc định:** cpWER pilot tăng dù dev tốt hơn. Giữ nguyên đầy đủ kết quả để thể hiện hồi quy. Phương án giữ clustering và chỉ nối ngữ cảnh ASR nằm trong [báo cáo context-only](context-only/report.md).\n\n## So sánh trên nhãn gốc",
        )
    if frozen.get("protocol") == "context-only":
        report = report.replace(
            "Đã chạy lại cả hai backend trên cùng 18 audio pilot.",
            "Giữ nguyên dự đoán phân người nói baseline cho cả hai backend. Chạy lại ASR ECAPA trên cả 18 audio pilot với ngữ cảnh nối mảnh; pyannote dùng lại ASR baseline. Confidence được chấm lại cho cả hai. Đây là so sánh can thiệp ASR có kiểm soát, không phải chạy lại toàn bộ diarization.",
        )
        report = report.replace(
            "Quét ngưỡng clustering bằng DER trên cả 30 phiên, sau đó so sánh cpWER của cấu hình được chọn với baseline trên 18 phiên dev (2 hội thoại đủ 9 điều kiện). Khoảng nối mảnh ASR chọn giữa 0 và 0,3 s trên cùng dev. Chỉ giữ cấu hình ứng viên khi cpWER dev thấp hơn baseline. Không dùng pilot để chọn ngưỡng hoặc trọng số.",
            "Giữ clustering baseline. Chọn khoảng nối mảnh ECAPA-ASR giữa 0 và 0,3 s theo cpWER trên 18 phiên dev (2 hội thoại đủ 9 điều kiện). Pyannote giữ nguyên ASR. Không dùng nhãn pilot để chọn khoảng nối hoặc trọng số. Phương án này được kiểm tra thêm sau khi thử nghiệm đổi ngưỡng cho thấy khả năng tổng quát kém; pilot là thăm dò, không phải tập kiểm chứng cuối độc lập.",
        )
        report = report.replace(
            "Confidence dùng 60 kết quả dev (30 phiên × 2 backend)",
            "Confidence dùng 30 kết quả ECAPA dev, sau đó áp dụng cho cả hai backend",
        )
        report = report.replace(
            "python scripts/compare_improvement.py dev",
            "python scripts/compare_improvement.py context-dev",
        )
        report = report.replace(
            "MEETING_LLM_ENABLED=false MEETING_ASR_BATCH_SIZE=1 uv run --no-sync python scripts/compare_improvement.py validate\n",
            "",
        )
        report = report.replace(
            "python scripts/compare_improvement.py pilot",
            "python scripts/compare_improvement.py context-pilot",
        )
        report = report.replace(
            "python scripts/report_improvement.py",
            "python scripts/report_improvement.py --directory results/improvement-2026-10-02/context-only",
        )
        report += "\nKết quả thử đổi clustering (kể cả hồi quy) vẫn được giữ trong [báo cáo thử nghiệm đầu](../report.md). Không bật mặc định ngưỡng 0,85 của pyannote hoặc clean-clustering 0,5 của ECAPA.\n"
    (OUT / "report.md").write_text(report, encoding="utf-8")
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.5))
    for ax, key, title in zip(
        axes, ("wer", "cpwer", "strict_der"), ("WER", "cpWER", "Strict DER"), strict=True
    ):
        names = ["pyannote", "ecapa"]
        x = np.arange(2)
        before = [100 * summary["metrics"][b]["before_" + key] for b in names]
        after = [100 * summary["metrics"][b][key] for b in names]
        ax.bar(x - 0.18, before, 0.36, label="Before", color="#94a3b8")
        ax.bar(x + 0.18, after, 0.36, label="After", color="#2563eb")
        for pos, value in list(zip(x - 0.18, before)) + list(zip(x + 0.18, after)):
            ax.text(pos, value + 0.5, f"{value:.1f}", ha="center", fontsize=8)
        ax.set_xticks(x, names)
        ax.set_ylim(0, max(before + after) * 1.2)
        ax.set_title(title)
        ax.set_ylabel("Error (%)")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend()
    fig.suptitle("Same 18 pilot sessions / 2 source conversations — lower is better", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "comparison.svg")
    fig.savefig(OUT / "comparison.png", dpi=160)
    plt.close(fig)
    parts = [
        '<!doctype html><html lang="vi"><meta charset="utf-8"><title>Đối chiếu pilot</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 16px}table{width:100%;border-collapse:collapse}td,th{border:1px solid #ddd;padding:10px;vertical-align:top}td:first-child{white-space:nowrap}audio{width:100%}</style><h1>Transcript sạch trước / sau</h1><p>Audio và lời tham chiếu giữ nguyên. Nhãn SPEAKER là mã cụm, không so sánh trực tiếp mã giữa hai lần chạy.</p>'
    ]
    prior_rows = read(args.baseline_rows)
    for session_id in sorted({r["conversation_id"] for r in rows}):
        sample = next(
            r for r in rows if r["conversation_id"] == session_id and r["condition"] == "ovl0_clean"
        )
        parts.append(
            f'<h2>{html.escape(session_id)}</h2><audio controls src="{html.escape(os.path.relpath(sample["audio"], OUT))}"></audio>'
        )
        reference = read(sample["reference_json"])
        parts.append(
            "<details><summary>Lời tham chiếu</summary>"
            + "<br>".join(html.escape(u["text"]) for u in reference["utterances"])
            + "</details>"
        )
        for backend in ("pyannote", "ecapa"):
            new = next(
                r
                for r in rows
                if r["conversation_id"] == session_id
                and r["condition"] == "ovl0_clean"
                and r["backend"] == backend
            )
            old = next(
                r for r in prior_rows if r["audio"] == new["audio"] and r["backend"] == backend
            )
            parts.append(f"<h3>{backend}</h3><table><tr><th>Trước</th><th>Sau</th></tr><tr>")
            for row in (old, new):
                utterances = read(Path(row["prediction_dir"]) / "transcript.json")["utterances"]
                parts.append(
                    "<td>"
                    + "<br><br>".join(
                        f"{u['start']:.2f}–{u['end']:.2f} {html.escape(u['speaker'])}: {html.escape(u['text'])}"
                        for u in utterances
                    )
                    + "</td>"
                )
            parts.append("</tr></table>")
    parts.append("</html>")
    (OUT / "listen.html").write_text("\n".join(parts), encoding="utf-8")
    print("Report, charts, confidence summary and audio comparison generated.")


if __name__ == "__main__":
    main()
