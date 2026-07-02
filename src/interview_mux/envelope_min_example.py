"""Canonical typed min-examples for analysis envelope fields (prompts + schema hints)."""

from __future__ import annotations

import copy
from typing import Any

# Sample memory_updates — one row per common patch key so models see expected shapes.
MEMORY_UPDATES_MIN_EXAMPLE: dict[str, Any] = {
    "themes_append": [
        {
            "id": "theme_sample",
            "label": "Sample theme",
            "summary": "One-line theme summary from transcript.",
            "segment_ids": ["seg_001"],
            "confidence": 0.8,
            "sources": ["stage_key"],
        }
    ],
    "major_questions_append": [
        {
            "question": "Sample open question from the interview?",
            "segment_ids": ["seg_002"],
            "priority": "medium",
        }
    ],
    "style_patch": {
        "tone": "conversational and direct",
        "tone_class": "conversational",
        "format_class": "one_on_one",
        "format_notes": "Single guest Q&A",
        "pacing": "moderate",
        "interviewer_style": "curious",
        "interviewee_style": "reflective",
    },
    "narrative_patch": {"thesis": "Sample thesis line.", "audience": "General podcast listeners"},
    "interview_identity_patch": {
        "one_line_summary": "Guest discusses topic X in depth.",
        "title": "Optional episode title",
    },
    "entities_append": ["Sample Entity"],
    "hypotheses_append": [
        {
            "id": "hyp_sample",
            "statement": "Tentative interpretation to verify later.",
            "status": "open",
            "evidence_segment_ids": ["seg_003"],
        }
    ],
    "confidence_patch": {"overall": 0.85, "content": 0.85},
    "segment_summary_patch": {"seg_001": "Brief segment gist."},
    "gaps_summary_patch": {"open_count": 0},
}

NEEDS_MIN_EXAMPLE: list[dict[str, Any]] = [
    {
        "type": "operator",
        "stage": None,
        "reason": "Use only when human input is required; empty [] when none.",
        "blocking": False,
        "params": {},
    }
]

FOLLOW_UP_INVESTIGATIONS_MIN_EXAMPLE: list[dict[str, Any]] = [
    {
        "kind": "theme_unmapped",
        "question": "Which segment covers this theme?",
        "priority": "medium",
        "blocking": False,
        "suggested_action": {"type": "rerun_stage", "stage": "segment_classification"},
        "target": {"topic_name": "sample_topic"},
    }
]

ARTIFACTS_PLACEHOLDER_MIN_EXAMPLE: dict[str, Any] = {
    "_schema_hint": "Replace with stage-specific artifact keys from the stage prompt",
}


def build_envelope_min_example(
    *,
    artifacts: dict[str, Any] | None = None,
    include_optional_arrays: bool = True,
) -> dict[str, Any]:
    """
    Return a fully typed envelope min-example for prompts and format blocks.

    ``include_optional_arrays`` — when True, ``needs`` and ``follow_up_investigations``
    include one sample row (teaching shape). When False, those arrays are empty.
    """
    art = artifacts if artifacts is not None else copy.deepcopy(ARTIFACTS_PLACEHOLDER_MIN_EXAMPLE)
    return {
        "status": "complete",
        "artifacts": copy.deepcopy(art) if isinstance(art, dict) else art,
        "memory_updates": copy.deepcopy(MEMORY_UPDATES_MIN_EXAMPLE),
        "needs": copy.deepcopy(NEEDS_MIN_EXAMPLE) if include_optional_arrays else [],
        "follow_up_investigations": (
            copy.deepcopy(FOLLOW_UP_INVESTIGATIONS_MIN_EXAMPLE) if include_optional_arrays else []
        ),
        "confidence": 0.85,
        "reasoning_summary": "2-5 sentences summarizing conclusions for the next stage.",
    }


# Back-compat alias used by required_response_format and prompt_validation.
ENVELOPE_SKELETON: dict[str, Any] = build_envelope_min_example()
