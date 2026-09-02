"""Remediation framework — classified ladder dispatch and honest outcomes."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.operator_gates import is_automated_classified
from interview_mux.remediation_framework import (
    policy_remediation_active,
    run_classified_ladder,
    run_delivery_recover_preflight,
)
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("remediation_framework", create=True)


def test_automated_classified_vo_contract_not_operator_gate() -> None:
    from interview_mux.operator_gates import should_stamp_needs_operator

    meta = {"partial_auto": True, "homunculus_version": "0.1.0"}
    reason = "VO contract: seated line vo_preface_episode_orientation missing from gap_report"
    assert is_automated_classified("nugget_layup_compose", reason)
    assert not should_stamp_needs_operator("nugget_layup_compose", reason, meta=meta)


def test_vo_seated_coverage_ladder(ctx: RunContext) -> None:
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_019"],
                    "omitted_line_ids": [],
                    "orientation_id": "vo_layup_seg_019",
                }
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_019",
                    "delivery": "synthesize",
                    "required": True,
                    "skipped_optional": True,
                    "gap_type": "layup",
                    "text": "Before we dive in.",
                    "placement": "before",
                    "targets_segment_id": "seg_019",
                }
            ]
        },
    )
    outcome = run_classified_ladder(
        ctx,
        consumer_stage="edl_narrative_audit",
        exc=RuntimeError("VO coverage not rendered: ['vo_layup_seg_019']"),
        error_class="vo_seated_coverage",
    )
    assert outcome.playbook_id == "edl_vo_coverage_ladder"
    assert outcome.resume_stage in {"vo_synthesize", "edl", "edl_narrative_audit"}


def test_delivery_recover_preflight_vo_contract(ctx: RunContext) -> None:
    from interview_mux.opening_orientation import ORIENTATION_LINE_ID

    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": [ORIENTATION_LINE_ID],
                    "omitted_line_ids": [],
                    "orientation_id": ORIENTATION_LINE_ID,
                }
            }
        },
    )
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []})
    outcome = run_delivery_recover_preflight(
        ctx,
        consumer_stage="nugget_layup_compose",
        message="seated line vo_preface_episode_orientation missing from gap_report",
    )
    assert outcome.error_class == "vo_contract_repair"
    assert not policy_remediation_active(ctx) or outcome.detail
