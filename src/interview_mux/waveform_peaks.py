"""Waveform peak envelope for GUI timeline.

Producer SSOT: ``ingest`` writes ``ingest/waveform_peaks.json`` for normalized
audio. GUI / API paths load only (may compute ephemeral peaks in-memory for
non-cached or non-normalized paths — never persist).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from interview_mux.file_store import read_json
from interview_mux.run_context import RunContext

PEAKS_REL = "ingest/waveform_peaks.json"
_WINDOW_MS = 100
_NORMALIZED_REL = "ingest/normalized.wav"


def _resolve_audio_path(ctx: RunContext, rel_path: str) -> Path:
    p = ctx.read_path(rel_path)
    if not p.is_file():
        raise FileNotFoundError(f"Audio not found: {rel_path}")
    return p


# Frames per read. 2^20 mono float32 frames is 4 MiB; the old whole-file read
# held three float64 copies of a one-hour tape at once (about 4 GB) and was
# the run's memory peak before any model had loaded (ISSUES entry 54).
_BLOCK_FRAMES = 1 << 20


def generate_peaks(audio_path: Path, *, window_ms: int = _WINDOW_MS) -> list[dict[str, int | float]]:
    """Per-window peak envelope, streamed so memory does not scale with tape length."""
    with sf.SoundFile(str(audio_path)) as handle:
        sample_rate = int(handle.samplerate)
    if sample_rate <= 0:
        return []
    win_size = max(1, int(sample_rate * window_ms / 1000.0))
    block = max(win_size, (_BLOCK_FRAMES // win_size) * win_size)
    peaks_parts: list[np.ndarray] = []
    carry = np.zeros((0,), dtype=np.float32)
    for chunk in sf.blocks(str(audio_path), blocksize=block, always_2d=True, dtype="float32"):
        mono = chunk.mean(axis=1, dtype=np.float32)
        if carry.size:
            mono = np.concatenate([carry, mono])
        usable = (len(mono) // win_size) * win_size
        if usable:
            windows = mono[:usable].reshape(-1, win_size)
            peaks_parts.append(np.max(np.abs(windows), axis=1))
        carry = mono[usable:]
    if not peaks_parts:
        return []
    peaks = np.concatenate(peaks_parts).astype(np.float64)
    peak_max = float(np.max(peaks)) or 1.0
    times_ms = (np.arange(len(peaks)) * win_size / float(sample_rate) * 1000.0).astype(np.int64)
    return [
        {"t_ms": int(t), "peak": round(float(p / peak_max), 4)}
        for t, p in zip(times_ms, peaks, strict=True)
    ]


def _peaks_payload(rel_path: str, audio_path: Path) -> dict[str, Any]:
    fingerprint = f"{audio_path.stat().st_size}:{int(audio_path.stat().st_mtime)}"
    peaks = generate_peaks(audio_path)
    return {
        "source_path": rel_path,
        "source_fingerprint": fingerprint,
        "window_ms": _WINDOW_MS,
        "duration_ms": int(len(peaks) * _WINDOW_MS) if peaks else 0,
        "peaks": peaks,
    }


def persist_normalized_peaks(ctx: RunContext) -> dict[str, Any]:
    """Ingest-owned write of peaks for ``ingest/normalized.wav`` (ING-B3)."""
    audio_path = _resolve_audio_path(ctx, _NORMALIZED_REL)
    payload = _peaks_payload(_NORMALIZED_REL, audio_path)
    ctx.write_json(PEAKS_REL, payload, stage_key="ingest")
    return payload


def load_or_generate_peaks(ctx: RunContext, rel_path: str) -> dict[str, Any]:
    """Load cached peaks when valid; otherwise compute in-memory (no write).

    GUI must not persist ``ingest/waveform_peaks.json`` — ingest is sole writer.
    """
    audio_path = _resolve_audio_path(ctx, rel_path)
    fingerprint = f"{audio_path.stat().st_size}:{int(audio_path.stat().st_mtime)}"
    if rel_path == _NORMALIZED_REL:
        cache_path = ctx.read_path(PEAKS_REL)
        if cache_path.is_file():
            cached = read_json(cache_path)
            if (
                cached.get("source_path") == rel_path
                and cached.get("source_fingerprint") == fingerprint
            ):
                return cached
    return _peaks_payload(rel_path, audio_path)
