from interview_mux.llm_output_resilience import resolve_persist_plan
from run_fixtures import isolated_run_ctx


def test_block_partial_segment_classification_on_coverage_lint(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "seg_class_block")
    envelope = {
        "status": "partial",
        "artifacts": {"segments": [{"segment_id": "seg_001", "type": "interviewee_answer"}]},
    }
    plan = resolve_persist_plan(
        ctx,
        "segment_classification",
        envelope,
        {"verdict": "accept"},
        [],
        ["segment_coverage_ratio: 0.50 < 1.0"],
    )
    assert plan.action == "none"
    summary = (plan.report.summary or "").lower()
    assert "blocked" in summary or "schema validation failed" in summary
