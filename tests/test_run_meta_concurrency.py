from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    (root / "ASSETS" / "executions").mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
        },
    )
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_mutate_run_meta_preserves_unrelated_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.mutate_run_meta(lambda m: m.update({"stage_reuse": {"ingest": {"action": "accept"}}}))
    ctx.mutate_run_meta(
        lambda m: m.setdefault("pending_write_approval", {}).update(
            {"ingest": {"paths": ["ingest/checksums.json"]}}
        )
    )
    meta = ctx.read_json("run_meta.json")
    assert meta["stage_reuse"]["ingest"]["action"] == "accept"
    assert "ingest" in meta["pending_write_approval"]
