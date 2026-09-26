"""Scoped compatibility for official pyannote 3.x checkpoint metadata.

Keep Torch's weights-only loader enabled. Never dynamically trust globals named
by a checkpoint, patch torch.load, or disable safe loading process-wide.
"""

from contextlib import contextmanager
from threading import RLock

_LOAD_LOCK = RLock()


@contextmanager
def pyannote_checkpoint_context():
    import torch
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    # The official segmentation-3.0 checkpoint stores these metadata types.
    # The allowlist is removed on exit, including when loading fails.
    with _LOAD_LOCK:
        existing = set(torch.serialization.get_safe_globals())
        additions = [
            cls
            for cls in (torch.torch_version.TorchVersion, Specifications, Problem, Resolution)
            if cls not in existing
        ]
        with torch.serialization.safe_globals(additions):
            yield
