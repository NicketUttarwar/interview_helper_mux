"""Cross-speaker source overlaps the union repair cannot merge are trimmed (ISSUES 97)."""

from __future__ import annotations

from run_fixtures import isolated_run_ctx

from interview_mux.edl_overlap_repair import trim_residual_source_overlaps
from interview_mux.edl_qc import _validate_no_overlapping_source_ranges


def _clip(sid: str, start: int, end: int, speaker: str) -> dict:
    return {
        "type": "speech",
        "segment_id": sid,
        "speaker_id": speaker,
        "source_start_ms": start,
        "source_end_ms": end,
        "duration_ms": end - start,
    }


def test_exec_063_shape_trims_the_earlier_clip_end(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_overlap_trim")
    edl = {
        "clips": [
            _clip("seg_004", 216970, 222580, "spk_2"),
            _clip("seg_005", 222790, 223950, "spk_0"),
            _clip("seg_006", 223570, 244430, "spk_2"),
        ],
        "ordered_segment_ids": ["seg_004", "seg_005", "seg_006"],
    }
    before = _validate_no_overlapping_source_ranges(edl["clips"])
    assert before and "seg_005" in before[0]

    actions = trim_residual_source_overlaps(ctx, edl)

    assert actions == [
        {
            "action": "trim_residual_source_overlap",
            "trimmed": "seg_005",
            "side": "end",
            "against": "seg_006",
            "overlap_ms": 380,
        }
    ]
    assert edl["clips"][1]["source_end_ms"] == 223570
    assert edl["clips"][1]["duration_ms"] == 780
    assert edl["clips"][2]["source_start_ms"] == 223570
    assert _validate_no_overlapping_source_ranges(edl["clips"]) == []
    assert edl["timeline_duration_ms"] > 0


def test_tiny_earlier_clip_trims_the_later_start_instead(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_overlap_trim_later")
    edl = {
        "clips": [
            _clip("seg_010", 1000, 1500, "spk_0"),
            _clip("seg_011", 1100, 9000, "spk_1"),
        ]
    }
    actions = trim_residual_source_overlaps(ctx, edl)
    assert actions[0]["trimmed"] == "seg_011" and actions[0]["side"] == "start"
    assert edl["clips"][1]["source_start_ms"] == 1500
    assert _validate_no_overlapping_source_ranges(edl["clips"]) == []


def test_no_overlap_means_no_action(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_overlap_none")
    edl = {"clips": [_clip("a", 0, 1000, "s"), _clip("b", 1000, 2000, "t")]}
    assert trim_residual_source_overlaps(ctx, edl) == []
