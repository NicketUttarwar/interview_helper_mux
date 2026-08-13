"""High-value speech islands: volume-gated STT-skip + multi low-conf clusters.

Detects passionate / other-language / domain bursts where STT is sparse or low-conf
but the speaker is clearly present (near-average volume). These islands are never
standalone keepers — fuse + hard must_keep happen downstream.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

HV_ISLANDS_PATH = "analysis/high_value_speech_islands.json"
HV_BOOSTS_PATH = "analysis/high_value_speech_boosts.json"

_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "min_gap_ms": 2000,
    "min_cluster_ms": 1500,
    "min_cluster_words": 3,
    "min_island_ms": 1200,
    "max_island_ms": 20000,
    "level_ratio_min": 0.55,
    "level_ratio_max": 1.45,
    "speech_rms_floor_ratio": 0.35,
    "ranking_boost": 0.85,
    "importance_score": 0.92,
    # Flow-preserving multi-cluster join/separate (connector fuse).
    "cluster_join_max_gap_ms": 8000,
    "flow_break_min_high_conf_ms": 12000,
    "flow_break_min_high_conf_segments": 1,
    "multi_cluster_min_islands": 2,
    "max_island_cluster_rounds": 32,
    "per_cluster_fuse": True,
    "island_cluster_structure": {
        "llm_tier": "economy",
        "fail_open_deterministic": True,
        "lock_forced_seams": True,
        "max_block_chars": 48000,
    },
}

CLUSTERS_PATH = "analysis/high_value_island_clusters.json"


def high_value_speech_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = cfg if cfg is not None else merged_config()
    analysis = resolved.get("analysis") if isinstance(resolved.get("analysis"), dict) else {}
    block = (
        analysis.get("high_value_speech_islands")
        if isinstance(analysis.get("high_value_speech_islands"), dict)
        else {}
    )
    return {**_DEFAULTS, **block}


def enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(high_value_speech_cfg(cfg).get("enabled", True))


def _ms(row: dict[str, Any], key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _token(w: dict[str, Any]) -> str:
    return str(w.get("text") or w.get("word") or "").strip()


def _load_words(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("transcript/full.json"):
        return []
    try:
        tr = ctx.read_json("transcript/full.json")
    except Exception:
        return []
    if not isinstance(tr, dict):
        return []
    words = [w for w in (tr.get("words") or []) if isinstance(w, dict) and _token(w)]
    words.sort(key=lambda w: (_ms(w, "start_ms"), _ms(w, "end_ms")))
    return words


def _resolve_wav(ctx: RunContext) -> Path | None:
    for keys in (("ingest", "normalized.wav"), ("ingest", "source.wav")):
        try:
            path = ctx.read_path(*keys)
        except Exception:
            path = None
        if path and Path(path).is_file():
            return Path(path)
    return None


def _energy_stats(
    wav_path: Path | None,
) -> tuple[Any, Any, float] | None:
    """Return (rms_array, times_ms_array, median_rms) or None."""
    if wav_path is None or not wav_path.is_file():
        return None
    try:
        import numpy as np

        from interview_mux.audio_energy import energy_windows_from_path

        packed = energy_windows_from_path(wav_path)
        if packed is None:
            return None
        rms, times_ms, _peak = packed
        if rms is None or len(rms) == 0:
            return None
        positive = rms[rms > 0]
        if positive.size == 0:
            return None
        median = float(np.median(positive))
        if median <= 0:
            return None
        return rms, times_ms, median
    except Exception:
        return None


def _span_mean_rms(
    energy: tuple[Any, Any, float] | None,
    start_ms: int,
    end_ms: int,
) -> float | None:
    if energy is None or end_ms <= start_ms:
        return None
    rms, times_ms, _median = energy
    try:
        import numpy as np

        mask = (times_ms >= start_ms) & (times_ms <= end_ms)
        if not np.any(mask):
            # widen slightly for short windows
            pad = max(200, (end_ms - start_ms) // 4)
            mask = (times_ms >= start_ms - pad) & (times_ms <= end_ms + pad)
        if not np.any(mask):
            return None
        return float(np.mean(rms[mask]))
    except Exception:
        return None


def _passes_volume_gate(
    span_rms: float | None,
    median_rms: float | None,
    *,
    conf: dict[str, Any],
) -> tuple[bool, float | None]:
    if span_rms is None or median_rms is None or median_rms <= 0:
        return False, None
    ratio = float(span_rms) / float(median_rms)
    floor = float(conf.get("speech_rms_floor_ratio") or 0.35)
    lo = float(conf.get("level_ratio_min") or 0.55)
    hi = float(conf.get("level_ratio_max") or 1.45)
    if ratio < floor:
        return False, ratio
    if ratio < lo or ratio > hi:
        return False, ratio
    return True, ratio


def _merge_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (_ms(s, "start_ms"), _ms(s, "end_ms")))
    out: list[dict[str, Any]] = [dict(ordered[0])]
    for row in ordered[1:]:
        prev = out[-1]
        if _ms(row, "start_ms") <= _ms(prev, "end_ms") + 250:
            prev["end_ms"] = max(_ms(prev, "end_ms"), _ms(row, "end_ms"))
            prev["word_count"] = int(prev.get("word_count") or 0) + int(
                row.get("word_count") or 0
            )
            kinds = list(
                dict.fromkeys(
                    [
                        *(prev.get("kinds") or [prev.get("kind")]),
                        *(row.get("kinds") or [row.get("kind")]),
                    ]
                )
            )
            prev["kinds"] = [k for k in kinds if k]
            prev["kind"] = prev["kinds"][-1] if prev["kinds"] else prev.get("kind")
            reasons = list(
                dict.fromkeys(
                    [
                        *(prev.get("suspect_reasons") or [prev.get("suspect_reason")]),
                        *(row.get("suspect_reasons") or [row.get("suspect_reason")]),
                    ]
                )
            )
            prev["suspect_reasons"] = [r for r in reasons if r]
            prev["suspect_reason"] = "+".join(prev["suspect_reasons"][:3])
            # Prefer the stronger (closer to 1.0) level ratio when merging.
            for key in ("mean_rms", "level_ratio"):
                a = prev.get(key)
                b = row.get(key)
                if a is None:
                    prev[key] = b
                elif b is not None and key == "level_ratio":
                    if abs(float(b) - 1.0) < abs(float(a) - 1.0):
                        prev[key] = b
        else:
            out.append(dict(row))
    return out


def _find_stt_skip_energy_spans(
    words: list[dict[str, Any]],
    energy: tuple[Any, Any, float] | None,
    *,
    conf: dict[str, Any],
) -> list[dict[str, Any]]:
    if energy is None or len(words) < 2:
        return []
    _rms, _times, median = energy
    min_gap = int(conf.get("min_gap_ms") or 2000)
    min_island = int(conf.get("min_island_ms") or 1200)
    max_island = int(conf.get("max_island_ms") or 20000)
    out: list[dict[str, Any]] = []
    for i in range(len(words) - 1):
        a_end = _ms(words[i], "end_ms") or _ms(words[i], "start_ms")
        b_start = _ms(words[i + 1], "start_ms")
        gap = b_start - a_end
        if gap < min_gap:
            continue
        # Clip to max island length centered on the gap if huge.
        start = a_end
        end = b_start
        if end - start > max_island:
            mid = (start + end) // 2
            start = mid - max_island // 2
            end = start + max_island
        if end - start < min_island:
            continue
        span_rms = _span_mean_rms(energy, start, end)
        ok, ratio = _passes_volume_gate(span_rms, median, conf=conf)
        if not ok:
            continue
        out.append(
            {
                "kind": "stt_skip_energy",
                "kinds": ["stt_skip_energy"],
                "start_ms": int(start),
                "end_ms": int(end),
                "duration_ms": int(end - start),
                "word_count": 0,
                "mean_rms": span_rms,
                "level_ratio": ratio,
                "suspect_reason": "speech_energy_without_words",
                "suspect_reasons": ["speech_energy_without_words"],
            }
        )
    return out


def _find_low_conf_cluster_spans(
    low_conf_doc: dict[str, Any] | None,
    energy: tuple[Any, Any, float] | None,
    *,
    conf: dict[str, Any],
) -> list[dict[str, Any]]:
    islands = [
        i
        for i in ((low_conf_doc or {}).get("islands") or [])
        if isinstance(i, dict) and i.get("failure_mode") != "noise"
    ]
    if not islands:
        return []
    min_words = int(conf.get("min_cluster_words") or 3)
    min_cluster_ms = int(conf.get("min_cluster_ms") or 1500)
    min_island = int(conf.get("min_island_ms") or 1200)
    max_island = int(conf.get("max_island_ms") or 20000)
    median = energy[2] if energy is not None else None
    out: list[dict[str, Any]] = []
    for island in islands:
        start = _ms(island, "start_ms")
        end = _ms(island, "end_ms")
        dur = max(0, end - start)
        words_n = int(island.get("word_count") or island.get("n_words") or 0)
        if words_n < min_words and dur < min_cluster_ms:
            continue
        if dur < min_island or dur > max_island:
            continue
        span_rms = _span_mean_rms(energy, start, end) if energy is not None else None
        if energy is not None:
            ok, ratio = _passes_volume_gate(span_rms, median, conf=conf)
            if not ok:
                continue
        else:
            # Without wav we cannot volume-gate — skip (volume gate required).
            continue
        out.append(
            {
                "kind": "low_conf_cluster",
                "kinds": ["low_conf_cluster", str(island.get("cluster_kind") or "")],
                "start_ms": start,
                "end_ms": end,
                "duration_ms": dur,
                "word_count": words_n,
                "mean_rms": span_rms,
                "level_ratio": ratio,
                "suspect_reason": "low_conf_cluster_with_presence",
                "suspect_reasons": ["low_conf_cluster_with_presence"],
                "source_island_id": island.get("island_id"),
                "cluster_kind": island.get("cluster_kind"),
            }
        )
    return out


def _segment_ids_touched(
    ctx: RunContext, start_ms: int, end_ms: int
) -> list[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    try:
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return []
    if not isinstance(man, dict):
        return []
    hits: list[str] = []
    for seg in man.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        s0, s1 = _ms(seg, "start_ms"), _ms(seg, "end_ms")
        if s1 <= start_ms or s0 >= end_ms:
            continue
        sid = str(seg.get("segment_id") or "")
        if sid:
            hits.append(sid)
    return hits


def scan_high_value_speech_islands(
    ctx: RunContext,
    *,
    low_conf_islands: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
    wav_path: Path | str | None = None,
    energy_override: tuple[Any, Any, float] | None = None,
) -> dict[str, Any]:
    """Detect 0+ high-value islands; write ``analysis/high_value_speech_islands.json``."""
    conf = high_value_speech_cfg(cfg)
    empty = {
        "version": 1,
        "enabled": bool(conf.get("enabled", True)),
        "island_count": 0,
        "islands": [],
        "segment_ids_touched": [],
        "skip_reason": None,
    }
    if not conf.get("enabled", True):
        empty["skip_reason"] = "disabled"
        ctx.write_json(HV_ISLANDS_PATH, empty)
        return empty

    words = _load_words(ctx)
    path = Path(wav_path) if wav_path else _resolve_wav(ctx)
    energy = energy_override if energy_override is not None else _energy_stats(path)

    low_doc = low_conf_islands
    if low_doc is None and ctx.artifact_exists("analysis/low_conf_islands.json"):
        try:
            raw = ctx.read_json("analysis/low_conf_islands.json")
            low_doc = raw if isinstance(raw, dict) else None
        except Exception:
            low_doc = None

    spans = _merge_spans(
        [
            *_find_stt_skip_energy_spans(words, energy, conf=conf),
            *_find_low_conf_cluster_spans(low_doc, energy, conf=conf),
        ]
    )

    islands: list[dict[str, Any]] = []
    touched: list[str] = []
    for index, span in enumerate(spans):
        sids = _segment_ids_touched(ctx, _ms(span, "start_ms"), _ms(span, "end_ms"))
        row = {
            **span,
            "island_id": f"hvi_{index + 1:03d}",
            "segment_ids_touched": sids,
        }
        islands.append(row)
        touched.extend(sids)

    out = {
        "version": 1,
        "enabled": True,
        "island_count": len(islands),
        "islands": islands,
        "segment_ids_touched": list(dict.fromkeys(touched)),
        "detector": {
            "min_gap_ms": conf.get("min_gap_ms"),
            "min_cluster_ms": conf.get("min_cluster_ms"),
            "min_cluster_words": conf.get("min_cluster_words"),
            "level_ratio_min": conf.get("level_ratio_min"),
            "level_ratio_max": conf.get("level_ratio_max"),
            "wav": str(path) if path else None,
            "has_energy": energy is not None,
        },
        "skip_reason": None if energy is not None else "no_wav_energy",
    }
    ctx.write_json(HV_ISLANDS_PATH, out)
    write_high_value_boosts(ctx, out, cfg=conf)
    return out


def write_high_value_boosts(
    ctx: RunContext,
    islands_doc: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Strong ranking / pack boosts for segments touching high-value islands."""
    conf = cfg if isinstance(cfg, dict) else high_value_speech_cfg()
    boost = float(conf.get("ranking_boost") or 0.85)
    importance = float(conf.get("importance_score") or 0.92)
    priors: list[dict[str, Any]] = []
    for sid in islands_doc.get("segment_ids_touched") or []:
        sid_s = str(sid or "")
        if not sid_s:
            continue
        priors.append(
            {
                "segment_id": sid_s,
                "soft_boost": boost,
                "importance_score": importance,
                "source": "high_value_speech_island",
                "high_value_speech": True,
            }
        )
    out = {
        "version": 1,
        "mode": "high_value_prefer_include",
        "priors": priors,
    }
    ctx.write_json(HV_BOOSTS_PATH, out)
    # Also merge into lexicon boosts so ranking payload already reads them.
    path = "analysis/stt_lexicon_island_boosts.json"
    existing: dict[str, Any] = {"version": 1, "mode": "soft_prefer_include_only", "priors": []}
    if ctx.artifact_exists(path):
        try:
            loaded = ctx.read_json(path)
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            pass
    by_sid = {
        str(r.get("segment_id")): dict(r)
        for r in (existing.get("priors") or [])
        if isinstance(r, dict) and r.get("segment_id")
    }
    for row in priors:
        sid = str(row["segment_id"])
        prev = by_sid.get(sid)
        merged = {**(prev or {}), **row}
        # Keep the stronger boost.
        if prev is not None:
            merged["soft_boost"] = max(
                float(prev.get("soft_boost") or 0), float(row["soft_boost"])
            )
            merged["importance_score"] = max(
                float(prev.get("importance_score") or 0),
                float(row["importance_score"]),
            )
        by_sid[sid] = merged
    existing["priors"] = sorted(
        by_sid.values(), key=lambda r: float(r.get("soft_boost") or 0), reverse=True
    )
    existing["version"] = 1
    ctx.write_json(path, existing)
    return out


