"""Rebuild reorder bridges and auto-mint pair-specific spoken glue for naked seams."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

# Chapter-scale source jump — spoken hinge required (and stinger when music on).
CHAPTER_SCALE_GAP_MS = 60_000

# Only used when mastering.synthetic_framing.allow_canned_bridge_fallback is on.
CANNED_BRIDGE_TEXT = "There is more to that story."


def _chapter_ends_from_plan(plan: dict[str, Any] | None) -> set[str]:
    ends: set[str] = set()
    if not isinstance(plan, dict):
        return ends
    for ch in plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        ids = [str(x) for x in (ch.get("segment_ids") or []) if x]
        if ids:
            ends.add(ids[-1])
    return ends


def _narrative_mode(ctx: RunContext) -> str | None:
    for rel in (
        "mastering/mastering_plan.json",
        "master/narrative_plan.json",
    ):
        if not ctx.artifact_exists(rel):
            continue
        doc = ctx.read_json(rel)
        if isinstance(doc, dict) and doc.get("narrative_mode"):
            return str(doc.get("narrative_mode"))
    return None


def rebuild_reorder_bridges(
    ctx: RunContext,
    ordered: list[str],
    segments_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Rebuild + annotate bridges from the air order about to enter EDL."""
    from interview_mux.bridge_voice_policy import annotate_reorder_bridges
    from interview_mux.reorder_bridges import build_reorder_bridges

    plan = (
        ctx.read_json("master/narrative_plan.json")
        if ctx.artifact_exists("master/narrative_plan.json")
        else None
    )
    chapter_ends = _chapter_ends_from_plan(plan if isinstance(plan, dict) else None)
    # Also treat selection chapter last members as ends when narrative plan thin
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            chapter_ends |= _chapter_ends_from_plan(sel)

    bridges = annotate_reorder_bridges(
        build_reorder_bridges(
            [str(s) for s in ordered if s],
            segments_by_id,
            chapter_ends=chapter_ends,
        ),
        narrative_mode=_narrative_mode(ctx),
    )
    ctx.write_json("understanding/reorder_bridges.json", bridges)
    return bridges


def default_bridge_text(pair: dict[str, Any]) -> str:
    """Deterministic speakable hinge text (never chapter/act scaffolding)."""
    kind = str(pair.get("kind") or "reorder")
    try:
        gap = int(pair.get("source_gap_ms")) if pair.get("source_gap_ms") is not None else 0
    except (TypeError, ValueError):
        gap = 0
    category = str(pair.get("suggested_line_category") or "")

    if kind == "chapter_jump" or abs(gap) >= CHAPTER_SCALE_GAP_MS:
        if gap < 0:
            return "Stepping back—here's what led there."
        return "Next, the focus shifts."
    if category == "extracted_context" or gap < 0:
        return "That connects to something earlier."
    if category == "story_bridge":
        return "Meanwhile, another thread opens."
    return "And then—what happened next?"


def is_chapter_scale_pair(pair: dict[str, Any]) -> bool:
    kind = str(pair.get("kind") or "")
    if kind == "chapter_jump":
        return True
    try:
        gap = int(pair.get("source_gap_ms")) if pair.get("source_gap_ms") is not None else 0
    except (TypeError, ValueError):
        gap = 0
    return abs(gap) >= CHAPTER_SCALE_GAP_MS


