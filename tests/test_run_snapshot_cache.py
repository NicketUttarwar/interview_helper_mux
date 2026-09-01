"""Per-run stage/journey snapshot cache invalidation."""

from __future__ import annotations

from interview_mux.run_context import RunContext
from interview_mux.web.run_snapshot_cache import (
    clear_run_snapshot_cache,
    get_or_build_run_snapshot,
    invalidate_run_snapshot,
)
from run_fixtures import init_run_meta_for_test, patch_executions_root


def test_snapshot_cache_invalidates_on_mark_done(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_cache", create=True)
    init_run_meta_for_test(ctx)
    clear_run_snapshot_cache()

    calls = {"stages": 0}

    def build_stages() -> list[dict]:
        calls["stages"] += 1
        return [{"id": "ingest", "status": "pending"}]

    def build_journey(stages: list[dict]) -> dict:
        return {"phase": "prepare", "stages": stages}

    job: dict = {"status": "idle"}
    get_or_build_run_snapshot(ctx, job=job, build_stages=build_stages, build_journey=build_journey)
    get_or_build_run_snapshot(ctx, job=job, build_stages=build_stages, build_journey=build_journey)
    assert calls["stages"] == 1

    ctx.mark_done("ingest")
    get_or_build_run_snapshot(ctx, job=job, build_stages=build_stages, build_journey=build_journey)
    assert calls["stages"] == 2

    invalidate_run_snapshot(ctx.run_id)
    get_or_build_run_snapshot(ctx, job=job, build_stages=build_stages, build_journey=build_journey)
    assert calls["stages"] == 3
