"""Append-only experiment log required by the technical spec."""

from __future__ import annotations

import csv
from pathlib import Path

from meeting_asr.settings import PROJECT_ROOT

COLUMNS = (
    "run_id",
    "git_commit",
    "config_hash",
    "dataset",
    "diar_backend",
    "masking",
    "der_lenient",
    "der_strict",
    "miss",
    "fa",
    "confusion",
    "wer",
    "cpwer_oracle",
    "cpwer_cascaded",
    "conf_variant",
    "conf_threshold",
    "coverage",
    "flag_precision",
    "flag_recall",
    "flag_f1",
    "flag_auc",
    "rtf",
    "notes",
)

DEFAULT_LOG = PROJECT_ROOT / "results" / "experiments.csv"


def experiment_log_path(path=None):
    return DEFAULT_LOG if path is None else Path(path)


def append_experiment_rows(rows, path=None):
    destination = experiment_log_path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_header = not destination.exists() or destination.stat().st_size == 0
    with destination.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(
                {column: "" if row.get(column) is None else row[column] for column in COLUMNS}
            )
    return destination
