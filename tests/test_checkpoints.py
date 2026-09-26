import pickle

import pytest

from meeting_asr.checkpoints import pyannote_checkpoint_context


class UntrustedMetadata:
    pass


def test_pyannote_metadata_loads_without_disabling_weights_only(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("pyannote.audio")
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    path = tmp_path / "metadata.pt"
    metadata = Specifications(
        problem=Problem.MULTI_LABEL_CLASSIFICATION,
        resolution=Resolution.FRAME,
        duration=10.0,
        classes=["speaker1", "speaker2"],
    )
    torch.save({"version": torch.torch_version.TorchVersion("2.8.0"), "task": metadata}, path)
    previous = list(torch.serialization.get_safe_globals())
    with pyannote_checkpoint_context():
        restored = torch.load(path, weights_only=True)
        assert restored["task"] == metadata
    assert set(torch.serialization.get_safe_globals()) == set(previous)


def test_untrusted_metadata_still_rejected_and_allowlist_restored(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("pyannote.audio")
    path = tmp_path / "untrusted.pt"
    torch.save(UntrustedMetadata(), path)
    previous = list(torch.serialization.get_safe_globals())
    with pytest.raises(pickle.UnpicklingError), pyannote_checkpoint_context():
        torch.load(path, weights_only=True)
    assert set(torch.serialization.get_safe_globals()) == set(previous)


def test_context_preserves_existing_allowlist_and_nested_scopes():
    torch = pytest.importorskip("torch")
    pytest.importorskip("pyannote.audio")
    version = torch.torch_version.TorchVersion
    with torch.serialization.safe_globals([version]):
        previous = set(torch.serialization.get_safe_globals())
        with pyannote_checkpoint_context(), pyannote_checkpoint_context():
            assert version in torch.serialization.get_safe_globals()
        assert set(torch.serialization.get_safe_globals()) == previous
