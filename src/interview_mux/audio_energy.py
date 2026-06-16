"""Shared RMS energy window helpers for transcript review, spine, and enrichment."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

DEFAULT_WINDOW_SEC = 0.4


def energy_windows_from_path(
    wav_path: Path,
    *,
    window_sec: float = DEFAULT_WINDOW_SEC,
) -> tuple[np.ndarray, np.ndarray, float] | None:
    """Return (rms_per_window, window_center_times_ms, peak) for mono WAV."""
    if wav_path is None or not wav_path.is_file():
        return None
    audio, sample_rate = sf.read(str(wav_path), always_2d=True)
    mono = audio.mean(axis=1).astype(np.float64)
    if mono.size == 0 or sample_rate <= 0:
        return None
    peak = float(np.max(np.abs(mono))) or 1.0
    win_size = max(1, int(sample_rate * window_sec))
    usable = (len(mono) // win_size) * win_size
    if usable <= 0:
        return None
    windows = mono[:usable].reshape(-1, win_size)
    rms = np.sqrt(np.mean(np.square(windows), axis=1))
    times_ms = (np.arange(len(rms)) * win_size / float(sample_rate) * 1000.0).astype(np.float64)
    return rms, times_ms, peak


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
