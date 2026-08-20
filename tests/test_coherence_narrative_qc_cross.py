from __future__ import annotations

from interview_mux.narrative_qc import validate_flow1_narrative
from interview_mux.run_context import RunContext


def test_narrative_qc_cross_missing_callback(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("nqc", create=True)
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "t", "topics": [{"name": "Vision", "summary": "Future"}]},
    )
    ctx.write_json(
        "master/coverage_audit.json",
        {"coverage_score": 0.5, "topic_mappings": [], "missing_coverage": []},
    )
    duration = 31 * 60 * 1000
    ctx.write_json(
        "understanding/coherence_report.json",
        {
            "schema_version": 1,
            "gate": {"activated": True, "min_duration_ms": 1800000, "duration_ms": duration},
            "derived_from": {"computed_at": "t", "phase": "post_coverage", "duration_ms": duration},
            "scores": [],
            "risks": [
                {
                    "risk_id": "mc1",
                    "kind": "missing_callback",
                    "time_ms": duration // 2,
                    "confidence": 0.7,
                    "evidence": {"topic": "Vision"},
                    "status": "open",
                }
            ],
            "summary": {"topic_drift_count": 0, "claim_contradiction_count": 0, "missing_callback_count": 1},
        },
    )
    errors = validate_flow1_narrative(ctx)
    assert any("Coherence missing_callback" in e for e in errors)

    from interview_mux.artifact_repairs import repair_coverage_audit

    repaired, notes = repair_coverage_audit(
        ctx, ctx.read_json("master/coverage_audit.json")
    )
    ctx.write_json("master/coverage_audit.json", repaired, skip_handoff=True)
    assert notes
    after = validate_flow1_narrative(ctx)
    assert not any("Coherence missing_callback" in e for e in after)


def test_narrative_qc_coherence_callback_outside_brief_topics(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("nqc2", create=True)
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "t", "topics": [{"name": "Other", "summary": "Unrelated"}]},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/coverage_audit.json",
        {"coverage_score": 0.5, "topic_mappings": [], "missing_coverage": []},
        skip_handoff=True,
    )
    duration = 31 * 60 * 1000
    ctx.write_json(
        "understanding/coherence_report.json",
        {
            "schema_version": 1,
            "gate": {"activated": True, "min_duration_ms": 1800000, "duration_ms": duration},
            "derived_from": {"computed_at": "t", "phase": "post_coverage", "duration_ms": duration},
            "scores": [],
            "risks": [
                {
                    "risk_id": "mc2",
                    "kind": "missing_callback",
                    "time_ms": duration // 2,
                    "confidence": 0.7,
                    "evidence": {"topic": "From tissue biopsy to liquid biopsy"},
                    "status": "open",
                }
            ],
            "summary": {"topic_drift_count": 0, "claim_contradiction_count": 0, "missing_callback_count": 1},
        },
        skip_handoff=True,
    )
    errors = validate_flow1_narrative(ctx)
    assert any("Coherence missing_callback" in e for e in errors)
    from interview_mux.artifact_repairs import repair_coverage_audit

    repaired, notes = repair_coverage_audit(
        ctx, ctx.read_json("master/coverage_audit.json")
    )
    ctx.write_json("master/coverage_audit.json", repaired, skip_handoff=True)
    assert any(
        n.get("action") == "seed_missing_coverage_from_coherence_callback"
        for n in notes
        if isinstance(n, dict)
    )
    after = validate_flow1_narrative(ctx)
    assert not any("Coherence missing_callback" in e for e in after)
