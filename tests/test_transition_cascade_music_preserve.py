"""Transition cascade must not wipe music via 5A adjudicate unmark."""

from __future__ import annotations

from pathlib import Path

from interview_mux.stage_order_migration import migrate_stale_stage_order_on_resume
from interview_mux.transition_vo import maybe_propagate_transitions_spoken_text_change
from interview_mux.vo_synthesis_audit import (
    _TRANSITION_SPOKEN_TEXT_CASCADE_STAGES,
    unmark_transition_spoken_text_cascade_stages,
)
from run_fixtures import isolated_run_ctx


def test_transition_cascade_stages_exclude_adjudicate():
    assert "vo_line_adjudicate" not in _TRANSITION_SPOKEN_TEXT_CASCADE_STAGES
    assert "vo_synthesize" in _TRANSITION_SPOKEN_TEXT_CASCADE_STAGES
    assert "mmaudio_sfx" not in _TRANSITION_SPOKEN_TEXT_CASCADE_STAGES


def test_unmark_transition_leaves_adjudicate_and_music(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "tr_cascade")
    for stage in (
        "vo_line_adjudicate",
        "vo_synthesize",
        "edl",
        "assembly_preview",
        "mmaudio_sfx",
        "mix",
    ):
        ctx.mark_done(stage, force=True)
    unmarked = unmark_transition_spoken_text_cascade_stages(ctx)
    assert "vo_line_adjudicate" not in unmarked
    assert "mmaudio_sfx" not in unmarked
    assert ctx.is_done("vo_line_adjudicate")
    assert ctx.is_done("mmaudio_sfx")
    assert not ctx.is_done("vo_synthesize")
    assert not ctx.is_done("mix")


def test_transition_text_change_does_not_unmark_adjudicate(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "tr_text")
    ctx.mark_done("vo_line_adjudicate", force=True)
    ctx.mark_done("vo_synthesize", force=True)
    ctx.mark_done("mmaudio_sfx", force=True)
    prior = {
        "transitions": [
            {
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "text": "Old bridge.",
            }
        ]
    }
    new = {
        "transitions": [
            {
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "text": "New bridge.",
            }
        ]
    }
    result = maybe_propagate_transitions_spoken_text_change(
        ctx, prior_doc=prior, new_doc=new, stage="test"
    )
    assert "vo_line_adjudicate" not in (result.get("unmarked") or [])
    assert ctx.is_done("vo_line_adjudicate")
    assert ctx.is_done("mmaudio_sfx")


def test_migrate_heals_marker_when_outputs_present(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "heal_5a")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    # Downstream music done without adjudicate marker, but adjudicate outputs exist.
    ctx.mark_done("mmaudio_sfx", force=True)
    ctx.write_json(
        "understanding/vo_line_adjudication.json",
        {"lines": [], "status": "complete"},
        skip_handoff=True,
    )

    def fake_ok(_ctx, stage: str) -> bool:
        return stage == "vo_line_adjudicate"

    monkeypatch.setattr(
        "interview_mux.stage_order_migration._stage_output_ok", fake_ok
    )
    monkeypatch.setattr(
        "interview_mux.stage_order_migration.detect_stale_new_stage_order",
        lambda _ctx: "vo_line_adjudicate",
    )
    result = migrate_stale_stage_order_on_resume(ctx)
    assert result.get("healed_marker") is True
    assert result.get("cleared") == []
    assert ctx.is_done("vo_line_adjudicate")
    assert ctx.is_done("mmaudio_sfx")
