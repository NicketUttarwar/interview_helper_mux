from __future__ import annotations

from interview_mux.llm_shard_plans import DECOMPOSE_ELIGIBLE, build_deterministic_shard_plan
from interview_mux.context_volley import build_message_volley
from interview_mux.analysis_memory import should_merge_envelope
from run_fixtures import isolated_run_ctx
from interview_mux.analysis_memory import ensure_analysis_workspace


def test_decompose_eligible_includes_boundary_and_content_context():
    assert "boundary_detection" in DECOMPOSE_ELIGIBLE
    assert "content_context" in DECOMPOSE_ELIGIBLE
    assert "content_brief_reanchor" in DECOMPOSE_ELIGIBLE
    assert "full_master_ranking" in DECOMPOSE_ELIGIBLE


def test_deterministic_shard_plan_for_long_transcript():
    stage_input = {"transcript": "word " * 20000}
    plan, source = build_deterministic_shard_plan(
        "content_context",
        stage_input,
        truncation_flags=["max_stage_data_chars"],
    )
    assert source == "deterministic"
    assert len(plan) >= 2
    assert "text_start" in plan[0]


def test_should_merge_after_collate_success():
    assert should_merge_envelope(
        {"verdict": "decompose"},
        {"status": "complete", "needs": []},
        routed_via_collate=True,
    )


def test_collate_volley_three_shards_three_assistant_turns(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_084_h")
    ensure_analysis_workspace(ctx)
    collate_input = {
        "mode": "collate",
        "shard_outputs": [
            {"label": f"s{i}", "segment_ids": [f"seg_{i}"], "envelope": {"reasoning_summary": f"r{i}", "artifacts": {}}}
            for i in range(3)
        ],
    }
    volley = build_message_volley(ctx, "segment_classification", collate_input, profile="collate")
    assert len([m for m in volley if m["role"] == "assistant"]) == 3
