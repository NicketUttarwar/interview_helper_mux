"""Lightweight stage-input signals from transcript/audio artifacts (spike winners, no new ML deps)."""

from __future__ import annotations

from typing import Any, TypedDict

import numpy as np

from interview_mux.audio_energy import energy_windows_from_path
from interview_mux.boundary_observability import ladder_guidance_for_pace, pace_class_from_sap
from interview_mux.interview_spine.constants import PAUSE_LADDER_MS
from interview_mux.run_context import RunContext

VALUE_FEATURES_PATH = "understanding/value_features.json"


class PauseLadderCandidate(TypedDict):
    threshold_ms: int
    split_times_ms: list[int]
    count: int


class PauseLadderHints(TypedDict, total=False):
    thresholds_ms: list[int]
    candidates: list[PauseLadderCandidate]
    pace_class: str
    ladder_guidance: str


_WINDOW_SEC = 0.4
_SILENCE_DBFS = -45.0

# H-ING-03 — shared with interview_spine/boundaries.py via stage_enrichment helpers
TRUST_DIP_BASELINE_PERCENTILE = 60
TRUST_DIP_THRESHOLD_RATIO = 0.55
TRUST_DIP_MAX_FLAGS = 8
TRUST_DIP_WINDOW_COUNT = 12
TRUST_DIP_MIN_DIP_RATIO_FOR_COMPREHENSION = 0.35
TRUST_DIP_CORROBORATION_WINDOW_MS = 2500
TRUST_DIP_LOW_CONF_THRESHOLD = 0.75


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


def pause_ladder_hints_from_words(
    words: list[dict[str, Any]],
    *,
    pace_class: str = "conversational",
) -> PauseLadderHints:
    """H-SEG-02: candidate boundary times at multiple pause thresholds (word-gap ladder)."""
    if len(words) < 2:
        return {
            "thresholds_ms": list(PAUSE_LADDER_MS),
            "candidates": [],
            "pace_class": pace_class,
            "ladder_guidance": ladder_guidance_for_pace(pace_class),
        }

    candidates: list[PauseLadderCandidate] = []
    for threshold in PAUSE_LADDER_MS:
        hits: list[int] = []
        for i in range(1, len(words)):
            prev = words[i - 1]
            cur = words[i]
            if prev.get("end_ms") is None or cur.get("start_ms") is None:
                continue
            gap = float(cur["start_ms"]) - float(prev["end_ms"])
            if gap >= threshold:
                hits.append(int(cur["start_ms"]))
        candidates.append(
            {
                "threshold_ms": threshold,
                "split_times_ms": hits[:40],
                "count": len(hits),
            }
        )
    return {
        "thresholds_ms": list(PAUSE_LADDER_MS),
        "candidates": candidates,
        "pace_class": pace_class,
        "ladder_guidance": ladder_guidance_for_pace(pace_class),
    }


def thin_pause_ladder_hints(
    hints: PauseLadderHints,
    pace_class: str,
    *,
    ctx: RunContext | None = None,
) -> PauseLadderHints:
    """Cap split_times_ms for LLM input while preserving full counts for observability."""
    from interview_mux.segment_timeline_standard import is_fine_granularity

    out: PauseLadderHints = dict(hints)
    candidates = list(hints.get("candidates") or [])
    out["pre_thin_candidates"] = candidates
    fine = is_fine_granularity()
    oversplit = any(
        int(c.get("threshold_ms") or 0) == PAUSE_LADDER_MS[0]
        and int(c.get("count") or 0) > 50
        for c in candidates
        if isinstance(c, dict)
    )
    if not fine and (oversplit or pace_class == "calm"):
        out["preferred_tiers"] = [700, 1200]
    elif fine:
        out["preferred_tiers"] = list(PAUSE_LADDER_MS)
    thinned: list[PauseLadderCandidate] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        row = dict(c)
        splits = list(row.get("split_times_ms") or [])
        row["split_times_ms"] = splits[:40]
        thinned.append(row)  # type: ignore[arg-type]
    out["candidates"] = thinned
    return out


def pause_ladder_hints(ctx: RunContext) -> PauseLadderHints:
    """H-SEG-02: candidate boundary times at multiple pause thresholds."""
    pace_class = pace_class_from_sap(ctx)
    return pause_ladder_hints_from_words(_load_words(ctx), pace_class=pace_class)


def _energy_windows(ctx: RunContext) -> tuple[np.ndarray, np.ndarray, float] | None:
    return energy_windows_from_path(ctx.read_path("ingest", "normalized.wav"), window_sec=_WINDOW_SEC)


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
        seg_median = float(np.percentile(seg_rms, 50))
        # H-F1N-02: segment-relative peak vs segment median (not global noise floor alone).
        # Global p90 gate: local peak must meet or exceed interview-wide p90 when present.
        if seg_p90 >= seg_median * 1.35 and (seg_p90 >= p90 or seg_p90 >= p50 * 1.2):
            regions.append(
                {
                    "segment_id": sid,
                    "emphasis_score": round(min(1.0, seg_p90 / max(p90, 1e-9)), 3),
                    "note": "acoustic emphasis peak in segment",
                }
            )

    regions.sort(key=lambda r: r.get("emphasis_score", 0), reverse=True)
    return regions[:max_regions]


