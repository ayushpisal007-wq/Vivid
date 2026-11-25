#!/usr/bin/env python
"""Pre-fetch every checkpoint Vivid uses, plus the AnimeGANv2 network code from torch.hub.

Safe to re-run: verified files are kept and interrupted downloads resume.

Usage:
    python tools/download_weights.py
    VIVID_STYLES=hayao_v3,shinkai_v3 python tools/download_weights.py    # only these
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from registry import Registry, load_hub_generator  # noqa: E402
from weight_store import WEIGHTS, ensure  # noqa: E402


def main() -> int:
    wanted = [s.strip() for s in os.environ.get("VIVID_STYLES", "").split(",") if s.strip()]
    if wanted:  # lite deployment: fetch and test just these
        missing = Registry(only=wanted).unavailable
        print("missing: " + str(missing) if missing else "ok      " + ", ".join(wanted))
        return 1 if missing else 0
    failed = []
    for filename in WEIGHTS:
        try:
            path = ensure(filename)
            print(f"ok      {filename}  ({path.stat().st_size / 1e6:.1f} MB)")
        except Exception as e:
            failed.append(filename)
            print(f"FAILED  {filename}: {e}")
    try:
        load_hub_generator()
        print("ok      torch.hub network code")
    except Exception as e:
        failed.append("torch.hub network code")
        print(f"FAILED  torch.hub network code: {e}")
    if failed:
        print(f"\n{len(failed)} item(s) failed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
