from __future__ import annotations

from interview_mux.coherence.compact import compact_for_volley
from interview_mux.context_volley import _compact_coherence_summary
from interview_mux.run_context import RunContext


def test_compact_for_volley_caps(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("volley", create=True)
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
            "risks": [
                {"risk_id": f"r{i}", "kind": "topic_drift", "time_ms": i, "confidence": 0.6, "evidence": {}, "status": "open"}
                for i in range(10)
            ],
            "summary": {"topic_drift_count": 10, "claim_contradiction_count": 0, "missing_callback_count": 0},
        },
    )
    summary = compact_for_volley(ctx, "topic_coverage_audit")
    assert summary is not None
    assert len(summary["risks"]) <= 5
    shaped = _compact_coherence_summary(summary, "topic_coverage_audit")
    assert len(shaped["risks"]) <= 5
