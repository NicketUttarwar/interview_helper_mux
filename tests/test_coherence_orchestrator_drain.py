from __future__ import annotations

from interview_mux.analysis_memory import update_completion_from_analysis
from interview_mux.run_context import RunContext


def test_blocking_contradiction_blocks_analysis_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("block", create=True)
    ctx.write_json(
        "understanding/analysis_state.json",
        {"schema_version": 1, "themes": [{"id": "t1", "label": "T"}], "major_questions": [], "style": {}, "narrative": {}},
    )
    ctx.write_json(
        "understanding/investigation_queue.json",
        {
            "items": [
                {
                    "id": "inv_001",
                    "kind": "claim_contradiction",
                    "status": "open",
                    "blocking": True,
                    "question": "fix",
                    "suggested_action": {"type": "rerun_stage", "stage": "content_brief_reanchor"},
                    "target": {"risk_id": "r1"},
                }
            ]
        },
    )
    completion = update_completion_from_analysis(ctx)
    assert completion["analysis_ready"] is False
    assert any("claim_contradiction" in b for b in completion["blockers"])
