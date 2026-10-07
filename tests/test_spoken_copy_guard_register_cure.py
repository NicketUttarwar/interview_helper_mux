"""A required line with a register slip is cured, not blocked (ISSUES 182).

The run this guards (granola 47-minute source, macOS exec_029): the
transitions LLM wrote the bridge for seg_044 -> seg_045 with a name
attribution ("Sam explains that ..."). The guard flagged
``spoken_name_attribution``; the pair had no topic evidence, so there was no
grounded hinge, the verdict was ``block`` with ``no_grounded_fallback``, the
stage failed and the attempt memo refused the retry. One wording slip in one
of ten transitions took delivery down. ISSUES 128 cures a repeated sentence
before blocking; a register slip is the same shape: a wording fault, not a
grounding fault.
"""

from __future__ import annotations

import pytest

from interview_mux.spoken_copy_guard import (
    _strip_name_attribution_clause,
    assert_guarded_spoken_copy,
    guard_spoken_copy,
    scrub_spoken_register,
    spoken_copy_violations,
)

_EVIDENCE = {
    "before_excerpt": "I said, like this idea of a professional chat roulette as part of your brain.",
    "after_excerpt": "I think a lot of the initial success is that it feels private, intimate, safe.",
    "source_gap_ms": 6320,
    "before_segment_id": "seg_045",
    "before_air_index": 30,
    "before_is_opening_tape": False,
}


def test_leading_name_attribution_is_cured_into_a_fallback() -> None:
    text = "Sam explains that balance gets sharper as AI work tools multiply."
    assert "spoken_name_attribution" in spoken_copy_violations(text, evidence=_EVIDENCE)
    decision = guard_spoken_copy(
        text, evidence=_EVIDENCE, required=True, purpose="transition_plan[seg_044->seg_045]"
    )
    assert decision["action"] == "fallback"
    assert decision["text"] == "Balance gets sharper as AI work tools multiply."
    assert not spoken_copy_violations(decision["text"], evidence=_EVIDENCE)


def test_the_asserting_wrapper_no_longer_raises_for_a_register_slip() -> None:
    text = "Sam describes how the product stays private as AI work tools multiply."
    decision = assert_guarded_spoken_copy(
        text, evidence=_EVIDENCE, purpose="transition_plan[seg_044->seg_045]"
    )
    assert decision["action"] == "fallback"
    assert decision["text"] == "The product stays private as AI work tools multiply."


def test_a_parenthetical_attribution_is_cured() -> None:
    text = "Private by default, as Sam explains, is what made the first minutes feel safe."
    cured = _strip_name_attribution_clause(text)
    assert cured == "Private by default is what made the first minutes feel safe."
    decision = guard_spoken_copy(text, evidence=_EVIDENCE, required=True, purpose="transition")
    assert decision["action"] == "fallback"
    assert decision["text"] == cured


def test_an_attribution_on_a_later_sentence_is_cured() -> None:
    text = "The clean surface came first. Sam adds that the harder question was when AI should step in."
    cured = _strip_name_attribution_clause(text)
    assert cured == (
        "The clean surface came first. The harder question was when AI should step in."
    )


def test_a_role_label_attribution_is_cured_through_the_same_path() -> None:
    text = "The host adds that the clean surface came from an earlier question."
    decision = guard_spoken_copy(text, evidence=_EVIDENCE, required=True, purpose="transition")
    assert decision["action"] == "fallback"
    assert decision["text"] == "The clean surface came from an earlier question."


def test_a_line_that_is_only_an_attribution_still_blocks() -> None:
    text = "Sam explains."
    with pytest.raises(ValueError, match="spoken_copy_guard"):
        assert_guarded_spoken_copy(text, evidence=_EVIDENCE, purpose="transition")


def test_a_clean_line_is_untouched() -> None:
    text = "That balance gets sharper as AI work tools multiply."
    assert scrub_spoken_register(text) == text
    decision = guard_spoken_copy(text, evidence=_EVIDENCE, required=True, purpose="transition")
    assert decision["action"] == "allow"
    assert decision["text"] == text
