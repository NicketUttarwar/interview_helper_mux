"""End-C: glue before EDL — deferred durable only; heal pins writers (MUX_FORENSICS=0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.bridge_completeness import (
    assert_bridges_complete,
    bridge_heal_may_soft_complete,
    deferred_pair_is_durable,
    missing_reorder_bridges,
)
from interview_mux.heal_routing import classify_heal_error
from interview_mux.nugget_layup import PLAN_REL
from interview_mux.stage_completion import PRODUCER_PIN_TABLE, high_gap_heal_resume_stage
from run_fixtures import isolated_run_ctx

AFTER = "seg_049"
BEFORE = "seg_056"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.e2e_soft.e2e_quality_waivers_enabled",
        lambda meta=None: False,
    )
    return isolated_run_ctx(tmp_path, "endc_glue")


def test_endc_deferred_text_only_not_complete() -> None:
    bridges = {"pairs": [{"after_id": AFTER, "before_id": BEFORE, "kind": "reorder"}]}
    deferred = {
        "transitions": [],
        "deferred_transition_pairs": [
            {
                "after_segment_id": AFTER,
                "before_segment_id": BEFORE,
                "text": "Moving from A to B, what changed?",
                "auto_minted": True,
            }
        ],
    }
    assert not deferred_pair_is_durable(deferred["deferred_transition_pairs"][0])
    assert len(missing_reorder_bridges(bridges, transitions=deferred)) == 1
    with pytest.raises(SystemExit, match="bridge_completeness"):
        assert_bridges_complete(bridges, transitions=deferred, soft=False)


def test_endc_beyond_freeze_deferred_is_durable() -> None:
    bridges = {"pairs": [{"after_id": AFTER, "before_id": BEFORE, "kind": "reorder"}]}
    deferred = {
        "transitions": [],
        "deferred_transition_pairs": [
            {
                "after_segment_id": AFTER,
                "before_segment_id": BEFORE,
                "text": "Moving from A to B, what changed?",
                "beyond_pair_freeze": True,
                "deferred_reason": "beyond_pair_freeze",
            }
        ],
    }
    assert deferred_pair_is_durable(deferred["deferred_transition_pairs"][0])
    assert missing_reorder_bridges(bridges, transitions=deferred) == []
    doc = assert_bridges_complete(bridges, transitions=deferred, soft=False)
    assert doc["complete"] is True


def test_endc_vo_before_target_still_covers_seam() -> None:
    """Destination-only placement=before VO remains valid one-host-turn glue."""
    bridges = {"pairs": [{"after_id": AFTER, "before_id": BEFORE, "kind": "reorder"}]}
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_before",
                "placement": "before",
                "targets_segment_id": BEFORE,
                "text": "Before we land there — what set this up?",
                "delivery": "synthesize",
            }
        ]
    }
    assert missing_reorder_bridges(bridges, gap_report=gap, transitions=None) == []


def test_endc_soft_complete_refused_without_waiver() -> None:
    assert bridge_heal_may_soft_complete(waivers_enabled=False) is False
    assert bridge_heal_may_soft_complete(waivers_enabled=True) is True


def test_endc_bridge_incomplete_pins_transitions_not_edl(ctx) -> None:
    route = classify_heal_error(
        "HARD: bridge incomplete: bridge_completeness: 1 reorder join(s) lack glue",
        ctx,
        stage="edl",
    )
    assert route is not None
    assert route.from_stage == "transitions"
    assert route.from_stage != "edl"
    assert PRODUCER_PIN_TABLE["bridge_incomplete"] == "transitions"


def test_endc_framing_quality_pins_compose_or_layup_never_edl(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        PLAN_REL,
        {"ordered_segment_ids": [AFTER, BEFORE], "layups": []},
        skip_handoff=True,
    )
    route = classify_heal_error(
        'master/edl.json: impact segment "seg_056" lacks preceding framing VO '
        "(vo_frame_1). Re-run nugget_layup_compose (never soft-pass EDL).",
        ctx,
        stage="edl_narrative_audit",
    )
    assert route is not None
    # S5: empty plan → framing owns; claimed-air miss would pin layup. Never EDL.
    assert route.from_stage in {"nugget_layup_compose", "gap_framing_compose"}
    assert route.from_stage != "edl"
    assert high_gap_heal_resume_stage(ctx) == "gap_framing_compose"

    # Without layup plan → gap_framing_compose
    plan_path = ctx.final_path(*PLAN_REL.split("/"))
    plan_path.unlink(missing_ok=True)
    route2 = classify_heal_error(
        "missing_forward_cue on impact block — rewrite framing",
        ctx,
        stage="edl",
    )
    assert route2 is not None
    assert route2.from_stage == "gap_framing_compose"
    assert route2.from_stage != "edl"
