"""F-2: identical-halt resume prefers live classify over PLAYBOOK_REGISTRY."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_routing import PLAYBOOK_REGISTRY
from interview_mux.recovery_controller import live_identical_halt_resume_stage
from interview_mux.stage_completion import high_gap_heal_resume_stage
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "f2_live_resume")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "partial_auto": True},
        skip_handoff=True,
    )
    return run


def test_live_resume_high_gap_prefers_helper_over_registry(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registry cold default is gap_framing_compose; live helper may pin layup."""
    cold = PLAYBOOK_REGISTRY["high_gap_unframed"].resume_stage
    assert cold == "gap_framing_compose"

    monkeypatch.setattr(
        "interview_mux.stage_completion.high_gap_heal_resume_stage",
        lambda _ctx: "nugget_layup_compose",
    )
    resume = live_identical_halt_resume_stage(ctx, "high_gap_unframed", "edl")
    assert resume == "nugget_layup_compose"
    assert resume != cold


def test_live_resume_falls_back_to_registry_when_no_helper(ctx) -> None:
    resume = live_identical_halt_resume_stage(ctx, "musicgen_theme_failed", "mix")
    spec = PLAYBOOK_REGISTRY.get("musicgen_theme_failed")
    if spec and spec.resume_stage:
        assert resume == spec.resume_stage
    else:
        assert resume == "mix"


def test_live_resume_matches_high_gap_helper_when_layup_plan(ctx) -> None:
    from interview_mux.nugget_layup import PLAN_REL

    # Bypass sanitize admit — only need artifact_exists for live pin.
    dest = ctx.final_path(*PLAN_REL.split("/", 1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        '{"version":1,"ordered_segment_ids":["seg_a"],"lines":[]}\n',
        encoding="utf-8",
    )
    live = high_gap_heal_resume_stage(ctx)
    halt = live_identical_halt_resume_stage(ctx, "high_gap_unframed", "edl")
    assert halt == live
    assert halt == "nugget_layup_compose"
