"""Journey open_coherence_risks must match analysis_state open risks."""

from __future__ import annotations

from interview_mux.journey_orchestrator import _open_coherence_risk_count, build_journey_snapshot
from interview_mux.run_context import RunContext
from run_fixtures import populated_analysis_state


def test_coherence_risk_count_matches_journey(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    state = populated_analysis_state(ctx.run_id)
    state["coherence_risks"] = [
        {"id": "r1", "status": "open", "kind": "topic_drift"},
        {"id": "r2", "status": "resolved", "kind": "topic_drift"},
        {"id": "r3", "status": "open", "kind": "claim_contradiction"},
    ]
    ctx.write_json("understanding/analysis_state.json", state, skip_handoff=True)
    assert _open_coherence_risk_count(ctx) == 2
    journey = build_journey_snapshot(ctx)
    assert journey["open_coherence_risks"] == 2
