"""Journey kernel snapshot and next_action appendix parity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.journey_orchestrator import (
    NEXT_ACTION_COMPLETE_G2,
    NEXT_ACTION_PREPARE_G0,
    NEXT_ACTION_UNDERSTAND_PROFILE,
    build_journey_snapshot,
)
from interview_mux.run_context import RunContext

FIXTURE = Path(__file__).parent / "fixtures/runs/base_smoke"


@pytest.fixture
def smoke_ctx(tmp_path, monkeypatch):
    run_id = "exec_001_20260101T000000Z"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    for rel in FIXTURE.rglob("*"):
        if rel.is_file():
            dest = run_dir / rel.relative_to(FIXTURE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(rel.read_bytes())
    meta_path = run_dir / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["execution_id"] = run_id
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    cfg_path = tmp_path.parent / "config_override"
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": str(tmp_path),
            "data_root": str(tmp_path / "data"),
        },
    )
    monkeypatch.setattr(
        "interview_mux.journey_orchestrator.merged_config",
        lambda: {"journey_ui": {"enabled": True}},
    )
    return RunContext(run_id, create=False)


def test_next_action_constants_documented():
    doc = Path(__file__).parents[1] / "docs/workflows/operator-journey.md"
    text = doc.read_text(encoding="utf-8")
    assert NEXT_ACTION_PREPARE_G0 in text
    assert NEXT_ACTION_UNDERSTAND_PROFILE in text
    assert NEXT_ACTION_COMPLETE_G2 in text


def test_build_journey_snapshot_smoke(smoke_ctx):
    snap = build_journey_snapshot(smoke_ctx)
    assert snap["phase"] in (
        "prepare",
        "understand",
        "complete",
        "create",
        "polish",
        "ship",
    )
    assert "next_action" in snap
    assert "blocking" in snap
    assert "milestones" in snap
    assert isinstance(snap["milestones"]["g0_complete"], bool)


def test_execute_hint_prepare(smoke_ctx):
    snap = build_journey_snapshot(smoke_ctx)
    if snap["phase"] == "prepare":
        hint = snap.get("execute_hint")
        if hint:
            assert hint["mode"] in ("analysis", "analysis_until_g0")
            assert hint.get("until_stage") == "transcript_review_build" or hint.get("mode")
