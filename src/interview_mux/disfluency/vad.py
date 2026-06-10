from __future__ import annotations

import numpy as np
import soundfile as sf


def gap_has_voice_activity(
    wav_path: str,
    start_ms: int,
    end_ms: int,
    *,
    energy_dbfs: float = -42.0,
) -> tuple[bool, float]:
    """Energy-based VAD on a short window."""
    audio, sample_rate = sf.read(wav_path, always_2d=True)
    mono = audio.mean(axis=1).astype(np.float64)
    if sample_rate <= 0 or len(mono) == 0:
        return False, 0.0
    s0 = max(0, int(start_ms * sample_rate / 1000))
    s1 = min(len(mono), int(end_ms * sample_rate / 1000))
    if s1 <= s0:
        return False, 0.0
    chunk = mono[s0:s1]
    peak = float(np.max(np.abs(mono))) if len(mono) else 1e-9
    peak = max(peak, 1e-9)
    rms = float(np.sqrt(np.mean(np.square(chunk)))) if len(chunk) else 0.0
    dbfs = 20.0 * np.log10(max(rms / peak, 1e-9))
    return bool(dbfs > energy_dbfs), float(dbfs)
