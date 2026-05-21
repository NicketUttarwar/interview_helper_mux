from __future__ import annotations

from pathlib import Path
from typing import Any


def apply_room_polish(
    input_wav: Path,
    output_wav: Path,
    *,
    conn: Any | None = None,
    denoise: bool = True,
) -> Path:
    """
    Mandatory room polish: light denoise (noisereduce) + optional pedalboard high-pass.
    Always runs on the final timeline; not optional and not gated.
    """
    _ = conn  # reserved for future run_event logging

    try:
        import soundfile as sf
    except ImportError as e:
        raise ImportError("Install deps: pip install -r requirements.txt") from e

    data, rate = sf.read(str(input_wav))
    mono = data.mean(axis=1) if data.ndim > 1 else data

    if denoise:
        try:
            import noisereduce as nr

            mono = nr.reduce_noise(y=mono, sr=rate, stationary=True, prop_decrease=0.4)
        except ImportError:
            pass

    try:
        from pedalboard import HighpassFilter, Pedalboard

        board = Pedalboard([HighpassFilter(cutoff_frequency_hz=80)])
        mono = board(mono, rate)
    except ImportError:
        pass

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_wav), mono, rate)
    return output_wav
