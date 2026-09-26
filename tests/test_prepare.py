import json

import numpy as np
import pytest

from meeting_asr.data_gen.prepare import prepare_dataset
from meeting_asr.data_gen.simulate import write_mono_wav


def test_audit_splits_original_speakers_and_rejects_duplicates(tmp_path):
    entries = []
    for i in range(6):
        wav = tmp_path / f"{i}.wav"
        t = np.arange(16000) / 16000
        write_mono_wav(wav, np.sin(2 * np.pi * (200 + i * 30) * t) * 0.2, 16000)
        entries.append(
            {
                "clip_id": str(i),
                "speaker": str(i),
                "text": "xin chào",
                "source": "test",
                "license": "fixture",
                "wav": wav.name,
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"clips": entries}))
    out = tmp_path / "out"
    report = prepare_dataset(manifest, out)
    assert report["splits"]["dev"]["speakers"] == 3
    dev = json.loads((out / "dev.json").read_text())["clips"]
    test = json.loads((out / "test.json").read_text())["clips"]
    assert {e["speaker"] for e in dev}.isdisjoint({e["speaker"] for e in test})
    entries[1]["wav"] = entries[0]["wav"]
    manifest.write_text(json.dumps({"clips": entries}))
    with pytest.raises(ValueError, match="duplicate audio"):
        prepare_dataset(manifest, out)
