"""A segment-id remap of gap_report.json must write under the accepted body owner.

chapter_close_hitch remaps upstream refs after re-cutting the map. When a merge
folds two interviewer lines onto one target the remap counts as a body change,
and writing under the hitch's own key was refused:

    authority_denied:persist:understanding/gap_report.json:chapter_close_hitch:
    pre_soft_freeze:gap_framing_compose (gap_body_writers:gap_framing_compose|nugget_layup_compose)

The hitch failed, and delivery cascaded on a real 6-minute run.
"""

from __future__ import annotations

from interview_mux.artifact_ownership import assert_gap_report_body_sole_writer
from interview_mux.segment_id_remap import gap_report_remap_owner


def _report(authority: bool, texts: list[str]) -> dict:
    return {
        "nugget_layup_authority": authority,
        "interviewer_lines": [
            {"line_id": f"vo_seed_seg_{i:03d}", "targets_segment_id": f"seg_{i:03d}", "text": t}
            for i, t in enumerate(texts, 1)
        ],
    }


def test_owner_is_compose_before_authority_and_layup_after() -> None:
    assert gap_report_remap_owner(_report(False, ["a"])) == "gap_framing_compose"
    assert gap_report_remap_owner(_report(True, ["a"])) == "nugget_layup_compose"
    assert gap_report_remap_owner(None) == "gap_framing_compose"


def test_merge_folding_remap_is_accepted_under_the_named_owner() -> None:
    """Two lines folded onto one target is a body change; the named owner may make it."""
    prior = _report(False, ["What changed?", "And then?"])
    new = _report(False, ["What changed?"])  # a merge dropped the second target
    assert_gap_report_body_sole_writer(
        None, stage_key=gap_report_remap_owner(prior), prior=prior, new=new,
        mutation_class="segment_id_remap",
    )


def test_the_hitch_key_itself_is_still_refused() -> None:
    import pytest
    from interview_mux.artifact_ownership import AuthorityDenied

    prior = _report(False, ["What changed?", "And then?"])
    new = _report(False, ["What changed?"])
    with pytest.raises(AuthorityDenied):
        assert_gap_report_body_sole_writer(
            None, stage_key="chapter_close_hitch", prior=prior, new=new,
            mutation_class="segment_id_remap",
        )
