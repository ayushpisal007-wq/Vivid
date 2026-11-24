#!/usr/bin/env python
"""Upload Vivid to a Hugging Face Docker Space.

Log in first, in your own terminal (the token is never passed to this script):
    huggingface-cli login

Usage:
    python tools/deploy_space.py ayushpisal/vivid
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import shutil
import subprocess

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SKIP = ("docs/", "tests/", "deploy/", "failure_cases/", "README.md", "PLAN.md", "DESIGN.md", "requirements-dev.txt")


def main() -> None:
    repo = sys.argv[1]
    api = HfApi()
    print("Logged in as", api.whoami()["name"])
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True)
    # Upload exactly what git tracks, so nothing local or private can slip in.
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    with tempfile.TemporaryDirectory() as tmp:
        for name in filter(None, tracked):
            if name.startswith(SKIP) or not (ROOT / name).exists():
                continue
            (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, Path(tmp) / name)
        shutil.copy(ROOT / "deploy" / "space_README.md", Path(tmp) / "README.md")
        api.upload_folder(repo_id=repo, repo_type="space", folder_path=tmp, delete_patterns="*", commit_message="Deploy Vivid")
    print(f"Uploaded. Build logs: https://huggingface.co/spaces/{repo}?logs=build")


if __name__ == "__main__":
    main()
