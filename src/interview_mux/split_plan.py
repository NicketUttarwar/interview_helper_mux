"""Propose + auto-apply duration/overload splits → segments/split_plan.json."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def propose_split_plan(
    ctx: RunContext,
    *,
    boundaries: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    content_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a split plan from overloaded / over-long segments."""
    from interview_mux.boundary_enrich import detect_overloaded_segment_ids
    from interview_mux.config import merged_config

    bounds = boundaries
    if bounds is None and ctx.artifact_exists("segments/boundaries.json"):
        bounds = ctx.read_json("segments/boundaries.json")
    man = manifest
    if man is None and ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
    brief = content_brief
    if brief is None and ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")

    if not isinstance(bounds, dict):
        return {"version": 1, "proposals": [], "auto_apply": True, "applied": False}

    overloaded = detect_overloaded_segment_ids(
        bounds,
        content_brief=brief if isinstance(brief, dict) else None,
        manifest=man if isinstance(man, dict) else None,
    )
    sc = ((merged_config().get("analysis") or {}).get("segmentation") or {})
    max_ms = sc.get("max_segment_duration_ms")
    max_ms_i = int(max_ms) if max_ms is not None else 60_000

    by_id = {
        str(r.get("segment_id")): r
        for r in (bounds.get("boundaries") or [])
        if isinstance(r, dict) and r.get("segment_id")
    }
    proposals: list[dict[str, Any]] = []
    for sid in sorted(overloaded):
        row = by_id.get(sid)
        if not row:
            continue
        try:
            start = int(row.get("start_ms") or 0)
            end = int(row.get("end_ms") or start)
        except (TypeError, ValueError):
            continue
        span = end - start
        reason = "overload"
        if span > max_ms_i:
            reason = "max_duration"
        # Midpoint cut suggestion (enrich will refine to pause/topic)
        cut = start + span // 2
        proposals.append(
            {
                "segment_id": sid,
                "reason": reason,
                "span_ms": span,
                "suggested_cut_ms": [cut],
                "auto_apply": True,
            }
        )

    return {
        "version": 1,
        "proposals": proposals,
        "proposal_count": len(proposals),
        "auto_apply": True,
        "applied": False,
        "max_segment_duration_ms": max_ms_i,
    }


def write_split_plan(ctx: RunContext, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    doc = plan if isinstance(plan, dict) else propose_split_plan(ctx)
    ctx.write_json("segments/split_plan.json", doc)
    return doc


def apply_split_plan(
    ctx: RunContext,
    *,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Auto-apply duration/overload enrich to boundaries when plan says so.

    Returns updated plan with applied flag / actions.
    """
    from interview_mux.boundary_collate import normalize_boundary_timeline
    from interview_mux.boundary_enrich import enrich_boundary_rows
    from interview_mux.stage_coupling import publish_boundary_contract

    doc = plan if isinstance(plan, dict) else (
        ctx.read_json("segments/split_plan.json")
        if ctx.artifact_exists("segments/split_plan.json")
        else propose_split_plan(ctx)
    )
    if not doc.get("auto_apply", True) or not (doc.get("proposals") or []):
        doc = dict(doc)
        doc["applied"] = False
        doc["skip_reason"] = "no_proposals_or_auto_apply_false"
        ctx.write_json("segments/split_plan.json", doc)
        return doc

    if not ctx.artifact_exists("segments/boundaries.json"):
        doc = dict(doc)
        doc["applied"] = False
        doc["skip_reason"] = "no_boundaries"
        ctx.write_json("segments/split_plan.json", doc)
        return doc

    boundaries = ctx.read_json("segments/boundaries.json")
    transcript = (
        ctx.read_json("transcript/full.json")
        if ctx.artifact_exists("transcript/full.json")
        else None
    )
    speakers = (
        ctx.read_json("understanding/speakers.json")
        if ctx.artifact_exists("understanding/speakers.json")
        else None
    )
    brief = (
        ctx.read_json("understanding/content_brief.json")
        if ctx.artifact_exists("understanding/content_brief.json")
        else None
    )
    manifest = (
        ctx.read_json("segments/manifest.json")
        if ctx.artifact_exists("segments/manifest.json")
        else None
    )
    rows = [dict(r) for r in (boundaries.get("boundaries") or []) if isinstance(r, dict)]
    before_n = len(rows)
    enriched, actions = enrich_boundary_rows(
        rows,
        transcript=transcript if isinstance(transcript, dict) else None,
        speakers_doc=speakers if isinstance(speakers, dict) else None,
        content_brief=brief if isinstance(brief, dict) else None,
        manifest=manifest if isinstance(manifest, dict) else None,
    )
    raw_words = transcript.get("words") if isinstance(transcript, dict) else None
    timeline_words = (
        [w for w in raw_words if isinstance(w, dict)] if isinstance(raw_words, list) else None
    )
    normalized, _ = normalize_boundary_timeline(enriched, words=timeline_words)
    out = dict(boundaries)
    out["boundaries"] = normalized
    publish_boundary_contract(out)
    from interview_mux.shared_path_commit import commit_boundaries_doc

    # split_plan_apply is not an ALLOW producer — enrich only; keep prior claim.
    # Where the epoch reserves boundaries for its owner, the enrichment waits.
    commit_boundaries_doc(
        ctx,
        out,
        stage_key="split_plan_apply",
        claim_producer=False,
        optional=True,
    )

    doc = dict(doc)
    doc["applied"] = True
    doc["actions"] = actions[:40]
    doc["boundary_count_before"] = before_n
    doc["boundary_count_after"] = len(normalized)
    ctx.write_json("segments/split_plan.json", doc)
    return doc


def mark_split_rerank_cascade(ctx: RunContext, *, reason: str) -> None:
    """Record that ranking/gaps/transitions should re-run after splits."""

    def _mut(meta: dict) -> None:
        meta["split_rerank_cascade"] = {
            "needed": True,
            "reason": reason,
        }

    ctx.mutate_run_meta(_mut)


def clear_split_rerank_cascade(ctx: RunContext) -> None:
    def _mut(meta: dict) -> None:
        if "split_rerank_cascade" in meta:
            meta["split_rerank_cascade"] = {
                **(meta.get("split_rerank_cascade") or {}),
                "needed": False,
                "cleared_at_ranking": True,
            }

    ctx.mutate_run_meta(_mut)


def split_rerank_needed(ctx: RunContext) -> bool:
    if not ctx.artifact_exists("run_meta.json"):
        return False
    meta = ctx.read_json("run_meta.json")
    if not isinstance(meta, dict):
        return False
    row = meta.get("split_rerank_cascade")
    return isinstance(row, dict) and bool(row.get("needed"))
