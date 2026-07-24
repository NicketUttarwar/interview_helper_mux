"""Per-speaker level matching for Flow 1 speech clips (mix house-chain step 3).

Derives stable gains from transcript/segment windows on source audio, targets the
median eligible speaker level, clamps gain, and fail-opens to 0 dB.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from pydub import AudioSegment

from interview_mux.run_context import RunContext

DEFAULT_MAX_GAIN_DB = 6.0
DEFAULT_MIN_SPEECH_SEC = 5.0


def speaker_level_match_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        import interview_mux.config as mux_config

        cfg = mux_config.merged_config()
    mix = cfg.get("mix") or {}
    raw = mix.get("per_speaker_level_match") if isinstance(mix, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "max_gain_db": float(raw.get("max_gain_db", DEFAULT_MAX_GAIN_DB)),
        "min_speech_sec": float(raw.get("min_speech_sec", DEFAULT_MIN_SPEECH_SEC)),
    }


def _speaker_windows_from_segments(ctx: RunContext) -> dict[str, list[tuple[int, int]]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return {}
    manifest = ctx.read_json("segments/manifest.json")
    if not isinstance(manifest, dict):
        return {}
    out: dict[str, list[tuple[int, int]]] = {}
    for seg in manifest.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        speaker_id = str(seg.get("speaker_id") or "").strip()
        if not speaker_id:
            continue
        try:
            start = int(seg.get("start_ms") or 0)
            end = int(seg.get("end_ms") or start)
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        out.setdefault(speaker_id, []).append((start, end))
    return out


def _speaker_windows_from_transcript(ctx: RunContext) -> dict[str, list[tuple[int, int]]]:
    if not ctx.artifact_exists("transcript/full.json"):
        return {}
    full = ctx.read_json("transcript/full.json")
    if not isinstance(full, dict):
        return {}
    words = full.get("words") or []
    if not isinstance(words, list) or not words:
        return {}
    spans: dict[str, list[tuple[int, int]]] = {}
    current_sid = ""
    span_start: int | None = None
    span_end: int | None = None
    for word in words:
        if not isinstance(word, dict):
            continue
        sid = str(word.get("speaker_id") or word.get("speaker") or "").strip()
        try:
            w0 = int(float(word.get("start_ms") or 0))
            w1 = int(float(word.get("end_ms") or w0))
        except (TypeError, ValueError):
            continue
        if w1 <= w0 or not sid:
            continue
        if sid != current_sid:
            if current_sid and span_start is not None and span_end is not None:
                spans.setdefault(current_sid, []).append((span_start, span_end))
            current_sid = sid
            span_start = w0
            span_end = w1
        else:
            span_end = max(span_end or w1, w1)
    if current_sid and span_start is not None and span_end is not None:
        spans.setdefault(current_sid, []).append((span_start, span_end))
    return spans


def collect_speaker_windows(ctx: RunContext) -> dict[str, list[tuple[int, int]]]:
    """Prefer segment manifest speaker ranges; fall back to transcript word spans."""
    from_segments = _speaker_windows_from_segments(ctx)
    if from_segments:
        return from_segments
    return _speaker_windows_from_transcript(ctx)


def _concat_windows(source: AudioSegment, windows: list[tuple[int, int]]) -> AudioSegment:
    out = AudioSegment.silent(duration=0, frame_rate=source.frame_rate)
    for start, end in windows:
        lo = max(0, int(start))
        hi = min(len(source), max(lo, int(end)))
        if hi <= lo:
            continue
        out += source[lo:hi]
    return out


def measure_level_db(segment: AudioSegment) -> float | None:
    """Integrated LUFS when possible; otherwise pydub RMS dBFS. None if unusable."""
    if len(segment) <= 0 or segment.rms <= 0:
        return None
    try:
        import numpy as np
        import pyloudnorm as pyln

        samples = np.array(segment.get_array_of_samples(), dtype=np.float64)
        if segment.channels > 1:
            samples = samples.reshape((-1, segment.channels)).mean(axis=1)
        peak = float(1 << (8 * segment.sample_width - 1))
        if peak <= 0:
            return None
        samples = samples / peak
        meter = pyln.Meter(segment.frame_rate)
        lufs = float(meter.integrated_loudness(samples))
        if math.isfinite(lufs):
            return lufs
    except Exception:
        pass
    try:
        db = float(segment.dBFS)
        return db if math.isfinite(db) else None
    except Exception:
        return None


def build_speaker_gains(
    ctx: RunContext,
    source: AudioSegment,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Return speaker_id → gain_db. Fail-open to empty/zeros when disabled or unusable."""
    settings = speaker_level_match_cfg(cfg)
    if not settings["enabled"]:
        return {}
    windows_by_speaker = collect_speaker_windows(ctx)
    if not windows_by_speaker:
        return {}

    min_ms = int(float(settings["min_speech_sec"]) * 1000)
    max_gain = abs(float(settings["max_gain_db"]))
    levels: dict[str, float] = {}
    for speaker_id, windows in windows_by_speaker.items():
        speech = _concat_windows(source, windows)
        if len(speech) < min_ms:
            continue
        level = measure_level_db(speech)
        if level is None:
            continue
        levels[speaker_id] = level

    if not levels:
        return {sid: 0.0 for sid in windows_by_speaker}

    target = float(statistics.median(levels.values()))
    gains: dict[str, float] = {sid: 0.0 for sid in windows_by_speaker}
    for speaker_id, level in levels.items():
        raw = target - level
        gains[speaker_id] = max(-max_gain, min(max_gain, raw))
    return gains


def gain_db_for_speaker(gains: dict[str, float], speaker_id: str | None) -> float:
    if not speaker_id:
        return 0.0
    return float(gains.get(str(speaker_id), 0.0))


def apply_speaker_gain(audio: AudioSegment, gain_db: float) -> AudioSegment:
    if abs(float(gain_db)) < 1e-3:
        return audio
    return audio.apply_gain(float(gain_db))


def speaker_id_for_segment(ctx: RunContext, segment_id: str) -> str | None:
    if not segment_id or not ctx.artifact_exists("segments/manifest.json"):
        return None
    manifest = ctx.read_json("segments/manifest.json")
    if not isinstance(manifest, dict):
        return None
    for seg in manifest.get("segments") or []:
        if isinstance(seg, dict) and str(seg.get("segment_id") or "") == segment_id:
            sid = str(seg.get("speaker_id") or "").strip()
            return sid or None
    return None