def mint_missing_transitions(
    ctx: RunContext,
    missing: list[dict[str, Any]],
    *,
    transitions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append pair-bound transition entries for every missing reorder seam.

    Returns the updated transitions document (also written to disk).
    """
    from interview_mux.spoken_meta_lint import assert_speakable_or_raise

    doc: dict[str, Any]
    if isinstance(transitions, dict):
        doc = dict(transitions)
    elif ctx.artifact_exists("master/transitions.json"):
        loaded = ctx.read_json("master/transitions.json")
        doc = dict(loaded) if isinstance(loaded, dict) else {"transitions": []}
    else:
        doc = {"transitions": []}

    items = [t for t in (doc.get("transitions") or []) if isinstance(t, dict)]
    existing = {
        (
            str(t.get("after_segment_id") or ""),
            str(t.get("before_segment_id") or ""),
        )
        for t in items
    }

    synthetic_plan = (
        ctx.read_json("understanding/synthetic_framing_plan.json")
        if ctx.artifact_exists("understanding/synthetic_framing_plan.json")
        else None
    )
    from interview_mux.synthetic_framing import (
        planned_transition_for_pair,
        synthetic_framing_cfg,
    )

    minted = 0
    unplanned: list[str] = []
    allow_canned = bool(
        synthetic_framing_cfg().get("allow_canned_bridge_fallback", False)
    )
    for pair in missing:
        if not isinstance(pair, dict):
            continue
        a = str(pair.get("after_segment_id") or "")
        b = str(pair.get("before_segment_id") or "")
        if not a or not b or (a, b) in existing:
            continue
        planned = planned_transition_for_pair(synthetic_plan, a, b)
        if not planned:
            if not allow_canned:
                unplanned.append(f"{a}->{b}")
                continue
            text = CANNED_BRIDGE_TEXT
            assert_speakable_or_raise(text, context="transition")
            tr_type = "chapter" if is_chapter_scale_pair(pair) else "bridge"
            items.append(
                {
                    "after_segment_id": a,
                    "before_segment_id": b,
                    "text": text,
                    "type": tr_type,
                    "auto_minted": True,
                    "canned_bridge_fallback": True,
                    "kind": pair.get("kind") or "reorder",
                    "source_gap_ms": pair.get("source_gap_ms"),
                }
            )
            existing.add((a, b))
            minted += 1
            continue
        text = str(planned.get("text") or "").strip()
        if not text:
            text = default_bridge_text(pair)
        assert_speakable_or_raise(text, context="transition")
        tr_type = "chapter" if is_chapter_scale_pair(pair) else "bridge"
        items.append(
            {
                "after_segment_id": a,
                "before_segment_id": b,
                "text": text,
                "type": tr_type,
                "auto_minted": False,
                "synthetic_plan_line_id": planned.get("line_id"),
                "target_duration_ms": planned.get("target_duration_ms"),
                "comprehension_reason": planned.get("comprehension_reason"),
                "kind": pair.get("kind") or "reorder",
                "source_gap_ms": pair.get("source_gap_ms"),
            }
        )
        existing.add((a, b))
        minted += 1

    if unplanned:
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "Synthetic framing plan did not cover every required reorder seam: "
            + ", ".join(unplanned[:8]),
            stage="edl",
            reason="synthetic_plan_missing_required_seams",
            detail={"missing_pairs": unplanned, "canned_fallback_disabled": True},
        )
    doc["transitions"] = items
    if minted:
        ctx.write_json("master/transitions.json", doc)
        ctx.log(
            f"seam_glue: materialized {minted} planned spoken transition(s) for reorder joins",
            level="info",
            stage="edl",
            detail={"minted": minted},
        )
    return doc


def ensure_seam_glue(
    ctx: RunContext,
    *,
    ordered: list[str],
    segments_by_id: dict[str, dict[str, Any]],
    gap_report: dict[str, Any] | None,
    transitions: dict[str, Any] | None,
    soft: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Rebuild bridges, mint missing transitions, assert pair-specific completeness.

    Returns (bridges, transitions_doc, completeness_doc).
    """
    from interview_mux.bridge_completeness import (
        assert_bridges_complete,
        missing_reorder_bridges,
    )

    bridges = rebuild_reorder_bridges(ctx, ordered, segments_by_id)
    missing = missing_reorder_bridges(
        bridges,
        gap_report=gap_report,
        transitions=transitions,
    )
    transitions_doc = transitions if isinstance(transitions, dict) else {"transitions": []}
    if missing:
        transitions_doc = mint_missing_transitions(
            ctx, missing, transitions=transitions_doc
        )
    completeness = assert_bridges_complete(
        bridges,
        gap_report=gap_report,
        transitions=transitions_doc,
        soft=soft,
    )
    ctx.write_json("master/bridge_completeness.json", completeness)
    return bridges, transitions_doc, completeness
