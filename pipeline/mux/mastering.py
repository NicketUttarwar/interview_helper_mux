from __future__ import annotations

from pathlib import Path


def master_lufs(
    input_wav: Path,
    output_wav: Path,
    *,
    target_lufs: float = -16.0,
    apply_lufs: bool = True,
) -> Path:
    """Apply pyloudnorm integrated loudness normalization (optional)."""
    try:
        import numpy as np
        import pyloudnorm as pyln
        import soundfile as sf
    except ImportError as e:
        raise ImportError("Install deps: pip install -r requirements.txt") from e

    data, rate = sf.read(str(input_wav))
    if data.ndim > 1:
        data = data.mean(axis=1)
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    if apply_lufs:
        meter = pyln.Meter(rate)
        loudness = meter.integrated_loudness(data)
        data = pyln.normalize.loudness(data, loudness, target_lufs)
    sf.write(str(output_wav), data, rate)
    return output_wav
