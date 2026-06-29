from interview_mux.llm_output_resilience import resolve_persist_plan


def test_block_partial_segment_classification_on_coverage_lint():
    envelope = {
        "status": "partial",
        "artifacts": {"segments": [{"segment_id": "seg_001", "type": "interviewee_answer"}]},
    }
    plan = resolve_persist_plan(
        "segment_classification",
        envelope,
        {"verdict": "accept"},
        [],
        ["segment_coverage_ratio: 0.50 < 1.0"],
    )
    assert plan.action == "none"
    assert "blocked" in (plan.report.summary or "").lower()
