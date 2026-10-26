"""Download a pinned evaluation source lock without changing the application environment.

Usage: python scripts/collect_evaluation_data.py data/gold/vi_asr_v1/source_lock.json
Source locks contain public URLs, expected sizes and optional upstream SHA256s.
Audio and annotations stay under the local, git-ignored dataset directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(root, entry):
    target = (root / entry["local_path"]).resolve()
    if not target.is_relative_to(root):
        raise ValueError("download path escapes dataset directory")
    expected = entry.get("sha256")
    if target.is_file():
        actual = checksum(target)
        if (expected is None or actual == expected) and target.stat().st_size == entry["bytes"]:
            return {**entry, "sha256": actual, "cache_hit": True}
        raise ValueError(f"existing file differs from source lock: {entry['local_path']}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    for attempt in range(3):
        try:
            request = Request(entry["url"], headers={"User-Agent": "meeting-asr-evaluation/1"})
            with urlopen(request, timeout=60) as response, temporary.open("wb") as stream:
                shutil.copyfileobj(response, stream, length=1024 * 1024)
            actual = checksum(temporary)
            if temporary.stat().st_size != entry["bytes"] or (expected and expected != actual):
                raise ValueError(f"download checksum/size mismatch: {entry['local_path']}")
            temporary.replace(target)
            return {**entry, "sha256": actual, "cache_hit": False}
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError("unreachable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", type=Path)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    root = args.lock.resolve().parent
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    files = lock["files"]
    missing = sum(f["bytes"] for f in files if not (root / f["local_path"]).exists())
    if shutil.disk_usage(root).free < missing + 2 * 1024**3:
        raise ValueError("insufficient free disk space for sources and 2 GiB preparation reserve")
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download, root, entry): entry for entry in files}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                json.dumps(
                    {
                        "file": result["local_path"],
                        "bytes": result["bytes"],
                        "cache_hit": result["cache_hit"],
                    }
                ),
                flush=True,
            )
            # Keep progress usable if interrupted; reruns verify completed files.
            report = root / "downloads.json"
            temporary = report.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(
                    sorted(results, key=lambda r: r["local_path"]), ensure_ascii=False, indent=2
                )
                + "\n"
            )
            temporary.replace(report)


if __name__ == "__main__":
    main()
