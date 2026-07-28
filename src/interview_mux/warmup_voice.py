"""Ensure a neutral warm-up reference voice exists for probe TTS.

ASSETS/ is gitignored — this module (and scripts/ensure_warmup_voice.py)
creates ASSETS/local_speech/warmup_voice/neutral.wav on demand.
"""

from __future__ import annotations

import struct
import subprocess
import wave
from pathlib import Path

from interview_mux.config import repo_root


def default_neutral_path() -> Path:
    return repo_root() / "ASSETS" / "local_speech" / "warmup_voice" / "neutral.wav"


def _write_silence_wav(dest: Path, *, seconds: float = 2.0, rate: int = 24000) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    nframes = int(rate * seconds)
    with wave.open(str(dest), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        # Soft low-amplitude tone so TTS refs are non-empty (not pure digital silence).
        frames = bytearray()
        for i in range(nframes):
            # ~220 Hz soft sine approximation via triangle (no math import needed)
            period = max(1, rate // 220)
            pos = i % period
            amp = int(800 * (1 - abs(pos - period / 2) / (period / 2)))
            frames += struct.pack("<h", amp)
        wf.writeframes(bytes(frames))
    return dest


def _try_macos_say(dest: Path) -> Path | None:
    """Bootstrap a spoken neutral ref via macOS `say` + afconvert."""
    say = Path("/usr/bin/say")
    afconvert = Path("/usr/bin/afconvert")
    if not say.is_file() or not afconvert.is_file():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    aiff = dest.with_suffix(".aiff")
    try:
        proc = subprocess.run(
            [
                str(say),
                "-v",
                "Samantha",
                "-o",
                str(aiff),
                "This is a neutral system warm-up voice for audio probes.",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0 or not aiff.is_file():
            return None
        proc2 = subprocess.run(
            [
                str(afconvert),
                "-f",
                "WAVE",
                "-d",
                "LEI16@24000",
                str(aiff),
                str(dest),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc2.returncode == 0 and dest.is_file() and dest.stat().st_size > 44:
            return dest
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if aiff.is_file():
            try:
                aiff.unlink()
            except OSError:
                pass
    return None


def ensure_neutral_warmup_voice(dest: Path | None = None) -> Path:
    """Create neutral.wav if missing. Prefer macOS say; else soft-tone wav."""
    path = dest or default_neutral_path()
    if path.is_file() and path.stat().st_size > 44:
        return path
    spoken = _try_macos_say(path)
    if spoken is not None:
        return spoken
    return _write_silence_wav(path)
