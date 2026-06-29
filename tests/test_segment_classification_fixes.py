from __future__ import annotations

from interview_mux.artifact_completeness import hydrate_manifest_from_boundaries
from interview_mux.context_volley import build_message_volley
from interview_mux.llm_shard_plans import normalize_shard_plan
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


def test_normalize_shard_plan_maps_integer_ids_to_boundary_segment_ids():
    stage_input = {
        "boundaries": {
            "boundaries": [
                {"segment_id": "seg_001", "start_ms": 0, "end_ms": 1000},
                {"segment_id": "seg_002", "start_ms": 1000, "end_ms": 2000},
            ]
        }
    }
    shard_plan = [
        {"label": "Segment 1", "segment_ids": [1]},
        {"label": "Segment 2", "segment_ids": [2]},
    ]
    normalized = normalize_shard_plan("segment_classification", stage_input, shard_plan)
    assert normalized[0]["segment_ids"] == ["seg_001"]
    assert normalized[1]["segment_ids"] == ["seg_002"]


def test_collate_volley_accepts_integer_segment_ids_in_shard_output(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "collate_int_ids")
    collate_input = {
        "mode": "collate",
        "shard_outputs": [
            {
                "label": "s1",
                "segment_ids": [1],
                "envelope": {"reasoning_summary": "r1", "artifacts": {}},
            }
        ],
    }
    volley = build_message_volley(ctx, "segment_classification", collate_input, profile="collate")
    assistant = next(m for m in volley if m["role"] == "assistant")
    assert "segments: 1" in assistant["content"]


def test_hydrate_manifest_from_boundaries_fills_timeline_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.write_json(
        "segments/boundaries.json",
        {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 1500,
                    "speaker_id": "spk_1",
                    "proposed_split_reason": "topic_shift",
                }
            ]
        },
    )
    ctx.write_json(
        "understanding/speakers.json",
        {"speakers": [{"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9}]},
    )
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_1"},
                {"text": "world", "start_ms": 500, "end_ms": 1200, "speaker_id": "spk_1"},
            ]
        },
    )
    manifest = {
        "segments": [
            {
                "segment_id": "seg_001",
                "type": "interviewee_answer",
                "speaker_id": "spk_1",
                "speaker_role": "interviewee",
                "topic_tags": ["intro"],
            }
        ]
    }
    hydrated = hydrate_manifest_from_boundaries(ctx, manifest)
    seg = hydrated["segments"][0]
    assert seg["start_ms"] == 0
    assert seg["end_ms"] == 1500
    assert seg["text"] == "hello world"
