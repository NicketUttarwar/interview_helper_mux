"""Audit → narrative alignment loop for story-unsafe masters.

Selection is the air-order authority. When an EDL narrative audit fails because
early-act chapters lost all selected segments, align ``narrative_plan`` down to
the selection — never expand the selection back toward leftovers.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _audit_fail(doc: dict[str, Any] | None) -> bool:
    if not isinstance(doc, dict):
        return False
    return str(doc.get("verdict") or "").strip().lower() == "fail"


def maybe_repair_after_narrative_audit(ctx: RunContext, artifacts: dict[str, Any]) -> dict[str, Any]:
    """If audit fails, align narrative_plan to selection once (no leftover reinclusion)."""
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

    if not ctx.artifact_exists("master/selection.json"):
        return artifacts

    from interview_mux.artifact_repairs import (
        align_narrative_plan_to_selection,
        repair_coverage_audit,
        repair_edl_audit,
        repair_master_selection,
    )
    from interview_mux.artifact_writes import write_validated_artifact

    sel = ctx.read_json("master/selection.json")
    notes: list[dict[str, Any]] = []
    if isinstance(sel, dict):
        repaired_sel, sel_notes = repair_master_selection(ctx, sel)
        notes.extend(sel_notes)
        write_validated_artifact(
            ctx,
            "master/selection.json",
            repaired_sel,
            merge_from_disk=False,
            stage_key="edl_narrative_audit_repair",
        )
    notes.extend(align_narrative_plan_to_selection(ctx))
    if ctx.artifact_exists("master/coverage_audit.json"):
        cov = ctx.read_json("master/coverage_audit.json")
        if isinstance(cov, dict):
            repaired_cov, cov_notes = repair_coverage_audit(ctx, cov)
            notes.extend(cov_notes)
            write_validated_artifact(
                ctx,
                "master/coverage_audit.json",
                repaired_cov,
                merge_from_disk=False,
                stage_key="topic_coverage_audit",
            )

    def _mark(m: dict) -> None:
        m["edl_narrative_audit_repair_done"] = True
        # Do not force ranking redo — expanding selection undoes creative packs.
        m.pop("edl_narrative_audit_needs_rerank", None)

    ctx.mutate_run_meta(_mark)

    out = dict(artifacts)
    repaired_audit, audit_notes = repair_edl_audit(ctx, out)
    notes.extend(audit_notes)
    out = repaired_audit
    out["repair_attempted"] = True
    out["repair_notes"] = notes[:12]
    ctx.log(
        f"edl_narrative_audit fail → aligned narrative to selection "
        f"({len(notes)} notes); demoted restore-excluded false fails",
        level="warning",
        stage="edl_narrative_audit",
        detail=notes[:8],
    )
    if _audit_fail(out):
        from interview_mux.edl_narrative_remutate import (
            apply_edl_narrative_remutate,
            plan_edl_narrative_remutate,
        )

        remutate = plan_edl_narrative_remutate(ctx, out)
        out["remutate"] = remutate
        if not remutate.get("exhausted"):
            applied = apply_edl_narrative_remutate(ctx, remutate)
            out["remutate_applied"] = applied
            ctx.log(
                "edl_narrative_audit still fail → typed remutate planned "
                f"(actions={remutate.get('actions')}, from={remutate.get('from_stage')})",
                level="warning",
                stage="edl_narrative_audit",
            )
        else:
            ctx.log(
                "edl_narrative_audit remutate exhausted — leaving fail for operator",
                level="error",
                stage="edl_narrative_audit",
            )
    return out
