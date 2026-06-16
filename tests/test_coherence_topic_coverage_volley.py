from __future__ import annotations

from interview_mux.coherence.compact import attach_coherence_summary
from interview_mux.run_context import RunContext


def test_build_input_includes_coherence_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("cov_volley", create=True)
    duration = 31 * 60 * 1000
    ctx.write_json(
        "transcript/full.json",
        {"words": [{"text": "x", "start_ms": 0, "end_ms": duration, "speaker_id": "s"}]},
    )
    ctx.write_json(
        "understanding/coherence_report.json",
        {
            "schema_version": 1,
            "gate": {"min_duration_ms": 1800000, "activated": True, "duration_ms": duration},
            "derived_from": {"computed_at": "t", "phase": "post_reanchor", "duration_ms": duration},
            "scores": [],
            "risks": [],
            "summary": {"topic_drift_count": 0, "claim_contradiction_count": 0, "missing_callback_count": 0},
        },
    )
    payload: dict = {}
    attach_coherence_summary(payload, ctx, "topic_coverage_audit")
    assert "coherence_summary" in payload
    assert payload["coherence_summary"]["activated"] is True
