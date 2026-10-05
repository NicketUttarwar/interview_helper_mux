"""A garbled sign-off cut as its own segment after the closing sponsor read is not story (ISSUES 170).

exec_020: seg_050 "You are listening to usHS\\ufffd bone and cut-" followed the
closing CTA parent seg_049 as a top-level segment and aired as the episode's
last clip; the child-based checks never looked at it.
"""

from __future__ import annotations

from interview_mux.media_ip_cta import _tape_tail_scrap_ids

BY_ID = {
    "seg_048": {"start_ms": 3_400_000, "end_ms": 3_450_000, "text": "Diagnosis is much better than cure."},
    "seg_049": {"start_ms": 3_506_320, "end_ms": 3_538_260, "text": "Thanks again to our sponsor, Agilisium Labs."},
    "seg_050": {"start_ms": 3_562_180, "end_ms": 3_567_460, "text": "You are listening to usHS� bone and cut -"},
}


def test_scrap_after_closing_sponsor_read_is_taken() -> None:
    assert _tape_tail_scrap_ids(BY_ID, ["seg_048", "seg_050"], {"seg_049"}) == {"seg_050"}


def test_closing_story_after_the_outro_stays() -> None:
    by_id = dict(BY_ID)
    by_id["seg_050"] = {"start_ms": 3_562_180, "end_ms": 3_590_000, "text": "One more thought on how early detection changes treatment decisions for patients."}
    assert _tape_tail_scrap_ids(by_id, ["seg_048", "seg_050"], {"seg_049"}) == set()


def test_no_closing_sponsor_near_the_end_means_no_tail() -> None:
    by_id = dict(BY_ID)
    by_id["seg_049"] = {"start_ms": 100_000, "end_ms": 130_000, "text": "Sponsor read."}
    assert _tape_tail_scrap_ids(by_id, ["seg_048", "seg_050"], {"seg_049"}) == set()


def test_tail_child_between_excluded_siblings_is_taken() -> None:
    """exec_022 (ISSUES 174): seg_031a-h and j-k excluded, seg_031i aired as the last clip."""
    from interview_mux.media_ip_cta import _closing_outro_tail_ids

    by_id = {f"seg_031{c}": {"start_ms": 3_500_000 + i * 3000, "end_ms": 3_503_000 + i * 3000} for i, c in enumerate("abcdefghijk")}
    by_id["seg_031"] = {"start_ms": 3_500_000, "end_ms": 3_533_000}
    by_id["seg_031i"]["end_ms"] = 3_529_600  # 3.4 s before tape end, as on exec_022
    by_id["seg_029"] = {"start_ms": 3_000_000, "end_ms": 3_100_000}
    excluded = [{"segment_id": f"seg_031{c}", "reason": "media_ip_cta"} for c in "abcdefghjk"]
    selection = {"excluded_segment_ids": excluded}
    out = _closing_outro_tail_ids(by_id, ["seg_029", "seg_031i"], {"seg_031"}, selection)
    assert out == {"seg_031i"}


def test_story_child_before_the_sponsor_read_stays() -> None:
    from interview_mux.media_ip_cta import _closing_outro_tail_ids

    by_id = {f"seg_031{c}": {"start_ms": 3_500_000 + i * 3000, "end_ms": 3_503_000 + i * 3000} for i, c in enumerate("abcd")}
    by_id["seg_031"] = {"start_ms": 3_500_000, "end_ms": 3_512_000}
    excluded = [{"segment_id": f"seg_031{c}", "reason": "media_ip_cta"} for c in "bc"]
    out = _closing_outro_tail_ids(by_id, ["seg_031a", "seg_031d"], {"seg_031"}, {"excluded_segment_ids": excluded})
    assert out == {"seg_031d"}
