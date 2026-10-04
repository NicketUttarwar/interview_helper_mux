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
