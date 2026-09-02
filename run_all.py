#!/usr/bin/env python
"""Vivid -- convenience runner: cartoonize -> compare -> failure_cases -> portfolio.

Each stage also runs standalone (see README); this just chains them with
the defaults for a one-command end-to-end demo build.

Usage:
    python run_all.py
"""
from __future__ import annotations

import subprocess
import sys

STAGES = [
    [sys.executable, "cartoonize.py"],
    [sys.executable, "compare.py"],
    [sys.executable, "failure_cases.py"],
    [sys.executable, "portfolio.py"],
]


def main():
    for stage in STAGES:
        print(f"\n=== Running: {' '.join(stage)} ===")
        result = subprocess.run(stage)
        if result.returncode != 0:
            print(f"\nStage failed: {' '.join(stage)} (exit {result.returncode})")
            sys.exit(result.returncode)
    print("\nAll stages complete. Open portfolio/index.html to view the result.")


if __name__ == "__main__":
    main()
