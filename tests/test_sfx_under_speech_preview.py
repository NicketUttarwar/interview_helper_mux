"""Tests for under-speech SFX preview rendering."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from run_fixtures import isolated_run_ctx
from interview_mux.sound_design import render_sfx_under_speech_preview


def _write_tone(path: Path, *, duration_sec: float = 1.0, amplitude: int = 8000) -> None:
    rate = 48000
    n = int(rate * duration_sec)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{n}h", *([amplitude] * n)))


def test_render_sfx_under_speech_preview(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run-preview")
    ingest = ctx.path("ingest")
    ingest.mkdir(parents=True, exist_ok=True)
    _write_tone(ingest / "normalized.wav", duration_sec=3.0, amplitude=4000)

    assets = ctx.path("sound_design", "assets")
    assets.mkdir(parents=True, exist_ok=True)
    _write_tone(assets / "bed_theme.wav", duration_sec=1.0, amplitude=6000)

    out = render_sfx_under_speech_preview(ctx, "bed_theme")
    assert out.is_file()
    assert out.name == "bed_theme_under_speech.wav"
    assert out.stat().st_size > 1000

    cached = render_sfx_under_speech_preview(ctx, "bed_theme")
    assert cached == out
