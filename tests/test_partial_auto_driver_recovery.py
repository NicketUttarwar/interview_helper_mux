"""Driver handle_gate recovery paths — partial-auto VO ladders."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.remediation_framework import run_classified_ladder
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("driver_recovery_test", create=True)


def test_classified_ladder_vo_coverage_message(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_019",
                    "delivery": "synthesize",
                    "required": True,
                    "gap_type": "layup",
                    "text": "Line.",
                    "placement": "before",
                    "targets_segment_id": "seg_019",
                }
            ]
        },
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_019"],
                    "omitted_line_ids": [],
                    "orientation_id": None,
                }
            }
        },
    )
    outcome = run_classified_ladder(
        ctx,
        consumer_stage="edl_narrative_audit",
        exc=RuntimeError("VO coverage not rendered: vo_layup_seg_019"),
        error_class="vo_seated_coverage",
    )
    assert outcome.playbook_id == "edl_vo_coverage_ladder"
    assert outcome.error_class == "vo_seated_coverage"
