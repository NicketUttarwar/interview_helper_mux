"""Good-enough advance for segment_classification before hard LLM gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interview_mux.first_try import first_try_mode_enabled


@dataclass
class GoodEnoughResult:
    cleared: bool
    message: str = ""


def try_good_enough_advance(
    ctx: Any,
    stage_key: str,
    lint_errors: list[str] | None,
) -> GoodEnoughResult:
    if stage_key != "segment_classification" or not first_try_mode_enabled():
        return GoodEnoughResult(cleared=False)

    from interview_mux.artifact_completeness import complete_manifest_from_boundaries
    from interview_mux.artifact_issue_triage import _read_stage_artifact, _write_stage_artifact
    from interview_mux.coverage_limits import partition_lint_errors
    from interview_mux.lint_repair_bridge import try_staged_structural_repair
    from interview_mux.stage_acceptance import stage_acceptance_ok

    rel, artifact = _read_stage_artifact(ctx, stage_key, staged=True)
    if not rel or not artifact:
        return GoodEnoughResult(cleared=False)

    errors = list(lint_errors or [])
    repair = try_staged_structural_repair(ctx, stage_key, errors)
    if repair.outcome.name == "REPAIRED_OK" and repair.acceptance_ok:
        return GoodEnoughResult(
            cleared=True,
            message="Segment classification: structural repair cleared staged manifest",
        )

    completed = complete_manifest_from_boundaries(ctx, artifact)
    _write_stage_artifact(ctx, stage_key, rel, completed)
    acceptance = stage_acceptance_ok(
        ctx,
        stage_key,
        staged=True,
        include_cross_validate=False,
        include_downstream=False,
    )
    blocking, warnings = partition_lint_errors(acceptance.lint_errors or acceptance.all_errors)
    if acceptance.ok and not blocking:
        ctx.log(
            "Segment classification: accepted good-enough manifest "
            f"({len(warnings)} soft warning(s))",
            level="info",
            stage=stage_key,
            action_id="segment_classification.good_enough_advance",
            detail={"warnings": warnings[:4]},
        )
        return GoodEnoughResult(
            cleared=True,
            message="Segment classification: accepted good-enough manifest from boundaries",
        )
    return GoodEnoughResult(cleared=False)


__all__ = ["GoodEnoughResult", "try_good_enough_advance"]
