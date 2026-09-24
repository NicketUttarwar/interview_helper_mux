"""Soft-upstream membership floors for full_master_ranking."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _coverage_hollow(ctx: RunContext) -> bool:
    if not ctx.artifact_exists("master/coverage_audit.json"):
        return True
    try:
        cov = ctx.read_json("master/coverage_audit.json")
    except Exception:
        return True
    if not isinstance(cov, dict) or not cov:
        return True
    topics = cov.get("topics") or cov.get("topic_coverage") or cov.get("covered_topics")
    if isinstance(topics, list) and len(topics) == 0:
        return True
    if isinstance(topics, dict) and not topics:
        return True
    return False


def _framing_hollow(ctx: RunContext) -> bool:
    for rel in (
        "understanding/gap_framing_plan.json",
        "understanding/gap_report.json",
    ):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        gaps = doc.get("gaps") or doc.get("lines") or doc.get("framing_lines")
        if isinstance(gaps, list) and gaps:
            return False
        if doc.get("segments") or doc.get("must_keep_segment_ids"):
            return False
    return True


def expand_must_keep_for_soft_upstream(
    ctx: RunContext, payload: dict[str, Any]
) -> dict[str, Any]:
    """When coverage/framing is hollow, inject deterministic must_keep expansion."""
    if not (_coverage_hollow(ctx) or _framing_hollow(ctx)):
        return payload
    extra: set[str] = set()
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        extra |= {str(s) for s in hard_keep_segment_ids(ctx) if s}
    except Exception:
        pass
    for rel in (
        "analysis/high_value_speech_islands.json",
        "analysis/high_value_speech_boosts.json",
    ):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        for sid in doc.get("segment_ids_touched") or []:
            if sid:
                extra.add(str(sid))
        for row in doc.get("priors") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                extra.add(str(row["segment_id"]))
            elif isinstance(row, str) and row:
                extra.add(row)
    if ctx.artifact_exists("master/narrative_plan.json"):
        try:
            from interview_mux.rank_candidates import chapter_order_from_plan

            plan = ctx.read_json("master/narrative_plan.json")
            chapter = chapter_order_from_plan(plan if isinstance(plan, dict) else None)
            # Chapter heads: first id of each chapter.
            if isinstance(plan, dict):
                for ch in plan.get("chapters") or []:
                    if isinstance(ch, dict):
                        ids = [str(x) for x in (ch.get("segment_ids") or []) if x]
                        if ids:
                            extra.add(ids[0])
            for sid in chapter[:8]:
                extra.add(sid)
        except Exception:
            pass
    cta = {str(s) for s in (payload.get("cta_omit_segment_ids") or []) if s}
    extra -= cta
    if not extra:
        return payload
    keeps = [str(s) for s in (payload.get("must_keep_segment_ids") or []) if s]
    have = set(keeps)
    for sid in sorted(extra):
        if sid not in have:
            keeps.append(sid)
            have.add(sid)
    payload["must_keep_segment_ids"] = keeps
    payload["soft_upstream_must_keep_expanded"] = True
    return payload


def enforce_membership_duration_floor(
    ctx: RunContext,
    artifacts: dict[str, Any],
    *,
    stage: str = "full_master_ranking",
) -> dict[str, Any]:
    """If pack undershoots brief min, re-fill from hard-keeps / chapter / HV islands."""
    from interview_mux.selection_auto_pack import estimated_duration_sec

    ordered = [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s]
    if not ordered:
        return artifacts
    brief_min = 0.0
    if ctx.artifact_exists("understanding/delivery_brief.json"):
        try:
            from interview_mux.delivery_brief import load_delivery_brief

            brief = load_delivery_brief(ctx)
            band = (brief or {}).get("target_duration_sec") or {}
            if isinstance(band, dict) and band.get("min") is not None:
                brief_min = float(band["min"])
        except Exception:
            brief_min = 0.0
    if brief_min <= 0:
        return artifacts
    dur = estimated_duration_sec(ctx, ordered)
    if dur >= brief_min * 0.95:
        return artifacts
    # Undersize — pull additional candidates back from excludes / extras.
    candidates: list[str] = []
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        candidates.extend(sorted(hard_keep_segment_ids(ctx)))
    except Exception:
        pass
    if ctx.artifact_exists("master/narrative_plan.json"):
        try:
            from interview_mux.rank_candidates import chapter_order_from_plan

            plan = ctx.read_json("master/narrative_plan.json")
            candidates.extend(chapter_order_from_plan(plan if isinstance(plan, dict) else None))
        except Exception:
            pass
    have = set(ordered)
    added: list[str] = []
    for sid in candidates:
        s = str(sid)
        if not s or s in have:
            continue
        ordered.append(s)
        have.add(s)
        added.append(s)
        if estimated_duration_sec(ctx, ordered) >= brief_min * 0.95:
            break
    if not added:
        return artifacts
    artifacts = dict(artifacts)
    artifacts["ordered_segment_ids"] = ordered
    # Drop added ids from excludes if present.
    excl = []
    for row in artifacts.get("excluded_segment_ids") or []:
        sid = str(row.get("segment_id") if isinstance(row, dict) else row)
        if sid in set(added):
            continue
        excl.append(row)
    artifacts["excluded_segment_ids"] = excl
    try:
        ctx.log(
            f"membership duration floor: restored {len(added)} segment(s) "
            f"(brief_min={brief_min:.0f}s)",
            level="info",
            stage=stage,
            detail={"added": added[:12]},
        )
    except Exception:
        pass
    return artifacts
