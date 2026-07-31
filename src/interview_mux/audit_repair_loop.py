"""Audit → topo repair → bounded re-rank loop for story-unsafe masters."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _audit_fail(doc: dict[str, Any] | None) -> bool:
    if not isinstance(doc, dict):
        return False
    return str(doc.get("verdict") or "").strip().lower() == "fail"


def maybe_repair_after_narrative_audit(ctx: RunContext, artifacts: dict[str, Any]) -> dict[str, Any]:
    """If audit fails, topo-repair selection once and mark cascade for re-rank.

    Does not invoke LLM here (caller may re-run ranking). Max one auto-repair
    per run via run_meta flag.
    """
    if not _audit_fail(artifacts):
        return artifacts

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if isinstance(meta, dict) and meta.get("edl_narrative_audit_repair_done"):
        ctx.log(
            "edl_narrative_audit still fail after prior repair — leaving for operator",
            level="warning",
            stage="edl_narrative_audit",
        )
        return artifacts

    plan = (
        ctx.read_json("master/narrative_plan.json")
        if ctx.artifact_exists("master/narrative_plan.json")
        else None
    )
    if not ctx.artifact_exists("master/selection.json"):
        return artifacts

    from interview_mux.selection_order_repair import repair_selection_order
    from interview_mux.artifact_writes import write_validated_artifact

    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return artifacts
    repaired, notes = repair_selection_order(sel, plan if isinstance(plan, dict) else None)
    if notes:
        write_validated_artifact(
            ctx,
            "master/selection.json",
            repaired,
            merge_from_disk=False,
            stage_key="edl_narrative_audit_repair",
        )
        ctx.log(
            f"edl_narrative_audit fail → topo-repaired selection ({len(notes)} notes); "
            "invalidate ranking for bounded re-rank",
            level="warning",
            stage="edl_narrative_audit",
            detail=notes[:8],
        )

    def _mark(m: dict) -> None:
        m["edl_narrative_audit_repair_done"] = True
        m["edl_narrative_audit_needs_rerank"] = True

    ctx.mutate_run_meta(_mark)

    # Clear ranking + transitions done markers so delivery can re-pick order
    for sid in ("full_master_ranking", "transitions"):
        marker = ctx.final_path(".stage_done", sid)
        if marker.is_file():
            try:
                marker.unlink()
            except OSError:
                pass

    out = dict(artifacts)
    out["repair_attempted"] = True
    out["repair_notes"] = notes[:12] if notes else []
    return out
