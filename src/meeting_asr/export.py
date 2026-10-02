"""Export reviewed text, preserving timestamps and disclosing stale summaries."""

from __future__ import annotations

import html
import io
import os
from pathlib import Path


def timestamp(seconds: float, separator=",") -> str:
    value = max(0, round(seconds * 1000))
    hours, value = divmod(value, 3600000)
    minutes, value = divmod(value, 60000)
    secs, millis = divmod(value, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def evidence_text(item, turns):
    by_id = {turn.get("turn_id"): turn for turn in turns}
    sources = [by_id[i] for i in item.get("source_turn_ids", []) if i in by_id]
    if not sources:
        return " · chưa có dẫn chứng"
    refs = ", ".join(
        f"{timestamp(t['start'], '.')}–{timestamp(t['end'], '.')} ({t['speaker']})" for t in sources
    )
    review = (
        " · nguồn cần soát"
        if any(t.get("flagged") and not t.get("reviewed") for t in sources)
        else ""
    )
    return " · nguồn: " + refs + review


def export_markdown(view: dict) -> bytes:
    minutes = view["edited"]
    lines = [
        f"# Biên bản họp — {minutes['audio_id']}",
        "",
        f"Thời lượng: {timestamp(minutes['duration'], '.')} · {minutes['num_speakers']} người nói",
        "",
    ]
    if view["summary_stale"]:
        lines += ["> Transcript đã thay đổi; cần tạo lại tóm tắt và việc cần làm.", ""]
    elif minutes.get("summary"):
        lines += ["## Tóm tắt", ""]
        if minutes.get("summary_points"):
            for item in minutes["summary_points"]:
                lines.append("- " + item["text"] + evidence_text(item, minutes["turns"]))
            lines.append("")
        else:
            lines += [minutes["summary"], ""]
        if minutes.get("decisions"):
            lines += ["## Quyết định", ""]
            for item in minutes["decisions"]:
                lines.append("- " + item["text"] + evidence_text(item, minutes["turns"]))
            lines.append("")
        if minutes.get("topics"):
            lines += ["Chủ đề: " + ", ".join(minutes["topics"]), ""]
        if minutes.get("action_items"):
            lines += ["## Việc cần làm", ""]
            for item in minutes["action_items"]:
                uncertain = " · cần xác nhận" if item["uncertain"] else ""
                lines.append(
                    f"- {item['speaker'] or 'Chưa rõ người phụ trách'}: {item['task']}"
                    f" · hạn: {item['deadline'] or 'chưa nêu'}{uncertain}"
                    + evidence_text(item, minutes["turns"])
                )
            lines.append("")
    lines += ["## Nội dung", ""]
    for turn in minutes["turns"]:
        status = "đã soát" if turn.get("reviewed") else ("cần soát" if turn["flagged"] else "")
        lines += [
            f"**{timestamp(turn['start'], '.')}–{timestamp(turn['end'], '.')} · "
            f"{turn['speaker']}**" + (f" ({status})" if status else ""),
            "",
            turn["text"],
            "",
        ]
    return "\n".join(lines).encode("utf-8")


def export_srt(view: dict) -> bytes:
    lines = []
    for index, turn in enumerate(view["edited"]["turns"], 1):
        end = max(turn["end"], turn["start"] + 0.001)
        lines += [
            str(index),
            f"{timestamp(turn['start'])} --> {timestamp(end)}",
            f"{turn['speaker']}: {' '.join(turn['text'].split())}",
            "",
        ]
    return "\n".join(lines).encode("utf-8")


def export_pdf(view: dict) -> bytes:
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font_path = Path(
        os.getenv("MEETING_PDF_FONT") or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    if not font_path.is_file():
        raise ValueError("Set MEETING_PDF_FONT to a Unicode TTF font supporting Vietnamese")
    if "MeetingUnicode" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("MeetingUnicode", str(font_path)))
    style = ParagraphStyle(
        "Vietnamese",
        parent=getSampleStyleSheet()["Normal"],
        fontName="MeetingUnicode",
        fontSize=10,
        leading=16,
    )
    output = io.BytesIO()
    document = SimpleDocTemplate(output, title="Biên bản họp", author="Meeting Minutes ASR")
    paragraphs = []
    text = export_markdown(view).decode("utf-8")
    for block in text.split("\n\n"):
        paragraphs += [Paragraph(html.escape(block).replace("\n", "<br/>"), style), Spacer(1, 8)]
    document.build(paragraphs)
    return output.getvalue()


def export_result(view: dict, fmt: str) -> tuple[bytes, str]:
    if fmt == "md":
        return export_markdown(view), "text/markdown; charset=utf-8"
    if fmt == "srt":
        return export_srt(view), "application/x-subrip; charset=utf-8"
    if fmt == "pdf":
        return export_pdf(view), "application/pdf"
    raise ValueError("export format must be md, srt or pdf")
