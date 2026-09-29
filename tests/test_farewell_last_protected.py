"""A farewell the ranker placed last is not pulled forward as a mid-arc jump (ISSUES 68)."""

from __future__ import annotations

from interview_mux.air_order_integrity import is_farewell_text, pull_mid_arc_reverse_jumps

# exec_054: later-tape material, then the guest farewell seg_063 as the ending.
STARTS = {
    "seg_060": 2_900_000,
    "seg_063": 2_988_860,
    "seg_072": 3_283_670,
    "seg_073": 3_341_730,
    "seg_075": 3_418_330,
}
ORDER = ["seg_060", "seg_072", "seg_073", "seg_075", "seg_063"]


def test_farewell_in_final_slot_stays_last() -> None:
    pulled, moved, _ = pull_mid_arc_reverse_jumps(
        ORDER, STARTS, margin_ms=0, protect_final_ids={"seg_063"}
    )
    assert pulled[-1] == "seg_063"
    assert "seg_063" not in moved


def test_without_protection_the_old_behaviour_is_unchanged() -> None:
    pulled, moved, _ = pull_mid_arc_reverse_jumps(ORDER, STARTS, margin_ms=0)
    assert pulled[-1] != "seg_063"
    assert "seg_063" in moved


def test_earlier_tape_leftovers_after_a_signoff_are_still_pulled() -> None:
    """The original bug: earlier-tape ids appended after the sign-off."""
    starts = {"seg_045": 1_000, "seg_047": 2_000, "seg_051": 9_000}
    order = ["seg_051", "seg_045", "seg_047"]
    pulled, moved, _ = pull_mid_arc_reverse_jumps(
        order, starts, margin_ms=0, protect_final_ids={"seg_047"}
    )
    # seg_045 is a mid-arc jump; it moves before the sign-off.
    assert pulled.index("seg_045") < pulled.index("seg_051")


def test_farewell_text_detection() -> None:
    assert is_farewell_text("Mohan, co-founder and CEO of OneCell. Mohan, thank you very much.")
    assert is_farewell_text("Thanks so much for joining us today.")
    assert not is_farewell_text("And that assay becomes a companion diagnostic.")
