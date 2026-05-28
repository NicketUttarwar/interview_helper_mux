from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np
import pytest

from interview_mux.mastering_bus import (
    AssemblyBusMetrics,
    loudnorm_offset,
    measure_assembly_bus,
    target_lufs_for_flow,
)


def _write_tone_wav(path: Path, *, rate: int = 48000, seconds: float = 2.0, amplitude: float = 0.25) -> None:
    samples = int(rate * seconds)
    t = np.linspace(0, seconds, samples, endpoint=False)
    mono = (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    pcm = np.clip(mono * 32767, -32768, 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())


def test_measure_assembly_bus_returns_finite_lufs(tmp_path: Path) -> None:
    wav = tmp_path / "assembly.wav"
    _write_tone_wav(wav)
    metrics = measure_assembly_bus(wav)
    assert isinstance(metrics, AssemblyBusMetrics)
    assert math.isfinite(metrics.integrated_lufs)
    assert metrics.sample_rate_hz == 48000
    assert metrics.channels == 1
    assert metrics.duration_seconds == pytest.approx(2.0, rel=0.01)


def test_measure_assembly_bus_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        measure_assembly_bus(tmp_path / "missing.wav")


def test_target_lufs_for_flow_uses_build_070_defaults() -> None:
    assert target_lufs_for_flow("flow1") == -16.0
    assert target_lufs_for_flow("flow2") == -14.0
    assert target_lufs_for_flow("flow1", config={"flow1_target_lufs": -15.5}) == -15.5


def test_loudnorm_offset() -> None:
    assert loudnorm_offset(-16.0, -20.0) == "4.00"
