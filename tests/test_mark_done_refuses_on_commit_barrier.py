"""A commit-barrier refusal during mark_done's auto-flush refuses the seal (ISSUES 163).

exec_016: the barrier refused edl_narrative_audit's staged audit, mark_done's
broad except swallowed WriteApprovalBlockedError, and the stage was sealed with
nothing committed: "Stage finished", then "Cleared stale .stage_done ...
newer uncommitted pending", three times, then the thrash cap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx

STAGE = "edl_narrative_audit"
REL = "master/edl_narrative_audit.json"


def _stage_pending(ctx) -> None:
    import os

    committed = ctx.run_dir / "master" / "edl_narrative_audit.json"
    committed.parent.mkdir(parents=True, exist_ok=True)
    committed.write_text(
        '{"verdict": "warn", "blocking_issues": [], "warnings": [], '
        '"recommended_actions": [], "reasoning_summary": "ok"}'
    )
    os.utime(committed, (1_700_000_000, 1_700_000_000))
    root = ctx.run_dir / ".pending_writes" / STAGE / "master"
    root.mkdir(parents=True, exist_ok=True)
    (root / "edl_narrative_audit.json").write_text('{"verdict": "fail", "blocking_issues": [{"issue": "x"}]}')


def test_barrier_refusal_is_not_a_seal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.artifact_ownership import AuthorityDenied
    from interview_mux.stage_resilience import StageResilienceDecision

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_barrier_seal")
    _stage_pending(ctx)
    monkeypatch.setattr("interview_mux.v2.config.v2_auto_commit", lambda: True)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: False)
    monkeypatch.setattr(
        "interview_mux.stage_resilience.validate_staged_before_flush",
        lambda c, s: StageResilienceDecision(
            action="halt", reasons=["stale blocking issue"], acceptance_ok=False
        ),
    )
    with pytest.raises(AuthorityDenied, match="commit_barrier"):
        ctx.mark_done(STAGE)
    assert not (ctx.run_dir / ".stage_done" / STAGE).exists()
    assert (ctx.run_dir / ".pending_writes" / STAGE / "master" / "edl_narrative_audit.json").exists()


def test_try_mark_done_reports_the_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.done_authority import try_mark_done
    from interview_mux.stage_resilience import StageResilienceDecision

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_barrier_try")
    _stage_pending(ctx)
    monkeypatch.setattr("interview_mux.v2.config.v2_auto_commit", lambda: True)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: False)
    monkeypatch.setattr(
        "interview_mux.stage_resilience.validate_staged_before_flush",
        lambda c, s: StageResilienceDecision(action="halt", reasons=["x"], acceptance_ok=False),
    )
    assert try_mark_done(ctx, STAGE) is False
