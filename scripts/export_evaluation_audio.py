"""Materialize embedded source audio from a collected JSONL manifest.

Example (all ViMD test audio, original bytes, extra disk space required):
  python scripts/export_evaluation_audio.py data/gold/vi_asr_v1 \
      --manifest manifests/vimd/test.jsonl --out exports/vimd_test

Use --limit for a diagnostic subset. The source manifest is never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    root = args.root.resolve()
    source = root / args.manifest
    target = root / args.out
    manifest_target = target / "manifest.jsonl"
    if manifest_target.resolve() == source.resolve():
        raise ValueError("export must not overwrite source manifest")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    if args.limit:
        # Round-robin across provinces, rather than taking only the first province.
        provinces = defaultdict(list)
        for row in rows:
            provinces[row.get("province_code", "unknown")].append(row)
        ordered = []
        while provinces:
            for key in sorted(provinces):
                ordered.append(provinces[key].pop(0))
                if not provinces[key]:
                    del provinces[key]
        rows = ordered[: args.limit]
    wanted = defaultdict(dict)
    for row in rows:
        locator = row.get("audio_locator")
        if locator:
            wanted[locator["parquet"]][locator["row"]] = row
    target.mkdir(parents=True, exist_ok=True)
    exported = 0
    for parquet, by_index in wanted.items():
        offset = 0
        for batch in pq.ParquetFile(root / parquet).iter_batches(batch_size=8, columns=["audio"]):
            for index in range(offset, offset + batch.num_rows):
                if index not in by_index:
                    continue
                row = by_index[index]
                data = batch.slice(index - offset, 1).to_pylist()[0]["audio"]["bytes"]
                if hashlib.sha256(data).hexdigest() != row["source_audio_sha256"]:
                    raise ValueError("embedded source audio checksum mismatch")
                name = Path(row["id"]).name
                if name != row["id"]:
                    raise ValueError("unsafe source ID")
                output = target / "audio" / name
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
                row["audio_path"] = os.path.relpath(output, root)
                exported += 1
            offset += batch.num_rows
        print(f"Exported {parquet}", flush=True)
    if exported != sum(bool(r.get("audio_locator")) for r in rows):
        raise ValueError("source rows missing from parquet")
    with manifest_target.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows), "exported": exported, "manifest": str(manifest_target)}))


if __name__ == "__main__":
    main()
