"""A rerun_stage need the walk satisfies itself does not fail the stage (ISSUES 177).

exec_024: boundary_topic_resplit answered partial with a blocking
"rerun content_brief_reanchor"; the resplit reruns segment_classification and
content_brief_reanchor itself right after it persists. The stage failed (3
errors) and only the retry passed.
"""

from __future__ import annotations

from interview_mux.llm_simple import is_walk_satisfied_need


def _need(stage: str) -> dict:
    return {"type": "rerun_stage", "stage": stage, "blocking": True}


def test_resplit_follow_up_stages_are_satisfied() -> None:
    assert is_walk_satisfied_need("boundary_topic_resplit", _need("content_brief_reanchor"))
    assert is_walk_satisfied_need("boundary_topic_resplit", _need("segment_classification"))


def test_later_stage_is_satisfied_by_the_walk() -> None:
    assert is_walk_satisfied_need("gap_framing_compose", _need("episode_structure_compose"))


def test_upstream_rerun_stays_blocking() -> None:
    assert not is_walk_satisfied_need("boundary_topic_resplit", _need("boundary_detection"))
    assert not is_walk_satisfied_need("full_master_ranking", _need("narrative_arc_plan"))


def test_other_need_types_and_self_are_untouched() -> None:
    assert not is_walk_satisfied_need("gap_framing_compose", {"type": "transcript_excerpt", "stage": "episode_structure_compose"})
    assert not is_walk_satisfied_need("gap_framing_compose", _need("gap_framing_compose"))
