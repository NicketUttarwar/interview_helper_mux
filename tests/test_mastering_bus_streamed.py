"""Streamed BS.1770 loudness matches pyloudnorm (ISSUES 58)."""

from __future__ import annotations

import numpy as np
import pyloudnorm as pyln
import pytest
import soundfile as sf

from interview_mux import mastering_bus as mb


@pytest.mark.parametrize("rate,channels,seconds", [(48000, 2, 7.3), (44100, 1, 5.05)])
def test_streamed_loudness_matches_pyloudnorm(tmp_path, monkeypatch, rate, channels, seconds) -> None:
    monkeypatch.setattr(mb, "_BLOCK_FRAMES", 17_000)
    rng = np.random.default_rng(11)
    n = int(seconds * rate)
    t = np.arange(n) / rate
    env = 0.2 + 0.8 * (np.sin(2 * np.pi * 0.4 * t) > 0)
    sig = env * (0.25 * np.sin(2 * np.pi * 440 * t) + 0.05 * rng.standard_normal(n))
    data = np.stack([sig, 0.7 * sig][:channels], axis=1) if channels > 1 else sig
    path = tmp_path / "a.wav"
    sf.write(str(path), data.astype(np.float32), rate, subtype="FLOAT")
    ref_data, _ = sf.read(str(path), always_2d=True, dtype="float64")
    ref = pyln.Meter(rate).integrated_loudness(ref_data)
    got, r, ch, frames = mb.streamed_integrated_loudness(path)
    assert (r, ch, frames) == (rate, channels, n)
    assert abs(got - ref) < 0.01
