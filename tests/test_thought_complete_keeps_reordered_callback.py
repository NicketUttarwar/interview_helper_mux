"""A thought-complete recut never consumes a reordered clip from earlier on tape (ISSUES 151)."""

from __future__ import annotations

from interview_mux.thought_complete_recut import apply_thought_complete_to_clips


def _speech(sid: str, start: int, end: int) -> dict:
    return {"type": "speech", "segment_id": sid, "source_start_ms": start, "source_end_ms": end, "duration_ms": end - start}


def test_callback_from_earlier_tape_stays_on_air() -> None:
    clips = [
        _speech("seg_041", 2_390_000, 2_398_000),  # hangs at 40:00
        _speech("seg_005", 300_000, 340_000),  # reordered callback from 05:00
        _speech("seg_042", 2_398_000, 2_430_000),
    ]
    finding = {"segment_id": "seg_041", "kind": "thought_complete_recut", "detail": {"keep_end_ms": 2_401_000}}
    out, _ov, _changed = apply_thought_complete_to_clips(
        clips, finding, overrides={}, excluded=set(), exclude_reasons={}
    )
    assert "seg_005" in [c.get("segment_id") for c in out]


def test_tape_that_continues_is_still_consumed() -> None:
    clips = [
        _speech("seg_041", 2_390_000, 2_398_000),
        _speech("seg_042", 2_398_000, 2_400_500),  # inside the extension
        _speech("seg_043", 2_401_000, 2_430_000),
    ]
    finding = {"segment_id": "seg_041", "kind": "thought_complete_recut", "detail": {"keep_end_ms": 2_401_000}}
    out, _ov, _changed = apply_thought_complete_to_clips(
        clips, finding, overrides={}, excluded=set(), exclude_reasons={}
    )
    assert "seg_042" not in [c.get("segment_id") for c in out]
