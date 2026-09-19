"""Disk-grounded spoken-synthetic occupancy for selected EDL adjacencies."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

SEAM_OCCUPANCY_REL = "master/seam_occupancy.json"


def build_seam_occupancy(
    ctx: RunContext,
    *,
    selection: dict[str, Any] | None = None,
    gap_report: dict[str, Any] | None = None,
    transitions_doc: dict[str, Any] | None = None,
    persist: bool = True,
    stage_key: str = "transitions",
) -> dict[str, Any]:
    """Resolve one authoritative spoken synthetic for every selected adjacency."""
    from interview_mux.gap_framing import choose_seam_synthetic

    if selection is None:
        selection = (
            ctx.read_json("master/selection.json")
            if ctx.artifact_exists("master/selection.json")
            else {}
        )
    if gap_report is None:
        gap_report = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
    if transitions_doc is None:
        transitions_doc = (
            ctx.read_json("master/transitions.json")
            if ctx.artifact_exists("master/transitions.json")
            else {}
        )
    selection = selection if isinstance(selection, dict) else {}
    gap_report = gap_report if isinstance(gap_report, dict) else {}
    transitions_doc = transitions_doc if isinstance(transitions_doc, dict) else {}
    order = [
        str(segment_id)
        for segment_id in (selection.get("ordered_segment_ids") or [])
        if segment_id
    ]
    seams: list[dict[str, Any]] = []
    clean = True
    transitions = [
        row
        for row in (transitions_doc.get("transitions") or [])
        if isinstance(row, dict) and str(row.get("text") or "").strip()
    ]
    for after, before in zip(order, order[1:]):
        choice = choose_seam_synthetic(
            after,
            before,
            gap_report=gap_report,
            transitions_doc=transitions_doc,
            ctx=ctx,
        )
        transition_count = sum(
            1
            for row in transitions
            if str(row.get("after_segment_id") or "").strip() == after
            and str(row.get("before_segment_id") or "").strip() == before
        )
        # choose_seam_synthetic is the occupancy SSOT; duplicate transition rows
        # remain visibly unclean even though the chooser deterministically picks one.
        seam_clean = transition_count <= 1
        clean = clean and seam_clean
        seams.append(
            {
                "after_segment_id": after,
                "before_segment_id": before,
                "kind": str(choice.get("kind") or "none"),
                "line_id": choice.get("line_id"),
                "text": choice.get("text"),
                "occupied": str(choice.get("kind") or "none") != "none",
                "transition_count": transition_count,
                "clean": seam_clean,
            }
        )
    doc = {
        "version": 1,
        "selection_order": order,
        "seams": seams,
        "clean": clean,
        "source": "choose_seam_synthetic",
    }
    if persist:
        # Occupancy is transitions-safe metadata and must remain writable after
        # soft/hard seat freeze without claiming authority over VO seats.
        ctx.write_json(
            SEAM_OCCUPANCY_REL,
            doc,
            stage_key=stage_key,
            skip_handoff=True,
        )
    return doc


__all__ = ["SEAM_OCCUPANCY_REL", "build_seam_occupancy"]
