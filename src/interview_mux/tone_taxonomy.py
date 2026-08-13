"""Minimal tone/format taxonomy helpers for analysis profile validation."""

from __future__ import annotations

from typing import Any

OPERATOR_LOCKABLE_IDENTITY_FIELDS = frozenset(
    {"interview_identity", "themes", "major_questions", "entities", "speakers"}
)
OPERATOR_LOCKABLE_STYLE_FIELDS = frozenset({"style", "narrative", "confidence"})

# Keep in sync with analysis_state.schema.json / speakers_artifact.schema.json.
FORMAT_CLASS_VALUES = frozenset(
    {
        "one_on_one",
        "panel",
        "fireside",
        "technical_deep_dive",
        "media_profile",
        "debate",
    }
)
TONE_CLASS_VALUES = frozenset(
    {
        "journalistic",
        "conversational",
        "investor",
        "technical",
        "human_interest",
    }
)

# Map common near-miss LLM labels onto the locked enum (schema-aligned).
_TONE_CLASS_ALIASES = {
    "human interest": "human_interest",
    "human-interest": "human_interest",
    "warm": "human_interest",
    "intimate": "human_interest",
    "energetic": "conversational",
    "formal": "journalistic",
    "business": "investor",
    "tech": "technical",
    "unknown": "conversational",
}
_FORMAT_CLASS_ALIASES = {
    "one-on-one": "one_on_one",
    "1on1": "one_on_one",
    "deep_dive": "technical_deep_dive",
    "technical deep dive": "technical_deep_dive",
    "tutorial": "technical_deep_dive",
    "unknown": "one_on_one",
}


def validate_format_class(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s in FORMAT_CLASS_VALUES:
        return s
    aliased = _FORMAT_CLASS_ALIASES.get(s.lower())
    return aliased if aliased in FORMAT_CLASS_VALUES else None


def validate_tone_class(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s in TONE_CLASS_VALUES:
        return s
    aliased = _TONE_CLASS_ALIASES.get(s.lower())
    return aliased if aliased in TONE_CLASS_VALUES else None


def compact_profile_style_hints(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    style = state.get("style")
    return {"style": style} if isinstance(style, dict) else {}
