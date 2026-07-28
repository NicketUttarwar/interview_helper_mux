"""Validated artifact writes with optional merge from on-disk state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.artifact_repairs import is_manifest_segment_id
from interview_mux.null_field_policy import omit_nullable_null_leaves_for_disk, stage_key_for_artifact_path
from interview_mux.prompt_validation import validate_artifact_write
from interview_mux.run_context import RunContext


def _prepare_for_disk_validation(
    out: dict[str, Any],
    *,
    rel_path: str,
    stage_key: str | None,
) -> dict[str, Any]:
    sk = stage_key or stage_key_for_artifact_path(rel_path)
    if not sk:
        return out
    return omit_nullable_null_leaves_for_disk(sk, out)


def _prepare_segment_artifact(
    ctx: RunContext,
    rel_path: str,
    out: dict[str, Any],
    *,
    stage_key: str | None = None,
) -> dict[str, Any]:
    if rel_path == "segments/boundaries.json":
        from interview_mux.segment_timeline import normalize_boundary_document, segment_timeline_cfg
        from interview_mux.segment_timeline_standard import (
            normalize_boundary_rows,
            segmentation_cfg,
            validate_boundary_timeline,
        )
        from interview_mux.stage_coupling import publish_boundary_contract, read_segment_contract

        boundaries = out.get("boundaries") or []
        if isinstance(boundaries, list):
            from interview_mux.artifact_repairs import repair_boundaries

            out, _repair_actions = repair_boundaries(ctx, out)
            boundaries = out.get("boundaries") or []
            repaired_rows, _actions = normalize_boundary_rows(
                [row for row in boundaries if isinstance(row, dict)]
            )
            if repaired_rows:
                out = {**out, "boundaries": repaired_rows}
        normalized = normalize_boundary_document(out)
        boundaries = normalized.get("boundaries") or []
        errors = validate_boundary_timeline([b for b in boundaries if isinstance(b, dict)])
        published = publish_boundary_contract(
            normalized,
            timeline_errors=errors,
            publisher_stage=stage_key or "boundary_detection",
        )
        if segmentation_cfg().get("block_invalid_boundary_commit", True):
            contract = read_segment_contract(published) or {}
            if not contract.get("timeline_valid"):
                detail = (contract.get("timeline_errors") or errors or ["timeline invalid"])[:2]
                raise ValueError(
                    f"segments/boundaries.json: cannot commit invalid timeline — {'; '.join(str(x) for x in detail)}"
                )
        return published

    if rel_path == "segments/manifest.json":
        from interview_mux.artifact_completeness import hydrate_manifest_from_boundaries

        boundary_doc = None
        if ctx.artifact_exists("segments/boundaries.json"):
            boundary_doc = ctx.read_json("segments/boundaries.json")
        out = hydrate_manifest_from_boundaries(ctx, out)
        from interview_mux.segment_timeline import normalize_manifest_document

        return normalize_manifest_document(
            out,
            boundary_doc if isinstance(boundary_doc, dict) else None,
            overwrite_times=True,
        )

    return out


def _validate_canonical_segment_ids(rel_path: str, out: dict[str, Any]) -> None:
    from interview_mux.segment_timeline_standard import segmentation_cfg

    if not segmentation_cfg().get("enforce_canonical_segment_id_format", True):
        return
    bad: list[str] = []
    if rel_path == "segments/boundaries.json":
        for row in out.get("boundaries") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                sid = str(row["segment_id"])
                if not is_manifest_segment_id(sid):
                    bad.append(sid)
    elif rel_path == "segments/manifest.json":
        for row in out.get("segments") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                sid = str(row["segment_id"])
                if not is_manifest_segment_id(sid):
                    bad.append(sid)
    if bad:
        raise ValueError(
            f"{rel_path}: non-canonical segment_id format(s): {', '.join(sorted(set(bad))[:4])}"
        )


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

    out = _prepare_segment_artifact(ctx, rel_path, out, stage_key=stage_key)
    _validate_canonical_segment_ids(rel_path, out)

    if rel_path == "segments/boundaries.json":
        from interview_mux.artifact_repairs import sync_content_brief_topic_segment_ids

        sync_content_brief_topic_segment_ids(ctx)

    if rel_path == "segments/manifest.json":
        pass  # already hydrated in _prepare_segment_artifact

    # Normalize LLM nulls / coherence coupling before disk schema + post-commit lint.
    from interview_mux.artifact_repairs import apply_repairs_for_stage

    sk = stage_key or None
    out, _ = apply_repairs_for_stage(ctx, sk or "", out, rel_path=rel_path)

    out = _prepare_for_disk_validation(out, rel_path=rel_path, stage_key=stage_key)

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

    out = _prepare_segment_artifact(ctx, rel_path, out, stage_key=stage_key)

    out = _prepare_for_disk_validation(out, rel_path=rel_path, stage_key=stage_key)

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
