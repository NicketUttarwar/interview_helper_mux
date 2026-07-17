"""Deterministic structural repair before LLM retry loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from interview_mux.artifact_repairs import apply_repairs_for_stage
from interview_mux.stage_acceptance import stage_acceptance_ok

STRUCTURAL_LINT_PATTERNS: tuple[str, ...] = (
    "duplicate segment_id",
    "manifest times not monotonic",
    "zero-length boundary",
    "zero-length segment",
)

REPAIR_STAGES = frozenset({"boundary_detection", "segment_classification"})


class RepairOutcome(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    REPAIRED_OK = "repaired_ok"
    REPAIRED_PARTIAL = "repaired_partial"
    NOT_REPAIRABLE = "not_repairable"


@dataclass
class StructuralRepairResult:
    outcome: RepairOutcome
    applied: list[dict[str, Any]] = field(default_factory=list)
    remaining_lint: list[str] = field(default_factory=list)
    acceptance_ok: bool = False

    @property
    def repaired(self) -> bool:
        return bool(self.applied)


def _joined_lint(lint_errors: list[str]) -> str:
    return " ".join(lint_errors).lower()


def lint_errors_structurally_repairable(lint_errors: list[str]) -> bool:
    if not lint_errors:
        return False
    joined = _joined_lint(lint_errors)
    if any(p in joined for p in STRUCTURAL_LINT_PATTERNS):
        return True
    if "segment_coverage_ratio" in joined:
        return True
    if "warnings" in joined and "null" in joined:
        return True
    return False


def _segment_count_from_artifact(stage_key: str, artifact: dict[str, Any]) -> int:
    if stage_key == "boundary_detection":
        return len(artifact.get("boundaries") or [])
    if stage_key == "segment_classification":
        return len(artifact.get("segments") or [])
    return 0


def try_staged_structural_repair(
    ctx: Any,
    stage_key: str,
    lint_errors: list[str],
) -> StructuralRepairResult:
    if stage_key not in REPAIR_STAGES:
        return StructuralRepairResult(outcome=RepairOutcome.NOT_APPLICABLE)
    if not lint_errors_structurally_repairable(lint_errors):
        return StructuralRepairResult(outcome=RepairOutcome.NOT_REPAIRABLE)

    from interview_mux.artifact_issue_triage import _read_stage_artifact, _write_stage_artifact, triage_cfg

    rel, artifact = _read_stage_artifact(ctx, stage_key, staged=True)
    if not rel or not artifact:
        return StructuralRepairResult(outcome=RepairOutcome.NOT_APPLICABLE)

    seg_before = _segment_count_from_artifact(stage_key, artifact)
    applied: list[dict[str, Any]] = []
    patched = artifact

    if stage_key == "segment_classification" and any(
        "segment_coverage_ratio" in str(e).lower() for e in lint_errors
    ):
        from interview_mux.artifact_completeness import complete_manifest_from_boundaries

        patched = complete_manifest_from_boundaries(ctx, artifact)
        applied.append({"action": "complete_manifest_from_boundaries"})

    repair_patched, repair_applied = apply_repairs_for_stage(ctx, stage_key, patched, rel_path=rel)
    if repair_applied:
        patched = repair_patched
        applied.extend(repair_applied)

    if not applied:
        return StructuralRepairResult(
            outcome=RepairOutcome.NOT_REPAIRABLE,
            remaining_lint=list(lint_errors),
        )

    seg_after = _segment_count_from_artifact(stage_key, patched)
    cfg = triage_cfg()
    min_segments = int(cfg.get("min_segments_after_auto_resolve") or 1)
    max_delete_ratio = float(cfg.get("max_segments_deleted_per_fix_all") or 0.10)
    if seg_before and seg_after < min_segments:
        return StructuralRepairResult(
            outcome=RepairOutcome.REPAIRED_PARTIAL,
            applied=applied,
            remaining_lint=list(lint_errors),
        )
    if seg_before and (seg_before - seg_after) / seg_before > max_delete_ratio:
        return StructuralRepairResult(
            outcome=RepairOutcome.REPAIRED_PARTIAL,
            applied=applied,
            remaining_lint=list(lint_errors),
        )

    _write_stage_artifact(ctx, stage_key, rel, patched)
    acceptance = stage_acceptance_ok(
        ctx,
        stage_key,
        staged=True,
        include_cross_validate=False,
        include_downstream=False,
    )

    ctx.log(
        f"Structural repair applied ({len(applied)} action(s)) — acceptance={acceptance.ok}",
        level="info",
        stage=stage_key,
        action_id="itr.structural_repair",
        detail={"applied": applied[:8], "lint_remaining": acceptance.lint_errors[:4]},
    )

    if acceptance.ok:
        return StructuralRepairResult(
            outcome=RepairOutcome.REPAIRED_OK,
            applied=applied,
            acceptance_ok=True,
        )

    return StructuralRepairResult(
        outcome=RepairOutcome.REPAIRED_PARTIAL,
        applied=applied,
        remaining_lint=acceptance.lint_errors or acceptance.all_errors,
    )
