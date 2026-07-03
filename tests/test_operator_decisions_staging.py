"""Operator decision queue must stay consistent during write-approval staging."""

from __future__ import annotations

import json

import pytest

from interview_mux.operator_decisions import (
    OperatorDecision,
    mark_decision_resolved,
    pending_decision_count,
    set_stage_decisions,
    stage_decisions_summary,
)
from interview_mux.write_staging import record_pending_approval, staging_root
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def test_mark_decision_resolved_updates_staged_and_committed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "dec_staging")
    stage_key = "segment_classification"

    staged_manifest = staging_root(ctx, stage_key) / "segments" / "manifest.json"
    staged_manifest.parent.mkdir(parents=True, exist_ok=True)
    staged_manifest.write_text(
        json.dumps(minimal_manifest(minimal_manifest_segment("seg_001")))
    )
    record_pending_approval(ctx, stage_key)

    set_stage_decisions(
        ctx,
        stage_key,
        [
            OperatorDecision(
                id="dec_resolve_me",
                kind="propagation",
                headline="Test propagation",
                detail="detail",
                options=[],
            )
        ],
    )

    staged_decisions = staging_root(ctx, stage_key) / "understanding" / "operator_decisions.json"
    assert staged_decisions.is_file()
    assert pending_decision_count(ctx, stage_key) == 1

    mark_decision_resolved(ctx, stage_key, "dec_resolve_me")

    assert pending_decision_count(ctx, stage_key) == 0
    summary = stage_decisions_summary(ctx, stage_key)
    assert summary["ready_for_review"] is True

    staged_doc = json.loads(staged_decisions.read_text())
    committed_doc = json.loads((ctx.run_dir / "understanding" / "operator_decisions.json").read_text())
    assert staged_doc["by_stage"][stage_key]["decisions"] == []
    assert committed_doc["by_stage"][stage_key]["decisions"] == []
