"""Field necessity tiers for LLM output normalization (omit | fabricate | block)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from interview_mux.field_path_match import normalize_field_path, path_matches_pattern
from interview_mux.null_field_policy import (
    critical_fields_for_stage,
    nullable_fields_for_stage,
)
from interview_mux.openai_structured_output import resolve_parent_stage_key

# Evidentiary / structural paths — never fabricate.
NEVER_FABRICATE_PATHS: frozenset[str] = frozenset(
    {
        "segment_ids",
        "evidence_segment_ids",
        "topics[].segment_ids",
        "key_claims[].segment_ids",
        "key_claims[].evidence_segment_ids",
        "start_ms",
        "end_ms",
        "approx_time_range",
        "key_claims[].approx_time_range",
        "topics[].approx_time_range",
        "speaker_id",
        "speakers[].speaker_id",
        "role",
        "speakers[].role",
        "thesis",
        "boundaries",
        "boundaries[].segment_id",
        "boundaries[].start_ms",
        "boundaries[].end_ms",
        "before_segment_id",
        "after_segment_id",
        "ordered_segment_ids",
        "segments[].segment_id",
        "segments[].type",
        "coverage_score",
        "speakers",
        "topics",
        "topics[].name",
        "topics[].summary",
        "segments",
        "evaluations",
        "gaps",
        "highlights",
        "transitions",
        "chapters",
        "description",
    }
)

# Prefer omit over fabricate when null.
COMMENTARY_FIELD_PATTERNS: frozenset[str] = frozenset(
    {
        "notes",
        "warnings",
        "segments[].notes",
        "evaluations[].notes",
        "gaps[].notes",
        "transitions[].notes",
        "ordering_constraints",
        "subtitle",
        "keywords",
        "format_notes",
        "pacing",
        "interviewer_style",
        "interviewee_style",
    }
)

# Low-risk leaves — auto-fabricate when null or type-mismatched (permissive default).
GLOBAL_FABRICATABLE_LEAVES: frozenset[str] = frozenset(
    {
        "audience",
        "subtitle",
        "keywords",
        "label",
        "description",
        "tone",
        "tone_class",
        "format_class",
        "confidence",
        "reason",
        "title",
        "one_line_summary",
    }
)

FABRICATABLE_FIELDS: dict[str, frozenset[str]] = {
    "speaker_roles": frozenset({"notes"}),
    "content_context": frozenset({"audience", "emotional_beats", "jargon_glossary", "key_claims"}),
    "content_brief_reanchor": frozenset({"audience", "emotional_beats", "jargon_glossary", "key_claims"}),
    "boundary_detection": frozenset({"notes", "warnings"}),
    "segment_classification": frozenset({"segments[].notes", "segments[].topic_tags"}),
    "missing_framing": frozenset({"evaluations[].notes"}),
    "optimal_questions": frozenset({"gaps[].notes"}),
    "topic_coverage_audit": frozenset({"notes", "gaps"}),
    "narrative_arc_plan": frozenset({"notes", "ordering_constraints"}),
    "full_master_ranking": frozenset({"notes", "excluded_segment_ids"}),
    "highlight_selection": frozenset({"notes"}),
    "transitions": frozenset({"transitions[].notes"}),
    "podcast_show_description": frozenset({"subtitle", "keywords"}),
    "podcast_sfx_brief": frozenset({"notes"}),
    "sfx_brief": frozenset({"notes"}),
    "sfx_prompt_craft": frozenset({"notes"}),
    "sound_design_palettes": frozenset({"notes"}),
    "sound_design_plan_flow1": frozenset({"notes"}),
    "sound_design_plan_flow2": frozenset({"notes"}),
    "edl_narrative_audit": frozenset({"notes"}),
}


class FieldAction(str, Enum):
    OMIT = "omit"
    FABRICATE = "fabricate"
    BLOCK = "block"


def _is_never_fabricate(path: str) -> bool:
    norm = normalize_field_path(path)
    for pat in NEVER_FABRICATE_PATHS:
        if path_matches_pattern(norm, pat):
            return True
    return False


def _is_critical(stage_key: str, path: str) -> bool:
    for pat in critical_fields_for_stage(stage_key):
        if path_matches_pattern(path, pat):
            return True
    return False


def _is_nullable(stage_key: str, path: str) -> bool:
    for pat in nullable_fields_for_stage(stage_key):
        if path_matches_pattern(path, pat):
            return True
    norm = normalize_field_path(path)
    for pat in COMMENTARY_FIELD_PATTERNS:
        if path_matches_pattern(norm, pat):
            return True
    return False


def _is_fabricatable(stage_key: str, path: str) -> bool:
    for pat in FABRICATABLE_FIELDS.get(stage_key, frozenset()):
        if path_matches_pattern(path, pat):
            return True
    norm = normalize_field_path(path)
    leaf = norm.split(".")[-1] if norm else norm
    if leaf in GLOBAL_FABRICATABLE_LEAVES:
        return True
    return False


def classify_field_path(
    stage_key: str | None,
    path: str,
    *,
    prefer_omit: bool = True,
    permissive: bool = True,
) -> FieldAction:
    """Decide omit | fabricate | block for a null or type-mismatch field path."""
    sk = resolve_parent_stage_key(stage_key or "") or stage_key or ""
    norm = normalize_field_path(path)
    leaf = norm.split(".")[-1] if norm else norm

    if _is_never_fabricate(norm) or _is_critical(sk, norm):
        return FieldAction.BLOCK

    if _is_nullable(sk, norm) or (prefer_omit and leaf in {"notes", "warnings"}):
        return FieldAction.OMIT

    if _is_fabricatable(sk, norm):
        return FieldAction.FABRICATE

    if leaf in {"notes", "warnings", "subtitle", "keywords"}:
        return FieldAction.OMIT

    # Permissive default: auto-repair unknown optional fields instead of blocking.
    if permissive:
        return FieldAction.FABRICATE

    return FieldAction.BLOCK


def parse_verification_error_path(error: str) -> str | None:
    """Extract artifact field path from jsonschema error message."""
    err = error.strip()
    if ": " not in err:
        return None
    loc = err.split(": ", 1)[0].strip()
    for prefix in ("envelope.artifacts.", "artifacts.", "envelope."):
        if loc.startswith(prefix):
            loc = loc[len(prefix) :]
            break
    if loc in ("(root)", "root"):
        return None
    return loc
