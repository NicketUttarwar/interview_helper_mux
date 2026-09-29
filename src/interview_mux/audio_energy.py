"""Shared RMS energy window helpers for transcript review, spine, and enrichment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

DEFAULT_WINDOW_SEC = 0.4
# Frames per streamed read (8 MiB of float64 mono).
_BLOCK_FRAMES = 1 << 20


@lru_cache(maxsize=8)
def _energy_windows_cached(
    resolved: str,
    mtime_ns: int,
    window_sec: float,
) -> tuple[tuple[float, ...], tuple[float, ...], float] | None:
    """Cache RMS windows by absolute path + mtime so multi-chunk stages don't re-read WAVs."""
    wav_path = Path(resolved)
    if not wav_path.is_file():
        return None
    # Streamed in blocks: a whole-file float64 read plus copies was several GB
    # for a one-hour tape and got the edl stage killed (ISSUES entry 58).
    with sf.SoundFile(str(wav_path)) as handle:
        sample_rate = int(handle.samplerate)
    if sample_rate <= 0:
        return None
    win_size = max(1, int(sample_rate * window_sec))
    block = max(win_size, (_BLOCK_FRAMES // win_size) * win_size)
    rms_parts: list[np.ndarray] = []
    peak = 0.0
    total = 0
    carry = np.zeros((0,), dtype=np.float64)
    for chunk in sf.blocks(str(wav_path), blocksize=block, always_2d=True, dtype="float64"):
        mono = chunk.mean(axis=1)
        total += len(mono)
        if mono.size:
            peak = max(peak, float(np.max(np.abs(mono))))
        if carry.size:
            mono = np.concatenate([carry, mono])
        usable = (len(mono) // win_size) * win_size
        if usable:
            windows = mono[:usable].reshape(-1, win_size)
            rms_parts.append(np.sqrt(np.mean(np.square(windows), axis=1)))
        carry = mono[usable:]
    if total == 0 or not rms_parts:
        return None
    peak = peak or 1.0
    rms = np.concatenate(rms_parts)
    times_ms = (np.arange(len(rms)) * win_size / float(sample_rate) * 1000.0).astype(np.float64)
    # Store as tuples so the cache value is hashable/immutable.
    return tuple(float(x) for x in rms), tuple(float(x) for x in times_ms), peak


def energy_windows_from_path(
    wav_path: Path,
    *,
    window_sec: float = DEFAULT_WINDOW_SEC,
) -> tuple[np.ndarray, np.ndarray, float] | None:
    """Return (rms_per_window, window_center_times_ms, peak) for mono WAV."""
    if wav_path is None or not Path(wav_path).is_file():
        return None
    resolved = str(Path(wav_path).resolve())
    try:
        mtime_ns = Path(resolved).stat().st_mtime_ns
    except OSError:
        return None
    packed = _energy_windows_cached(resolved, mtime_ns, float(window_sec))
    if packed is None:
        return None
    rms_t, times_t, peak = packed
    return np.asarray(rms_t, dtype=np.float64), np.asarray(times_t, dtype=np.float64), peak


def find_silence_valley_ms(
    wav_path: Path,
    target_ms: int,
    *,
    search_ms: int = 200,
    window_sec: float = DEFAULT_WINDOW_SEC,
) -> int:
    """Search ±search_ms around target for minimum RMS (silence valley)."""
    packed = energy_windows_from_path(wav_path, window_sec=window_sec)
    if packed is None:
        return target_ms
    rms, times_ms, _peak = packed
    lo = max(0, target_ms - search_ms)
    hi = target_ms + search_ms
    mask = (times_ms >= lo) & (times_ms <= hi)
    if not np.any(mask):
        return target_ms
    idx = np.argmin(rms[mask])
    return int(times_ms[mask][idx])


def rms_at_ms(wav_path: Path, center_ms: int, *, window_sec: float = DEFAULT_WINDOW_SEC) -> float | None:
    packed = energy_windows_from_path(wav_path, window_sec=window_sec)
    if packed is None:
        return None
    rms, times_ms, _peak = packed
    if times_ms.size == 0:
        return None
    idx = int(np.argmin(np.abs(times_ms - center_ms)))
    return float(rms[idx])
