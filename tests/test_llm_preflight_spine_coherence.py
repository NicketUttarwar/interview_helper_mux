from __future__ import annotations

import json

from interview_mux.llm_preflight import run_preflight
from run_fixtures import isolated_run_ctx, minimal_speakers


def test_preflight_boundary_detection_requires_spine(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pf_spine_bd")
    speakers = minimal_speakers()
    speakers["speakers"] = [
        {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9, "evidence": ["x"]},
    ]
    ctx.write_json("understanding/speakers.json", speakers, stage_key="speaker_roles")
    errors = run_preflight("boundary_detection", ctx)
    assert any("interview_spine" in e for e in errors)


def test_preflight_narrative_arc_requires_coherence_report_for_long_interview(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pf_coherence")
    duration_ms = 31 * 60 * 1000
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "long interview fixture",
            "words": [
                {"text": "start", "start_ms": 0, "end_ms": 1000, "speaker_id": "spk_0"},
                {"text": "end", "start_ms": duration_ms - 1000, "end_ms": duration_ms, "speaker_id": "spk_1"},
            ],
        },
    )
    audit_path = ctx.path("master", "coverage_audit.json")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps({"topic_mappings": [], "coverage_score": 0.5}),
        encoding="utf-8",
    )
    monkeypatch.setattr("interview_mux.coherence.coherence_active", lambda: True)
    monkeypatch.setattr(
        "interview_mux.coherence.duration_gate.coherence_activated",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.llm_preflight._ensure_coherence_report",
        lambda _ctx: None,
    )
    errors = run_preflight("narrative_arc_plan", ctx)
    assert any("coherence_report" in e for e in errors)
