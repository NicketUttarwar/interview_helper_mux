"""Journey kernel snapshot and next_action appendix parity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.journey_orchestrator import (
    NEXT_ACTION_COMPLETE_G2,
    NEXT_ACTION_PREPARE_G0,
    NEXT_ACTION_UNDERSTAND_PROFILE,
    _active_operator_action,
    _active_substep,
    _blocking,
    _is_llm_gate_message,
    build_journey_snapshot,
)
from interview_mux.run_context import RunContext

FIXTURE = Path(__file__).parent / "fixtures/runs/base_smoke"


@pytest.fixture
def smoke_ctx(tmp_path, monkeypatch):
    run_id = "exec_001_20260101T000000Z"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    for rel in FIXTURE.rglob("*"):
        if rel.is_file():
            dest = run_dir / rel.relative_to(FIXTURE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(rel.read_bytes())
    meta_path = run_dir / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["execution_id"] = run_id
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    cfg_path = tmp_path.parent / "config_override"
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": str(tmp_path),
            "data_root": str(tmp_path / "data"),
        },
    )
    monkeypatch.setattr(
        "interview_mux.journey_orchestrator.merged_config",
        lambda: {"journey_ui": {"enabled": True}},
    )
    return RunContext(run_id, create=False)


def test_next_action_constants_documented():
    doc = Path(__file__).parents[1] / "docs/workflows/operator-journey.md"
    text = doc.read_text(encoding="utf-8")
    assert NEXT_ACTION_PREPARE_G0 in text
    assert NEXT_ACTION_UNDERSTAND_PROFILE in text
    assert NEXT_ACTION_COMPLETE_G2 in text


def test_build_journey_snapshot_smoke(smoke_ctx):
    snap = build_journey_snapshot(smoke_ctx)
    assert snap["phase"] in (
        "prepare",
        "understand",
        "complete",
        "create",
        "polish",
        "ship",
    )
    assert "next_action" in snap
    assert "blocking" in snap
    assert "active_operator_action" in snap
    assert "milestones" in snap
    assert isinstance(snap["milestones"]["g0_complete"], bool)
    for key in ("sfx_generated", "sfx_listen_complete", "placement_qa_ready"):
        assert key in snap["milestones"]


def test_active_substep_write_approval_priority():
    job = {
        "status": "awaiting_write_approval",
        "stage": "ingest",
        "pending_write_stage": "ingest",
        "message": "Review ingest outputs before saving",
    }
    out = _active_substep(None, job=job, blocking={}, hint=None)
    assert out["active_substep_id"] == "write_approval:ingest"
    assert "ingest" in out["active_substep_label"].lower()


def test_active_substep_running_job():
    job = {"status": "running", "stage": "transcribe", "current_stage": "transcribe"}
    out = _active_substep(None, job=job, blocking={}, hint=None)
    assert out["active_substep_id"] == "running"
    assert "transcribe" in out["active_substep_label"].lower()


def test_active_substep_blocked_gate(smoke_ctx):
    snap = build_journey_snapshot(smoke_ctx)
    blocking = snap.get("blocking") or {}
    assert blocking.get("blocked")
    out = _active_substep(smoke_ctx, job=None, blocking=blocking, hint=snap.get("execute_hint"))
    sub_id = str(out.get("active_substep_id") or "")
    assert sub_id.startswith("blocked:") or sub_id.startswith("gate:")


def test_active_substep_stage_reuse_blocking():
    blocking = {
        "blocked": True,
        "reason": "stage_reuse",
        "stage_id": "transcribe",
        "message": "Choose reuse or run fresh",
    }
    out = _active_substep(None, job=None, blocking=blocking, hint=None)
    assert out["active_substep_id"] == "stage_reuse:transcribe"


def test_active_substep_stage_reuse_job():
    job = {"status": "needs_operator", "stage": "transcribe", "needs_stage_reuse": True}
    out = _active_substep(None, job=job, blocking={}, hint=None)
    assert out["active_substep_id"] == "stage_reuse:transcribe"


def test_journey_milestones_sfx_generated(tmp_path, monkeypatch):
    from interview_mux.gates import set_selected_flow
    from interview_mux.journey_state import compute_milestones
    from run_fixtures import isolated_run_ctx, seed_flow1_sound_spend_ready

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "journey_sfx")
    set_selected_flow(ctx, "flow1")
    seed_flow1_sound_spend_ready(ctx)
    ctx.mark_done("mmaudio_sfx_flow1")
    ms = compute_milestones(ctx)
    assert ms["sfx_generated"] is True
    assert ms["sfx_listen_complete"] is True
    assert ms["placement_qa_ready"] is False


def test_execute_hint_flow2_polish_skips_preview(tmp_path, monkeypatch):
    from interview_mux.gates import set_selected_flow
    from interview_mux.journey_orchestrator import execute_hint
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "journey_f2")
    set_selected_flow(ctx, "flow2")
    ctx.mark_done("highlight_selection")
    ctx.mark_done("sfx_prompt_craft")
    milestones = {
        "g0_complete": True,
        "g1_complete": True,
        "g2_complete": True,
        "sfx_approved": True,
        "sfx_generated": False,
        "sfx_listen_complete": True,
        "preview_ready": False,
        "preview_listened": False,
    }
    hint = execute_hint("polish", "flow2", "flow2", milestones)
    assert hint is not None
    assert hint.get("from_stage") == "mmaudio_sfx_flow2"


def test_execute_hint_prepare(smoke_ctx):
    snap = build_journey_snapshot(smoke_ctx)
    if snap["phase"] == "prepare":
        hint = snap.get("execute_hint")
        if hint:
            assert hint["mode"] in ("analysis", "analysis_until_g0")
            assert hint.get("until_stage") == "transcript_review_build" or hint.get("mode")


def test_blocking_write_approval_short_circuits_reuse_scan(tmp_path, monkeypatch):
    from interview_mux.journey_orchestrator import _blocking
    from run_fixtures import init_run_meta_for_test, isolated_run_ctx

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {
            "assets_root": str(tmp_path / "ASSETS"),
            "executions_root": str(tmp_path / "ASSETS" / "executions"),
            "data_root": str(tmp_path / "data"),
        },
    )
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": str(tmp_path / "ASSETS"),
            "executions_root": str(tmp_path / "ASSETS" / "executions"),
            "data_root": str(tmp_path / "data"),
        },
    )
    ctx = isolated_run_ctx(tmp_path, "exec_001_20260101T000000Z")
    init_run_meta_for_test(ctx)
    job = {
        "status": "awaiting_write_approval",
        "stage": "ingest",
        "pending_write_stage": "ingest",
        "message": "Awaiting your review",
        "pending_write_paths": ["ingest/normalized.wav"],
    }
    snap = _blocking(ctx, job=job, milestones={"g0_complete": False})
    assert snap["blocked"] is True
    assert snap["reason"] == "write_approval"
    assert snap["stage_id"] == "ingest"
    assert snap["message"] == "Awaiting your review"


def test_blocking_reuse_scan_only_first_pending_stage(tmp_path, monkeypatch):
    from interview_mux.journey_orchestrator import _blocking
    from run_fixtures import init_run_meta_for_test, isolated_run_ctx

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {
            "assets_root": str(tmp_path / "ASSETS"),
            "executions_root": str(tmp_path / "ASSETS" / "executions"),
            "data_root": str(tmp_path / "data"),
            "stage_execution_reuse": {"enabled": True},
        },
    )
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": str(tmp_path / "ASSETS"),
            "executions_root": str(tmp_path / "ASSETS" / "executions"),
            "data_root": str(tmp_path / "data"),
            "stage_execution_reuse": {"enabled": True},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "exec_001_20260101T000000Z")
    init_run_meta_for_test(ctx)

    calls: list[str] = []

    def _fake_reuse(current, stage_id):
        calls.append(stage_id)
        return []

    monkeypatch.setattr(
        "interview_mux.stage_execution_reuse.reuse_candidates_if_undecided",
        _fake_reuse,
    )

    snap = _blocking(ctx, job={"status": "idle"}, milestones={"g0_complete": False})
    assert snap["blocked"] is False
    assert calls == ["audio_preclean"]


def test_active_operator_action_write_approval(tmp_path, monkeypatch):
    from run_fixtures import init_run_meta_for_test, isolated_run_ctx

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": str(tmp_path / "ASSETS"),
            "executions_root": str(tmp_path / "ASSETS" / "executions"),
            "data_root": str(tmp_path / "data"),
        },
    )
    ctx = isolated_run_ctx(tmp_path, "exec_001_20260101T000000Z")
    init_run_meta_for_test(ctx)
    job = {
        "status": "awaiting_write_approval",
        "stage": "ingest",
        "pending_write_stage": "ingest",
        "message": "Awaiting your review",
        "pending_write_paths": ["ingest/normalized.wav", "ingest/checksums.json"],
    }
    blocking = {"blocked": True, "reason": "write_approval", "stage_id": "ingest", "message": "Awaiting your review"}
    action = _active_operator_action(ctx, job=job, blocking=blocking, milestones={})
    assert action["mode"] == "needs_you"
    assert action["stage_id"] == "ingest"
    assert action["substep_id"] == "write_approval:ingest"
    assert action["modal_auto_open"] is True
    assert "Review" in action["headline"]
    assert "2 staged files" in action["subline"]


def test_active_operator_action_running_job():
    job = {
        "status": "running",
        "stage": "transcribe",
        "message": "Transcribe: uploading audio…",
    }
    action = _active_operator_action(None, job=job, blocking={}, milestones={})
    assert action["mode"] == "running"
    assert action["stage_id"] == "transcribe"
    assert "uploading" in action["headline"].lower()
    assert action["modal_auto_open"] is False


def test_is_llm_gate_message_recognizes_budget_exhaustion() -> None:
    assert _is_llm_gate_message(
        "Stage content_context: primary attempt budget exhausted (4/4)."
    )
    assert _is_llm_gate_message("LLM stage gate (content_context): blocked")
    assert not _is_llm_gate_message("Awaiting your review")


def test_blocking_budget_exhaustion_uses_llm_gate_reason(tmp_path, monkeypatch):
    from run_fixtures import init_run_meta_for_test, isolated_run_ctx

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "exec_001_20260101T000000Z")
    init_run_meta_for_test(ctx)
    job = {
        "status": "gate",
        "stage": "content_context",
        "message": "Stage content_context: primary attempt budget exhausted (4/4).",
    }
    blocking = _blocking(ctx, job=job, milestones={})
    assert blocking["blocked"] is True
    assert blocking["reason"] == "llm_gate"
    assert blocking["stage_id"] == "content_context"


def test_build_journey_snapshot_includes_active_operator_action(smoke_ctx):
    snap = build_journey_snapshot(smoke_ctx)
    action = snap["active_operator_action"]
    assert isinstance(action, dict)
    assert "mode" in action
    assert "modal_auto_open" in action
    if action.get("mode") == "needs_you":
        assert action.get("stage_id")
        assert action.get("headline")