def _spine_quotability_boost(
    ctx: RunContext,
    start_ms: Any,
    end_ms: Any,
) -> float:
    from interview_mux.interview_spine import SPINE_PATH
    from interview_mux.interview_spine.config import spine_flow2_quotability_enabled

    if not spine_flow2_quotability_enabled() or start_ms is None or end_ms is None:
        return 0.0
    if not ctx.artifact_exists(SPINE_PATH):
        return 0.0
    spine = ctx.read_json(SPINE_PATH)
    if not isinstance(spine, dict):
        return 0.0
    boost = 0.0
    for event in spine.get("boundary_events") or []:
        if not isinstance(event, dict):
            continue
        if event.get("type") not in ("trust_dip", "prosody_shift", "novelty_hint"):
            continue
        time_ms = int(event.get("time_ms") or 0)
        if float(start_ms) <= time_ms <= float(end_ms):
            boost = max(boost, min(0.12, float(event.get("confidence") or 0.5) * 0.12))
    return boost


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
        spine_boost = _spine_quotability_boost(ctx, start_ms, end_ms)
        quotability = round(
            min(1.0, length_score * 0.45 + energy_score + question_boost + spine_boost),
            3,
        )
        signals.append({"segment_id": sid, "quotability_score": quotability})

    signals.sort(key=lambda s: s.get("quotability_score", 0), reverse=True)
    return signals[:max_signals]


def compute_trust_dip_flags(
    rms: np.ndarray,
    times_ms: np.ndarray,
    *,
    window_count: int = TRUST_DIP_WINDOW_COUNT,
    max_flags: int = TRUST_DIP_MAX_FLAGS,
) -> list[dict[str, Any]]:
    """Deterministic trust-dip windows from RMS arrays (shared spine + value_features path)."""
    if len(rms) < window_count:
        return []

    chunk = max(1, len(rms) // window_count)
    flags: list[dict[str, Any]] = []
    baseline = float(np.percentile(rms, TRUST_DIP_BASELINE_PERCENTILE))
    for i in range(0, len(rms), chunk):
        window = rms[i : i + chunk]
        if window.size == 0:
            continue
        local_p50 = float(np.percentile(window, 50))
        if local_p50 < baseline * TRUST_DIP_THRESHOLD_RATIO:
            t_ms = int(times_ms[min(i, len(times_ms) - 1)])
            flags.append(
                {
                    "start_ms": t_ms,
                    "dip_ratio": round(local_p50 / max(baseline, 1e-9), 3),
                    "note": f"Trust dip proxy at ~{t_ms // 1000}s — review transcript/audio alignment",
                }
            )
    return flags[:max_flags]


def low_confidence_near_ms(
    ctx: RunContext,
    time_ms: int,
    *,
    window_ms: int = TRUST_DIP_CORROBORATION_WINDOW_MS,
    threshold: float = TRUST_DIP_LOW_CONF_THRESHOLD,
) -> bool:
    """True when transcript words near time_ms have ASR confidence below threshold."""
    for word in _load_words(ctx):
        if abs(int(word.get("start_ms", 0)) - time_ms) <= window_ms:
            if float(word.get("confidence") or 1.0) < threshold:
                return True
    return False


def acoustic_stress_near_ms(
    ctx: RunContext,
    time_ms: int,
    *,
    window_ms: int = TRUST_DIP_CORROBORATION_WINDOW_MS,
    min_stress: float = 0.25,
) -> bool:
    """H-G0-02 corroboration: review chunk with acoustic stress overlapping time_ms."""
    if not ctx.artifact_exists("transcript/review_queue.json"):
        return False
    queue = ctx.read_json("transcript/review_queue.json")
    for chunk in queue.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        start_ms = int(chunk.get("start_ms") or 0)
        end_ms = int(chunk.get("end_ms") or 0)
        if start_ms - window_ms <= time_ms <= end_ms + window_ms:
            if float(chunk.get("acoustic_stress_score") or 0.0) >= min_stress:
                return True
    return False


def trust_dip_corroborated(ctx: RunContext, time_ms: int, *, dip_ratio: float | None = None) -> bool:
    """Require severe dip ratio plus G0 stress or low-confidence words before downstream risk flags."""
    if dip_ratio is not None and dip_ratio > TRUST_DIP_MIN_DIP_RATIO_FOR_COMPREHENSION:
        return False
    return low_confidence_near_ms(ctx, time_ms) or acoustic_stress_near_ms(ctx, time_ms)


def quality_trajectory_flags(ctx: RunContext, *, window_count: int = TRUST_DIP_WINDOW_COUNT) -> list[dict[str, Any]]:
    """H-ING-03: trust-dip flags from sliding RMS dips (NISQA-class proxy)."""
    packed = _energy_windows(ctx)
    if packed is None:
        return []

    rms, times_ms, _peak = packed
    return compute_trust_dip_flags(rms, times_ms, window_count=window_count)


def communicative_salience_score(chunk: dict[str, Any]) -> float:
    """H-G0-01: rank review chunks by communicative salience, not confidence alone."""
    confidence = float(chunk.get("confidence") or 1.0)
    low_conf = max(0.0, 1.0 - confidence)
    word_count = len(str(chunk.get("text") or "").split())
    density = min(1.0, word_count / 40.0)
    duration_ms = max(1.0, float(chunk.get("end_ms", 0)) - float(chunk.get("start_ms", 0)))
    pause_proxy = min(1.0, duration_ms / 8000.0)
    stress = float(chunk.get("acoustic_stress_score") or 0.0)
    return round(
        low_conf * 0.45 + density * 0.2 + pause_proxy * 0.15 + stress * 0.2,
        4,
    )


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
