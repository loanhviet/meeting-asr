"""MeetEval-only subprocess: no application/model runtime imports."""

from __future__ import annotations

import importlib.metadata
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path


def run(payload):
    import meeteval
    from meeteval.wer.wer.cp import cp_word_error_rate
    from meeteval.wer.wer.time_constrained import (
        time_constrained_minimum_permutation_word_error_rate,
    )
    from meeteval.wer.wer.time_constrained_orc import time_constrained_orc_wer

    version = importlib.metadata.version("meeteval")
    if version != "0.4.3":
        raise RuntimeError("paper metrics require the pinned MeetEval 0.4.3")
    reference = meeteval.io.SegLST(payload["reference"])
    hypothesis = meeteval.io.SegLST(payload["hypothesis"])
    result = {}
    options = {
        "collar": payload["collar"],
        "reference_pseudo_word_level_timing": "character_based",
        "hypothesis_pseudo_word_level_timing": "character_based_points",
        "reference_sort": "segment",
        "hypothesis_sort": "segment",
    }
    # Single-recording functions retain empty hypotheses as deletions instead
    # of letting the multifile API reject an absent hypothesis session.
    for name, function in [
        ("cpwer", cp_word_error_rate),
        ("tcpwer", time_constrained_minimum_permutation_word_error_rate),
        ("tcorcwer", time_constrained_orc_wer),
    ]:
        result[name] = asdict(
            function(reference, hypothesis, **(options if name != "cpwer" else {}))
        )
    return {
        "metrics": result,
        "protocol": {
            "scorer": "meeteval",
            "version": version,
            "time_collar_sec": payload["collar"],
            "reference_word_timing": "character_based_from_reference_utterances",
            "hypothesis_word_timing": "character_based_points_from_model_utterances",
            "normalization": "project lowercase/punctuation/NFC; whitespace units",
            "orc_reference_units": "reference utterances, not individual words",
            "note": "Temporal metric definitions follow MeetEval; this is not full paper benchmark reproduction.",
        },
    }


if __name__ == "__main__":
    value = run(json.loads(Path(sys.argv[1]).read_text()))
    Path(sys.argv[2]).write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=lambda x: float(x) if isinstance(x, Decimal) else str(x),
            allow_nan=False,
        )
        + "\n"
    )
