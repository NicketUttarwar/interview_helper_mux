"""Validate LLM stage artifacts against JSON Schema (docs/cross-cutting/json-schemas/artifacts/)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from interview_mux.config import repo_root

# stage_key -> artifact schema filename (under artifacts/)
STAGE_ARTIFACT_SCHEMAS: dict[str, str] = {
    "speaker_roles": "speakers_artifact.schema.json",
    "content_context": "content_brief_artifact.schema.json",
    "boundary_detection": "boundaries_artifact.schema.json",
    "segment_classification": "manifest_artifact.schema.json",
    "sound_design_palettes": "sound_design_palettes_artifact.schema.json",
    "missing_framing": "gap_evaluations_artifact.schema.json",
    "optimal_questions": "gap_report.schema.json",
    "topic_coverage_audit": "coverage_audit_artifact.schema.json",
    "narrative_arc_plan": "narrative_plan_artifact.schema.json",
    "full_master_ranking": "master_selection_artifact.schema.json",
    "highlight_selection": "highlights_artifact.schema.json",
    "transitions": "transitions_artifact.schema.json",
    "podcast_sfx_brief": "podcast_sfx_artifact.schema.json",
    "sound_design_plan_flow1": "sound_design_plan_flow1_artifact.schema.json",
    "elevenlabs_prompt_craft": "elevenlabs_prompts_artifact.schema.json",
    "sfx_brief": "sfx_montage_artifact.schema.json",
    "podcast_show_description": "show_description_artifact.schema.json",
}


def _schemas_dir() -> Path:
    return repo_root() / "docs" / "cross-cutting" / "json-schemas" / "artifacts"


@lru_cache(maxsize=32)
def _load_schema(filename: str) -> dict[str, Any] | None:
    path = _schemas_dir() / filename
    if not path.is_file():
        # gap_report lives one level up
        alt = repo_root() / "docs" / "cross-cutting" / "json-schemas" / filename
        if alt.is_file():
            return json.loads(alt.read_text(encoding="utf-8"))
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validate_stage_artifacts(stage_key: str, artifacts: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors (empty if OK or no schema)."""
    filename = STAGE_ARTIFACT_SCHEMAS.get(stage_key)
    if not filename or not artifacts:
        return []
    schema = _load_schema(filename)
    if not schema:
        return []
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(artifacts), key=lambda e: list(e.path)):
        loc = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{loc}: {err.message}")
    return errors[:12]


def format_validation_feedback(errors: list[str]) -> str:
    return (
        "## Schema validation failed\n"
        "Fix `artifacts` to satisfy the stage schema. Errors:\n"
        + "\n".join(f"- {e}" for e in errors)
    )
