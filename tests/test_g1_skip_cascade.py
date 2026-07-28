"""G1 skip-optional must not set meta on empty skip; repair cascade guarded."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_repairs import repair_gap_report
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root, patch_merged_config


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    patch_merged_config(monkeypatch, {"v2": {"g1_optional": True}})
    return RunContext("exec_g1_skip", create=True)


def test_repair_gap_report_no_cascade_from_empty_skip_meta(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("interview_mux.v2.config.v2_g1_optional", lambda: True)
    ctx.write_json("run_meta.json", {"g1_vo_skipped_optional": True})  # stale empty-skip meta
    doc = {
        "version": 1,
        "interviewer_lines": [
            {
                "line_id": "line_001",
                "delivery": "synthesize",
                "targets_segment_id": "seg_001",
                "text": "Hello?",
                "placement": "before",
            }
        ],
    }
    repaired, applied = repair_gap_report(ctx, doc)
    assert not any(a.get("action") == "mark_skipped_optional" for a in applied)
    assert not repaired["interviewer_lines"][0].get("skipped_optional")


def test_repair_gap_report_cascades_when_line_ids_recorded(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("interview_mux.v2.config.v2_g1_optional", lambda: True)
    ctx.write_json(
        "run_meta.json",
        {
            "g1_vo_skipped_optional": True,
            "g1_skip_applied_line_ids": ["line_001"],
        },
    )
    doc = {
        "version": 1,
        "interviewer_lines": [
            {
                "line_id": "line_001",
                "delivery": "synthesize",
                "targets_segment_id": "seg_001",
                "text": "Hello?",
                "placement": "before",
                "skipped_optional": True,
            },
            {
                "line_id": "line_002",
                "delivery": "synthesize",
                "targets_segment_id": "seg_002",
                "text": "More?",
                "placement": "before",
            },
        ],
    }
    repaired, applied = repair_gap_report(ctx, doc)
    assert any(a.get("action") == "mark_skipped_optional" for a in applied)
    assert repaired["interviewer_lines"][1].get("skipped_optional") is True
