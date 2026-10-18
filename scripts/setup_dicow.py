"""Install the pinned author's runtime separately from the baseline .venv."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTHOR_COMMIT = "801e2130d00142a7da5845754f87b97550053a75"


def call(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--root", type=Path, default=ROOT / ".cache/dicow")
    parser.add_argument("--torch-backend", choices=["cpu", "cu128"])
    args = parser.parse_args()
    uv = shutil.which("uv")
    if not uv:
        parser.error("Install uv first: python -m pip install uv")
    runtime_root = args.root.resolve()
    upstream = runtime_root / "upstream/DiCoW"
    upstream.parent.mkdir(parents=True, exist_ok=True)
    if not upstream.exists():
        call(
            "git",
            "clone",
            "--filter=blob:none",
            "https://github.com/BUTSpeechFIT/DiCoW.git",
            upstream,
        )
    call("git", "-C", upstream, "checkout", AUTHOR_COMMIT)
    call("git", "-C", upstream, "submodule", "update", "--init", "--recursive")
    environment = runtime_root / "venv"
    python = environment / "bin/python"
    if not python.exists():
        call(uv, "venv", "--python", args.python, environment)
    call(
        uv,
        "pip",
        "install",
        "--python",
        python,
        "--link-mode",
        "copy",
        *(["--torch-backend", args.torch_backend] if args.torch_backend else []),
        "--build-constraint",
        ROOT / "requirements/dicow-build.txt",
        "--constraint",
        ROOT / "requirements/dicow-runtime.lock.txt",
        "-r",
        ROOT / "requirements/dicow-runtime.txt",
        "-e",
        upstream / "DiariZen/pyannote-audio",
    )
    installed = subprocess.check_output([uv, "pip", "freeze", "--python", str(python)], text=True)
    manifest = {
        "author_repository": "https://github.com/BUTSpeechFIT/DiCoW",
        "author_commit": AUTHOR_COMMIT,
        "diarizen_commit": subprocess.check_output(
            ["git", "-C", str(upstream / "DiariZen"), "rev-parse", "HEAD"], text=True
        ).strip(),
        "python": str(python),
        "packages": installed.splitlines(),
    }
    (runtime_root / "runtime.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("DiCoW runtime ready. Model weights download on the first inference run.")


if __name__ == "__main__":
    main()
