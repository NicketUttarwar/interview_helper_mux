"""Lazy waveform peak envelope for GUI timeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from interview_mux.file_store import read_json, write_json
from interview_mux.run_context import RunContext

PEAKS_REL = "ingest/waveform_peaks.json"
_WINDOW_MS = 100


def _resolve_audio_path(ctx: RunContext, rel_path: str) -> Path:
    p = ctx.path(rel_path)
    if not p.is_file():
        raise FileNotFoundError(f"Audio not found: {rel_path}")
    return p


def generate_peaks(audio_path: Path, *, window_ms: int = _WINDOW_MS) -> list[dict[str, int | float]]:
    audio, sample_rate = sf.read(str(audio_path), always_2d=True)
    mono = audio.mean(axis=1).astype(np.float64)
    if mono.size == 0 or sample_rate <= 0:
        return []
    win_size = max(1, int(sample_rate * window_ms / 1000.0))
    usable = (len(mono) // win_size) * win_size
    if usable <= 0:
        return []
    windows = mono[:usable].reshape(-1, win_size)
    peaks = np.max(np.abs(windows), axis=1)
    peak_max = float(np.max(peaks)) or 1.0
    times_ms = (np.arange(len(peaks)) * win_size / float(sample_rate) * 1000.0).astype(np.int64)
    return [
        {"t_ms": int(t), "peak": round(float(p / peak_max), 4)}
        for t, p in zip(times_ms, peaks, strict=True)
    ]


def load_or_generate_peaks(ctx: RunContext, rel_path: str) -> dict[str, Any]:
    cache_path = ctx.path(PEAKS_REL)
    if rel_path == "ingest/normalized.wav" and cache_path.is_file():
        cached = read_json(cache_path)
        if cached.get("source_path") == rel_path:
            return cached

    audio_path = _resolve_audio_path(ctx, rel_path)
    peaks = generate_peaks(audio_path)
    payload = {
        "source_path": rel_path,
        "window_ms": _WINDOW_MS,
        "duration_ms": int(len(peaks) * _WINDOW_MS) if peaks else 0,
        "peaks": peaks,
    }
    if rel_path == "ingest/normalized.wav":
        write_json(cache_path, payload)
    return payload
