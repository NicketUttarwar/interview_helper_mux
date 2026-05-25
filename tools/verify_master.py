#!/usr/bin/env python3
"""QA check for mastered WAV (BUILD-052)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tools/verify_master.py <master.wav>")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"Not found: {path}")
        sys.exit(1)

    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    print(proc.stdout)
    print(f"OK: {path}")


if __name__ == "__main__":
    main()
