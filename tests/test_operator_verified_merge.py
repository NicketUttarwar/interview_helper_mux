"""Operator-verified profile blocks direct memory overwrites."""

from __future__ import annotations

from interview_mux.analysis_memory import default_analysis_state, merge_memory_updates


def test_operator_verified_blocks_direct_themes_merge():
    state = default_analysis_state("run_ov")
    state["meta"]["operator_verified"] = True
    state["themes"] = [{"id": "t1", "label": "Operator theme"}]
    merged, _ = merge_memory_updates(
        state,
        {"themes": [{"id": "t2", "label": "LLM theme"}]},
        skip_operator_conflicts=True,
    )
    assert merged["themes"] == state["themes"]
