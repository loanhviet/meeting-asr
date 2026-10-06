from pathlib import Path

import pytest

from meeting_asr.export import export_markdown, export_pdf, export_srt


def view():
    return {
        "summary_stale": True,
        "edited": {
            "audio_id": "x",
            "duration": 6,
            "num_speakers": 1,
            "summary": "old summary",
            "action_items": [],
            "topics": [],
            "turns": [
                {
                    "start": 1.234,
                    "end": 3.456,
                    "speaker": "An",
                    "text": "Đã sửa tiếng Việt <test>",
                    "flagged": True,
                    "reviewed": True,
                }
            ],
        },
    }


def test_exports_use_reviewed_text_and_disclose_stale_summary():
    data = view()
    md = export_markdown(data).decode()
    assert "Đã sửa tiếng Việt" in md
    assert "old summary" not in md
    assert "cần tạo lại" in md
    srt = export_srt(data).decode()
    assert "00:00:01,234 --> 00:00:03,456" in srt
    assert "An: Đã sửa tiếng Việt" in srt


@pytest.mark.skipif(
    not Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf").is_file(),
    reason="Unicode PDF font unavailable",
)
def test_pdf_embeds_unicode_font_and_escapes_markup(monkeypatch):
    monkeypatch.setenv("MEETING_PDF_FONT", "")
    assert export_pdf(view()).startswith(b"%PDF-")


def test_grounded_export_resolves_audio_times_and_includes_decisions():
    data = view()
    data["summary_stale"] = False
    turn = data["edited"]["turns"][0]
    turn["turn_id"] = "source"
    data["edited"]["summary_points"] = [
        {"text": "Chốt bản thử nghiệm", "source_turn_ids": ["source"], "uncertain": False}
    ]
    data["edited"]["decisions"] = [
        {"text": "Gửi báo cáo", "source_turn_ids": ["source"], "uncertain": False}
    ]
    output = export_markdown(data).decode()
    assert "## Quyết định" in output
    assert "Gửi báo cáo" in output
    assert "nguồn: 00:00:01.234–00:00:03.456 (An)" in output
    data["summary_stale"] = True
    assert "Gửi báo cáo" not in export_markdown(data).decode()
