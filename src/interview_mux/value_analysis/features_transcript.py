from __future__ import annotations

import statistics
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.value_analysis.config import require_value_analysis_flag

VALUE_FEATURES_PATH = "understanding/value_features.json"

_INTERVIEWER_ALIASES = frozenset({"interviewer", "host", "moderator"})


def _load_transcript(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists("transcript/full.json"):
        data = ctx.read_json("transcript/full.json")
        if isinstance(data, dict):
            return data
    return {}


def _load_segments(ctx: RunContext, transcript: dict[str, Any]) -> list[dict[str, Any]]:
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        if isinstance(manifest, dict):
            return [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]

    raw = transcript.get("segments") or []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        start_ms = item.get("start_ms")
        end_ms = item.get("end_ms")
        if start_ms is None and item.get("start_time") is not None:
            start_ms = int(float(item["start_time"]) * 1000)
        if end_ms is None and item.get("end_time") is not None:
            end_ms = int(float(item["end_time"]) * 1000)
        out.append({**item, "start_ms": start_ms, "end_ms": end_ms})
    return out


def _speaker_role_map(ctx: RunContext) -> dict[str, str]:
    for rel in ("understanding/speakers.json", "transcript/speakers.json"):
        if not ctx.artifact_exists(rel):
            continue
        data = ctx.read_json(rel)
        if not isinstance(data, dict):
            continue
        roles: dict[str, str] = {}
        for row in data.get("speakers") or []:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("speaker_id", "")).strip()
            if sid:
                roles[sid] = str(row.get("role", "unknown")).lower()
        if roles:
            return roles
    return {}


def _is_interviewer(speaker_key: str, role_map: dict[str, str]) -> bool:
    key = speaker_key.strip().lower()
    if not key:
        return False
    role = role_map.get(speaker_key, role_map.get(key, "")).lower()
    if role in _INTERVIEWER_ALIASES:
        return True
    return key in _INTERVIEWER_ALIASES


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    return int(statistics.quantiles(values, n=100)[int(pct) - 1])


def extract_transcript_features(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    require_value_analysis_flag(cfg, "transcript_features")

    transcript = _load_transcript(ctx)
    words = [w for w in (transcript.get("words") or []) if isinstance(w, dict)]
    segments = _load_segments(ctx, transcript)
    role_map = _speaker_role_map(ctx)

    pauses_ms: list[float] = []
    for i in range(1, len(words)):
        gap = float(words[i].get("start_ms", 0)) - float(words[i - 1].get("end_ms", 0))
        if gap > 0:
            pauses_ms.append(gap)

    total_ms = max(float(words[-1].get("end_ms", 0)), 1.0) if words else 0.0
    word_count = len(words)
    wpm = (word_count / (total_ms / 60000.0)) if total_ms > 0 else 0.0

    seg_lengths = [
        len(str(seg.get("text", "")).split())
        for seg in segments
        if seg.get("text")
    ]

    interviewer_turns = 0
    for seg in segments:
        speaker = str(
            seg.get("speaker_id")
            or seg.get("speaker_label")
            or seg.get("speaker")
            or ""
        )
        if _is_interviewer(speaker, role_map):
            interviewer_turns += 1
    if segments:
        interviewer_ratio = interviewer_turns / len(segments)
    else:
        interviewer_words = sum(
            1
            for w in words
            if _is_interviewer(
                str(w.get("speaker_id", w.get("speaker_label", ""))),
                role_map,
            )
            or str(w.get("speaker_role", "")).lower() in _INTERVIEWER_ALIASES
        )
        interviewer_ratio = interviewer_words / word_count if word_count else 0.0

    median_pause = statistics.median(pauses_ms) if pauses_ms else 0.0
    p50_seg = int(statistics.median(seg_lengths)) if seg_lengths else 0
    p90_seg = _percentile(sorted(seg_lengths), 90)

    tags: dict[str, list[str]] = {"LEX": [], "COM": [], "CRE": []}
    if wpm < 110:
        tags["LEX"].append("slow_pacing")
    if median_pause > 800:
        tags["LEX"].append("long_pauses")
    if p90_seg > 120:
        tags["COM"].append("long_segments")
    if interviewer_ratio > 0.45:
        tags["CRE"].append("interviewer_heavy")

    return {
        "profile": "transcript",
        "words_per_minute_proxy": round(wpm, 2),
        "median_pause_ms": round(median_pause, 1),
        "segment_count": len(segments),
        "segment_length_p50": p50_seg,
        "segment_length_p90": p90_seg,
        "interviewer_turn_ratio": round(interviewer_ratio, 3),
        "tags": tags,
    }
