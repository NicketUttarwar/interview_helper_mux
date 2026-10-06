"""Complete-thought cut guardrail: source-adjacent incomplete seams."""

from __future__ import annotations

from interview_mux.gap_vo_prior_context import (
    SOURCE_ADJACENT_COMPLETES_MAX_GAP_MS,
    clause_continues_after,
    ends_complete_thought,
    source_adjacent_completes,
    source_adjacent_completes_at,
)
from interview_mux.segment_fuse import incomplete_thought_hints


def _words_for(left: str, right: str, *, gap_ms: int, left_spk: str = "spk_0", right_spk: str = "spk_0"):
    words: list[dict] = []
    t = 0
    for tok in left.split():
        words.append(
            {"text": tok, "speaker_id": left_spk, "start_ms": t, "end_ms": t + 180}
        )
        t += 200
    cut = words[-1]["end_ms"]
    t = cut + gap_ms
    for tok in right.split():
        words.append(
            {"text": tok, "speaker_id": right_spk, "start_ms": t, "end_ms": t + 180}
        )
        t += 200
    return words, cut


def test_provision_called_ldt_is_source_adjacent_complete() -> None:
    prev = "The other way is a provision"
    later = "called LDT, Lab Develop Test."
    assert source_adjacent_completes(prev, later, 1020, same_speaker=True)
    assert not ends_complete_thought(prev, next_pause_ms=1020, later_head=later)
    words, cut = _words_for(prev, later, gap_ms=1020)
    assert source_adjacent_completes_at(words, cut)
    assert clause_continues_after(words, cut)


def test_provision_called_ldt_cross_speaker_tight_gap() -> None:
    prev = "The other way is a provision"
    later = "called LDT Lab Develop Test"
    assert source_adjacent_completes(prev, later, 900, same_speaker=False)
    words, cut = _words_for(prev, later, gap_ms=900, left_spk="spk_0", right_spk="spk_1")
    assert source_adjacent_completes_at(words, cut)


def test_negative_finished_provision_then_called_him() -> None:
    prev = "That's my provision."
    later = "Called him yesterday about the results."
    assert not source_adjacent_completes(
        prev, later, 1200, same_speaker=True
    )
    assert ends_complete_thought(prev, next_pause_ms=1200, later_head=later)


def test_negative_wide_gap_no_fuse() -> None:
    prev = "The other way is a provision"
    later = "called LDT"
    assert not source_adjacent_completes(
        prev, later, SOURCE_ADJACENT_COMPLETES_MAX_GAP_MS + 200, same_speaker=True
    )


def test_fuse_hints_force_without_prior_hanging() -> None:
    hints = {
        "hanging_setup_end": False,
        "source_adjacent_completes": True,
        "later_opens_nominal_complement": True,
        "earlier_lands_complete_idea": False,
        "island_straddle": False,
    }
    assert incomplete_thought_hints(hints)


def test_incomplete_seam_order_repairs_b_before_a() -> None:
    from interview_mux.air_order_integrity import repair_incomplete_seam_order

    spans = {
        "seg_022": {
            "start_ms": 1000,
            "end_ms": 2000,
            "text": "The other way is a provision",
            "speaker_id": "spk_0",
        },
        "seg_023": {
            "start_ms": 2100,
            "end_ms": 5000,
            "text": "called LDT, Lab Develop Test. So if you have a lab",
            "speaker_id": "spk_0",
        },
    }
    ordered = ["seg_023", "seg_022", "seg_027"]
    repaired, actions = repair_incomplete_seam_order(ordered, spans)
    assert repaired.index("seg_022") < repaired.index("seg_023")
    assert repaired.index("seg_022") + 1 == repaired.index("seg_023")
    assert any(a.get("code") == "incomplete_seam_order" for a in actions)


def test_incomplete_seam_order_pulls_missing_completion() -> None:
    from interview_mux.air_order_integrity import repair_incomplete_seam_order

    spans = {
        "seg_022": {
            "start_ms": 1000,
            "end_ms": 2000,
            "text": "The other way is a provision",
            "speaker_id": "spk_0",
        },
        "seg_023": {
            "start_ms": 2100,
            "end_ms": 5000,
            "text": "called LDT Lab Develop Test",
            "speaker_id": "spk_0",
        },
    }
    ordered = ["seg_022", "seg_027"]
    repaired, actions = repair_incomplete_seam_order(ordered, spans)
    assert "seg_023" in repaired
    assert repaired.index("seg_022") + 1 == repaired.index("seg_023")
    assert any(a.get("action") == "incomplete_seam_pull_completion" for a in actions)


def test_air_bound_refuses_hinge_orphan_of_completion_prefix() -> None:
    from interview_mux.ideal_cuts import resolve_keeper_air_bounds

    prev = "The other way is a provision"
    later = "called LDT Lab Develop Test So if you have a lab that is certified okay"
    words, cut = _words_for(prev, later, gap_ms=1000)
    # B's full slab starts at the seam; ideal would snap start far into the slab.
    b_start = cut  # abutting
    b_end = words[-1]["end_ms"]
    # Simulate a distant hinge window by clamping via a fake ideal cut mid-slab.
    mid = b_start + 4000
    cuts = {
        "cuts": [
            {
                "cut_id": "cut_nmd",
                "start_ms": mid,
                "end_ms": b_end,
                "priority": "should_keep",
            }
        ]
    }
    meta: dict = {}
    start, end = resolve_keeper_air_bounds(
        source_start_ms=b_start,
        source_end_ms=b_end,
        cuts_doc=cuts,
        words=words,
        segment_id="seg_023",
        min_keep_ms=500,
        # Tape predecessor ends at the seam so open cannot walk into A.
        prev_keeper_end_ms=b_start,
        meta_out=meta,
    )
    assert start == b_start
    assert "incomplete_seam_preserve" in str(meta.get("air_bound_reason") or "")
    assert end > start
    # Completion prefix ("called LDT…") must remain inside the kept window.
    assert start <= b_start < end


def test_prior_complete_thought_false_when_chrono_next_completes() -> None:
    from interview_mux.gap_vo_prior_context import build_prior_native_context

    segments = {
        "seg_022": {
            "segment_id": "seg_022",
            "start_ms": 1000,
            "end_ms": 2000,
            "text": "The other way is a provision",
            "speaker_id": "spk_0",
        },
        "seg_023": {
            "segment_id": "seg_023",
            "start_ms": 2100,
            "end_ms": 5000,
            "text": "called LDT Lab Develop Test",
            "speaker_id": "spk_0",
        },
        "seg_027": {
            "segment_id": "seg_027",
            "start_ms": 6000,
            "end_ms": 9000,
            "text": "parts of the overall cell you are capturing",
            "speaker_id": "spk_0",
        },
    }
    # Air order has 027 after 022 (023 omitted from air order list) — chrono next still 023.
    pkt = build_prior_native_context(
        target_segment_id="seg_027",
        ordered_ids=["seg_022", "seg_027"],
        segments_by_id=segments,
    )
    assert pkt is not None
    assert pkt["prior_complete_thought"] is False
