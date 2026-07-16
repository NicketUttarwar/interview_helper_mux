"""Central timeline standard for boundary_detection and segment_classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interview_mux.config import merged_config
from interview_mux.segment_timeline import validate_boundary_rows
from interview_mux.stage_coupling import contract_segment_ids


def segmentation_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    raw = analysis.get("segmentation") or {}
    defaults = {
        "reject_invalid_shards": True,
        "deterministic_collate_authoritative": True,
        "deterministic_classification_collate_authoritative": True,
        "block_invalid_boundary_commit": True,
        "block_partial_classification": True,
        "fabricate_missing_segments": True,
        "require_type_diversity": True,
        "enforce_field_parity": True,
        "drop_orphan_manifest_rows": True,
        "boundary_proactive_decompose_pace_classes": ["calm", "brisk"],
    }
    return {**defaults, **raw}


def normalize_boundary_rows(
    rows: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from interview_mux.boundary_collate import normalize_boundary_timeline

    return normalize_boundary_timeline(rows, cfg=cfg)


def validate_boundary_timeline(
    rows: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[str]:
    from interview_mux.segment_timeline import segment_timeline_cfg

    st_cfg = segment_timeline_cfg(cfg)
    return validate_boundary_rows(
        rows,
        require_speaker_id=bool(st_cfg.get("require_speaker_id", True)),
        allow_overlap_ms=int(st_cfg.get("allow_overlap_ms", 0)),
    )


def contract_ordered_segment_ids(boundaries_doc: dict[str, Any] | None) -> list[str]:
    return contract_segment_ids(boundaries_doc)


def boundary_rows_from_envelope(env: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = env.get("artifacts") if isinstance(env, dict) else {}
    if not isinstance(artifacts, dict):
        return []
    boundaries = artifacts.get("boundaries") or []
    if not isinstance(boundaries, list):
        return []
    return [dict(row) for row in boundaries if isinstance(row, dict)]


def normalize_shard_envelope(
    env: dict[str, Any],
    shard_meta: dict[str, Any] | None = None,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize boundary rows inside a shard envelope."""
    if not isinstance(env, dict):
        return env
    rows = boundary_rows_from_envelope(env)
    if not rows:
        return env
    normalized, applied = normalize_boundary_rows(rows, cfg=cfg)
    if not normalized and not applied:
        return env
    merged = dict(env)
    artifacts = dict(merged.get("artifacts") or {})
    artifacts["boundaries"] = normalized
    merged["artifacts"] = artifacts
    routing = dict(merged.get("_routing_meta") or {})
    if applied:
        routing["shard_timeline_repair"] = applied[:12]
        routing["shard_timeline_repair_count"] = len(applied)
    if shard_meta:
        routing["shard_label"] = shard_meta.get("label")
    merged["_routing_meta"] = routing
    return merged


@dataclass
class ShardRejectResult:
    rejected: bool
    errors: list[str]


def reject_or_repair_shard(stage_key: str, env: dict[str, Any], *, cfg: dict[str, Any] | None = None) -> ShardRejectResult:
    """Return rejected=True when shard timeline is invalid after normalize."""
    if stage_key != "boundary_detection":
        return ShardRejectResult(rejected=False, errors=[])
    seg_cfg = segmentation_cfg(cfg)
    if not seg_cfg.get("reject_invalid_shards", True):
        return ShardRejectResult(rejected=False, errors=[])
    rows = boundary_rows_from_envelope(env)
    if not rows:
        return ShardRejectResult(rejected=True, errors=["no boundaries in shard"])
    errors = validate_boundary_timeline(rows, cfg=cfg)
    return ShardRejectResult(rejected=bool(errors), errors=errors)


def _preview_segment_ids(rows: list[dict[str, Any]], *, limit: int = 12) -> list[str]:
    ids: list[str] = []
    for row in rows:
        sid = str(row.get("segment_id") or "")
        if sid:
            ids.append(sid)
        if len(ids) >= limit:
            break
    return ids


def format_shard_identity(
    shard: dict[str, Any] | None,
    stage_key: str,
    env: dict[str, Any] | None = None,
) -> str:
    """Human-readable shard identity for volley memory and collate volleys."""
    shard = shard or {}
    label = str(shard.get("label") or "shard")
    rows = boundary_rows_from_envelope(env or {})
    boundary_count = len(rows)
    seg_ids = [str(x) for x in (shard.get("segment_ids") or []) if x]
    if not seg_ids and rows:
        seg_ids = _preview_segment_ids(rows)

    start_ms = shard.get("start_ms")
    end_ms = shard.get("end_ms")
    if stage_key == "boundary_detection" and start_ms is not None and end_ms is not None:
        span = f"{label} ({int(start_ms)}–{int(end_ms)} ms"
        if boundary_count:
            span += f", {boundary_count} boundaries"
        return span + ")"

    if seg_ids:
        preview = ", ".join(seg_ids[:12])
        if len(seg_ids) > 12:
            preview += "…"
        return preview

    if boundary_count:
        return f"{label} ({boundary_count} boundaries)"

    return label
