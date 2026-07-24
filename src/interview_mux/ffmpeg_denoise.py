"""Deterministic offline denoise fallback using FFmpeg audio filters."""

from __future__ import annotations

from pathlib import Path

from interview_mux.operator_subprocess import run_command
from interview_mux.run_context import RunContext


def denoise_wav(
    source: Path,
    output: Path,
    *,
    highpass_hz: int = 80,
    lowpass_hz: int = 12_000,
    noise_reduction_db: float = 12.0,
    ctx: RunContext | None = None,
) -> Path:
    """Denoise ``source`` into a complete PCM WAV, replacing no partial output."""
    if not source.is_file():
        raise FileNotFoundError(source)
    if not 20 <= highpass_hz < lowpass_hz:
        raise ValueError("FFmpeg denoise frequencies must satisfy 20 <= highpass < lowpass")
    if not 0.01 <= noise_reduction_db <= 97.0:
        raise ValueError("FFmpeg afftdn noise reduction must be between 0.01 and 97 dB")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.stem}.ffmpeg-denoise.tmp.wav")
    temp.unlink(missing_ok=True)
    filters = (
        f"highpass=f={highpass_hz},"
        f"lowpass=f={lowpass_hz},"
        f"afftdn=nr={noise_reduction_db:g}"
    )
    try:
        run_command(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-y",
                "-i",
                str(source),
                "-af",
                filters,
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(temp),
            ],
            ctx=ctx,
            stage="audio_preclean",
            label=f"ffmpeg local denoise → {output.name}",
            capture_output=True,
        )
        if not temp.is_file() or temp.stat().st_size < 44:
            raise RuntimeError("FFmpeg denoise did not produce a valid WAV")
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
    return output
