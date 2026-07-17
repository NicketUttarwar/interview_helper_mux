"""Whether pipeline stages are truly complete on disk (UI + runner parity)."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_completeness import artifact_status_for_stage
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext

# Non-primary outputs that must exist before a stage is marked done.
STAGE_SECONDARY_ARTIFACT_PATHS: dict[str, list[str]] = {
    "optimal_questions": ["understanding/interviewer_script.txt"],
}


class StageArtifactsIncompleteError(ValueError):
    """Raised when a stage must not be marked done or advanced past."""

    def __init__(self, stage_id: str, reason: str) -> None:
        self.stage_id = stage_id
        self.reason = reason
        super().__init__(f"Stage {stage_id} artifacts incomplete — {reason}")


def stage_required_artifact_paths(stage_id: str) -> list[str]:
    """Producer artifact path(s) that must be complete before a stage is truly done."""
    paths: list[str] = []
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_id)
    if rel:
        paths.append(rel)
    paths.extend(STAGE_SECONDARY_ARTIFACT_PATHS.get(stage_id, []))
    return paths


def stage_artifact_incompleteness(
    ctx: RunContext,
    stage_id: str,
    *,
    lifecycle: dict[str, Any] | None = None,
) -> str | None:
    """Human-readable reason when required artifacts are not complete, else None."""
    for path in stage_required_artifact_paths(stage_id):
        phase = (lifecycle or {}).get(path)
        if phase in ("n_a", "skipped"):
            continue
        if not ctx.artifact_exists(path):
            return f"{path} is pending"
        st = artifact_status_for_stage(path, ctx, stage_id)
        if st != "complete":
            return f"{path} is {st}"
    return None


def reconcile_stage_done_marker(ctx: RunContext, stage_id: str) -> bool:
    """
    Clear .stage_done when artifacts are not acceptable.
    Returns True when the stage remains marked done after reconcile.
    """
    if not ctx.is_done(stage_id):
        return False
    reason = stage_artifact_incompleteness(ctx, stage_id)
    if not reason:
        return True
    marker = ctx.final_path(".stage_done", stage_id)
    if marker.is_file():
        marker.unlink(missing_ok=True)
        ctx.log(
            f"Cleared stale .stage_done/{stage_id}: {reason}",
            level="warning",
            stage=stage_id,
            detail={"reason": reason},
        )
    return False


def assert_stage_artifacts_complete(ctx: RunContext, stage_id: str) -> None:
    reason = stage_artifact_incompleteness(ctx, stage_id)
    if reason:
        raise StageArtifactsIncompleteError(stage_id, reason)


def _staged_resilience_partial_acceptable(
    rel: str,
    doc: dict[str, Any],
    stage_id: str,
    ctx: RunContext | None = None,
) -> bool:
    """Allow partial-persist rescue saves when the stage producer content is semantically complete.

    Critical LLM stages never approve resilience-partial staging — Fail closed; re-run instead.
    """
    from interview_mux.artifact_completeness import compute_gaps
    from interview_mux.llm_flow_hardening import ALL_CRITICAL_LLM_STAGES
    from interview_mux.llm_output_resilience import artifact_resilience_partial

    if ctx and _staged_zero_pickup_acceptable(ctx, stage_id, rel, doc):
        return True
    if stage_id in ALL_CRITICAL_LLM_STAGES:
        return False
    if not artifact_resilience_partial(doc):
        return False
    producer = STAGE_ARTIFACT_DISK_PATHS.get(stage_id)
    if not producer or rel != producer:
        return False
    return not compute_gaps(rel, doc, stage_key=stage_id)


def _staged_zero_pickup_acceptable(
    ctx: RunContext,
    stage_id: str,
    rel: str,
    doc: dict[str, Any],
) -> bool:
    """Empty interviewer_lines are valid when gap-fill was skipped or no segment needs pickup."""
    if stage_id != "optimal_questions" or rel != "understanding/gap_report.json":
        return False
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

    if gap_fill_was_skipped(ctx):
        return True
    lines = doc.get("interviewer_lines")
    if not isinstance(lines, list) or lines:
        return False
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return False
    try:
        eval_doc = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return False
    evals = eval_doc.get("evaluations") or []
    if not isinstance(evals, list) or not evals:
        return False
    for row in evals:
        if not isinstance(row, dict):
            continue
        if row.get("self_explanatory"):
            continue
        severity = str(row.get("severity") or "").lower()
        if severity in {"high", "critical"}:
            return False
        gap_type = str(row.get("gap_type") or "")
        if gap_type and gap_type != "ok_with_light_bridge":
            return False
    return True


def staged_artifacts_acceptable(ctx: RunContext, stage_id: str) -> tuple[bool, str]:
    """True when pending staged JSON artifacts are safe to flush and mark done."""
    from interview_mux.artifact_completeness import compute_staged_write_gaps
    from interview_mux.llm_flow_hardening import ALL_CRITICAL_LLM_STAGES
    from interview_mux.llm_output_resilience import artifact_resilience_partial
    from interview_mux.prompt_validation import validate_artifact_write
    from interview_mux.write_staging import list_stage_staging_paths, read_pending_json

    for rel in list_stage_staging_paths(ctx, stage_id):
        if not rel.endswith(".json"):
            continue
        try:
            doc = read_pending_json(ctx, stage_id, rel)
        except Exception as exc:
            return False, f"{rel}: cannot read staged file ({exc})"
        if not isinstance(doc, dict):
            return False, f"{rel}: staged content is not a JSON object"
        if artifact_resilience_partial(doc) and not _staged_resilience_partial_acceptable(
            rel, doc, stage_id, ctx
        ):
            return False, (
                f"{rel} is a partial rescue save — re-run the stage instead of approving."
            )
        te = (doc.get("_meta") or {}).get("truncation_escalation") or {}
        flags = te.get("final_flags") or []
        if flags and stage_id in ALL_CRITICAL_LLM_STAGES:
            return False, (
                f"{rel} has truncation flags ({', '.join(list(flags)[:2])}) — "
                "re-run instead of approving."
            )
        errors = validate_artifact_write(rel, doc)
        if errors:
            return False, f"{rel}: {'; '.join(errors[:3])}"
        if compute_staged_write_gaps(rel, doc, stage_id=stage_id):
            return False, f"{rel} would remain incomplete after save"
    return True, ""
