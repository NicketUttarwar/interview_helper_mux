from __future__ import annotations

from interview_mux.llm_subtasks import _apply_deterministic_segment_collate


def test_contract_ordered_segment_collate():
    collate_env = {
        "status": "partial",
        "artifacts": {
            "segments": [
                {
                    "segment_id": "seg_002",
                    "type": "interviewee_answer",
                    "speaker_role": "interviewee",
                    "topic_tags": [],
                }
            ]
        },
    }
    shard_outputs = [
        {
            "envelope": {
                "artifacts": {
                    "segments": [
                        {
                            "segment_id": "seg_001",
                            "type": "interviewer_question",
                            "speaker_role": "interviewer",
                            "topic_tags": [],
                        }
                    ]
                }
            }
        },
        {
            "envelope": {
                "artifacts": {
                    "segments": [
                        {
                            "segment_id": "seg_002",
                            "type": "interviewee_answer",
                            "speaker_role": "interviewee",
                            "topic_tags": ["a"],
                        }
                    ]
                }
            }
        },
    ]
    merged = _apply_deterministic_segment_collate(
        collate_env,
        shard_outputs,
        contract_ids=["seg_001", "seg_002"],
    )
    segments = merged["artifacts"]["segments"]
    assert [s["segment_id"] for s in segments] == ["seg_001", "seg_002"]


def test_build_obligation_fail_closed_on_invalid_timeline():
    from interview_mux.classification_obligation import build_obligation
    from interview_mux.run_context import RunContext

    boundaries = {
        "boundaries": [
            {"segment_id": "seg_001", "start_ms": 0, "end_ms": 500, "speaker_id": "spk_0"},
            {"segment_id": "seg_002", "start_ms": 400, "end_ms": 900, "speaker_id": "spk_1"},
        ],
        "_meta": {
            "segment_contract": {
                "segment_ids": ["seg_001", "seg_002"],
                "timeline_valid": False,
            }
        },
    }
    obligation = build_obligation(RunContext("exec_obligation", create=False), boundaries, None)
    assert obligation["required_count"] == 0
    assert obligation.get("timeline_invalid") is True
