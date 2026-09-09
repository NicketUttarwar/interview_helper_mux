"""Sticky needs_operator clear for automated mid-delivery failures."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gui_job_reconcile import reconcile_sticky_needs_operator_job
from run_fixtures import isolated_run_ctx


def test_reconcile_sticky_needs_operator_clears_seed_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "sticky_no")
    ctx.write_json(
        "run_meta.json",
        {"partial_auto": True, "homunculus_version": "0.1.0"},
        skip_handoff=True,
    )
    job = {
        "status": "needs_operator",
        "stage": "transitions",
        "message": "RuntimeError:seed order: complete air_script_seams before running transitions",
    }
    out = reconcile_sticky_needs_operator_job(ctx, job)
    assert out["status"] == "idle"
    assert "Autopilot resume" in str(out.get("message") or "")
