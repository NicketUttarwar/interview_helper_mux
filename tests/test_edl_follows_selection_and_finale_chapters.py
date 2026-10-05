"""EDL follows the committed selection after an overlap merge, and the finale
rule reads the ranking's own chapters (ISSUES 176, exec_023)."""

from __future__ import annotations

from interview_mux.edl_overlap_repair import _drop_non_adjacent_transitions, _reorder_speech_blocks
from interview_mux.selection_order_repair import finale_tail_errors


def _sp(sid: str) -> dict:
    return {"type": "speech", "segment_id": sid}


def test_edl_blocks_follow_the_selection_order_with_their_vo() -> None:
    clips = [
        {"type": "vo_pickup", "line_id": "pre", "targets_segment_id": "seg_044", "placement": "before"},
        _sp("seg_044"),
        _sp("seg_045"),
        {"type": "transition", "after_segment_id": "seg_045", "before_segment_id": "seg_047"},
        _sp("seg_047"),
        {"type": "vo_pickup", "line_id": "vo_layup_seg_046", "targets_segment_id": "seg_046", "placement": "before"},
        _sp("seg_046"),
        _sp("seg_049"),
        {"type": "silence", "duration_ms": 400},
    ]
    out = _reorder_speech_blocks(clips, ["seg_044", "seg_046", "seg_045", "seg_047", "seg_049"])
    out = _drop_non_adjacent_transitions(out)
    order = [c["segment_id"] for c in out if c["type"] == "speech"]
    assert order == ["seg_044", "seg_046", "seg_045", "seg_047", "seg_049"]
    i = next(i for i, c in enumerate(out) if c.get("segment_id") == "seg_046")
    assert out[i - 1].get("line_id") == "vo_layup_seg_046"
    # seg_045 -> seg_047 are still neighbours, so their transition stays between them.
    seq = [c.get("segment_id") or c["type"] for c in out]
    t = seq.index("transition")
    assert seq[t - 1] == "seg_045" and seq[t + 1] == "seg_047"
    assert out[-1]["type"] == "silence"


def test_transition_left_between_non_neighbours_is_dropped() -> None:
    clips = [_sp("a"), {"type": "transition", "after_segment_id": "a", "before_segment_id": "b"}, _sp("b"), _sp("c")]
    out = _drop_non_adjacent_transitions(_reorder_speech_blocks(clips, ["b", "a", "c"]))
    assert not [c for c in out if c["type"] == "transition"]


def test_no_reorder_when_already_aligned_or_sets_differ() -> None:
    clips = [_sp("a"), _sp("b")]
    assert _reorder_speech_blocks(clips, ["a", "b"]) is None
    assert _reorder_speech_blocks(clips, ["a", "c"]) is None


PLAN = {
    "chapters": [
        {"segment_ids": ["seg_006", "seg_011"]},
        {"segment_ids": ["seg_045", "seg_046", "seg_047", "seg_049"]},
        {"segment_ids": ["seg_028", "seg_029", "seg_044"]},
    ]
}
ORDER = ["seg_006", "seg_011", "seg_028", "seg_029", "seg_044", "seg_045", "seg_047", "seg_046", "seg_049"]


def test_ranking_chapter_swap_is_not_a_finale_tail() -> None:
    assert finale_tail_errors(ORDER, PLAN)  # judged by the pre-ranking plan
    sel_chapters = [
        {"segment_ids": ["seg_006", "seg_011"]},
        {"segment_ids": ["seg_028", "seg_029", "seg_044"]},
        {"segment_ids": ["seg_045", "seg_047", "seg_046", "seg_049"]},
    ]
    assert finale_tail_errors(ORDER, PLAN, sel_chapters) == []


def test_real_early_chapter_after_the_finale_is_still_flagged() -> None:
    sel_chapters = [
        {"segment_ids": ["seg_006", "seg_011"]},
        {"segment_ids": ["seg_028", "seg_029", "seg_044"]},
        {"segment_ids": ["seg_045", "seg_047", "seg_046"]},
    ]
    order = ["seg_011", "seg_028", "seg_029", "seg_044", "seg_045", "seg_047", "seg_046", "seg_006"]
    assert finale_tail_errors(order, PLAN, sel_chapters)
