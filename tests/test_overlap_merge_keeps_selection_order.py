"""The EDL overlap merge seats the union where the selection keeps it (ISSUES 167).

exec_019: seg_019 (later retired) aired before seg_018 and overlapped seg_017.
The merge put the union at seg_019's slot, so the EDL read seg_017, seg_018
while the selection (consumed id dropped in place) read seg_018, seg_017, and
EDL narrative QC refused the EDL.
"""

from __future__ import annotations

from interview_mux.edl_overlap_repair import _rebuild_clips


def _speech(sid: str) -> dict:
    return {"type": "speech", "segment_id": sid, "source_start_ms": 0, "source_end_ms": 1000}


def test_union_sits_at_the_survivors_slot() -> None:
    clips = [
        _speech("seg_016"),
        {"type": "vo_pickup", "targets_segment_id": "seg_019", "placement": "before"},
        _speech("seg_019"),
        _speech("seg_018"),
        {"type": "transition", "after_segment_id": "seg_018", "before_segment_id": "seg_017"},
        _speech("seg_017"),
        _speech("seg_020"),
    ]
    out = _rebuild_clips(
        clips, members={"seg_019", "seg_017"}, survivor="seg_017", union_start=10, union_end=900
    )
    order = [c["segment_id"] for c in out if c.get("type") == "speech"]
    assert order == ["seg_016", "seg_018", "seg_017", "seg_020"]
    idx = [i for i, c in enumerate(out) if c.get("segment_id") == "seg_017"][0]
    assert out[idx - 1].get("type") == "vo_pickup"
    assert out[idx]["source_start_ms"] == 10 and out[idx]["source_end_ms"] == 900


def test_adjacent_members_collapse_in_place() -> None:
    clips = [
        _speech("seg_001"),
        _speech("seg_002"),
        {"type": "transition", "after_segment_id": "seg_002", "before_segment_id": "seg_003"},
        _speech("seg_003"),
    ]
    out = _rebuild_clips(clips, members={"seg_002", "seg_003"}, survivor="seg_002", union_start=0, union_end=5)
    assert [c.get("segment_id") for c in out if c.get("type") == "speech"] == ["seg_001", "seg_002"]
    assert not [c for c in out if c.get("type") == "transition"]


def test_no_survivor_clip_leaves_clips_unchanged() -> None:
    clips = [_speech("seg_001"), _speech("seg_002")]
    assert _rebuild_clips(clips, members={"seg_009"}, survivor="seg_009", union_start=0, union_end=1) == clips
