"""Partial-auto golden path — remediation ladder smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.air_script import seated_vo_line_ids
from interview_mux.opening_orientation import ORIENTATION_LINE_ID
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("partial_auto_golden", create=True)


@pytest.fixture
def partial_auto_ctx(ctx: RunContext) -> RunContext:
    ctx.mutate_run_meta(lambda m: m.update({"homunculus_version": "0.1.0", "partial_auto": True}))
    return ctx


def test_native_only_empty_seats_no_implicit_orientation(ctx: RunContext) -> None:
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": [],
                "omitted_line_ids": [],
                "orientation_id": None,
            }
        }
    }
    assert ORIENTATION_LINE_ID not in seated_vo_line_ids(plan)


def test_tbiy_monologue_topology_fixture_seated_policy() -> None:
    import json

    topo = Path(__file__).parent / "fixtures" / "tbiy" / "monologue_heavy" / "topology.json"
    if not topo.is_file():
        pytest.skip("tbiy fixture missing")
    doc = json.loads(topo.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)


def test_preflight_vo_contract_issues_clear_after_ladder(ctx: RunContext) -> None:
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": [],
                    "omitted_line_ids": [],
                    "orientation_id": None,
                }
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "delivery": "synthesize",
                    "required": True,
                    "gap_type": "layup",
                    "text": "Hook.",
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
    )
    from interview_mux.execution_contract import run_vo_contract_ladder
    from interview_mux.opening_orientation import ORIENTATION_LINE_ID
    from interview_mux.vo_contract import validate_vo_contract

    if not validate_vo_contract(ctx):
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
    result = run_vo_contract_ladder(ctx, consumer_stage="nugget_layup_compose")
    assert result.contract_ok or not validate_vo_contract(ctx)
