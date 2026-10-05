"""Air neighbours are not tape neighbours: the family sweep (ISSUES 179).

Each producer below read an air-order neighbour, or a list-order neighbour, as
if it were the clip next to it on tape, and cut, capped, fused or dropped
material on that basis in a reordered episode.
"""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.gap_framing import drop_contiguous_light_bridge_lines
from interview_mux.ideal_cuts import resolve_cut_overlaps
from interview_mux.junction_snip_qa import _merge_candidate_for_clip, _next_speech_source_start
from interview_mux.thought_complete_recut import apply_thought_complete_to_clips


def _speech(sid: str, s: int, e: int) -> dict:
    return {"segment_id": sid, "type": "speech", "source_start_ms": s, "source_end_ms": e, "duration_ms": e - s}


def test_junction_cap_is_the_tape_next_on_air_start() -> None:
    # Air: B(30-40s), A(10-20s), C(50-60s). B's tape-next on air is C, not A.
    clips = [_speech("B", 30_000, 40_000), _speech("A", 10_000, 20_000), _speech("C", 50_000, 60_000)]
    assert _next_speech_source_start(clips, 0) == 50_000
    # A's tape-next on air is B (aired earlier), not C.
    assert _next_speech_source_start(clips, 1) == 30_000
    assert _next_speech_source_start(clips, 2) is None


def test_junction_fuse_refuses_a_reordered_air_neighbour() -> None:
    clips = [_speech("B", 30_000, 40_000), _speech("A", 10_000, 20_000)]
    segs = {"A": {"speaker_id": "spk_1"}, "B": {"speaker_id": "spk_1"}}
    cand = _merge_candidate_for_clip(
        clips=clips, index=0, sid="B", src_start=30_000, src_end=40_000,
        speaker="spk_1", chapter=None, selection={}, segs=segs, gap_max_ms=24_000,
    )
    assert cand is None


def test_junction_fuse_refuses_a_union_over_another_on_air_clip() -> None:
    clips = [_speech("A", 10_000, 20_000), _speech("C", 21_000, 22_000), _speech("B", 25_000, 30_000)]
    # Air neighbours A -> (C) ... use A and B adjacent in a two-clip view with C elsewhere.
    view = [clips[0], clips[2], clips[1]]
    segs = {"A": {"speaker_id": "spk_1"}, "B": {"speaker_id": "spk_1"}, "C": {"speaker_id": "spk_0"}}
    cand = _merge_candidate_for_clip(
        clips=view, index=0, sid="A", src_start=10_000, src_end=20_000,
        speaker="spk_1", chapter=None, selection={}, segs=segs, gap_max_ms=24_000,
    )
    assert cand is None


def test_junction_fuse_still_merges_a_true_tape_neighbour() -> None:
    clips = [_speech("A", 10_000, 20_000), _speech("B", 20_200, 30_000)]
    segs = {"A": {"speaker_id": "spk_1"}, "B": {"speaker_id": "spk_1"}}
    cand = _merge_candidate_for_clip(
        clips=clips, index=0, sid="A", src_start=10_000, src_end=20_000,
        speaker="spk_1", chapter=None, selection={}, segs=segs, gap_max_ms=24_000,
    )
    assert cand and (cand["new_start_ms"], cand["new_end_ms"]) == (10_000, 30_000)


def test_lower_tier_cut_far_from_a_must_keep_survives() -> None:
    cuts = [
        {"cut_id": "must", "priority": "must_keep", "start_ms": 100_000, "end_ms": 200_000, "duration_ms": 100_000},
        {"cut_id": "early", "priority": "should_keep", "start_ms": 10_000, "end_ms": 20_000, "duration_ms": 10_000},
        {"cut_id": "clash", "priority": "optional", "start_ms": 150_000, "end_ms": 160_000, "duration_ms": 10_000},
    ]
    warnings: list[str] = []
    kept = {c["cut_id"] for c in resolve_cut_overlaps(cuts, warnings)}
    assert kept == {"must", "early"}
    assert warnings == ["dropped overlapping cut clash"]


