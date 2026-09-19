"""Crossfade, duration, and WAV chunk helpers for mix and MMAudio paths."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from interview_mux.operator_subprocess import run_command


DEFAULT_JUNCTION_CROSSFADE_MS: dict[tuple[str, str], int] = {
    ("speech", "speech"): 100,
    ("speech", "vo"): 160,
    ("vo", "speech"): 180,
    ("vo", "vo"): 120,
    ("music", "speech"): 900,
    ("speech", "music"): 600,
}


def organic_fade_out(
    seg: AudioSegment,
    duration_ms: int,
    *,
    floor_db: float = -72.0,
    curve: float = 1.8,
) -> AudioSegment:
    """Long tapered fade-out: linear-in-dB with a soft knee into silence.

    ``curve`` > 1 keeps the bed present longer in the first half of the window,
    then eases more gently toward silence than a linear amplitude fade.
    """
    if duration_ms <= 0 or len(seg) <= 0:
        return seg
    fade_ms = min(int(duration_ms), len(seg))
    if fade_ms <= 0:
        return seg
    head = seg[: max(0, len(seg) - fade_ms)]
    tail = seg[-fade_ms:]
    samples = tail.get_array_of_samples()
    if not samples:
        return seg
    import array

    import numpy as np

    arr = np.array(samples, dtype=np.float64)
    channels = max(1, int(tail.channels))
    if channels > 1:
        arr = arr.reshape((-1, channels))
    n_frames = arr.shape[0] if arr.ndim == 2 else len(arr)
    if n_frames <= 1:
        return seg[: max(0, len(seg) - fade_ms)]
    t = np.linspace(0.0, 1.0, n_frames, dtype=np.float64)
    power = max(1.0, float(curve))
    # Slow early attenuation, soft landing into floor_db.
    gain_db = float(floor_db) * (t**power)
    frame_gain = np.power(10.0, gain_db / 20.0)
    if arr.ndim == 2:
        shaped = arr * frame_gain[:, None]
        flat = shaped.reshape(-1)
    else:
        flat = arr * frame_gain
    max_amp = float(1 << (8 * tail.sample_width - 1)) - 1.0
    dtype = np.int16 if tail.sample_width == 2 else np.int32
    clipped = np.clip(np.rint(flat), -max_amp, max_amp).astype(dtype, copy=False)
    out_samples = array.array(tail.array_type)
    out_samples.frombytes(clipped.tobytes())
    faded = tail._spawn(out_samples)
    return head + faded if len(head) > 0 else faded


def organic_fade_in(
    seg: AudioSegment,
    duration_ms: int,
    *,
    floor_db: float = -72.0,
    curve: float = 1.6,
) -> AudioSegment:
    """Tapered fade-in mirrored from :func:`organic_fade_out`."""
    if duration_ms <= 0 or len(seg) <= 0:
        return seg
    fade_ms = min(int(duration_ms), len(seg))
    if fade_ms <= 0:
        return seg
    head = seg[:fade_ms]
    tail = seg[fade_ms:]
    samples = head.get_array_of_samples()
    if not samples:
        return seg
    import array

    import numpy as np

    arr = np.array(samples, dtype=np.float64)
    channels = max(1, int(head.channels))
    if channels > 1:
        arr = arr.reshape((-1, channels))
    n_frames = arr.shape[0] if arr.ndim == 2 else len(arr)
    if n_frames <= 1:
        return seg
    t = np.linspace(0.0, 1.0, n_frames, dtype=np.float64)
    power = max(1.0, float(curve))
    # Start near floor_db and ease up (inverse of fade-out taper).
    gain_db = float(floor_db) * ((1.0 - t) ** power)
    frame_gain = np.power(10.0, gain_db / 20.0)
    if arr.ndim == 2:
        shaped = arr * frame_gain[:, None]
        flat = shaped.reshape(-1)
    else:
        flat = arr * frame_gain
    max_amp = float(1 << (8 * head.sample_width - 1)) - 1.0
    dtype = np.int16 if head.sample_width == 2 else np.int32
    clipped = np.clip(np.rint(flat), -max_amp, max_amp).astype(dtype, copy=False)
    out_samples = array.array(head.array_type)
    out_samples.frombytes(clipped.tobytes())
    faded = head._spawn(out_samples)
    return faded + tail if len(tail) > 0 else faded


def junction_crossfade_ms(
    previous_kind: str | None,
    current_kind: str | None,
    *,
    config: dict[str, Any] | None = None,
    default_ms: int = 100,
) -> int:
    """Return a bounded crossfade for the audible junction type."""
    previous = "vo" if str(previous_kind or "") in {"vo_pickup", "transition"} else str(
        previous_kind or ""
    )
    current = "vo" if str(current_kind or "") in {"vo_pickup", "transition"} else str(
        current_kind or ""
    )
    configured = config if isinstance(config, dict) else {}
    key = f"{previous}_to_{current}"
    fallback = DEFAULT_JUNCTION_CROSSFADE_MS.get((previous, current), int(default_ms))
    try:
        value = int(configured.get(key, fallback))
    except (TypeError, ValueError):
        value = fallback
    return max(0, min(2500, value))


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
    """Nudge a cut end toward the nearest word boundary to avoid mid-word slices.

    When the nearest hinge is a word *end* and the next word starts later, park
    at the midpoint of that pause (not flush on the STT end / fixed margin) so
    the release stays audible through mix crossfades.
    """
    if not words or end_ms <= 0:
        return end_ms
    best = end_ms
    best_dist = max_shift_ms + 1
    best_key = ""
    best_boundary = end_ms
    for word in words:
        if not isinstance(word, dict):
            continue
        for key in ("end_ms", "start_ms"):
            boundary = int(word.get(key) or 0)
            if boundary <= 0:
                continue
            dist = abs(boundary - end_ms)
            if dist <= max_shift_ms and dist < best_dist:
                best_boundary = boundary
                best_key = key
                best = boundary + (margin_ms if key == "end_ms" else -margin_ms)
                best_dist = dist
    if best_key == "end_ms":
        try:
            from interview_mux.cut_edge_refine import pad_end_into_following_pause

            padded = pad_end_into_following_pause(best_boundary, words)
            if padded > best_boundary:
                best = padded
        except Exception:
            pass
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


def chunk_wav_by_max_bytes(
    path: Path,
    max_bytes: int,
    *,
    work_dir: Path,
    heartbeat: Any | None = None,
) -> list[Path]:
    if path.stat().st_size <= max_bytes:
        return [path]
    work_dir.mkdir(parents=True, exist_ok=True)
    pattern = work_dir / "chunk_%03d.wav"
    segment_sec = max(30, int(max_bytes / (48000 * 2 * 1.5)))
    if heartbeat is not None:
        heartbeat(
            f"Splitting {path.name} into ~{segment_sec}s chunks (ffmpeg)…",
        )
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
