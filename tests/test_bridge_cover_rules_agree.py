"""Bridge completeness agrees with the framing seam rule (ISSUES 151).

Clone adjacency moves a layup line to placement "after" on the prior native;
gap_framing._gap_line_covers_seam counts that as covering the seam, so the mint
skips the pair, while missing_reorder_bridges kept demanding glue and the
transitions stage refused on every attempt.
"""

from __future__ import annotations

from interview_mux.bridge_completeness import missing_reorder_bridges

PAIRS = {"pairs": [{"after_segment_id": "seg_029", "before_segment_id": "seg_031", "kind": "reorder"}]}


def _gap(placement: str, target: str) -> dict:
    return {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_031",
                "delivery": "synthesize",
                "text": "That is where the cost argument turns.",
                "targets_segment_id": target,
                "placement": placement,
            }
        ]
    }


def test_a_line_seated_after_the_prior_native_covers_the_pair() -> None:
    assert missing_reorder_bridges(PAIRS, gap_report=_gap("after", "seg_029")) == []


def test_a_line_before_the_destination_still_covers() -> None:
    assert missing_reorder_bridges(PAIRS, gap_report=_gap("before", "seg_031")) == []


def test_an_unrelated_line_does_not_cover() -> None:
    assert missing_reorder_bridges(PAIRS, gap_report=_gap("after", "seg_010"))