def test_bridge_vo_kept_at_a_short_backward_jump() -> None:
    segs = {
        "P": {"start_ms": 50_000, "end_ms": 51_500, "speaker_id": "spk_1"},
        "T": {"start_ms": 49_500, "end_ms": 60_000, "speaker_id": "spk_1"},
    }
    gap = {"interviewer_lines": [{"line_id": "vo_t", "placement": "before", "targets_segment_id": "T"}]}
    out, notes = drop_contiguous_light_bridge_lines(gap, segs, ordered_segment_ids=["P", "T"])
    assert notes == []
    assert [l["line_id"] for l in out["interviewer_lines"]] == ["vo_t"]


def test_thought_complete_extension_stops_at_a_tape_later_clip_aired_earlier() -> None:
    # Air: C(25-35s) then H(10-20s, hanging). Extending H to 30s would replay C's head.
    clips = [_speech("C", 25_000, 35_000), _speech("H", 10_000, 20_000)]
    finding = {"segment_id": "H", "kind": "thought_complete_recut", "detail": {"keep_end_ms": 30_000}}
    out, overrides, changed = apply_thought_complete_to_clips(
        clips, finding, overrides={}, excluded=set(), exclude_reasons={}
    )
    h = next(c for c in out if c["segment_id"] == "H")
    assert h["source_end_ms"] <= 25_000


def test_next_chapter_cap_ignores_a_chapter_earlier_on_tape() -> None:
    from interview_mux.chapter_close_hitch import _next_chapter_start_ms

    plan = {"chapters": [{"chapter_id": "ch_x", "segment_ids": ["X"]}, {"chapter_id": "ch_y", "segment_ids": ["Y"]}]}
    keepers = [{"segment_id": "X", "start_ms": 300_000}, {"segment_id": "Y", "start_ms": 100_000}]
    assert _next_chapter_start_ms(plan, keepers, "ch_x", after_ms=300_000) is None
    assert _next_chapter_start_ms(plan, keepers, "ch_x") == 100_000


def test_post_coda_drop_waits_for_the_closing_chapter(tmp_path: Path) -> None:
    from interview_mux.opening_adjacency_repair import drop_post_coda_reverse_jump_from_selection
    from run_fixtures import isolated_run_ctx, write_fixture_json

    ctx = isolated_run_ctx(tmp_path, "exec_mid_arc_late_tape")
    orig = ctx.write_json

    def _wrap(rel, data, **kwargs):
        if str(rel).replace("\\", "/") == "master/selection.json":
            kwargs["stage_key"] = "selection_order_sanitize"
        return orig(rel, data, **kwargs)

    ctx.write_json = _wrap  # type: ignore[method-assign]
    write_fixture_json(ctx, "run_meta.json", {})
    order = ["seg_003", "seg_070", "seg_073", "seg_004", "seg_005", "seg_009"]
    write_fixture_json(
        ctx,
        "master/selection.json",
        {
            "ordered_segment_ids": order,
            "excluded_segment_ids": [],
            # Late tape airs as chapter 1's payoff; chapter 2 returns to early tape.
            "chapters": [
                {"chapter_id": "ch_1", "segment_ids": ["seg_003", "seg_070", "seg_073"]},
                {"chapter_id": "ch_2", "segment_ids": ["seg_004", "seg_005", "seg_009"]},
            ],
        },
    )
    write_fixture_json(
        ctx,
        "segments/manifest.json",
        {
            "segments": [
                {"segment_id": "seg_003", "start_ms": 80_000, "end_ms": 90_000, "text": "open"},
                {"segment_id": "seg_070", "start_ms": 3_193_240, "end_ms": 3_274_380, "text": "adoption"},
                {"segment_id": "seg_073", "start_ms": 3_373_040, "end_ms": 3_502_960, "text": "payoff"},
                {"segment_id": "seg_004", "start_ms": 165_300, "end_ms": 184_340, "text": "cancer is deadly"},
                {"segment_id": "seg_005", "start_ms": 184_340, "end_ms": 263_860, "text": "historically"},
                {"segment_id": "seg_009", "start_ms": 471_720, "end_ms": 524_600, "text": "liquid biopsy"},
            ]
        },
    )
    assert drop_post_coda_reverse_jump_from_selection(ctx) == []
    assert json.loads((ctx.run_dir / "master" / "selection.json").read_text())["ordered_segment_ids"] == order
