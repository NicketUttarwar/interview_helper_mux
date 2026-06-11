"""run_single_stage invokes LLM hardening hooks."""

from __future__ import annotations

from unittest.mock import MagicMock

from interview_mux.pipeline import run_single_stage
from run_fixtures import isolated_run_ctx


def test_run_single_stage_calls_upstream_check(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_single_harden")
    ctx.mark_done("speaker_roles")
    calls: list[str] = []

    def _fake_upstream(c, stage_key):
        calls.append(stage_key)

    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.maybe_require_upstream_llm_progress",
        _fake_upstream,
    )
    monkeypatch.setattr(
        "interview_mux.analysis_orchestrator.drain_investigation_queue",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_cross_validate.maybe_cross_validate_after_stage",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "interview_mux.stages.understanding.run_content_context",
        MagicMock(),
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.run_wrapped_stage",
        lambda c, s, fn: fn(),
    )

    run_single_stage(ctx, "content_context")
    assert calls == ["content_context"]
