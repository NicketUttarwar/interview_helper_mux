"""Lightweight stage-input signals from transcript/audio artifacts (spike winners, no new ML deps)."""

from __future__ import annotations

from typing import Any

import numpy as np
import soundfile as sf

from interview_mux.run_context import RunContext

VALUE_FEATURES_PATH = "understanding/value_features.json"

_PAUSE_LADDER_MS = (400, 700, 1200)
_WINDOW_SEC = 0.4
_SILENCE_DBFS = -45.0


def _load_words(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("transcript/full.json"):
        return []
    transcript = ctx.read_json("transcript/full.json")
    words = [w for w in (transcript.get("words") or []) if isinstance(w, dict)]
    words.sort(key=lambda w: float(w.get("start_ms", 0)))
    return words


def _load_segments(ctx: RunContext) -> list[dict[str, Any]]:
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        if isinstance(manifest, dict):
            return [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]
    return []


def pause_ladder_hints(ctx: RunContext) -> dict[str, Any]:
    """H-SEG-02: candidate boundary times at multiple pause thresholds."""
    words = _load_words(ctx)
    if len(words) < 2:
        return {"thresholds_ms": list(_PAUSE_LADDER_MS), "candidates": []}

    candidates: list[dict[str, Any]] = []
    for threshold in _PAUSE_LADDER_MS:
        hits: list[int] = []
        for i in range(1, len(words)):
            gap = float(words[i].get("start_ms", 0)) - float(words[i - 1].get("end_ms", 0))
            if gap >= threshold:
                hits.append(int(words[i].get("start_ms", 0)))
        candidates.append(
            {
                "threshold_ms": threshold,
                "split_times_ms": hits[:40],
                "count": len(hits),
            }
        )
    return {"thresholds_ms": list(_PAUSE_LADDER_MS), "candidates": candidates}


def _energy_windows(ctx: RunContext) -> tuple[np.ndarray, np.ndarray, float] | None:
    wav_path = ctx.path("ingest", "normalized.wav")
    if not wav_path.is_file():
        return None
    audio, sample_rate = sf.read(str(wav_path), always_2d=True)
    mono = audio.mean(axis=1).astype(np.float64)
    if mono.size == 0 or sample_rate <= 0:
        return None
    peak = float(np.max(np.abs(mono))) or 1.0
    win_size = max(1, int(sample_rate * _WINDOW_SEC))
    usable = (len(mono) // win_size) * win_size
    if usable <= 0:
        return None
    windows = mono[:usable].reshape(-1, win_size)
    rms = np.sqrt(np.mean(np.square(windows), axis=1))
    times_ms = (np.arange(len(rms)) * win_size / float(sample_rate) * 1000.0).astype(np.float64)
    return rms, times_ms, peak


def emphasis_regions_for_segments(ctx: RunContext, *, max_regions: int = 24) -> list[dict[str, Any]]:
    """H-F1N-02: quiet-but-vital emphasis — high local RMS vs segment median."""
    packed = _energy_windows(ctx)
    segments = _load_segments(ctx)
    if packed is None or not segments:
        return []

    rms, times_ms, _peak = packed
    p90 = float(np.percentile(rms, 90)) if rms.size else 0.0
    p50 = float(np.percentile(rms, 50)) if rms.size else 0.0
    regions: list[dict[str, Any]] = []

    for seg in segments:
        sid = str(seg.get("segment_id") or seg.get("id") or "")
        start_ms = seg.get("start_ms")
        end_ms = seg.get("end_ms")
        if start_ms is None and seg.get("start_time") is not None:
            start_ms = int(float(seg["start_time"]) * 1000)
        if end_ms is None and seg.get("end_time") is not None:
            end_ms = int(float(seg["end_time"]) * 1000)
        if sid == "" or start_ms is None or end_ms is None:
            continue
        mask = (times_ms >= float(start_ms)) & (times_ms <= float(end_ms))
        if not np.any(mask):
            continue
        seg_rms = rms[mask]
        seg_p90 = float(np.percentile(seg_rms, 90))
        if seg_p90 >= p90 or (seg_p90 >= p50 * 1.35 and seg_p90 >= p50 + 1e-9):
            regions.append(
                {
                    "segment_id": sid,
                    "emphasis_score": round(min(1.0, seg_p90 / max(p90, 1e-9)), 3),
                    "note": "acoustic emphasis peak in segment",
                }
            )

    regions.sort(key=lambda r: r.get("emphasis_score", 0), reverse=True)
    return regions[:max_regions]


def quotability_signals(ctx: RunContext, *, max_signals: int = 30) -> list[dict[str, Any]]:
    """H-F2-02: paralinguistic × text quotability proxy per segment."""
    segments = _load_segments(ctx)
    packed = _energy_windows(ctx)
    if not segments:
        return []

    rms_global_p90 = 0.0
    times_ms: np.ndarray | None = None
    rms: np.ndarray | None = None
    if packed is not None:
        rms, times_ms, _ = packed
        rms_global_p90 = float(np.percentile(rms, 90)) if rms.size else 0.0

    signals: list[dict[str, Any]] = []
    for seg in segments:
        sid = str(seg.get("segment_id") or seg.get("id") or "")
        text = str(seg.get("text") or "").strip()
        if not sid or not text:
            continue
        words = text.split()
        word_count = len(words)
        question_boost = 0.15 if "?" in text else 0.0
        length_score = min(1.0, word_count / 80.0)
        energy_score = 0.0
        start_ms = seg.get("start_ms")
        end_ms = seg.get("end_ms")
        if rms is not None and times_ms is not None and start_ms is not None and end_ms is not None:
            mask = (times_ms >= float(start_ms)) & (times_ms <= float(end_ms))
            if np.any(mask):
                seg_p90 = float(np.percentile(rms[mask], 90))
                energy_score = min(1.0, seg_p90 / max(rms_global_p90, 1e-9)) * 0.5
        quotability = round(min(1.0, length_score * 0.45 + energy_score + question_boost), 3)
        signals.append({"segment_id": sid, "quotability_score": quotability})

    signals.sort(key=lambda s: s.get("quotability_score", 0), reverse=True)
    return signals[:max_signals]


def quality_trajectory_flags(ctx: RunContext, *, window_count: int = 12) -> list[dict[str, Any]]:
    """H-ING-03: trust-dip flags from sliding RMS dips (NISQA-class proxy)."""
    packed = _energy_windows(ctx)
    if packed is None:
        return []

    rms, times_ms, _peak = packed
    if len(rms) < window_count:
        return []

    chunk = max(1, len(rms) // window_count)
    flags: list[dict[str, Any]] = []
    baseline = float(np.percentile(rms, 60))
    for i in range(0, len(rms), chunk):
        window = rms[i : i + chunk]
        if window.size == 0:
            continue
        local_p50 = float(np.percentile(window, 50))
        if local_p50 < baseline * 0.55:
            t_ms = int(times_ms[min(i, len(times_ms) - 1)])
            flags.append(
                {
                    "start_ms": t_ms,
                    "dip_ratio": round(local_p50 / max(baseline, 1e-9), 3),
                    "note": f"Trust dip proxy at ~{t_ms // 1000}s — review transcript/audio alignment",
                }
            )
    return flags[:8]


def communicative_salience_score(chunk: dict[str, Any]) -> float:
    """H-G0-01: rank review chunks by communicative salience, not confidence alone."""
    confidence = float(chunk.get("confidence") or 1.0)
    low_conf = max(0.0, 1.0 - confidence)
    word_count = len(str(chunk.get("text") or "").split())
    density = min(1.0, word_count / 40.0)
    duration_ms = max(1.0, float(chunk.get("end_ms", 0)) - float(chunk.get("start_ms", 0)))
    pause_proxy = min(1.0, duration_ms / 8000.0)
    return round(low_conf * 0.55 + density * 0.25 + pause_proxy * 0.2, 4)


def compact_value_features_summary(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(VALUE_FEATURES_PATH):
        return None
    data = ctx.read_json(VALUE_FEATURES_PATH)
    if not isinstance(data, dict):
        return None
    profiles = data.get("profiles") or {}
    if not isinstance(profiles, dict):
        return None
    out: dict[str, Any] = {}
    transcript = profiles.get("transcript")
    if isinstance(transcript, dict):
        out["transcript_tags"] = transcript.get("tags")
        out["quality_trajectory_flags"] = transcript.get("quality_trajectory_flags")
    audio = profiles.get("audio")
    if isinstance(audio, dict):
        out["silence_ratio"] = audio.get("silence_ratio")
        out["rms_p90"] = audio.get("rms_p90")
    return out or None
