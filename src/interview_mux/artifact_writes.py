"""Validated artifact writes with optional merge from on-disk state."""

from __future__ import annotations

from datetime import datetime, timezone
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


def write_partial_artifact(
    ctx: RunContext,
    rel_path: str,
    data: dict[str, Any],
    *,
    resilience_report: Any,
    stage_key: str | None = None,
    partial: bool = True,
    merge_from_disk: bool = True,
) -> Any:
    """Write schema-valid artifact subset with resilience metadata."""
    payload = dict(data)
    meta = payload.pop("_meta", {}) if isinstance(payload.get("_meta"), dict) else {}
    meta["resilience"] = {
        "partial": partial,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "kept_paths": getattr(resilience_report, "kept_paths", []),
        "stripped_count": len(getattr(resilience_report, "stripped", []) or []),
        "generated_count": len(getattr(resilience_report, "generated", []) or []),
        "summary": getattr(resilience_report, "summary", ""),
    }
    if hasattr(resilience_report, "to_dict"):
        meta["resilience"]["report"] = resilience_report.to_dict()
    payload["_meta"] = meta

    out = payload
    if merge_from_disk:
        from interview_mux.artifact_completeness import merge_artifact

        existing: dict[str, Any] | None = None
        if ctx.artifact_exists(rel_path):
            raw = ctx.read_json(rel_path)
            if isinstance(raw, dict):
                existing = raw
        out = merge_artifact(rel_path, existing, payload, stage_key=stage_key)

    errors = validate_artifact_write(rel_path, out)
    if errors:
        ctx.log(
            f"Partial write {rel_path} failed schema — {'; '.join(errors[:3])}",
            level="warning",
            stage=stage_key,
            detail={"path": rel_path, "errors": errors[:6]},
        )
        raise ValueError(f"{rel_path}: partial schema validation failed")

    return ctx.write_json(rel_path, out, stage_key=stage_key)
