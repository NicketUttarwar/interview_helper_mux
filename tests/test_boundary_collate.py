from __future__ import annotations

from interview_mux.boundary_collate import (
    align_boundary_rows_to_shard,
    boundary_coverage_errors,
    merge_shard_boundaries,
    normalize_boundary_timeline,
)
from interview_mux.llm_subtasks import (
    _apply_deterministic_boundary_collate,
    _slice_pause_ladder_hints,
    _slice_stage_input,
)
from interview_mux.segment_timeline import validate_boundary_rows


def test_deterministic_boundary_collate_unions_shards_and_renumbers():
    collate_env = {
        "status": "partial",
        "artifacts": {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 500,
                    "speaker_id": "spk_0",
                    "proposed_split_reason": "pause",
                }
            ]
        },
    }
    shard_outputs = [
        {
            "envelope": {
                "artifacts": {
                    "boundaries": [
                        {
                            "segment_id": "seg_001",
                            "start_ms": 0,
                            "end_ms": 500,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        }
                    ]
                }
            }
        },
        {
            "envelope": {
                "artifacts": {
                    "boundaries": [
                        {
                            "segment_id": "seg_001",
                            "start_ms": 500,
                            "end_ms": 1200,
                            "speaker_id": "spk_1",
                            "proposed_split_reason": "question_answer_pair",
                        }
                    ]
                }
            }
        },
    ]
    merged = _apply_deterministic_boundary_collate(collate_env, shard_outputs)
    boundaries = merged["artifacts"]["boundaries"]
    assert merged["status"] == "complete"
    assert len(boundaries) == 2
    assert boundaries[0]["segment_id"] == "seg_001"
    assert boundaries[1]["segment_id"] == "seg_002"
    assert boundaries[1]["end_ms"] == 1200
    assert not validate_boundary_rows(boundaries)


def test_merge_shard_boundaries_drops_coarse_parent_and_snaps_overlap():
    """Reproduce exec_2338-style coarse shard + fine shard overlap."""
    shard_outputs = [
        {
            "envelope": {
                "artifacts": {
                    "boundaries": [
                        {
                            "segment_id": "seg_001",
                            "start_ms": 0,
                            "end_ms": 8210,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_002",
                            "start_ms": 8210,
                            "end_ms": 102260,
                            "speaker_id": "spk_1",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_003",
                            "start_ms": 102260,
                            "end_ms": 132440,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        },
                    ]
                }
            }
        },
        {
            "envelope": {
                "artifacts": {
                    "boundaries": [
                        {
                            "segment_id": "seg_001",
                            "start_ms": 0,
                            "end_ms": 8210,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_002",
                            "start_ms": 8210,
                            "end_ms": 11130,
                            "speaker_id": "spk_1",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_003",
                            "start_ms": 11130,
                            "end_ms": 26729,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_004",
                            "start_ms": 26729,
                            "end_ms": 39659,
                            "speaker_id": "spk_1",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_005",
                            "start_ms": 39659,
                            "end_ms": 63955,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_006",
                            "start_ms": 63955,
                            "end_ms": 71434,
                            "speaker_id": "spk_1",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_007",
                            "start_ms": 71434,
                            "end_ms": 77839,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_008",
                            "start_ms": 77839,
                            "end_ms": 81790,
                            "speaker_id": "spk_1",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_009",
                            "start_ms": 81790,
                            "end_ms": 88949,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_010",
                            "start_ms": 88949,
                            "end_ms": 102260,
                            "speaker_id": "spk_1",
                            "proposed_split_reason": "pause",
                        },
                    ]
                }
            }
        },
    ]
    merged_rows, applied = merge_shard_boundaries(shard_outputs)
    assert merged_rows
    assert any(action["action"] == "drop_coarse_dominated" for action in applied)
    assert not validate_boundary_rows(merged_rows)
    assert merged_rows[0]["start_ms"] == 0
    assert merged_rows[1]["start_ms"] == 8210
    assert merged_rows[-1]["end_ms"] >= 102260
    assert all(merged_rows[i]["end_ms"] <= merged_rows[i + 1]["start_ms"] for i in range(len(merged_rows) - 1))


def test_normalize_boundary_timeline_snaps_nearby_boundaries():
    rows = [
        {
            "segment_id": "seg_001",
            "start_ms": 0,
            "end_ms": 1000,
            "speaker_id": "spk_0",
            "proposed_split_reason": "pause",
        },
        {
            "segment_id": "seg_002",
            "start_ms": 980,
            "end_ms": 2500,
            "speaker_id": "spk_1",
            "proposed_split_reason": "pause",
        },
    ]
    normalized, applied = normalize_boundary_timeline(rows)
    assert normalized[1]["start_ms"] == 1000
    assert any(action["action"] == "snap_start_to_prev_end" for action in applied)
    assert not validate_boundary_rows(normalized)


def test_align_relative_shard_boundaries_to_absolute_window():
    rows = [
        {
            "segment_id": "seg_001",
            "start_ms": 0,
            "end_ms": 5000,
            "speaker_id": "spk_0",
            "proposed_split_reason": "pause",
        },
        {
            "segment_id": "seg_002",
            "start_ms": 5000,
            "end_ms": 12000,
            "speaker_id": "spk_1",
            "proposed_split_reason": "pause",
        },
    ]
    aligned, applied = align_boundary_rows_to_shard(rows, shard_start_ms=229009, shard_end_ms=448369)
    assert aligned[0]["start_ms"] == 229009
    assert aligned[-1]["end_ms"] == 241009
    assert any(action["action"] == "shift_relative_to_shard_start" for action in applied)


