"""Deterministic selection trim to fit delivery_brief duration targets.

Single shared pack algorithm (``pack_selection_to_duration``) used by both the
hard-budget safety net (``auto_pack_selection_to_brief`` → brief max) and the
editorial soft-pack (``creative_delivery.enforce_creative_selection_edit`` →
brief ideal) — previously two independent drop-loops that could drift out of
sync. Both now share the same volley-intact drop preference.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _segment_duration_ms(seg: dict[str, Any]) -> int:
    if seg.get("duration_ms") is not None:
        try:
            return max(0, int(seg["duration_ms"]))
        except (TypeError, ValueError):
            pass
    try:
        return max(0, int(seg.get("end_ms", 0)) - int(seg.get("start_ms", 0)))
    except (TypeError, ValueError):
        return 0


def _arc_critical_ids(ctx: RunContext) -> set[str]:
    ids: set[str] = set()
    if ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json")
        if isinstance(plan, dict):
            for key in ("must_keep_segment_ids", "spine_segment_ids", "anchor_segment_ids"):
                for sid in plan.get(key) or []:
                    if sid:
                        ids.add(str(sid))
            for act in plan.get("acts") or []:
                if isinstance(act, dict):
                    for sid in act.get("segment_ids") or []:
                        if sid:
                            ids.add(str(sid))
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        ids |= hard_keep_segment_ids(ctx)
    except Exception:
        pass
    try:
        from interview_mux.stages.audio_probes import authoritative_must_keep_ids

        ids |= authoritative_must_keep_ids(ctx)
    except Exception:
        pass
    if ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
            for ch in (sel.get("chapters") or []) if isinstance(sel, dict) else []:
                if isinstance(ch, dict):
                    ids.update(str(s) for s in (ch.get("segment_ids") or []) if s)
        except Exception:
            pass
    try:
        from interview_mux.stt_lexicon_islands import soft_protect_segment_ids

        ids |= soft_protect_segment_ids(ctx)
    except Exception:
        pass
    return ids


def _segments_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return {}
    man = ctx.read_json("segments/manifest.json")
    return {
        str(s.get("segment_id") or s.get("id") or ""): s
        for s in (man.get("segments") or [])
        if isinstance(s, dict)
    }


def estimated_duration_sec(ctx: RunContext, ordered_ids: list[str]) -> float:
    by_id = _segments_by_id(ctx)
    total_ms = 0
    for sid in ordered_ids:
        seg = by_id.get(str(sid))
        if seg:
            total_ms += _segment_duration_ms(seg)
    return total_ms / 1000.0


def _speaker_of_map(ctx: RunContext) -> dict[str, str]:
    try:
        return {sid: str(seg.get("speaker_id") or "") for sid, seg in _segments_by_id(ctx).items()}
    except Exception:
        return {}


def pack_selection_to_duration(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    target_sec: float,
    stage: str,
    meta_key: str,
    action_id: str,
    log_label: str,
    prefer_volley_intact: bool = True,
) -> dict[str, Any]:
    """Drop lowest-ranked non-arc-critical segments until within ``target_sec``.

    Prefers dropping mid-monologue segments (same speaker before/after) first
    so I<->S turn boundaries and speaker volleys survive denser trims — ties
    broken by rank (worst first). Returns ``selection`` unchanged when already
    within budget or nothing droppable remains.
    """
    ordered = [str(x) for x in (selection.get("ordered_segment_ids") or []) if x]
    if not ordered or target_sec is None or target_sec <= 0:
        return selection
    est = estimated_duration_sec(ctx, ordered)
    if est <= target_sec:
        return selection

    critical = _arc_critical_ids(ctx)
    try:
        from interview_mux.stt_lexicon_islands import soft_protect_segment_ids

        stt_protected = soft_protect_segment_ids(ctx)
        if stt_protected:
            ctx.log(
                f"STT island soft-protect: {len(stt_protected)} segment(s) treated as duration-critical",
                level="info",
                stage=stage,
                action_id="stt_island.soft_protect",
                detail={"segment_ids": sorted(stt_protected)[:20]},
            )
    except Exception:
        pass

    ranks = selection.get("segment_ranks") or selection.get("ranks") or {}
    if not isinstance(ranks, dict):
        ranks = {}

    def rank_of(sid: str) -> float:
        try:
            return float(ranks.get(sid, 9999))
        except (TypeError, ValueError):
            return 9999.0

    speaker_of = _speaker_of_map(ctx) if prefer_volley_intact else {}
    by_id = _segments_by_id(ctx)

    def drop_score(sid: str) -> tuple[float, float, float]:
        if not prefer_volley_intact:
            return (0.0, 0.0, rank_of(sid))
        idx = ordered.index(sid)
        spk = speaker_of.get(sid, "")
        prev = speaker_of.get(ordered[idx - 1], "") if idx > 0 else ""
        nxt = speaker_of.get(ordered[idx + 1], "") if idx + 1 < len(ordered) else ""
        mid_mono = spk and spk == prev == nxt
        dur = _segment_duration_ms(by_id.get(sid) or {})
        micro = 1.0 if dur > 0 and dur < 2500 else 0.0
        # Prefer dropping isolated / micro clips; keep mid-monologue native points intact.
        isolated = 0.0 if mid_mono else 1.0
        return (micro, isolated, rank_of(sid))

    droppable = [sid for sid in ordered if sid not in critical]
    droppable.sort(key=drop_score, reverse=True)  # drop mid-monologue + worst ranks first
    dropped: list[str] = []
    remaining = list(ordered)
    for sid in droppable:
        if estimated_duration_sec(ctx, remaining) <= target_sec:
            break
        if len(remaining) <= max(1, len(critical) or 1):
            break
        remaining = [x for x in remaining if x != sid]
        dropped.append(sid)

    if not dropped:
        return selection

    # Shadow advisory: vernacular must_keep that would have been protected if authoritative.
    shadow_vernacular: list[str] = []
    try:
        from interview_mux.stages.audio_probes import (
            enforcement_mode_for_ctx,
            load_must_keep_segment_ids,
        )

        vernacular_ids = load_must_keep_segment_ids(ctx)
        shadow_vernacular = [sid for sid in dropped if sid in vernacular_ids]
        if shadow_vernacular and enforcement_mode_for_ctx(ctx) != "authoritative":
            ctx.log(
                f"Shadow vernacular: {meta_key} dropped {len(shadow_vernacular)} must_keep id(s)",
                level="warning",
                stage=stage,
                action_id="vernacular.shadow.would_keep",
                detail={
                    "event": "vernacular_shadow_drop",
                    "dropped_must_keep": shadow_vernacular[:20],
                    "enforcement_mode": "shadow",
                },
            )
    except Exception:
        pass

    out = dict(selection)
    out["ordered_segment_ids"] = remaining
    excluded = list(out.get("excluded_segment_ids") or [])
    for sid in dropped:
        if sid not in excluded:
            excluded.append(sid)
    out["excluded_segment_ids"] = excluded
    after_sec = round(estimated_duration_sec(ctx, remaining), 1)
    meta = dict(out.get("_meta") or {})
    meta[meta_key] = {
        "dropped": dropped,
        "before_sec": round(est, 1),
        "after_sec": after_sec,
        "target_sec": target_sec,
        "shadow_vernacular_dropped": shadow_vernacular,
    }
    out["_meta"] = meta
    ctx.log(
        f"{log_label}: dropped {len(dropped)} segment(s) to fit {target_sec:.0f}s",
        level="info",
        stage=stage,
        action_id=action_id,
        detail={
            "event": meta_key,
            "dropped": dropped[:20],
            "before_sec": est,
            "after_sec": after_sec,
            "target_sec": target_sec,
            "shadow_vernacular_dropped": shadow_vernacular[:20],
        },
    )
    return out


def auto_pack_selection_to_brief(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    stage: str = "full_master_ranking",
) -> dict[str, Any]:
    """Hard-budget safety net: drop toward brief max duration (first_try mode only).

    Returns updated selection (may be unchanged). Logs pipeline.selection.auto_pack.
    """
    from interview_mux.delivery_brief import load_delivery_brief
    from interview_mux.first_try import first_try_mode_enabled

    if not first_try_mode_enabled():
        return selection
    brief = load_delivery_brief(ctx)
    if not brief:
        return selection
    budget = brief.get("target_duration_sec") if isinstance(brief.get("target_duration_sec"), dict) else {}
    max_sec = budget.get("max")
    try:
        max_sec_f = float(max_sec) if max_sec is not None else None
    except (TypeError, ValueError):
        max_sec_f = None
    if max_sec_f is None or max_sec_f <= 0:
        return selection

    packed = pack_selection_to_duration(
        ctx,
        selection,
        target_sec=max_sec_f,
        stage=stage,
        meta_key="auto_pack",
        action_id="pipeline.selection.auto_pack",
        log_label="Selection auto-pack",
    )
    try:
        from interview_mux.air_script import enforce_air_script_omits

        packed = enforce_air_script_omits(ctx, packed)
    except Exception:
        pass
    return packed
