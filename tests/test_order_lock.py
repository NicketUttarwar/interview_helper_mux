"""Revisioned order_lock — selection leads; EDL sync banned."""

from __future__ import annotations

import pytest

from interview_mux.order_hash import (
    assert_selection_leads_edl,
    bump_order_lock,
    copy_order_lock,
    copy_order_lock_if_clips_match,
    edl_speech_clip_ids,
    get_order_lock,
    order_drift_heal_action,
    order_hashes_match,
    order_locks_match,
    stamp_order_hash,
    sync_selection_order_to_edl,
)


def test_bump_order_lock_increments_on_reorder():
    sel = {"ordered_segment_ids": ["a", "b", "c"]}
    locked = bump_order_lock(sel, source="full_master_ranking")
    lock = get_order_lock(locked)
    assert lock is not None
    assert lock["revision"] == 1
    assert lock["authority"] == "master/selection.json"
    assert locked["order_content_hash"] == lock["order_content_hash"]

    reordered = bump_order_lock(
        {**locked, "ordered_segment_ids": ["c", "b", "a"]},
        source="timeline_optimizer",
    )
    lock2 = get_order_lock(reordered)
    assert lock2 is not None
    assert lock2["revision"] == 2
    assert lock2["supersedes"]


def test_copy_order_lock_propagates_without_new_revision():
    sel = bump_order_lock({"ordered_segment_ids": ["x", "y"]}, source="ranking")
    edl = copy_order_lock(sel, {"ordered_segment_ids": ["x", "y"], "clips": []})
    assert order_locks_match(sel, edl)
    assert get_order_lock(edl)["revision"] == get_order_lock(sel)["revision"]


def test_sync_selection_order_to_edl_is_banned():
    sel = bump_order_lock({"ordered_segment_ids": ["a"]}, source="ranking")
    edl = stamp_order_hash({"ordered_segment_ids": ["b"]})
    with pytest.raises(RuntimeError, match="banned"):
        sync_selection_order_to_edl(sel, edl)


def test_assert_selection_leads_edl():
    sel = bump_order_lock({"ordered_segment_ids": ["a", "b"]}, source="ranking")
    edl = copy_order_lock(sel, stamp_order_hash({"ordered_segment_ids": ["a", "b"]}))
    assert_selection_leads_edl(sel, edl)

    bad = stamp_order_hash({"ordered_segment_ids": ["b", "a"]})
    with pytest.raises(ValueError, match="diverges"):
        assert_selection_leads_edl(sel, bad)


def test_order_hashes_match_still_list_authoritative():
    sel = {"ordered_segment_ids": ["a", "b"], "order_content_hash": "stale"}
    edl = {"ordered_segment_ids": ["a", "b"], "order_content_hash": "other"}
    assert order_hashes_match(sel, edl)
    edl2 = {"ordered_segment_ids": ["b", "a"]}
    assert not order_hashes_match(sel, edl2)


def _speech(sid: str) -> dict:
    return {
        "type": "speech",
        "segment_id": sid,
        "source_start_ms": 0,
        "source_end_ms": 1000,
        "duration_ms": 1000,
    }


def test_copy_order_lock_if_clips_match_refuses_id_stamp_over_clip_order():
    """exec_1071: keep-list IDs must not be stamped onto a different mix clip order."""
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_049", "seg_053", "seg_055", "seg_056", "seg_062"]},
        source="ranking",
    )
    edl = {
        "ordered_segment_ids": ["seg_049", "seg_053", "seg_055", "seg_056", "seg_062"],
        "clips": [
            _speech("seg_049"),
            _speech("seg_056"),
            _speech("seg_062"),
            _speech("seg_053"),
            _speech("seg_055"),
        ],
    }
    assert edl_speech_clip_ids(edl) != sel["ordered_segment_ids"]
    assert order_hashes_match(sel, edl)
    assert order_drift_heal_action(sel, edl) == "rebuild"
    with pytest.raises(ValueError, match="speech clip order diverges"):
        copy_order_lock_if_clips_match(sel, edl)
    with pytest.raises(ValueError, match="speech clip order diverges"):
        assert_selection_leads_edl(sel, edl)


def test_copy_order_lock_if_clips_match_stamps_when_clips_already_match():
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_a", "seg_b"]},
        source="ranking",
    )
    edl = {
        "ordered_segment_ids": ["seg_b", "seg_a"],
        "clips": [_speech("seg_a"), _speech("seg_b")],
    }
    assert order_drift_heal_action(sel, edl) == "stamp"
    aligned = copy_order_lock_if_clips_match(sel, edl)
    assert aligned["ordered_segment_ids"] == ["seg_a", "seg_b"]
    assert edl_speech_clip_ids(aligned) == ["seg_a", "seg_b"]
    assert_selection_leads_edl(sel, aligned)
