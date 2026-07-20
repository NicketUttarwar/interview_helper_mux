"""Minimal tone/format taxonomy helpers for analysis profile validation."""

from __future__ import annotations

from typing import Any

OPERATOR_LOCKABLE_IDENTITY_FIELDS = frozenset(
    {"interview_identity", "themes", "major_questions", "entities", "speakers"}
)
OPERATOR_LOCKABLE_STYLE_FIELDS = frozenset({"style", "narrative", "confidence"})

FORMAT_CLASS_VALUES = frozenset(
    {"one_on_one", "panel", "fireside", "debate", "tutorial", "unknown"}
)
TONE_CLASS_VALUES = frozenset(
    {"conversational", "journalistic", "intimate", "energetic", "formal", "unknown"}
)


def validate_format_class(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s in FORMAT_CLASS_VALUES else None


def validate_tone_class(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s in TONE_CLASS_VALUES else None


def compact_profile_style_hints(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    style = state.get("style")
    return {"style": style} if isinstance(style, dict) else {}
