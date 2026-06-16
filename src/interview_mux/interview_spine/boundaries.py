from __future__ import annotations

from typing import Any

import numpy as np

from interview_mux.audio_energy import energy_windows_from_path

_PAUSE_LADDER_MS = (400, 700, 1200)


def build_boundary_events(
    *,
    words: list[dict[str, Any]],
    windows: list[dict[str, Any]],
    wav_path,
    segments: list[dict[str, Any]] | None = None,
    min_sources: int = 1,
) -> list[dict[str, Any]]:
    """Fuse silence, pause ladder, speaker turns, trust dips, prosody shifts."""
    from pathlib import Path

    path = Path(wav_path)
    events: list[dict[str, Any]] = []

    events.extend(_pause_ladder_events(words))
    events.extend(_speaker_turn_events(segments or []))
    events.extend(_silence_valley_events(path))
    events.extend(_trust_dip_events(path))
    events.extend(_prosody_shift_events(windows))
    from interview_mux.coherence.config import replace_stub_topic_shift_hints

    if not replace_stub_topic_shift_hints():
        events.extend(_topic_shift_hint_events(words))

    return _merge_nearby_events(events, min_sources=min_sources)


def _pause_ladder_events(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(words) < 2:
        return []
    out: list[dict[str, Any]] = []
    sorted_words = sorted(words, key=lambda w: float(w.get("start_ms", 0)))
    for threshold in _PAUSE_LADDER_MS:
        for i in range(1, len(sorted_words)):
            gap = float(sorted_words[i]["start_ms"]) - float(sorted_words[i - 1]["end_ms"])
            if gap >= threshold:
                out.append(
                    {
                        "time_ms": int(sorted_words[i]["start_ms"]),
                        "type": "pause_ladder",
                        "confidence": min(1.0, gap / max(threshold, 1)),
                        "sources": [f"pause_ladder_{threshold}ms"],
                        "window_ids": [],
                    }
                )
                break
    return out


def _speaker_turn_events(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in segments:
        start_ms = int(float(seg.get("start_time", 0)) * 1000)
        out.append(
            {
                "time_ms": start_ms,
                "type": "speaker_turn",
                "confidence": 0.75,
                "sources": ["aws_diarization"],
                "window_ids": [],
            }
        )
    return out


def _silence_valley_events(wav_path) -> list[dict[str, Any]]:
    packed = energy_windows_from_path(wav_path)
    if packed is None:
        return []
    rms, times_ms, _peak = packed
    baseline = float(np.percentile(rms, 50)) if rms.size else 0.0
    if baseline <= 0:
        return []
    out: list[dict[str, Any]] = []
    for i in range(1, len(rms) - 1):
        if rms[i] < baseline * 0.4 and rms[i] <= rms[i - 1] and rms[i] <= rms[i + 1]:
            out.append(
                {
                    "time_ms": int(times_ms[i]),
                    "type": "silence_valley",
                    "confidence": round(min(1.0, (baseline - rms[i]) / baseline), 3),
                    "sources": ["rms_vad"],
                    "window_ids": [],
                }
            )
    return out[:40]


def _trust_dip_events(wav_path) -> list[dict[str, Any]]:
    packed = energy_windows_from_path(wav_path)
    if packed is None:
        return []
    rms, times_ms, _peak = packed
    if len(rms) < 8:
        return []
    chunk = max(1, len(rms) // 12)
    baseline = float(np.percentile(rms, 60))
    out: list[dict[str, Any]] = []
    for i in range(0, len(rms), chunk):
        window = rms[i : i + chunk]
        if window.size == 0:
            continue
        local_p50 = float(np.percentile(window, 50))
        if local_p50 < baseline * 0.55:
            t_ms = int(times_ms[min(i, len(times_ms) - 1)])
            out.append(
                {
                    "time_ms": t_ms,
                    "type": "trust_dip",
                    "confidence": round(min(1.0, (baseline - local_p50) / max(baseline, 1e-9)), 3),
                    "sources": ["quality_trajectory"],
                    "window_ids": [],
                }
            )
    return out[:8]


def _prosody_shift_events(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    prev_band: str | None = None
    for win in windows:
        f0 = win.get("features", {}).get("f0_median_hz")
        if f0 is None:
            continue
        band = "low" if f0 < 120 else ("high" if f0 > 220 else "mid")
        if prev_band and band != prev_band:
            out.append(
                {
                    "time_ms": int(win["start_ms"]),
                    "type": "prosody_shift",
                    "confidence": 0.6,
                    "sources": ["f0_band_change"],
                    "window_ids": [win["window_id"]],
                }
            )
        prev_band = band
    return out


def _topic_shift_hint_events(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(words) < 2:
        return []
    out: list[dict[str, Any]] = []
    sorted_words = sorted(words, key=lambda w: float(w.get("start_ms", 0)))
    for i in range(1, len(sorted_words)):
        prev = sorted_words[i - 1]
        cur = sorted_words[i]
        if prev.get("speaker_id") == cur.get("speaker_id"):
            continue
        gap = float(cur["start_ms"]) - float(prev["end_ms"])
        if gap >= 700:
            out.append(
                {
                    "time_ms": int(cur["start_ms"]),
                    "type": "topic_shift_hint",
                    "confidence": round(min(1.0, gap / 1200.0), 3),
                    "sources": ["speaker_turn_pause"],
                    "window_ids": [],
                }
            )
    return out[:20]


def _merge_nearby_events(events: list[dict[str, Any]], *, min_sources: int = 1) -> list[dict[str, Any]]:
    if not events:
        return []
    events.sort(key=lambda e: (e["time_ms"], e["type"]))
    merged: list[dict[str, Any]] = []
    for ev in events:
        if merged and abs(ev["time_ms"] - merged[-1]["time_ms"]) <= 300:
            prev = merged[-1]
            prev_sources = set(prev.get("sources") or [])
            prev_sources.update(ev.get("sources") or [])
            prev["sources"] = sorted(prev_sources)
            prev["confidence"] = round(
                min(1.0, max(float(prev.get("confidence") or 0), float(ev.get("confidence") or 0))),
                3,
            )
            if ev.get("type") != prev.get("type"):
                prev["type"] = ev["type"]
            continue
        merged.append(dict(ev))
    if min_sources > 1:
        merged = [e for e in merged if len(e.get("sources") or []) >= min_sources]
    return merged[:80]