def test_clip_misscoped_full_ladder_rows_to_later_shard():
    rows = [
        {
            "segment_id": "seg_030",
            "start_ms": 230649,
            "end_ms": 238089,
            "speaker_id": "spk_0",
            "proposed_split_reason": "pause",
        },
        {
            "segment_id": "seg_040",
            "start_ms": 289890,
            "end_ms": 291890,
            "speaker_id": "spk_1",
            "proposed_split_reason": "pause",
        },
    ]
    aligned, applied = align_boundary_rows_to_shard(rows, shard_start_ms=229009, shard_end_ms=448369)
    assert aligned
    assert aligned[0]["start_ms"] >= 229009
    assert not applied


def test_clip_misscoped_rows_starting_at_zero_for_later_shard():
    rows = [
        {
            "segment_id": "seg_001",
            "start_ms": 0,
            "end_ms": 8210,
            "speaker_id": "spk_0",
            "proposed_split_reason": "pause",
        },
        {
            "segment_id": "seg_030",
            "start_ms": 230649,
            "end_ms": 238089,
            "speaker_id": "spk_1",
            "proposed_split_reason": "pause",
        },
    ]
    aligned, applied = align_boundary_rows_to_shard(rows, shard_start_ms=229009, shard_end_ms=448369)
    assert len(aligned) == 1
    assert aligned[0]["start_ms"] == 230649
    assert any(action["action"] == "clip_misscoped_to_shard_window" for action in applied)


def test_merge_shard_boundaries_aligns_relative_later_shards():
    shard_outputs = [
        {
            "label": "time_1",
            "start_ms": 0,
            "end_ms": 229009,
            "envelope": {
                "artifacts": {
                    "boundaries": [
                        {
                            "segment_id": "seg_001",
                            "start_ms": 0,
                            "end_ms": 229009,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        }
                    ]
                }
            },
        },
        {
            "label": "time_2",
            "start_ms": 229009,
            "end_ms": 448369,
            "envelope": {
                "artifacts": {
                    "boundaries": [
                        {
                            "segment_id": "seg_001",
                            "start_ms": 0,
                            "end_ms": 5000,
                            "speaker_id": "spk_1",
                            "proposed_split_reason": "pause",
                        },
                        {
                            "segment_id": "seg_002",
                            "start_ms": 5000,
                            "end_ms": 219360,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        },
                    ]
                }
            },
        },
    ]
    merged_rows, applied = merge_shard_boundaries(shard_outputs)
    assert merged_rows
    assert merged_rows[-1]["end_ms"] >= 448000
    assert any(action["action"] == "shift_relative_to_shard_start" for action in applied)
    assert not validate_boundary_rows(merged_rows)


def test_slice_pause_ladder_hints_to_shard_window():
    hints = {
        "candidates": [
            {
                "threshold_ms": 400,
                "split_times_ms": [4139, 230649, 448000, 684000],
                "count": 4,
            }
        ]
    }
    sliced = _slice_pause_ladder_hints(hints, start_ms=229009, end_ms=448369)
    times = sliced["candidates"][0]["split_times_ms"]
    assert 4139 not in times
    assert 230649 in times
    assert 448000 in times
    assert 684000 not in times


def test_slice_stage_input_injects_boundary_shard_window_and_sliced_hints():
    stage_input = {
        "transcript": {"words": [{"start_ms": 0, "end_ms": 1000, "text": "hi"}]},
        "pause_ladder_hints": {
            "candidates": [{"threshold_ms": 400, "split_times_ms": [100, 250000], "count": 2}]
        },
    }
    shard = {"label": "time_2", "start_ms": 229009, "end_ms": 448369}
    sliced = _slice_stage_input("boundary_detection", stage_input, shard)
    assert sliced["boundary_shard_window"]["start_ms"] == 229009
    assert 100 not in sliced["pause_ladder_hints"]["candidates"][0]["split_times_ms"]
    assert 250000 in sliced["pause_ladder_hints"]["candidates"][0]["split_times_ms"]


def test_boundary_collate_blocks_incomplete_coverage(tmp_path, monkeypatch):
    from interview_mux.run_context import RunContext

    monkeypatch.setenv("INTERVIEW_MUX_RUNS_ROOT", str(tmp_path))
    ctx = RunContext("exec_boundary_cov", create=True)
    ctx.write_json(
        "transcript/full.json",
        {"words": [{"start_ms": 0, "end_ms": 890575, "text": "x"}]},
        skip_handoff=True,
    )
    collate_env = {"status": "complete", "artifacts": {"warnings": []}}
    shard_outputs = [
        {
            "start_ms": 0,
            "end_ms": 890575,
            "envelope": {
                "artifacts": {
                    "boundaries": [
                        {
                            "segment_id": "seg_001",
                            "start_ms": 0,
                            "end_ms": 291890,
                            "speaker_id": "spk_0",
                            "proposed_split_reason": "pause",
                        }
                    ]
                }
            },
        }
    ]
    merged = _apply_deterministic_boundary_collate(collate_env, shard_outputs, ctx=ctx)
    assert merged["status"] == "blocked"
    assert boundary_coverage_errors(
        merged["artifacts"]["boundaries"],
        interview_duration_ms=890575,
    )
    assert any(n.get("blocking") for n in merged.get("needs") or [])

