"""Unattended Full-auto reliability: report, identical-failure halt, repairs, catalog."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.e2e_soft import e2e_quality_waivers_enabled, e2e_soft_enabled
from interview_mux.execution_report import (
    REPORT_MD_REL,
    build_execution_report,
    write_execution_report,
)
from interview_mux.identical_failures import (
    halt_after,
    record_identical_failure,
    upsert_fail_key,
)
from interview_mux.opening_adjacency_repair import (
    suppress_opening_layup_when_orientation_owns_slot,
)
from interview_mux.stage_families import source_profile_recipe
from interview_mux.unattended_resume import resume_producer_for_block

from tests.run_fixtures import isolated_run_ctx


def test_e2e_quality_waivers_off_even_when_soft(monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    monkeypatch.delenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", raising=False)
    assert e2e_soft_enabled() is True
    assert e2e_quality_waivers_enabled() is False
    monkeypatch.setenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", "1")
    assert e2e_quality_waivers_enabled() is True


def test_identical_failure_halts_at_three(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_ident_halt")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    assert halt_after() >= 3
    last = None
    for _ in range(3):
        last = record_identical_failure(
            ctx,
            failed_stage="edl_narrative_audit",
            producer="understanding/gap_report.json",
            reason="opening orientation and opening layup both target seg_001",
        )
    assert last is not None
    assert last["count"] == 3
    assert last["halt"] is True
    stored = json.loads(
        (ctx.run_dir / "operator" / "identical_failures.json").read_text(encoding="utf-8")
    )
    assert stored["signatures"][last["signature"]]["count"] == 3


def test_upsert_fail_key_survives_absolute_counts(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_ident_upsert")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    row = upsert_fail_key(ctx, "partial_artifact:content_brief.json", 2, failed_stage="sonic_context_build")
    assert row["count"] == 2
    assert row["halt"] is False
    row = upsert_fail_key(ctx, "partial_artifact:content_brief.json", 3, failed_stage="sonic_context_build")
    assert row["halt"] is True


def test_execution_report_written_on_halt(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_report_halt")
    (ctx.run_dir / "run_meta.json").write_text(
        json.dumps(
            {
                "homunculus_version": "0.1.0",
                "full_auto": True,
                "journey_milestones": {"g0_complete": True},
            }
        ),
        encoding="utf-8",
    )
    record_identical_failure(
        ctx,
        failed_stage="topic_coverage_audit",
        producer="understanding/gap_evaluations.json",
        reason="gap_evaluations.json pending",
    )
    record_identical_failure(
        ctx,
        failed_stage="topic_coverage_audit",
        producer="understanding/gap_evaluations.json",
        reason="gap_evaluations.json pending",
    )
    record_identical_failure(
        ctx,
        failed_stage="topic_coverage_audit",
        producer="understanding/gap_evaluations.json",
        reason="gap_evaluations.json pending",
    )
    report = write_execution_report(
        ctx,
        outcome="halted_identical_failure",
        halt_stage="topic_coverage_audit",
        root_cause="gap_evaluations.json pending after rewind",
        decisions=[{"severity": "major", "action": "pause"}],
    )
    assert report["outcome"] == "halted_identical_failure"
    assert report["g0"]["accepted_unreviewed"] is True
    assert report["research_next"]
    md = ctx.run_dir / REPORT_MD_REL
    assert md.is_file()
    text = md.read_text(encoding="utf-8")
    assert "halted_identical_failure" in text
    assert "topic_coverage_audit" in text


def test_execution_report_complete_ship_bar(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_report_ok")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    master = ctx.run_dir / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "master.wav").write_bytes(b"RIFF" + b"\x00" * 2000)
    pub = ctx.run_dir / "publish"
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "cover.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 100)
    (pub / "audio.mp3").write_bytes(b"ID3" + b"\x00" * 100)
    report = build_execution_report(ctx, outcome="complete")
    assert report["ship"]["master"]["present"] is True
    assert report["ship"]["cover"]["present"] is True


def test_opening_adjacency_keeps_orientation_suppresses_layup(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_open_adj")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "selection.json").write_text(
        json.dumps({"ordered_segment_ids": ["seg_001", "seg_002"]}),
        encoding="utf-8",
    )
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_001",
                "origin": "nugget_layup",
                "targets_segment_id": "seg_001",
                "placement": "before",
                "text": "What should we listen for next?",
            },
            {
                "line_id": "vo_preface_episode_orientation",
                "episode_orientation": True,
                "targets_segment_id": "seg_001",
                "placement": "before",
                "text": "Before the science, meet the founder.",
            },
        ]
    }
    (ctx.run_dir / "understanding" / "gap_report.json").write_text(
        json.dumps(gap), encoding="utf-8"
    )
    changed = suppress_opening_layup_when_orientation_owns_slot(ctx)
    assert "vo_layup_seg_001" in changed
    out = json.loads((ctx.run_dir / "understanding" / "gap_report.json").read_text(encoding="utf-8"))
    by_id = {ln["line_id"]: ln for ln in out["interviewer_lines"]}
    assert by_id["vo_layup_seg_001"].get("skipped_optional") is True
    assert by_id["vo_preface_episode_orientation"].get("skipped_optional") is not True


def test_resume_producer_for_topic_coverage_missing_gaps(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_resume_prod")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    resume = resume_producer_for_block(
        ctx,
        consumer_stage="topic_coverage_audit",
        message="P0 spine incomplete: understanding/gap_evaluations.json missing",
    )
    assert resume == "missing_framing"


def test_mark_done_refuses_partial_llm_artifact(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_mark_partial")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    (ctx.run_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "understanding" / "speakers.json").write_text(
        json.dumps({"speakers": []}),
        encoding="utf-8",
    )
    ctx.mark_done("speaker_roles")
    assert not ctx.is_done("speaker_roles")
    ctx.mark_done("speaker_roles", force=True)
    assert not ctx.is_done("speaker_roles")


def test_source_profile_recipe_noisy_mono():
    recipe = source_profile_recipe("noisy_mono")
    assert recipe.get("diarization_retry") == 2
    assert recipe.get("preclean_aggressiveness") == "high"


def test_unattended_defaults_follow_full_auto_env(monkeypatch, tmp_path: Path):
    from interview_mux.stage_resilience import unattended_defaults_enabled

    monkeypatch.delenv("MUX_FULL_AUTO", raising=False)
    monkeypatch.delenv("MUX_RUN_MODE", raising=False)
    monkeypatch.delenv("INTERVIEW_MUX_AUTO_ACCEPT_GATES", raising=False)
    ctx = isolated_run_ctx(tmp_path, "exec_unattended_off")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    assert unattended_defaults_enabled(ctx) is False
    monkeypatch.setenv("MUX_FULL_AUTO", "1")
    assert unattended_defaults_enabled(ctx) is True


def test_catalog_unattended_breakpoints_nonempty():
    import sys
    from pathlib import Path as P

    root = P(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    import catalog_unattended_breakpoints as cat

    catalog = cat.build_catalog()
    assert catalog["pipeline_stages"] == 67
    assert catalog["breakpoint_count"] > 50
    kinds = {row["kind"] for row in catalog["breakpoints"]}
    assert "completeness_gap_rule" in kinds
    assert "stage_contract" in kinds
    assert "driver_fail_key" in kinds
