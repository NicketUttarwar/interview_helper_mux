"""i11f: pre_mix must not treat commitment diverge as incomplete_cut.

exec_13167: mix remaster refused with
``publishability blocked at pre_mix: incomplete_cut_unresolved —
assembly_not_rendered_from_current_edl`` — chicken/egg (mix is the remaster).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error
from interview_mux.publishability_boundary import validate_publishability
from interview_mux.run_context import RunContext
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging
from run_fixtures import isolated_run_ctx


def _plant(ctx: RunContext) -> None:
    master = ctx.run_dir / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "edl.json").write_text(
        json.dumps(
            {
                "version": 1,
                "ordered_segment_ids": ["seg_001"],
                "timeline_duration_ms": 1000,
                "clips": [
                    {
                        "type": "speech",
                        "segment_id": "seg_001",
                        "source_start_ms": 0,
                        "source_end_ms": 1000,
                        "duration_ms": 1000,
                        "timeline_start_ms": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (master / "selection.json").write_text(
        json.dumps({"ordered_segment_ids": ["seg_001"], "excluded_segment_ids": []}),
        encoding="utf-8",
    )
    (master / "seam_autopsy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "blocking_reasons": ["assembly_not_rendered_from_current_edl"],
                "commitment": {
                    "status": "diverged",
                    "reasons": ["assembly_not_rendered_from_current_edl"],
                },
                "seams": [],
            }
        ),
        encoding="utf-8",
    )
    (master / "junction_snip_qa.json").write_text(
        json.dumps(
            {
                "version": 1,
                "critical_residuals": 0,
                "blocking_reasons": [],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i11f_premix_diverge")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.has_critical_residuals",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    _plant(run)
    return run


def test_i11_premix_ignores_assembly_not_rendered_seam_reason(ctx: RunContext) -> None:
    enter_stage_staging("mix")
    try:
        report = validate_publishability(ctx, checkpoint="pre_mix")
    finally:
        exit_stage_staging()
    assert not any(
        v.error_class == "incomplete_cut_unresolved" for v in report.violations
    ), [f"{v.error_class}:{v.detail}" for v in report.violations]
    assert not any(v.code == "seam_autopsy_blocking" for v in report.violations)


def test_i11_heal_routes_mislabeled_incomplete_cut_to_mix(ctx: RunContext) -> None:
    err = (
        "publishability blocked at pre_mix: incomplete_cut_unresolved — "
        "assembly_not_rendered_from_current_edl"
    )
    route = classify_heal_error(err, ctx, stage="mix")
    assert route is not None
    assert route.from_stage == "mix"
    assert route.from_stage != "junction_snip_qa"
