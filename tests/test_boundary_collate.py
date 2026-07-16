from __future__ import annotations

from interview_mux.boundary_collate import merge_shard_boundaries, normalize_boundary_timeline
from interview_mux.llm_subtasks import _apply_deterministic_boundary_collate
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
