"""HR-1: hitch remap is not a ranking commit.

Unmark ranking lattice before Phase A. Restamp sanitize hashes when seated.
Adopt fail pins layup — hitch is not complete. Never unmark VO/EDL/mix.
Do not start a run. F1 restamp, B-05 late-forbid, HR-2 commit bus, HR-4 stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_sanitize.reentry import stamp_matches, stamp_sanitize_meta
from interview_mux.chapter_close_hitch import (
    HITCH_RANKING_LATTICE_STAGES,
    apply_hitch_ranking_lattice_after_remap,
    apply_post_walk_patches,
    hitch_layup_adopt_failed,
    hitch_unmark_ranking_lattice,
)
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.heal_routing import classify_heal_error
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    incompleteness_resume_stage,
    parse_resume_stage_from_reason,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from interview_mux.thrash_hardening import heal_navigate
from interview_mux.write_staging import write_mirrored_json
from run_fixtures import isolated_run_ctx, mark_done_raw, minimal_gap_line, minimal_gap_report

_MAP = {"seg_001": "seg_101"}


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hr1_hitch")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _mark_lattice_and_late(ctx: RunContext) -> None:
    for sid in HITCH_RANKING_LATTICE_STAGES:
        mark_done_raw(ctx, sid)
    for sid in ("vo_synthesize", "edl", "mix"):
        mark_done_raw(ctx, sid)


def test_hr1_unmark_ranking_lattice_not_vo_edl_mix(ctx: RunContext) -> None:
    _mark_lattice_and_late(ctx)
    cleared = hitch_unmark_ranking_lattice(ctx)
    assert set(cleared) == set(HITCH_RANKING_LATTICE_STAGES)
    for sid in HITCH_RANKING_LATTICE_STAGES:
        assert not ctx.is_done(sid)
    assert ctx.is_done("vo_synthesize")
    assert ctx.is_done("edl")
    assert ctx.is_done("mix")
    out = apply_hitch_ranking_lattice_after_remap(ctx, mapping=_MAP)
    assert out["mode"] == "unmark"


def test_hr1_phase_a_restamps_not_unmarks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.assembly_wav_present",
        lambda _ctx: True,
    )
    _mark_lattice_and_late(ctx)
    stale = stamp_sanitize_meta(
        {
            "ordered_segment_ids": ["seg_101"],
            "order_content_hash": "after-hitch",
            "excluded_segment_ids": [],
        },
        ok=True,
        source="fixture",
        content_keys=["ordered_segment_ids", "order_content_hash"],
    )
    stale["_meta"]["sanitize"]["hash"] = "stale-pre-remap"
    write_mirrored_json(ctx, "master/selection.json", stale)
    gap_stale = stamp_sanitize_meta(
        minimal_gap_report(
            minimal_gap_line(
                line_id="vo_a",
                targets_segment_id="seg_101",
            )
        ),
        ok=True,
        source="fixture",
        content_keys=["interviewer_lines", "gaps", "opening_orientation"],
    )
    gap_stale["_meta"]["sanitize"]["hash"] = "stale-gap"
    write_mirrored_json(ctx, "understanding/gap_report.json", gap_stale)
    _mark_lattice_and_late(ctx)

    out = apply_hitch_ranking_lattice_after_remap(ctx, mapping=_MAP)
    assert out["mode"] == "restamp"
    assert out["cleared"] == []
    for sid in HITCH_RANKING_LATTICE_STAGES:
        assert ctx.is_done(sid)
    assert ctx.is_done("vo_synthesize")
    assert ctx.is_done("edl")
    sel = ctx.read_json("master/selection.json")
    assert stamp_matches(
        sel, content_keys=["ordered_segment_ids", "order_content_hash"]
    )
    gap = ctx.read_json("understanding/gap_report.json")
    assert stamp_matches(
        gap, content_keys=["interviewer_lines", "gaps", "opening_orientation"]
    )


def test_hr1_empty_mapping_skips(ctx: RunContext) -> None:
    _mark_lattice_and_late(ctx)
    out = apply_hitch_ranking_lattice_after_remap(ctx, mapping={})
    assert out["mode"] == "skip"
    assert ctx.is_done("full_master_ranking")


def test_hr1_post_walk_adopt_fail_is_failed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.adopt_layup_plan_to_selection",
        lambda *a, **k: {"ok": False, "error": "boom"},
    )
    monkeypatch.setattr(
        "interview_mux.chapter_close_hitch.apply_chapter_authority",
        lambda *a, **k: {},
    )
    monkeypatch.setattr(
        "interview_mux.chapter_close_hitch.align_episode_structure_to_narrative",
        lambda *a, **k: {"ok": True},
    )
    patches = apply_post_walk_patches(
        ctx,
        intent={},
        mapping=_MAP,
        new_ids={"seg_101"},
    )
    assert hitch_layup_adopt_failed(patches.get("layup_adopt"))
    assert patches["layup_adopt"].get("ok") is False


def test_hr1_adopt_fail_pins_layup_not_hitch(ctx: RunContext) -> None:
    ctx.write_json(
        "mastering/chapter_close_hitch.json",
        {
            "version": 1,
            "status": "running",
            "layup_adopt": {"ok": False, "error": "boom"},
        },
        skip_handoff=True,
    )
    mark_done_raw(ctx, "chapter_close_hitch")
    reason = stage_artifact_incompleteness(ctx, "chapter_close_hitch")
    assert reason is not None
    assert "hitch_layup_adopt_failed" in reason
    assert parse_resume_stage_from_reason(reason) == "nugget_layup_compose"
    assert parse_resume_stage_from_reason(reason) != "chapter_close_hitch"
    assert parse_resume_stage_from_reason(reason) != "edl"
    assert producer_pin_for_token(reason, ctx=ctx) == "nugget_layup_compose"
    assert incompleteness_resume_stage(ctx, "chapter_close_hitch") == (
        "nugget_layup_compose"
    )
    assert seed_stage_complete(ctx, "chapter_close_hitch") is False
    nav = heal_navigate(ctx, error=reason, stage="chapter_close_hitch")
    assert nav["from_stage"] == "nugget_layup_compose"
    assert nav["from_stage"] != "edl"
    route = classify_heal_error(reason, ctx, stage="chapter_close_hitch")
    assert route is not None
    assert route.from_stage == "nugget_layup_compose"


def test_hr1_adopt_ok_does_not_fail() -> None:
    assert hitch_layup_adopt_failed({"ok": True, "skipped": True}) is False
    assert hitch_layup_adopt_failed({"ok": True, "no_plan": True}) is False
    assert hitch_layup_adopt_failed({"ok": False, "error": "boom"}) is True
