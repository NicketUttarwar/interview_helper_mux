"""Chapter labels follow the locked air order under the hard freeze (ISSUES 152).

exec_013: edl_narrative_audit failed "chapter_continuity_broken" (chapter 2 at air
positions 11, 12, 15 with chapter 3 at 13-14); the hard-freeze branch of the audit
repair skipped every selection write, so the true blocker could never clear.
"""

from __future__ import annotations

from interview_mux.artifact_repairs import relabel_chapters_contiguous


def test_returning_chapter_merges_into_the_run_before_it() -> None:
    sel = {
        "ordered_segment_ids": ["a", "b", "c", "d", "e"],
        "chapters": [
            {"title": "two", "segment_ids": ["a", "b", "e"]},
            {"title": "three", "segment_ids": ["c", "d"]},
        ],
    }
    out, changed = relabel_chapters_contiguous(sel)
    assert changed
    assert out["ordered_segment_ids"] == sel["ordered_segment_ids"]
    assert [c["segment_ids"] for c in out["chapters"]] == [["a", "b"], ["c", "d", "e"]]


def test_unowned_opening_joins_the_first_chapter() -> None:
    sel = {
        "ordered_segment_ids": ["o1", "o2", "a", "b"],
        "chapters": [{"title": "one", "segment_ids": ["a", "b"]}],
    }
    out, changed = relabel_chapters_contiguous(sel)
    assert changed and out["chapters"][0]["segment_ids"] == ["o1", "o2", "a", "b"]


def test_contiguous_chapters_are_left_alone() -> None:
    sel = {
        "ordered_segment_ids": ["a", "b", "c"],
        "chapters": [{"segment_ids": ["a"]}, {"segment_ids": ["b", "c"]}],
    }
    out, changed = relabel_chapters_contiguous(sel)
    assert not changed and out is sel
