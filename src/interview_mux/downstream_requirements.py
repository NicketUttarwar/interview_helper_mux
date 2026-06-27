"""Downstream-required artifact fields for local gap-fill after partial persist."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RequirementKind = Literal["required", "fill_if_missing"]


@dataclass(frozen=True)
class FieldRequirement:
    artifact_path: str
    field_path: str
    kind: RequirementKind


STAGE_FIELD_REQUIREMENTS: dict[str, tuple[FieldRequirement, ...]] = {
    "content_context": (
        FieldRequirement("understanding/content_brief.json", "thesis", "required"),
        FieldRequirement("understanding/content_brief.json", "topics", "required"),
        FieldRequirement(
            "understanding/content_brief.json",
            "key_claims[].approx_time_range",
            "fill_if_missing",
        ),
    ),
    "speaker_roles": (
        FieldRequirement("understanding/speakers.json", "speakers", "required"),
    ),
}


def requirements_for_stage(stage_key: str) -> tuple[FieldRequirement, ...]:
    return STAGE_FIELD_REQUIREMENTS.get(stage_key, ())


def _claim_has_time_anchor(claim: dict[str, Any]) -> bool:
    if claim.get("approx_time_range"):
        return True
    for key in ("segment_ids", "evidence_segment_ids"):
        ids = claim.get(key)
        if isinstance(ids, list) and ids:
            return True
    return False


def list_fill_if_missing_gaps(
    stage_key: str,
    artifact_path: str,
    data: dict[str, Any] | None,
) -> list[str]:
    """Return dotted paths that need gap-fill (fill_if_missing only)."""
    if not data:
        return []
    gaps: list[str] = []
    for req in requirements_for_stage(stage_key):
        if req.artifact_path != artifact_path or req.kind != "fill_if_missing":
            continue
        if req.field_path == "key_claims[].approx_time_range":
            claims = data.get("key_claims") or []
            for i, claim in enumerate(claims):
                if isinstance(claim, dict) and not _claim_has_time_anchor(claim):
                    if str(claim.get("claim") or claim.get("text") or "").strip():
                        gaps.append(f"key_claims[{i}].approx_time_range")
    return gaps
