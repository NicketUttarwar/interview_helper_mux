"""Encode master.wav → podcast MP3 via ffmpeg (stereo by default)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def encode_master_to_mp3(
    master_wav: Path,
    dest_mp3: Path,
    *,
    bitrate_k: int = 192,
    channels: int = 2,
) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    if not master_wav.is_file():
        raise FileNotFoundError(master_wav)
    dest_mp3.parent.mkdir(parents=True, exist_ok=True)
    br = max(64, int(bitrate_k))
    ac = 2 if int(channels) >= 2 else 1
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(master_wav),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        f"{br}k",
        "-ar",
        "44100",
        "-ac",
        str(ac),
        str(dest_mp3),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dest_mp3.is_file():
        raise RuntimeError(f"ffmpeg MP3 encode failed: {proc.stderr[-800:]}")
    return dest_mp3
