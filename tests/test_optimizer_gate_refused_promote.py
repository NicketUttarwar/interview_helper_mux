"""A refused optimizer promote does not hold master_finalize (ISSUES 53)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gates import check_timeline_optimizer_pending
from interview_mux.run_context import RunContext
from interview_mux.timeline_optimizer.state import save_optimizer_state


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: dict) -> RunContext:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_optimizer_gate", create=True)
    monkeypatch.setattr(
        "interview_mux.timeline_optimizer.config.optimizer_cfg",
        lambda: {"block_finalize_until_take_or_skip": True},
    )
    save_optimizer_state(ctx, {"status": "running", **state})
    return ctx


def test_running_daemon_holds_the_gate(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, {})
    assert check_timeline_optimizer_pending(ctx) is True


def test_refused_promote_releases_the_gate(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, {"auto_promote_attempted": True})
    assert check_timeline_optimizer_pending(ctx) is False


def test_promoted_once_releases_the_gate(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, {"auto_promoted_once": True})
    assert check_timeline_optimizer_pending(ctx) is False


def test_finalize_does_not_owe_a_refused_or_skipped_best(tmp_path, monkeypatch) -> None:
    from interview_mux.stages.mastering import _optimizer_skipped

    ctx = _ctx(tmp_path, monkeypatch, {})
    assert _optimizer_skipped(ctx) is False
    ctx.mutate_run_meta(lambda m: m.__setitem__("timeline_optimizer_skipped", True))
    assert _optimizer_skipped(ctx) is True
