from __future__ import annotations

from pathlib import Path

from interview_mux.operator_subprocess import format_command, run_command


def extract_clip(source: Path, dest: Path, start_ms: int, end_ms: int) -> None:
    """Extract a PCM WAV clip from source audio using ffmpeg."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    start_s = start_ms / 1000.0
    duration_s = max((end_ms - start_ms) / 1000.0, 0.05)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_s:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration_s:.3f}",
        "-ar",
        "48000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(dest),
    ]
    run_command(
        cmd,
        label=f"ffmpeg extract clip → {dest.name}",
        capture_output=True,
    )
