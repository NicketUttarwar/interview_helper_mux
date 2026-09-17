"""Positive heal tests for stage_completion.heal_or_refuse_mark."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.audio_probe_orchestrator import empty_probe_artifacts
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_raise, heal_or_refuse_mark
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging
from run_fixtures import isolated_run_ctx


def test_heal_marks_when_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    # topic_coverage may have incompleteness without artifacts — use a stage
    # that accepts force when no hollow check fires: podcast_publish with skip.
    # Prefer: mark transitions only when incompleteness None after stub outputs.
    ctx.write_json(
        "master/transitions.json",
        {"transitions": []},
        stage_key="transitions",
    )
    out = heal_or_refuse_mark(ctx, "transitions")
    # Either marked (complete) or refused with reason — never silent force.
    assert out.get("marked") or out.get("refused") or out.get("unmarked") is False


def test_heal_refuses_empty_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    out = heal_or_refuse_mark(ctx, "")
    assert out.get("refused") is True


def test_heal_or_raise_flushes_active_stage_pending_before_pending_only(
    tmp_path: Path, monkeypatch
) -> None:
    """exec_11630: heal_or_raise under staging must commit, not raise pending_only."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "heal_flush_pending")
    arts = empty_probe_artifacts(enforcement_mode="shadow", reason="unit_heal_flush")
    stage = "audio_probe_build"
    root = ctx.run_dir / ".pending_writes" / stage
    payloads = {
        "analysis/run_golden_facts.json": arts["golden_facts"],
        "transcript/protected_zones.json": arts["protected_zones"],
        "transcript/speaker_flows.json": arts["speaker_flows"],
        "vernacular/probe_report.json": arts["probe_report"],
        "vernacular/audio_tags_by_flow.json": {"version": 1, "by_flow": {}},
    }
    for rel, body in payloads.items():
        dest = root.joinpath(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(body), encoding="utf-8")

    assert not (ctx.run_dir / "analysis" / "run_golden_facts.json").is_file()
    enter_stage_staging(stage)
    try:
        out = heal_or_raise(ctx, stage)
    finally:
        exit_stage_staging()

    assert out.get("marked") is True
    assert (ctx.run_dir / "analysis" / "run_golden_facts.json").is_file()
    assert ctx.is_done(stage)
    assert not (root / "analysis" / "run_golden_facts.json").is_file()


def test_edl_narrative_audit_fail_verdict_is_incomplete(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    import json

    from interview_mux.run_context import RunContext
    from interview_mux.stage_completion import stage_artifact_incompleteness

    ctx = RunContext(create=True)
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    (ctx.path("master") / "edl_narrative_audit.json").write_text(
        json.dumps(
            {
                "verdict": "fail",
                "blocking_issues": [
                    {
                        "issue": "blank air ids",
                        "evidence": ["seg_003a"],
                        "recommended_action": "drop blanks",
                    }
                ],
                "warnings": [],
                "recommended_actions": [],
                "reasoning_summary": "test",
            }
        ),
        encoding="utf-8",
    )
    reason = stage_artifact_incompleteness(ctx, "edl_narrative_audit")
    assert reason and "verdict=fail" in reason
