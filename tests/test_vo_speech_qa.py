"""VO speech QA rejects pure-tone stubs."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from interview_mux.vo_speech_qa import (
    FORBIDDEN_VO_BACKENDS,
    analyze_vo_wav,
    backend_allowed_for_vo,
    vo_passes_speech_qa,
)
from interview_mux.vo_synthesis_audit import record_synthesis
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


def _write_sine(path: Path, *, freq: float = 440.0, duration_sec: float = 2.0, rate: int = 16000) -> None:
    n = int(duration_sec * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(0.4 * 32767 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(n)
        )
        wf.writeframes(frames)


def _write_noisy_speechish(path: Path, *, duration_sec: float = 2.0, rate: int = 16000) -> None:
    """Broadband modulated signal that should pass crude speech QA."""
    n = int(duration_sec * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            t = i / rate
            # Multi-harmonic formant-ish + amplitude modulation
            env = 0.35 + 0.35 * abs(math.sin(2 * math.pi * 4.5 * t))
            val = 0.0
            for f, a in ((180, 0.3), (420, 0.25), (980, 0.2), (1600, 0.15), (2400, 0.1)):
                val += a * math.sin(2 * math.pi * f * t)
            # Mild noise
            val += 0.08 * math.sin(2 * math.pi * (37 + (i % 97)) * t)
            sample = int(max(-1.0, min(1.0, val * env)) * 32767)
            frames += struct.pack("<h", sample)
        wf.writeframes(bytes(frames))


def test_pure_tone_fails_speech_qa(tmp_path: Path) -> None:
    wav = tmp_path / "tone.wav"
    _write_sine(wav)
    row = analyze_vo_wav(wav)
    assert row["pass"] is False
    assert any("tone" in str(r) or "non_speech" in str(r) for r in row["reasons"])
    assert not vo_passes_speech_qa(wav)


def test_modulated_speechish_passes(tmp_path: Path) -> None:
    wav = tmp_path / "speech.wav"
    _write_noisy_speechish(wav)
    assert vo_passes_speech_qa(wav)


def test_forbidden_backends() -> None:
    assert not backend_allowed_for_vo("tone_stub")
    assert "tone_stub" in FORBIDDEN_VO_BACKENDS
    assert backend_allowed_for_vo("chatterbox")


def test_record_synthesis_rejects_tone_stub(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_vo_qa", create=True)
    wav = ctx.path("vo_pickup", "synthesized", "line.wav")
    _write_noisy_speechish(wav)
    try:
        record_synthesis(ctx, {"line_id": "line"}, backend="tone_stub", out_wav=wav)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Forbidden" in str(exc)
