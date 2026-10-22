"""Report a completed correction comparison without making API calls.

The glossary analysis reuses the text response for datasets with an empty
glossary, including failures. This prevents attributing a repeated random draw
to glossary context. Raw observed responses and usage remain in the source run.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path

import numpy as np
from compare_llm_correction import aggregate, reference_unit_changes
from run_asr_dev_baseline import write_json

from meeting_asr.correction import source_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--document", type=Path)
    args = parser.parse_args()
    original = json.loads((args.run / "summary.json").read_text())
    if not original["complete"]:
        raise ValueError("comparison is still running")
    baseline_text = (args.baseline / "predictions.jsonl").read_text()
    if source_hash(baseline_text) != original["experiment"]["baseline_sha256"]:
        raise ValueError("baseline predictions changed")
    baseline = json.loads((args.baseline / "summary.json").read_text())
    raw = [json.loads(line) for line in (args.run / "results.jsonl").read_text().splitlines()]
    text_rows = {r["id"]: r for r in raw if r["variant"] == "text"}
    inputs = [
        json.loads(line) for line in (args.run / "inference_inputs.jsonl").read_text().splitlines()
    ]
    for row in inputs:
        assert set(row) == {"variant", "target", "context", "glossary"}
        assert set(row["target"]) == {"turn_id", "text"}
    empty_glossary = {
        r["target"]["turn_id"] for r in inputs if r["variant"] == "glossary" and not r["glossary"]
    }
    rows = []
    for observed in raw:
        row = copy.deepcopy(observed)
        if row["variant"] == "glossary" and row["id"] in empty_glossary:
            row = copy.deepcopy(text_rows[row["id"]])
            row["variant"] = "glossary"
            row["correction"].update(cache_hit=True, reused_variant="text")
        row["reference_unit_changes"] = reference_unit_changes(
            row["reference"], row["hypothesis"], row["corrected"]
        )
        rows.append(row)
    variants = ("text", "glossary")
    results = {
        v: {
            "overall": aggregate([r for r in rows if r["variant"] == v]),
            "by_dataset": {
                d: aggregate([r for r in rows if r["variant"] == v and r["dataset"] == d])
                for d in sorted({r["dataset"] for r in rows})
            },
        }
        for v in variants
    }
    requested = [r for r in raw if not r["correction"].get("cache_hit")]
    known = [r for r in requested if r["correction"].get("usage")]
    usage = {
        name: sum(r["correction"].get("usage", {}).get(name, 0) for r in known)
        for name in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    latency = [r["correction"]["elapsed_sec"] for r in known if r["status"] == "ok"]
    report = {
        "complete": True,
        "model": "kimi-k3",
        "baseline": baseline["overall"],
        "results": results,
        "inference_inputs_exclude_reference_fields": True,
        "empty_glossary_reuses_text_response": True,
        "raw_usage": {
            "requests": len(requested),
            "requests_with_recorded_usage": len(known),
            "requests_with_unknown_usage": len(requested) - len(known),
            **usage,
            "successful_request_latency_p50_sec": float(np.percentile(latency, 50))
            if latency
            else None,
            "successful_request_latency_p95_sec": float(np.percentile(latency, 95))
            if latency
            else None,
        },
        "limits": [
            "Small dev subset, source references not independently reviewed.",
            "Changed reference units use automatic alignment and exclude insertions.",
            "Unknown usage on failed responses prevents a complete billing estimate.",
            "Raw repeated empty-glossary responses remain archived outside primary analysis.",
        ],
    }
    write_json(args.run / "analysis_summary.json", report)
    (args.run / "analysis_rows.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    fields = [
        "variant",
        "dataset",
        "id",
        "status",
        "reference",
        "hypothesis",
        "corrected",
        "baseline_wer",
        "wer",
        "cer",
        "restored",
        "damaged",
        "error",
    ]
    with (args.run / "review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            value = {k: row.get(k) for k in fields}
            for metric in ("baseline_wer", "wer", "cer"):
                value[metric] = row[metric]["rate"]
            value.update({k: row["reference_unit_changes"][k] for k in ("restored", "damaged")})
            writer.writerow(value)
    base = baseline["overall"]
    composition = ", ".join(
        f"{value['clips']} {name}" for name, value in baseline["by_dataset"].items()
    )
    latency_labels = {
        p: (
            f"{report['raw_usage'][f'successful_request_latency_{p}_sec']:.2f}s"
            if latency
            else "n/a"
        )
        for p in ("p50", "p95")
    }
    lines = [
        "# Thử hiệu chỉnh ASR bằng Kimi K3 — 22/10/2026",
        "",
        (
            "Nhánh: `feat/contextual-asr-correction`. Dùng API Alibaba Cloud với đúng model "
            "`kimi-k3`; key đọc từ CSV của người dùng. Không lưu key trong code/artifact."
        ),
        "",
        (
            f"{base['clips']} clip dev ({composition}), {base['audio_sec']:.2f} giây. "
            "ASR DiariZen + DiCoW đã đóng băng trước khi gọi LLM. Không dùng test, "
            "không gửi audio hoặc reference vào model. Nhãn nguồn chưa được nghe rà độc lập."
        ),
        "",
        "## Kết quả chính",
        "",
        "| Phương án | WER | CER | Clip giảm lỗi | Clip tăng lỗi | Clip thiếu phản hồi hợp lệ |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.append(f"| ASR gốc | {base['wer']['rate']:.2%} | {base['cer']['rate']:.2%} | — | — | 0 |")
    for variant, label in (
        ("text", "Kimi + ngữ cảnh miền"),
        ("glossary", "Kimi + ngữ cảnh + glossary"),
    ):
        r = results[variant]["overall"]
        lines.append(
            f"| {label} | {r['wer']['rate']:.2%} | {r['cer']['rate']:.2%} | "
            f"{r['improved_clips']} | {r['worsened_clips']} | {r['api_failed']} |"
        )
    lines.extend(
        [
            "",
            (
                "API lỗi được giữ nguyên ASR và vẫn tính vào mẫu số; số clip thiếu phản hồi "
                "ở phương án glossary gồm cả các phản hồi text lỗi được dùng lại khi glossary rỗng. "
                "Các bản sửa được chấm là gợi ý giả định qua validator, chưa được người nghe chấp nhận."
            ),
            "",
            "## Theo nguồn",
            "",
            "| Nguồn | Phương án | WER | CER |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for dataset in ("vietmed", "fleurs_vi"):
        b = baseline["by_dataset"][dataset]
        lines.append(f"| {dataset} | ASR gốc | {b['wer']['rate']:.2%} | {b['cer']['rate']:.2%} |")
        for variant in variants:
            r = results[variant]["by_dataset"][dataset]
            lines.append(
                f"| {dataset} | {variant} | {r['wer']['rate']:.2%} | {r['cer']['rate']:.2%} |"
            )
    lines.extend(
        [
            "",
            (
                "Glossary gồm 20 thuật ngữ y tế tổng quát, không lấy thực thể từ gold. "
                "FLEURS có glossary rỗng, nên phân tích chính dùng lại phản hồi `text`, "
                "kể cả lỗi API. Các phản hồi gọi lặp cùng prompt vẫn giữ trong artifact raw; "
                "không quy thay đổi do lượt sinh ngẫu nhiên thành lợi ích glossary."
            ),
            "",
            "## Lỗi mới cần review",
            "",
        ]
    )
    for variant in variants:
        r = results[variant]["overall"]
        lines.append(
            f"- `{variant}`: khôi phục {r['restored_reference_units']} đơn vị reference "
            f"nhưng làm sai {r['damaged_reference_units']} đơn vị vốn khớp; "
            f"{r['damaged_correct_clips']} clip có baseline đúng hoàn toàn bị tăng WER. "
            "Các số này dựa trên alignment, không tính lỗi chèn mới và không thay thế nghe rà."
        )
    risky = [r for r in rows if r["reference_unit_changes"]["damaged"]]
    for row in risky[:4]:
        lines.extend(
            [
                "",
                f"### {row['variant']} / {row['id']}",
                "",
                f"- Nhãn nguồn: {row['reference']}",
                f"- ASR: {row['hypothesis']}",
                f"- Gợi ý Kimi: {row['corrected']}",
                f"- Đơn vị vốn đúng bị đổi: {', '.join(row['reference_unit_changes']['damaged_reference_tokens'])}.",
            ]
        )
    lines.extend(
        [
            "",
            "## Vận hành và kiểm tra",
            "",
            (
                f"Có {len(requested)} lời gọi không lấy từ cache, {len(known)} có usage được lưu. "
                f"Quan sát {usage['prompt_tokens']} input token và {usage['completion_tokens']} "
                f"output token (gồm suy luận), tổng {usage['total_tokens']}. "
                f"{len(requested) - len(known)} phản hồi lỗi không có usage trong artifact lượt này; "
                "đây không phải tổng hóa đơn."
            ),
            "",
            (
                f"Độ trễ các lời gọi thành công có metadata: p50 "
                f"{latency_labels['p50']}, p95 {latency_labels['p95']}. "
                "Không tính timeout/không có metadata vào các percentile này."
            ),
            "",
            (
                "Kiểm tra hash baseline và các trường payload đã được thực hiện khi tạo báo cáo. "
                "Kết quả kiểm thử phần mềm/kiểm tra credential được lưu riêng trong "
                "`software_validation.json` của lượt chạy."
            ),
            "",
            "## File và cách đọc",
            "",
            "- `analysis_summary.json`, `analysis_rows.jsonl`, `review.csv`: phân tích chính.",
            "- `summary.json`, `results.jsonl`, thư mục `text/`, `glossary/`: kết quả raw đầy đủ.",
            "- `inference_inputs.jsonl`: dữ liệu thực sự gửi vào model, không có đáp án.",
            "- `cache/`: proposal và metadata, không có credential hoặc reasoning_content.",
            "",
            (
                "Kết quả này chưa đủ để tự động áp dụng sửa hoặc kết luận hiệu quả trên họp IT. "
                "Bước tiếp theo là nghe rà các patch, thử gold họp IT và recording độc lập, "
                "rồi chốt prompt/ngưỡng trên dev trước khi chấm test."
            ),
            "",
            (
                "API/model: [tài liệu chính thức Alibaba Cloud Kimi]"
                "(https://help.aliyun.com/zh/model-studio/kimi-api)."
            ),
        ]
    )
    text = "\n".join(lines) + "\n"
    (args.run / "REPORT.md").write_text(text, encoding="utf-8")
    if args.document:
        args.document.parent.mkdir(parents=True, exist_ok=True)
        args.document.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {"results": results, "raw_usage": report["raw_usage"]}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
