"""Per-join POV / line_category chooser for reorder bridges (succinct bias)."""

from __future__ import annotations

from typing import Any

# Soft word budgets for compose prompts
QUESTION_MAX_WORDS = 18
BRIDGE_MAX_WORDS = 35
SUMMARY_MAX_WORDS = 40


def choose_bridge_voice(pair: dict[str, Any], *, narrative_mode: str | None = None) -> dict[str, Any]:
    """Return suggested_line_category, suggested_pov, max_words for one adjacency."""
    kind = str(pair.get("kind") or "reorder")
    mode = str(narrative_mode or "")
    gap = pair.get("source_gap_ms")
    try:
        gap_i = int(gap) if gap is not None else None
    except (TypeError, ValueError):
        gap_i = None

    # Default documentary lean for big jumps / chapter hinges
    if kind == "chapter_jump" or (gap_i is not None and abs(gap_i) > 120_000):
        pov = "expository_third_person"
        category = "story_bridge"
        max_words = BRIDGE_MAX_WORDS
    elif kind == "split_sibling":
        # Short host prompt often smoothest
        pov = "host_second_person"
        category = "framing_question"
        max_words = QUESTION_MAX_WORDS
    elif gap_i is not None and gap_i < 0:
        # Backward in source time — need orientation
        pov = "expository_third_person"
        category = "extracted_context"
        max_words = BRIDGE_MAX_WORDS
    else:
        pov = "host_second_person"
        category = "framing_question"
        max_words = QUESTION_MAX_WORDS

    if mode == "documentary_bridge":
        pov = "expository_third_person"
        if category == "framing_question":
            category = "story_bridge"
            max_words = BRIDGE_MAX_WORDS
    elif mode in {"conversational_host", "sparse_source"} and category == "story_bridge":
        pov = "host_second_person"

    return {
        **pair,
        "suggested_line_category": category,
        "suggested_pov": pov,
        "max_words": max_words,
    }


def annotate_reorder_bridges(
    doc: dict[str, Any],
    *,
    narrative_mode: str | None = None,
) -> dict[str, Any]:
    pairs = [choose_bridge_voice(p, narrative_mode=narrative_mode) for p in (doc.get("pairs") or []) if isinstance(p, dict)]
    out = dict(doc)
    out["pairs"] = pairs
    out["count"] = len(pairs)
    return out
