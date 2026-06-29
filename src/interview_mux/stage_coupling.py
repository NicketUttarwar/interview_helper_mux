"""Upstream/downstream stage contracts for segmentation pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.segment_timeline import (
    normalize_boundary_document,
    sort_segments_by_start_ms,
    validate_boundary_rows,
    validate_timeline_monotonic,
    segment_timeline_cfg,
)

CONTRACT_VERSION = 1


def publish_boundary_contract(
    boundaries_doc: dict[str, Any],
    *,
    timeline_errors: list[str] | None = None,
    publisher_stage: str = "boundary_detection",
) -> dict[str, Any]:
    """Attach segment_contract to boundaries document."""
    doc = normalize_boundary_document(boundaries_doc)
    boundaries = doc.get("boundaries") or []
    if not isinstance(boundaries, list):
        boundaries = []
    sorted_b = sort_segments_by_start_ms([b for b in boundaries if isinstance(b, dict)])
    segment_ids = [str(b["segment_id"]) for b in sorted_b if b.get("segment_id")]
    errors = timeline_errors if timeline_errors is not None else validate_boundary_rows(
        sorted_b,
        require_speaker_id=segment_timeline_cfg().get("require_speaker_id", True),
        allow_overlap_ms=int(segment_timeline_cfg().get("allow_overlap_ms", 0)),
    )
    meta = dict(doc.get("_meta") or {}) if isinstance(doc.get("_meta"), dict) else {}
    meta["segment_contract"] = {
        "version": CONTRACT_VERSION,
        "segment_ids": segment_ids,
        "segment_count": len(segment_ids),
        "timeline_valid": not errors,
        "timeline_errors": errors[:4],
        "sorted_by_start_ms": True,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "publisher_stage": publisher_stage,
    }
    return {**doc, "boundaries": sorted_b, "_meta": meta}


def read_segment_contract(boundaries_doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(boundaries_doc, dict):
        return None
    meta = boundaries_doc.get("_meta")
    if not isinstance(meta, dict):
        return None
    contract = meta.get("segment_contract")
    return contract if isinstance(contract, dict) else None


def contract_segment_ids(boundaries_doc: dict[str, Any] | None) -> list[str]:
    contract = read_segment_contract(boundaries_doc)
    if contract:
        ids = contract.get("segment_ids") or []
        return [str(x) for x in ids if x]
    boundaries = boundaries_doc.get("boundaries") or [] if isinstance(boundaries_doc, dict) else []
    return [
        str(b["segment_id"])
        for b in boundaries
        if isinstance(b, dict) and b.get("segment_id")
    ]


def contract_timeline_valid(boundaries_doc: dict[str, Any] | None) -> bool:
    contract = read_segment_contract(boundaries_doc)
    if contract is not None:
        return bool(contract.get("timeline_valid"))
    if not isinstance(boundaries_doc, dict):
        return False
    boundaries = boundaries_doc.get("boundaries") or []
    return not validate_timeline_monotonic(
        [b for b in boundaries if isinstance(b, dict)],
        allow_overlap_ms=int(segment_timeline_cfg().get("allow_overlap_ms", 0)),
    )
