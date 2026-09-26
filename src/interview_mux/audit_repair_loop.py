"""Audit → narrative alignment loop for story-unsafe masters.

Selection is the air-order authority. When an EDL narrative audit fails,
align narrative metadata down to selection and demote disk-stale blockers —
never expand selection, never remutate/clear markers (ENA S7), never bind
coverage (ENA S8 — topic_coverage owns).
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _audit_fail(doc: dict[str, Any] | None) -> bool:
    if not isinstance(doc, dict):
        return False
    return str(doc.get("verdict") or "").strip().lower() == "fail"


def maybe_repair_after_narrative_audit(ctx: RunContext, artifacts: dict[str, Any]) -> dict[str, Any]:
    """Fail → one metadata align + demote. Refuse if still fail (no remutate)."""
    if not _audit_fail(artifacts):
        return artifacts

    from interview_mux.artifact_repairs import (
        align_narrative_plan_to_selection,
        repair_edl_audit,
    )

    notes: list[dict[str, Any]] = []
    if ctx.artifact_exists("master/selection.json"):
        try:
            from interview_mux.media_ip_cta import (
                heal_on_air_cta_residue,
                on_air_orphaned_cta_scrap_ids,
            )

            scraps = on_air_orphaned_cta_scrap_ids(ctx)
            if scraps:
                heal_on_air_cta_residue(ctx)
                notes.append(
                    {
                        "action": "orphaned_cta_child_omit",
                        "ids": scraps[:12],
                    }
                )
        except Exception:
            pass
    if ctx.artifact_exists("master/selection.json"):
        skip_sel_write = False
        try:
            from interview_mux.seat_authority import hard_freeze_active

            skip_sel_write = bool(hard_freeze_active(ctx))
        except Exception:
            skip_sel_write = False

        if skip_sel_write:
            notes.append(
                {
                    "action": "skip_selection_write_hard_freeze",
                    "reason": "narrative_aligns_plan_only",
                }
            )
            ctx.log(
                "edl_narrative_audit repair: skip selection rewrite under hard freeze",
                level="info",
                stage="edl_narrative_audit",
            )
            notes.extend(align_narrative_plan_to_selection(ctx))
        else:
            from interview_mux.edl_narrative_remutate import (
                apply_edl_narrative_metadata_align,
            )

            meta_out = apply_edl_narrative_metadata_align(ctx)
            for item in meta_out.get("notes") or []:
                if isinstance(item, dict):
                    notes.append(item)
                else:
                    notes.append({"action": str(item)})

    out = dict(artifacts)
    repaired_audit, audit_notes = repair_edl_audit(ctx, out)
    notes.extend(audit_notes)
    out = repaired_audit
    out["repair_attempted"] = True
    out["repair_notes"] = notes[:12]
    # ENA S7: never remutate / clear markers / repair_done re-entry.
    out.pop("remutate", None)
    out.pop("remutate_applied", None)
    if _audit_fail(out):
        ctx.log(
            "edl_narrative_audit fail after demote — leaving for operator "
            f"({len(notes)} notes; no remutate)",
            level="error",
            stage="edl_narrative_audit",
            detail=notes[:8],
        )
    else:
        ctx.log(
            f"edl_narrative_audit fail → demoted/aligned ({len(notes)} notes)",
            level="warning",
            stage="edl_narrative_audit",
            detail=notes[:8],
        )
    return out
