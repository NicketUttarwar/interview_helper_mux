#!/usr/bin/env python3
"""Step 4/QA: verify a mastered WAV (duration, sample rate, LUFS, peak)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


def _measure_lufs(path: Path) -> float | None:
    try:
        import numpy as np
        import pyloudnorm as pyln
        import soundfile as sf
    except ImportError:
        return None
    data, rate = sf.read(str(path))
    if data.ndim > 1:
        data = data.mean(axis=1)
    meter = pyln.Meter(rate)
    return float(meter.integrated_loudness(data))


def _peak_dbfs(path: Path) -> float | None:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        return None
    data, _rate = sf.read(str(path))
    if data.ndim > 1:
        data = data.mean(axis=1)
    peak = float(np.max(np.abs(data)))
    if peak <= 0:
        return -float("inf")
    return 20.0 * float(np.log10(peak))


def main() -> int:
    p = argparse.ArgumentParser(description="Verify podcast master WAV")
    p.add_argument("wav", type=Path, help="Path to WAV master")
    p.add_argument("--min-duration-sec", type=float, default=0.5)
    p.add_argument("--target-lufs", type=float, default=-16.0)
    p.add_argument("--lufs-tolerance", type=float, default=6.0)
    args = p.parse_args()

    path = args.wav.resolve()
    if not path.is_file():
        print(f"FAIL: not found: {path}", file=sys.stderr)
        return 1

    print(f"=== verify_master: {path} ===")
    fail = False
    meta = _ffprobe(path)
    fmt = meta.get("format", {})
    duration = float(fmt.get("duration", 0))
    print(f"  duration_sec: {duration:.2f}")
    if duration < args.min_duration_sec:
        print(f"  FAIL duration < {args.min_duration_sec}s")
        fail = True
    else:
        print("  OK   duration")

    streams = meta.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    sr = int(audio.get("sample_rate", 0))
    print(f"  sample_rate: {sr}")
    if sr > 0:
        print("  OK   sample_rate")
    else:
        print("  FAIL no audio stream")
        fail = True

    lufs = _measure_lufs(path)
    if lufs is not None:
        print(f"  integrated_lufs: {lufs:.1f}")
        if abs(lufs - args.target_lufs) <= args.lufs_tolerance:
            print(f"  OK   LUFS within ±{args.lufs_tolerance} of {args.target_lufs}")
        else:
            print(f"  WARN LUFS outside ±{args.lufs_tolerance} of {args.target_lufs}")
    else:
        print("  WARN pyloudnorm/soundfile unavailable — skip LUFS")

    peak = _peak_dbfs(path)
    if peak is not None:
        print(f"  peak_dbfs: {peak:.1f}")
        if peak > -0.5:
            print("  WARN peak near 0 dBFS (possible clipping)")
        else:
            print("  OK   peak headroom")

    if fail:
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
