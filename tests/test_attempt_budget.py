from __future__ import annotations

from interview_mux.attempt_budget import (
    check_arbiter_budget,
    max_arbiter_rejects,
    record_arbiter_reject,
    record_primary_attempt,
    stuck_count,
)
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_primary_attempt_count_increments(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx = isolated_run_ctx(tmp_path, "budget")
    assert record_primary_attempt(ctx, "content_context") == 1
    assert record_primary_attempt(ctx, "content_context") == 2


def test_arbiter_budget_exhaustion(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "max_arbiter_rejects_per_stage": 2}}},
    )
    ctx = isolated_run_ctx(tmp_path, "arb_budget")
    record_arbiter_reject(ctx, "content_context", "enqueue_investigation")
    record_arbiter_reject(ctx, "content_context", "retry_uptier")
    msg = check_arbiter_budget(ctx, "content_context")
    assert msg is not None
    assert "arbiter reject budget" in msg


def test_stuck_signature_tracking(tmp_path, monkeypatch):
    from interview_mux.attempt_budget import build_attempt_signature, record_stuck_signature

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "stuck_signature_threshold": 2}}},
    )
    ctx = isolated_run_ctx(tmp_path, "stuck")
    sig = build_attempt_signature({"status": "blocked"}, [], [], ["thesis empty"])
    record_stuck_signature(ctx, "speaker_roles", sig)
    record_stuck_signature(ctx, "speaker_roles", sig)
    assert stuck_count(ctx, "speaker_roles") >= 2


def test_stuck_signature_differs_when_lint_changes(tmp_path, monkeypatch):
    from interview_mux.attempt_budget import build_attempt_signature, record_stuck_signature

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "stuck_signature_threshold": 2}}},
    )
    ctx = isolated_run_ctx(tmp_path, "stuck_lint")
    sig_a = build_attempt_signature({"status": "blocked"}, [], [], ["thesis empty"])
    sig_b = build_attempt_signature({"status": "blocked"}, [], [], ["confidence_gte_min"])
    record_stuck_signature(ctx, "content_context", sig_a)
    record_stuck_signature(ctx, "content_context", sig_b)
    assert stuck_count(ctx, "content_context") == 1
