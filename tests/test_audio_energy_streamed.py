"""Energy windows stream the file and match the whole-file computation (ISSUES 58)."""

from __future__ import annotations

import numpy as np
import soundfile as sf

from interview_mux import audio_energy as ae


def _reference(path, window_sec):
    audio, sr = sf.read(str(path), always_2d=True)
    mono = audio.mean(axis=1).astype(np.float64)
    peak = float(np.max(np.abs(mono))) or 1.0
    win = max(1, int(sr * window_sec))
    usable = (len(mono) // win) * win
    w = mono[:usable].reshape(-1, win)
    rms = np.sqrt(np.mean(np.square(w), axis=1))
    t = (np.arange(len(rms)) * win / float(sr) * 1000.0).astype(np.float64)
    return rms, t, peak


def _wav(path, seconds, rate=16000, channels=1):
    rng = np.random.default_rng(3)
    n = int(seconds * rate)
    sig = 0.3 * np.sin(2 * np.pi * 180 * np.arange(n) / rate) + 0.05 * rng.standard_normal(n)
    data = np.stack([sig] * channels, axis=1) if channels > 1 else sig
    sf.write(str(path), data.astype(np.float32), rate, subtype="PCM_16")
    return path


def test_streamed_energy_matches_whole_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ae, "_BLOCK_FRAMES", 3000)
    ae._energy_windows_cached.cache_clear()
    for name, secs, ch in (("a.wav", 4.37, 1), ("b.wav", 2.2, 2)):
        path = _wav(tmp_path / name, secs, channels=ch)
        got = ae.energy_windows_from_path(path)
        rms, t, peak = _reference(path, ae.DEFAULT_WINDOW_SEC)
        assert got is not None
        assert np.allclose(got[0], rms, rtol=0, atol=1e-12)
        assert np.array_equal(got[1], t)
        assert abs(got[2] - peak) < 1e-12
