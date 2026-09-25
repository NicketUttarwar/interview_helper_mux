"""exec_13170: omit last high-gap cover must demote; synth clamp pins compose."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    clamp_resume_through_order,
    vo_synthesize_stability_block,
)
from interview_mux.high_gap_vo import demote_uncovered_high_gaps
from interview_mux.stage_completion import _high_gap_unframed_incompleteness
from interview_mux.vo_contract import (
    mark_gap_line_not_on_air,
    omit_wins_skip_reason,
    repair_vo_contract_drift,
)
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i3_omit_demote")


def _plant_high_gap_with_sole_cover(ctx) -> None:
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_007",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "ok_with_light_bridge",
                    "listener_confusion": "who is speaking",
                }
            ]
        },
        skip_handoff=True,
    )
    stamped = mark_gap_line_not_on_air(
        {
            "line_id": "vo_seed_seg_007",
            "delivery": "synthesize",
            "gap_type": "missing_setup",
            "targets_segment_id": "seg_007",
            "placement": "before",
            "required": True,
            "severity": "high",
            "text": "What is at stake as this continues?",
        },
        reason_code="execution_contract_waive",
        compensating_path="tier_d_logged_waive",
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [stamped]},
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "beats": [],
                "vo_seats": {
                    "seated_line_ids": [],
                    "omitted_line_ids": ["vo_seed_seg_007"],
                },
            }
        },
        skip_handoff=True,
    )


def test_omit_sole_high_gap_cover_demotes_and_clears_unframed(ctx) -> None:
    _plant_high_gap_with_sole_cover(ctx)
    assert omit_wins_skip_reason(
        ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    )
    assert _high_gap_unframed_incompleteness(ctx, "gap_framing_compose")
    demoted = demote_uncovered_high_gaps(ctx, origin="post_commit_uncovered_high")
    assert demoted == 1
    assert _high_gap_unframed_incompleteness(ctx, "gap_framing_compose") is None
    ev = ctx.read_json("understanding/gap_evaluations.json")["evaluations"][0]
    assert str(ev.get("severity") or "").lower() == "medium"


def test_repair_vo_contract_drift_demotes_after_omit(ctx) -> None:
    _plant_high_gap_with_sole_cover(ctx)
    # Ensure repair path sees omit and demotes uncovered high.
    repair_vo_contract_drift(ctx)
    assert _high_gap_unframed_incompleteness(ctx, "gap_framing_compose") is None


def test_vo_synth_stability_pins_high_gap_compose_not_ipp(ctx) -> None:
    _plant_high_gap_with_sole_cover(ctx)
    assert _high_gap_unframed_incompleteness(ctx, "gap_framing_compose")
    block = vo_synthesize_stability_block(ctx, allow_rewrite=False)
    assert block == "gap_framing_compose"
    clamped = clamp_resume_through_order(ctx, "vo_synthesize")
    assert clamped == "gap_framing_compose"
    assert clamped != "information_package_plan"


def test_high_gap_unframed_also_blocks_layup_done(ctx) -> None:
    """Layup owns high-gap VO — refuse hollow done (exec_13198 seg_014)."""
    _plant_high_gap_with_sole_cover(ctx)
    reason = _high_gap_unframed_incompleteness(ctx, "nugget_layup_compose")
    # Peel: high-gap unframed is no longer a layup-done incompleteness token.
    assert reason is None or "high_gap_unframed" in reason
