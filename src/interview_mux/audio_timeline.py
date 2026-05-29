"""Crossfade, duration, and WAV chunk helpers for mix and ElevenLabs paths."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydub import AudioSegment


def wav_duration_ms(path: Path) -> int:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return max(0, int(float(proc.stdout.strip()) * 1000))


def append_with_crossfade(
    base: AudioSegment,
    clip: AudioSegment,
    crossfade_ms: int,
) -> AudioSegment:
    if len(base) == 0:
        return clip
    if crossfade_ms <= 0:
        return base + clip
    xf = min(crossfade_ms, len(base), len(clip))
    if xf <= 0:
        return base + clip
    tail = base[-xf:].fade_out(xf)
    head = clip[:xf].fade_in(xf)
    merged = tail.overlay(head)
    return base[:-xf] + merged + clip[xf:]


def concat_clips_with_crossfade(clips: list[AudioSegment], crossfade_ms: int) -> AudioSegment:
    if not clips:
        return AudioSegment.silent(duration=0)
    out = clips[0]
    for clip in clips[1:]:
        out = append_with_crossfade(out, clip, crossfade_ms)
    return out


def chunk_wav_by_max_bytes(path: Path, max_bytes: int, *, work_dir: Path) -> list[Path]:
    if path.stat().st_size <= max_bytes:
        return [path]
    work_dir.mkdir(parents=True, exist_ok=True)
    pattern = work_dir / "chunk_%03d.wav"
    segment_sec = max(30, int(max_bytes / (48000 * 2 * 1.5)))
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-f",
            "segment",
            "-segment_time",
            str(segment_sec),
            "-c",
            "copy",
            str(pattern),
        ],
        check=True,
        capture_output=True,
    )
    chunks = sorted(work_dir.glob("chunk_*.wav"))
    if not chunks:
        return [path]
    return chunks
