import json

import pytest

from meeting_asr.models import Turn
from meeting_asr.summarize import Summarizer, validate_summary


def test_json_retry_and_cache_preserve_uncertain_action_items(tmp_path):
    payload = {
        "summary": "Đã thống nhất kế hoạch.",
        "topics": ["kế hoạch"],
        "action_items": [
            {"speaker": "A", "task": "gửi báo cáo", "deadline": None, "uncertain": True}
        ],
    }

    class Provider:
        calls = 0

        def complete(self, prompt, model):
            assert "[?]" in prompt
            self.calls += 1
            return "bad JSON" if self.calls == 1 else json.dumps(payload)

    provider = Provider()
    summarizer = Summarizer({"model": "fixture", "provider": "http"}, tmp_path, provider)
    turns = [Turn("1", 0, 3, "A", "tôi sẽ gửi báo cáo", [], flagged=True)]
    assert summarizer.summarize(turns) == payload
    assert summarizer.summarize(turns) == payload
    assert provider.calls == 2
    with pytest.raises(ValueError):
        validate_summary({"summary": "x", "topics": [], "action_items": [{"task": "x"}]})
