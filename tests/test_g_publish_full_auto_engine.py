"""G-Publish is not the operator's while the full-auto engine owns the run (ISSUES 92)."""

from __future__ import annotations

import pytest
from run_fixtures import isolated_run_ctx

from interview_mux.gates import check_g_publish_pending


def _stamp(ctx, **fields) -> None:
    ctx.mutate_run_meta(lambda m: m.update(fields))


@pytest.fixture(autouse=True)
def _podcast_enabled(monkeypatch):
    monkeypatch.setattr("interview_mux.gates.merged_config", lambda: {"podcast": {"enabled": True}})


def test_pending_flag_is_hidden_while_the_full_auto_engine_is_alive(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_gpub_engine")
    _stamp(ctx, run_mode="full-auto", full_auto=True, g_publish_pending=True,
           orchestrator={"active": True, "mode": "full-auto"})
    assert check_g_publish_pending(ctx) is False


def test_pending_flag_shows_once_the_engine_is_gone_without_a_sign_off(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_gpub_engine_gone")
    _stamp(ctx, run_mode="full-auto", full_auto=True, g_publish_pending=True,
           orchestrator={"active": False, "mode": "full-auto"})
    assert check_g_publish_pending(ctx) is True


def test_partial_mode_still_waits_for_the_operator(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_gpub_partial")
    _stamp(ctx, run_mode="partially-accelerated", partial_auto=True, g_publish_pending=True,
           orchestrator={"active": True, "mode": "partially-accelerated"},
           partial_auto_driver_active=True)
    assert check_g_publish_pending(ctx) is True
