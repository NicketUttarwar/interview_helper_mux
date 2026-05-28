"""Shared helpers for isolated run directories (import as `from run_fixtures import ...`)."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext


def init_run_meta_for_test(ctx: RunContext, input_audio_path: str = "ASSETS/input/demo.wav") -> None:
    """Minimal run_meta when run_dir is outside the repo tree (pytest tmp_path)."""
    now = datetime.now(timezone.utc).isoformat()
    meta: dict[str, Any] = {
        "created_at": now,
        "updated_at": now,
        "execution_id": ctx.run_id,
        "input_audio_path": input_audio_path,
        "storage_root": str(ctx.run_dir),
    }
    ctx.write_json("run_meta.json", meta)


def isolated_run_ctx(tmp_path: Path, run_id: str) -> RunContext:
    """Run under tmp_path only — avoids collisions with data/run_* in the repo."""
    ctx = RunContext(run_id, create=True)
    ctx.run_dir = tmp_path / run_id
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done").mkdir(exist_ok=True)
    (ctx.run_dir / "vo_pickup").mkdir(exist_ok=True)
    return ctx


def ctx_from_fixture(tmp_path: Path, *, run_id: str = "exec_smoke_fixture") -> RunContext:
    """Copy tests/fixtures/runs/base_smoke into tmp_path for pipeline/gate smokes."""
    fixture = Path(__file__).parent / "fixtures" / "runs" / "base_smoke"
    run_dir = tmp_path / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(fixture, run_dir)
    ctx = RunContext(run_id, create=False)
    ctx.run_dir = run_dir
    return ctx


def patch_server_ctx(monkeypatch, ctx: RunContext) -> None:
    """Route FastAPI handlers to an isolated RunContext."""
    from fastapi import HTTPException

    from interview_mux.web import server

    def _ctx(run_id: str) -> RunContext:
        if run_id != ctx.run_id:
            raise HTTPException(404, f"Run not found: {run_id}")
        return ctx

    monkeypatch.setattr(server, "_ctx", _ctx)
