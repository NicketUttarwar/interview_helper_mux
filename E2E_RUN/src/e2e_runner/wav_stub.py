"""Minimal valid WAV bytes for G1 VO stub uploads."""

from __future__ import annotations

import io
import struct
import wave


def minimal_wav_bytes(*, duration_s: float = 0.25, sample_rate: int = 16000) -> bytes:
    n_frames = max(1, int(sample_rate * duration_s))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


def write_stub_wav(path: str) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(minimal_wav_bytes())
