"""An intro cut into many pieces is not "opening tape airing late" (ISSUES 164).

exec_017: the episode opened with its intro in tape order, cut into eight
children (seg_001d..k). The listen-delight and post-master checks flagged
the pieces at clip indices 6 and 7 of 24 as late, which set cut_integrity to
0.5 (below the catastrophic 0.7) and failed the authoritative ship gate.
"""

from __future__ import annotations

from interview_mux.air_order_integrity import opening_tape_airs_late

INTRO = [f"seg_001{c}" for c in "defghijk"]
STORY = [f"seg_{n:03d}" for n in range(14, 30)]


def test_split_intro_at_the_start_is_not_late() -> None:
    assert not opening_tape_airs_late(INTRO + STORY, set(INTRO))


def test_cold_open_hook_before_the_intro_is_allowed() -> None:
    assert not opening_tape_airs_late(["seg_020"] + INTRO + STORY, set(INTRO))


def test_opening_tape_returning_mid_episode_is_late() -> None:
    order = INTRO[:2] + STORY[:8] + INTRO[2:3] + STORY[8:]
    assert opening_tape_airs_late(order, set(INTRO))


def test_no_opening_ids() -> None:
    assert not opening_tape_airs_late(STORY, set())
