"""Shared tone and interview-format taxonomy for analysis profile and downstream stages."""

from __future__ import annotations

from typing import Any

TONE_CLASS_VALUES: tuple[str, ...] = (
    "journalistic",
    "conversational",
    "investor",
    "technical",
    "human_interest",
)

FORMAT_CLASS_VALUES: tuple[str, ...] = (
    "one_on_one",
    "panel",
    "fireside",
    "technical_deep_dive",
    "media_profile",
    "debate",
)

OPERATOR_LOCKABLE_STYLE_FIELDS: tuple[str, ...] = (
    "style.tone",
    "style.tone_class",
    "style.format_class",
    "style.format_notes",
    "style.pacing",
    "style.interviewer_style",
    "style.interviewee_style",
)

OPERATOR_LOCKABLE_IDENTITY_FIELDS: tuple[str, ...] = (
    "interview_identity.title",
    "interview_identity.one_line_summary",
)


def validate_tone_class(value: str | None) -> bool:
    return isinstance(value, str) and value in TONE_CLASS_VALUES


def validate_format_class(value: str | None) -> bool:
    return isinstance(value, str) and value in FORMAT_CLASS_VALUES


def tone_class_for_show_description(state: dict[str, Any] | None) -> str | None:
    """Return profile tone_class when valid, else None."""
    if not isinstance(state, dict):
        return None
    style = state.get("style") or {}
    if not isinstance(style, dict):
        return None
    tc = style.get("tone_class")
    return tc if validate_tone_class(tc) else None


def format_class_from_state(state: dict[str, Any] | None) -> str | None:
    if not isinstance(state, dict):
        return None
    style = state.get("style") or {}
    if not isinstance(style, dict):
        return None
    fc = style.get("format_class")
    return fc if validate_format_class(fc) else None


def compact_profile_style_hints(state: dict[str, Any] | None) -> dict[str, str]:
    """Compact tone/format hints for stage input injection."""
    if not isinstance(state, dict):
        return {}
    style = state.get("style") or {}
    if not isinstance(style, dict):
        return {}
    out: dict[str, str] = {}
    tc = style.get("tone_class")
    if validate_tone_class(tc):
        out["tone_class"] = tc
    fc = style.get("format_class")
    if validate_format_class(fc):
        out["format_class"] = fc
    if style.get("tone"):
        out["tone_nuance"] = str(style["tone"])[:240]
    if style.get("format_notes"):
        out["format_notes"] = str(style["format_notes"])[:240]
    return out
