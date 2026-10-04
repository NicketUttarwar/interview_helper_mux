"""A fuse pass that re-plans the same merges has converged; it is not a critical cut residual (ISSUES 168).

exec_019: connector_fuse_pass recorded fuse_oscillation (critical) at 18:16
when round 2 planned exactly round 1's merges. Two hours later the
post-junction publishability checkpoint blocked junction_snip_qa on it
("critical_residuals=1 kinds=['fuse_oscillation'] sources=['delivery_ledger']").
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


def test_repeated_plan_records_an_advisory() -> None:
    from interview_mux import segment_fuse

    src = inspect.getsource(segment_fuse)
    branches = []
    rest = src
    while "if sig and sig == last_sig:" in rest:
        rest = rest[rest.index("if sig and sig == last_sig:") :]
        branches.append(rest[: rest.index("break")])
        rest = rest[1:]
    assert len(branches) == 2
    for branch in branches:
        assert 'kind="fuse_oscillation"' in branch
        assert 'severity="advisory"' in branch and 'severity="critical"' not in branch


def test_advisory_fuse_residual_does_not_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.delivery_guardrails import critical_residual_view, record_delivery_residual

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_fuse_repeat")
    record_delivery_residual(
        ctx,
        kind="fuse_oscillation",
        severity="advisory",
        stage="connector_fuse_pass",
        detail={"pass_id": "post_sanitize", "round": 2},
    )
    assert critical_residual_view(ctx).count == 0


def test_unknown_severity_still_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Callers must use a real severity; anything else blocks (documents the trap)."""
    from interview_mux.delivery_guardrails import critical_residual_view, record_delivery_residual

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_fuse_sev")
    record_delivery_residual(ctx, kind="x", severity="warning", stage="s", detail={"pass_id": "p"})
    assert critical_residual_view(ctx).count == 1
