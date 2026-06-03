"""Validated artifact writes with optional merge from on-disk state."""

from __future__ import annotations

from typing import Any

from interview_mux.prompt_validation import validate_artifact_write
from interview_mux.run_context import RunContext


def write_validated_artifact(
    ctx: RunContext,
    rel_path: str,
    data: dict[str, Any],
    *,
    merge_from_disk: bool = False,
    stage_key: str | None = None,
) -> Any:
    """
    Merge (optional), validate against on-disk schema, write JSON, log failures.

    Raises ValueError when validation fails (same as RunContext.write_json).
    """
    out = data
    if merge_from_disk:
        from interview_mux.artifact_completeness import merge_artifact

        existing: dict[str, Any] | None = None
        if ctx.artifact_exists(rel_path):
            raw = ctx.read_json(rel_path)
            if isinstance(raw, dict):
                existing = raw
        out = merge_artifact(rel_path, existing, data, stage_key=stage_key)

    errors = validate_artifact_write(rel_path, out)
    if errors:
        ctx.log(
            f"Cannot write {rel_path}: schema validation failed — {'; '.join(errors[:4])}",
            level="error",
            stage=stage_key,
            detail={"path": rel_path, "errors": errors[:8]},
        )
        raise ValueError(f"{rel_path}: schema validation failed — {'; '.join(errors[:6])}")

    return ctx.write_json(rel_path, out, stage_key=stage_key)
