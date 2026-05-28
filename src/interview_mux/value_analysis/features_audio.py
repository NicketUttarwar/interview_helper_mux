from __future__ import annotations

from typing import Any

import numpy as np
import soundfile as sf

from interview_mux.run_context import RunContext
from interview_mux.value_analysis.config import require_value_analysis_flag

_WINDOW_SEC = 0.4
_SILENCE_DBFS = -45.0


def extract_audio_features(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    require_value_analysis_flag(cfg, "audio_features")
    wav_path = ctx.path("ingest", "normalized.wav")
    if not wav_path.is_file():
        raise FileNotFoundError(f"Missing normalized audio: {wav_path}")

    audio, sample_rate = sf.read(str(wav_path), always_2d=True)
    mono = audio.mean(axis=1).astype(np.float64)
    duration_sec = len(mono) / float(sample_rate) if sample_rate else 0.0

    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    peak_ref = max(peak, 1e-9)
    peak_dbfs_proxy = float(20.0 * np.log10(peak_ref))

    win_size = max(1, int(sample_rate * _WINDOW_SEC))
    usable = (len(mono) // win_size) * win_size
    if usable > 0:
        windows = mono[:usable].reshape(-1, win_size)
        window_rms = np.sqrt(np.mean(np.square(windows), axis=1))
        rms_p50 = float(np.percentile(window_rms, 50))
        rms_p90 = float(np.percentile(window_rms, 90))
        dbfs = 20.0 * np.log10(np.maximum(window_rms / peak_ref, 1e-8))
        silence_ratio = float(np.mean(dbfs <= _SILENCE_DBFS))
    else:
        rms_p50 = 0.0
        rms_p90 = 0.0
        silence_ratio = 0.0

    return {
        "profile": "audio",
        "duration_sec": round(duration_sec, 2),
        "silence_ratio": round(silence_ratio, 4),
        "rms_p50": round(rms_p50, 6),
        "rms_p90": round(rms_p90, 6),
        "peak_dbfs_proxy": round(peak_dbfs_proxy, 2),
    }
