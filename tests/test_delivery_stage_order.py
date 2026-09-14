"""5C delivery stage order — adjudicate → synth → audit."""

from __future__ import annotations

from pathlib import Path

from interview_mux.stages.edl_narrative_audit import run_edl_narrative_audit
from interview_mux.stage_input_checks import collect_stage_input_issues
from interview_mux.v2.config import DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw


def test_delivery_order_5c():
    assert DELIVERY_ORDER.index("sound_design_vo_finalize") < DELIVERY_ORDER.index("vo_line_adjudicate")
    assert DELIVERY_ORDER.index("vo_line_adjudicate") < DELIVERY_ORDER.index("vo_synthesize")
    assert DELIVERY_ORDER.index("vo_synthesize") < DELIVERY_ORDER.index("edl_narrative_audit")
    assert DELIVERY_ORDER.index("edl_narrative_audit") < DELIVERY_ORDER.index("edl")


def test_edl_narrative_audit_build_input_notes_heard_wav(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "audit_heard")
    ctx.write_json("understanding/content_brief.json", {"thesis": "test", "topics": []}, skip_handoff=True)
    ctx.write_json(
        "master/coverage_audit.json",
        {"topics": [], "topic_mappings": [], "coverage_score": 1.0},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/narrative_plan.json",
        {"chapters": [], "arc_summary": "test", "ordering_constraints": []},
        skip_handoff=True,
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001"]}, skip_handoff=True)
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []}, skip_handoff=True)

    captured: dict = {}

    def fake_run_flow_llm_stage(_ctx, _stage, _prompt, build_input, persist):
        captured.update(build_input(_ctx))
        persist(
            _ctx,
            {
                "verdict": "pass",
                "blocking_issues": [],
                "warnings": [],
                "recommended_actions": [],
                "reasoning_summary": "heard wav flow ok",
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(
        "interview_mux.stages.edl_narrative_audit.run_flow_llm_stage",
        fake_run_flow_llm_stage,
    )
    mark_done_raw(ctx, "vo_synthesize")
    run_edl_narrative_audit(ctx)
    assert captured.get("audit_mode") == "heard_wav_flow"
    assert captured.get("vo_synthesis_complete") is False
    assert "vo_coverage" in captured


def test_edl_narrative_audit_prereq_requires_vo_synthesize(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "audit_prereq")
    issues = collect_stage_input_issues(ctx, "edl_narrative_audit")
    assert any("vo_synthesize" in i.message for i in issues)
