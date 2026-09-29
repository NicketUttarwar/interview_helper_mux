"""Waveform peaks stream the file and match the whole-file computation (ISSUES 54)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from interview_mux import waveform_peaks as wp


def _reference(audio_path: Path, window_ms: int) -> list[dict]:
    audio, sample_rate = sf.read(str(audio_path), always_2d=True)
    mono = audio.mean(axis=1).astype(np.float64)
    win_size = max(1, int(sample_rate * window_ms / 1000.0))
    usable = (len(mono) // win_size) * win_size
    windows = mono[:usable].reshape(-1, win_size)
    peaks = np.max(np.abs(windows), axis=1)
    peak_max = float(np.max(peaks)) or 1.0
    times_ms = (np.arange(len(peaks)) * win_size / float(sample_rate) * 1000.0).astype(np.int64)
    return [{"t_ms": int(t), "peak": round(float(p / peak_max), 4)} for t, p in zip(times_ms, peaks)]


def _wav(path: Path, seconds: float, rate: int = 16000, channels: int = 1) -> Path:
    rng = np.random.default_rng(7)
    n = int(seconds * rate)
    t = np.arange(n) / rate
    sig = 0.4 * np.sin(2 * np.pi * 220 * t) * (1 + 0.5 * np.sin(2 * np.pi * 0.3 * t))
    sig += 0.05 * rng.standard_normal(n)
    data = np.stack([sig] * channels, axis=1) if channels > 1 else sig
    sf.write(str(path), data.astype(np.float32), rate, subtype="PCM_16")
    return path


def test_streamed_peaks_match_whole_file(tmp_path, monkeypatch) -> None:
    # Small blocks so several block boundaries fall inside windows.
    monkeypatch.setattr(wp, "_BLOCK_FRAMES", 4096)
    path = _wav(tmp_path / "a.wav", seconds=3.37)
    assert wp.generate_peaks(path) == _reference(path, wp._WINDOW_MS)


def test_streamed_peaks_stereo_and_partial_window(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wp, "_BLOCK_FRAMES", 5000)
    path = _wav(tmp_path / "b.wav", seconds=1.234, rate=22050, channels=2)
    got = wp.generate_peaks(path)
    assert got == _reference(path, wp._WINDOW_MS)
    # 1.234 s at 100 ms windows: the trailing partial window is dropped.
    assert len(got) == 12


def test_empty_file_yields_no_peaks(tmp_path) -> None:
    path = tmp_path / "empty.wav"
    sf.write(str(path), np.zeros((0, 1), dtype=np.float32), 16000, subtype="PCM_16")
    assert wp.generate_peaks(path) == []
