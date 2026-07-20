"""Single acceptance contract for LLM stage progression (strict progression)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from interview_mux.artifact_cross_validate import STAGE_CHECKPOINTS, validate_cross_artifacts_for_stage
from interview_mux.config import merged_config
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, validate_artifact_write
from interview_mux.run_context import RunContext


@dataclass
class AcceptanceResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    lint_errors: list[str] = field(default_factory=list)
    null_violations: list[str] = field(default_factory=list)
    cross_validate_errors: list[str] = field(default_factory=list)
    downstream_errors: list[str] = field(default_factory=list)
    sufficiency_errors: list[str] = field(default_factory=list)

    @property
    def all_errors(self) -> list[str]:
        return (
            self.errors
            + self.schema_errors
            + self.lint_errors
            + self.null_violations
            + self.sufficiency_errors
            + self.cross_validate_errors
            + self.downstream_errors
        )


def _read_artifact(ctx: RunContext, stage_key: str, *, staged: bool) -> tuple[str | None, dict[str, Any] | None]:
    from interview_mux.write_staging import read_pending_json, staged_path

    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        return None, None
    if staged and staged_path(ctx, rel, stage_id=stage_key).is_file():
        return rel, read_pending_json(ctx, stage_key, rel)
    if ctx.artifact_exists(rel):
        return rel, ctx.read_json(rel)
    return None, None


def _lint_artifact_doc(stage_key: str, artifact: dict[str, Any], ctx: RunContext) -> list[str]:
    from interview_mux.deterministic_lint import _LINTERS

    fn = _LINTERS.get(stage_key)
    if not fn:
        return []
    try:
        return list(fn(artifact, ctx) or [])
    except Exception as exc:  # noqa: BLE001
        return [f"lint internal error: {exc}"]


def stage_acceptance_ok(
    ctx: RunContext,
    stage_key: str,
    *,
    staged: bool = True,
    include_cross_validate: bool = True,
    include_downstream: bool = True,
) -> AcceptanceResult:
    """True when producer artifact passes schema, lint, null policy, and optional cross-validate."""
    result = AcceptanceResult(ok=False)

    rel, artifact = _read_artifact(ctx, stage_key, staged=staged)
    if not rel or not artifact:
        label = "staged" if staged else "committed"
        result.errors.append(f"no_{label}_artifact")
        return result

    schema_errors = validate_artifact_write(rel, artifact)
    result.schema_errors = list(schema_errors or [])
    if result.schema_errors:
        return result

    result.lint_errors = _lint_artifact_doc(stage_key, artifact, ctx)
    if result.lint_errors:
        return result

    from interview_mux.null_field_policy import find_null_fields, null_policy_enabled, partition_nulls

    if null_policy_enabled():
        paths = find_null_fields(stage_key, artifact)
        critical, _ = partition_nulls(stage_key, paths)
        result.null_violations = list(critical or [])
        if result.null_violations:
            return result

    from interview_mux.sufficiency_engine import evaluate, sufficiency_enabled

    if sufficiency_enabled():
        findings = evaluate(stage_key, artifact, ctx)
        blocking = [f.message for f in findings if f.blocking]
        result.sufficiency_errors = blocking
        if blocking:
            return result

    if include_cross_validate:
        checkpoint = STAGE_CHECKPOINTS.get(stage_key)
        if checkpoint:
            result.cross_validate_errors = list(
                validate_cross_artifacts_for_stage(ctx, stage_key, staged=staged) or []
            )
            if result.cross_validate_errors:
                return result

    result.ok = True
    return result
