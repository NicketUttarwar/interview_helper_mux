"""Crossfade, duration, and WAV chunk helpers for mix and MMAudio paths."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from interview_mux.operator_subprocess import run_command


def wav_duration_ms(path: Path) -> int:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    proc = run_command(cmd, label=f"ffprobe duration {path.name}", capture_output=True)
    return max(0, int(float(proc.stdout.strip()) * 1000))


def _segment_rms_db(segment: AudioSegment) -> float:
    if len(segment) <= 0:
        return -120.0
    samples = segment.get_array_of_samples()
    if not samples:
        return -120.0
    peak = max(abs(s) for s in samples) or 1
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    if rms <= 0:
        return -120.0
    return 20.0 * math.log10(rms / peak)


def adaptive_crossfade_ms(
    tail: AudioSegment,
    head: AudioSegment,
    *,
    min_ms: int = 80,
    max_ms: int = 200,
    default_ms: int = 100,
) -> int:
    """Pick crossfade length from tail/head overlap energy (spectral clash heuristic)."""
    window = min(50, len(tail), len(head))
    if window <= 0:
        return default_ms
    tail_db = _segment_rms_db(tail[-window:])
    head_db = _segment_rms_db(head[:window])
    clash = max(0.0, (tail_db + head_db) / 2.0 + 36.0)
    span = max(1, max_ms - min_ms)
    scaled = min_ms + int(min(span, clash * 4))
    return max(min_ms, min(max_ms, scaled))


def snap_cut_to_word_boundary(
    end_ms: int,
    words: list[dict[str, Any]],
    *,
    margin_ms: int = 50,
    max_shift_ms: int = 400,
) -> int:
    """Nudge a cut end toward the nearest word boundary to avoid mid-word slices."""
    if not words or end_ms <= 0:
        return end_ms
    best = end_ms
    best_dist = max_shift_ms + 1
    for word in words:
        if not isinstance(word, dict):
            continue
        for key in ("end_ms", "start_ms"):
            boundary = int(word.get(key) or 0)
            if boundary <= 0:
                continue
            dist = abs(boundary - end_ms)
            if dist <= max_shift_ms and dist < best_dist:
                best = boundary + (margin_ms if key == "end_ms" else -margin_ms)
                best_dist = dist
    return max(0, best)


def append_with_crossfade(
    base: AudioSegment,
    clip: AudioSegment,
    crossfade_ms: int,
    *,
    adaptive: bool = False,
) -> AudioSegment:
    if len(base) == 0:
        return clip
    xf_ms = crossfade_ms
    if adaptive and len(base) > 0 and len(clip) > 0:
        xf_ms = adaptive_crossfade_ms(base, clip, default_ms=crossfade_ms)
    if xf_ms <= 0:
        return base + clip
    xf = min(xf_ms, len(base), len(clip))
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
    run_command(
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
        label=f"ffmpeg chunk {path.name}",
        capture_output=True,
    )
    chunks = sorted(work_dir.glob("chunk_*.wav"))
    if not chunks:
        return [path]
    return chunks
