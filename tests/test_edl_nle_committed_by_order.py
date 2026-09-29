"""edl accepts NLE edits whose order is already on the disk selection (ISSUES 56)."""

from __future__ import annotations

from interview_mux.stages.assembly import nle_committed_on_disk


def test_same_order_without_stamp_is_committed() -> None:
    order = ["seg_003", "seg_004", "seg_005"]
    assert nle_committed_on_disk(order, list(order), {"ordered_segment_ids": order}) is True


def test_same_order_with_stamp_is_committed() -> None:
    order = ["seg_003", "seg_004"]
    assert nle_committed_on_disk(order, list(order), {"nle_applied": True}) is True


def test_different_order_is_not_committed() -> None:
    assert (
        nle_committed_on_disk(["seg_003", "seg_004"], ["seg_004", "seg_003"], {"nle_applied": True})
        is False
    )
