#!/usr/bin/env python3
"""Verify DeepFilterNet local venv and optional smoke enhance."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from interview_mux.local_runtime import resolve_venv_python  # noqa: E402


def _synthetic_wav(path: Path, duration_sec: float = 0.25, rate: int = 48000) -> None:
    import struct

    n = int(rate * duration_sec)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        for i in range(n):
            val = int(8000 * (i % 50) / 50)
            wf.writeframes(struct.pack("<h", val))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    py = resolve_venv_python("deepfilter")
    script = ROOT / "tools" / "deepfilter_enhance.py"
    proc = subprocess.run([str(py), str(script), "--verify"], capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode
    print(proc.stdout.strip())

    if args.smoke or args.verify:
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.wav"
            _synthetic_wav(inp)
            proc = subprocess.run(
                [str(py), str(script), "--input-wav", str(inp), "--output-wav", str(out)],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print(proc.stderr or proc.stdout, file=sys.stderr)
                return proc.returncode
            if not out.is_file():
                print("smoke enhance produced no output", file=sys.stderr)
                return 1
            print(f"smoke OK → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