def load_high_value_islands(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(HV_ISLANDS_PATH):
        return {"version": 1, "islands": [], "island_count": 0, "segment_ids_touched": []}
    try:
        doc = ctx.read_json(HV_ISLANDS_PATH)
    except Exception:
        return {"version": 1, "islands": [], "island_count": 0, "segment_ids_touched": []}
    return doc if isinstance(doc, dict) else {"version": 1, "islands": []}


def high_value_must_keep_segment_ids(ctx: RunContext) -> set[str]:
    doc = load_high_value_islands(ctx)
    return {str(sid) for sid in (doc.get("segment_ids_touched") or []) if sid}


def authoritative_high_value_must_keep_ids(
    ctx: RunContext,
    *,
    cfg: dict[str, Any] | None = None,
) -> set[str]:
    if not enabled(cfg):
        return set()
    return high_value_must_keep_segment_ids(ctx)


def mark_segments_high_value(ctx: RunContext, segment_ids: set[str] | list[str]) -> int:
    """Stamp ``high_value_speech=true`` on manifest rows (interior islands)."""
    ids = {str(s) for s in segment_ids if s}
    if not ids or not ctx.artifact_exists("segments/manifest.json"):
        return 0
    try:
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return 0
    if not isinstance(man, dict):
        return 0
    changed = 0
    for seg in man.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = str(seg.get("segment_id") or "")
        if sid in ids and not seg.get("high_value_speech"):
            seg["high_value_speech"] = True
            seg["retention"] = "must_keep"
            changed += 1
    if changed:
        ctx.write_json("segments/manifest.json", man, stage_key="low_conf_island_scan")
    return changed


def _topic_overlap_tags(a: dict[str, Any], b: dict[str, Any]) -> float:
    ta = {str(t).casefold() for t in (a.get("topic_tags") or []) if t}
    tb = {str(t).casefold() for t in (b.get("topic_tags") or []) if t}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def _load_manifest_segments(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    try:
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return []
    segs = [
        s
        for s in ((man.get("segments") or []) if isinstance(man, dict) else [])
        if isinstance(s, dict) and s.get("segment_id")
    ]
    segs.sort(key=lambda s: (_ms(s, "start_ms"), str(s.get("segment_id"))))
    return segs


def _segments_between(
    segments: list[dict[str, Any]],
    *,
    after_ms: int,
    before_ms: int,
) -> list[dict[str, Any]]:
    """Segments whose span lies mostly between two island edges (intervening H)."""
    out: list[dict[str, Any]] = []
    for seg in segments:
        s0, s1 = _ms(seg, "start_ms"), _ms(seg, "end_ms")
        if s1 <= after_ms or s0 >= before_ms:
            continue
        # Prefer segments fully inside the gap; still count partials that aren't the islands.
        out.append(seg)
    return out


def _boundary_topic_shift(
    ctx: RunContext,
    *,
    after_ms: int,
    before_ms: int,
) -> bool:
    if not ctx.artifact_exists("segments/boundaries.json"):
        return False
    try:
        doc = ctx.read_json("segments/boundaries.json")
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    for row in doc.get("boundaries") or []:
        if not isinstance(row, dict):
            continue
        cut = _ms(row, "cut_ms") or _ms(row, "ms") or _ms(row, "time_ms")
        if cut < after_ms or cut > before_ms:
            continue
        reason = str(row.get("reason") or row.get("reason_code") or "").casefold()
        kind = str(row.get("kind") or row.get("boundary_kind") or "").casefold()
        if "topic" in reason or "topic" in kind or "chapter" in reason or "chapter" in kind:
            return True
        tags = row.get("tags") or row.get("signals") or []
        if isinstance(tags, list) and any(
            "topic" in str(t).casefold() or "chapter" in str(t).casefold() for t in tags
        ):
            return True
    return False


def _should_separate_islands(
    ctx: RunContext,
    left: dict[str, Any],
    right: dict[str, Any],
    segments: list[dict[str, Any]],
    *,
    conf: dict[str, Any],
) -> tuple[bool, str | None, list[str]]:
    """Return (separate, reason, hinge_segment_ids)."""
    left_end = _ms(left, "end_ms")
    right_start = _ms(right, "start_ms")
    gap = max(0, right_start - left_end)
    join_max = int(conf.get("cluster_join_max_gap_ms") or 8000)
    if gap > join_max:
        return True, "gap_over_join_max", []

    intervening = _segments_between(segments, after_ms=left_end, before_ms=right_start)
    # Exclude segments that heavily overlap either island.
    filtered: list[dict[str, Any]] = []
    for seg in intervening:
        s0, s1 = _ms(seg, "start_ms"), _ms(seg, "end_ms")
        overlap_left = min(s1, left_end) - max(s0, _ms(left, "start_ms"))
        overlap_right = min(s1, _ms(right, "end_ms")) - max(s0, right_start)
        if overlap_left > 0 and overlap_left >= 0.6 * max(1, s1 - s0):
            continue
        if overlap_right > 0 and overlap_right >= 0.6 * max(1, s1 - s0):
            continue
        filtered.append(seg)
    intervening = filtered
    hinge_ids = [str(s.get("segment_id")) for s in intervening if s.get("segment_id")]
    inter_ms = sum(max(0, _ms(s, "end_ms") - _ms(s, "start_ms")) for s in intervening)
    break_ms = int(conf.get("flow_break_min_high_conf_ms") or 12000)
    if inter_ms >= break_ms:
        return True, "long_high_conf_break", hinge_ids

    topic_floor = 0.15
    try:
        from interview_mux.segment_fuse import connector_fuse_cfg

        topic_floor = float(connector_fuse_cfg().get("same_topic_score_floor") or 0.15)
    except Exception:
        pass

    topic_change = False
    if intervening:
        # Compare topics of material immediately left of gap vs intervening, and intervening vs right.
        left_seg = None
        right_seg = None
        for seg in segments:
            if _ms(seg, "end_ms") <= left_end and (
                left_seg is None or _ms(seg, "end_ms") > _ms(left_seg, "end_ms")
            ):
                left_seg = seg
            if _ms(seg, "start_ms") >= right_start and (
                right_seg is None or _ms(seg, "start_ms") < _ms(right_seg, "start_ms")
            ):
                right_seg = seg
        mid = intervening[0]
        if left_seg is not None:
            score = _topic_overlap_tags(left_seg, mid)
            if score > 0 and score < topic_floor:
                topic_change = True
        if right_seg is not None:
            score = _topic_overlap_tags(mid, right_seg)
            if score > 0 and score < topic_floor:
                topic_change = True
        # Also left island-touching vs right island-touching via mid tags vs both sides.
        if left_seg is not None and right_seg is not None:
            lr = _topic_overlap_tags(left_seg, right_seg)
            if lr > 0 and lr < topic_floor:
                topic_change = True

    if _boundary_topic_shift(ctx, after_ms=left_end, before_ms=right_start):
        topic_change = True

    min_segs = int(conf.get("flow_break_min_high_conf_segments") or 1)
    if topic_change and len(intervening) >= min_segs:
        return True, "topic_subtopic_change", hinge_ids
    if topic_change and gap > 0:
        return True, "topic_subtopic_change", hinge_ids

    return False, None, []


def _default_hinge_attach(
    hinge_segs: list[dict[str, Any]],
    left: dict[str, Any],
    right: dict[str, Any],
    segments: list[dict[str, Any]],
) -> str:
    """Prefer attaching hinge to the side with higher topic overlap; else left."""
    if not hinge_segs:
        return "left"
    mid = hinge_segs[0]
    left_seg = None
    right_seg = None
    left_end = _ms(left, "end_ms")
    right_start = _ms(right, "start_ms")
    for seg in segments:
        if _ms(seg, "end_ms") <= left_end and (
            left_seg is None or _ms(seg, "end_ms") > _ms(left_seg, "end_ms")
        ):
            left_seg = seg
        if _ms(seg, "start_ms") >= right_start and (
            right_seg is None or _ms(seg, "start_ms") < _ms(right_seg, "start_ms")
        ):
            right_seg = seg
    left_score = _topic_overlap_tags(left_seg or {}, mid) if left_seg else 0.0
    right_score = _topic_overlap_tags(mid, right_seg or {}) if right_seg else 0.0
    if right_score > left_score + 1e-9:
        return "right"
    return "left"


def group_high_value_island_clusters(
    ctx: RunContext,
    *,
    cfg: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Group HV islands into flow-preserving clusters (simple vs multi)."""
    conf = high_value_speech_cfg(cfg)
    hv = load_high_value_islands(ctx)
    islands = [
        i
        for i in (hv.get("islands") or [])
        if isinstance(i, dict) and _ms(i, "end_ms") > _ms(i, "start_ms")
    ]
    islands.sort(key=lambda i: (_ms(i, "start_ms"), _ms(i, "end_ms")))
    segments = _load_manifest_segments(ctx)
    min_multi = int(conf.get("multi_cluster_min_islands") or 2)

    clusters: list[dict[str, Any]] = []
    if not islands:
        out = {
            "version": 1,
            "cluster_count": 0,
            "clusters": [],
            "config": {
                "cluster_join_max_gap_ms": conf.get("cluster_join_max_gap_ms"),
                "flow_break_min_high_conf_ms": conf.get("flow_break_min_high_conf_ms"),
                "flow_break_min_high_conf_segments": conf.get(
                    "flow_break_min_high_conf_segments"
                ),
                "multi_cluster_min_islands": min_multi,
            },
        }
        if write:
            ctx.write_json(CLUSTERS_PATH, out)
        return out

    current_members: list[dict[str, Any]] = [islands[0]]
    split_meta: list[dict[str, Any]] = []

    for nxt in islands[1:]:
        prev = current_members[-1]
        separate, reason, hinge_ids = _should_separate_islands(
            ctx, prev, nxt, segments, conf=conf
        )
        if separate:
            hinge_segs = [s for s in segments if str(s.get("segment_id")) in set(hinge_ids)]
            attach = _default_hinge_attach(hinge_segs, prev, nxt, segments)
            split_meta.append(
                {
                    "after_island_id": prev.get("island_id"),
                    "before_island_id": nxt.get("island_id"),
                    "separate_reason": reason,
                    "hinge_segment_ids": hinge_ids,
                    "hinge_attach": attach,
                }
            )
            clusters.append(_finalize_cluster(current_members, min_multi, segments))
            current_members = [nxt]
        else:
            current_members.append(nxt)
    clusters.append(_finalize_cluster(current_members, min_multi, segments))

    # Attach split metadata onto the cluster that ends at each split (left side).
    by_last = {c["member_island_ids"][-1]: c for c in clusters if c.get("member_island_ids")}
    for meta in split_meta:
        left = by_last.get(str(meta.get("after_island_id")))
        if left is not None:
            left["separate_reason_after"] = meta.get("separate_reason")
            left["hinge_segment_ids_after"] = meta.get("hinge_segment_ids") or []
            left["hinge_attach"] = meta.get("hinge_attach")
        # Mark right cluster's incoming hinge.
        for c in clusters:
            if c.get("member_island_ids") and c["member_island_ids"][0] == str(
                meta.get("before_island_id")
            ):
                c["separate_reason_before"] = meta.get("separate_reason")
                c["hinge_segment_ids_before"] = meta.get("hinge_segment_ids") or []
                if meta.get("hinge_attach") == "right":
                    c["hinge_attach"] = "right"
                    c["hinge_segment_ids"] = meta.get("hinge_segment_ids") or []
                break
        if left is not None and meta.get("hinge_attach") == "left":
            left["hinge_segment_ids"] = meta.get("hinge_segment_ids") or []

    for idx, c in enumerate(clusters):
        c["cluster_id"] = f"hvc_{idx + 1:03d}"

    out = {
        "version": 1,
        "cluster_count": len(clusters),
        "clusters": clusters,
        "splits": split_meta,
        "config": {
            "cluster_join_max_gap_ms": conf.get("cluster_join_max_gap_ms"),
            "flow_break_min_high_conf_ms": conf.get("flow_break_min_high_conf_ms"),
            "flow_break_min_high_conf_segments": conf.get(
                "flow_break_min_high_conf_segments"
            ),
            "multi_cluster_min_islands": min_multi,
        },
    }
    if write:
        ctx.write_json(CLUSTERS_PATH, out)
    return out


def _finalize_cluster(
    members: list[dict[str, Any]],
    min_multi: int,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    start = min(_ms(m, "start_ms") for m in members)
    end = max(_ms(m, "end_ms") for m in members)
    touched: list[str] = []
    for m in members:
        for sid in m.get("segment_ids_touched") or []:
            if sid and str(sid) not in touched:
                touched.append(str(sid))
    if not touched:
        for seg in segments:
            s0, s1 = _ms(seg, "start_ms"), _ms(seg, "end_ms")
            if s1 <= start or s0 >= end:
                continue
            sid = str(seg.get("segment_id") or "")
            if sid and sid not in touched:
                touched.append(sid)
    density = "multi" if len(members) >= min_multi else "simple"
    return {
        "member_island_ids": [str(m.get("island_id") or "") for m in members],
        "islands": members,
        "island_count": len(members),
        "density": density,
        "start_ms": start,
        "end_ms": end,
        "segment_ids_touched": touched,
        "hinge_segment_ids": [],
        "hinge_attach": None,
    }


def cluster_is_fuse_eligible(
    cluster: dict[str, Any],
    segments: list[dict[str, Any]] | None = None,
) -> bool:
    """True when the cluster still needs neighbor absorb (not fully interior)."""
    segs = segments or []
    by_id = {str(s.get("segment_id")): s for s in segs if isinstance(s, dict)}
    touched = [str(s) for s in (cluster.get("segment_ids_touched") or []) if s]
    i0, i1 = _ms(cluster, "start_ms"), _ms(cluster, "end_ms")
    if not touched:
        return True
    if len(touched) >= 2:
        return True
    sid = touched[0]
    seg = by_id.get(sid)
    if seg is None:
        return True
    seg_dur = max(0, _ms(seg, "end_ms") - _ms(seg, "start_ms"))
    island_dur = max(0, i1 - i0)
    fully_inside = _ms(seg, "start_ms") <= i0 and _ms(seg, "end_ms") >= i1
    if fully_inside and seg_dur >= max(island_dur * 2, island_dur + 2500):
        return False
    return True


def refresh_cluster_segment_touches(
    cluster: dict[str, Any],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Re-resolve segment_ids_touched against the current manifest."""
    i0, i1 = _ms(cluster, "start_ms"), _ms(cluster, "end_ms")
    touched: list[str] = []
    for seg in segments:
        s0, s1 = _ms(seg, "start_ms"), _ms(seg, "end_ms")
        if s1 <= i0 or s0 >= i1:
            continue
        sid = str(seg.get("segment_id") or "")
        if sid and sid not in touched:
            touched.append(sid)
    out = dict(cluster)
    out["segment_ids_touched"] = touched
    return out


__all__ = [
    "CLUSTERS_PATH",
    "HV_BOOSTS_PATH",
    "HV_ISLANDS_PATH",
    "authoritative_high_value_must_keep_ids",
    "cluster_is_fuse_eligible",
    "enabled",
    "group_high_value_island_clusters",
    "high_value_must_keep_segment_ids",
    "high_value_speech_cfg",
    "load_high_value_islands",
    "mark_segments_high_value",
    "refresh_cluster_segment_touches",
    "scan_high_value_speech_islands",
    "write_high_value_boosts",
]
