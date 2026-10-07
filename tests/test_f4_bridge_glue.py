"""F4 bridge / EDL glue: fail closed on empty hinge; hitch omit; VO-first WAV heal.

Fixture shape from exec_11165 ``seg_022→seg_026`` (snake_case chapter_close_hitch
tags, empty speakable glue). Does not resume that run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error
from interview_mux.loud_fail import LoudStageFailure
from interview_mux.nugget_layup import PLAN_REL
from interview_mux.recovery_controller import classify_error_class
from interview_mux.seam_glue import mint_missing_transitions
from run_fixtures import isolated_run_ctx

_FIX = Path(__file__).resolve().parent / "fixtures" / "f4_bridge_glue"
AFTER = "seg_022"
BEFORE = "seg_026"
MISSING = [
    {
        "after_segment_id": AFTER,
        "before_segment_id": BEFORE,
        "kind": "reorder",
        "source_gap_ms": 58_000,
    }
]


def _plant_ungrounded_pair(ctx) -> None:
    segs = json.loads((_FIX / "segments.json").read_text(encoding="utf-8"))
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [segs[AFTER], segs[BEFORE]]},
        skip_handoff=True,
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": [AFTER, BEFORE],
            "layups": [
                {
                    "target_segment_id": BEFORE,
                    "text": "Grounded layup copy for the destination native.",
                    "word_count": 8,
                    "skip": False,
                }
            ],
        },
        skip_handoff=True,
    )


def test_empty_ungrounded_seam_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("interview_mux.nugget_layup.nugget_layup_enabled", lambda: True)
    ctx = isolated_run_ctx(tmp_path, "f4_fail_closed")
    _plant_ungrounded_pair(ctx)
    # An unbridgeable seam plays unglued instead of stopping edl (ISSUES 185).
    out = mint_missing_transitions(ctx, MISSING, transitions={"transitions": []})
    assert not [t for t in (out.get("transitions") or []) if t.get("auto_minted")]


def test_hitch_cover_omits_spoken_transition_when_ungrounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("interview_mux.nugget_layup.nugget_layup_enabled", lambda: True)
    ctx = isolated_run_ctx(tmp_path, "f4_hitch_omit")
    _plant_ungrounded_pair(ctx)
    hitch = json.loads((_FIX / "hitch_edl.json").read_text(encoding="utf-8"))
    ctx.write_json("master/edl.json", hitch, skip_handoff=True)
    doc = mint_missing_transitions(ctx, MISSING, transitions={"transitions": []})
    rows = [r for r in (doc.get("transitions") or []) if isinstance(r, dict)]
    assert not any(
        str(r.get("after_segment_id")) == AFTER
        and str(r.get("before_segment_id")) == BEFORE
        for r in rows
    )


def test_missing_bridge_wav_heals_to_vo_synthesize_not_edl(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "f4_wav_heal")
    route = classify_heal_error(
        "edl: gap VO lines missing WAV: ['vo_layup_seg_012']",
        ctx,
        stage="edl",
    )
    assert route is not None
    assert route.from_stage == "vo_synthesize"
    assert route.from_stage != "edl"
    assert "mix" not in route.from_stage
    tr_route = classify_heal_error(
        "mix: current transition pairs missing WAV: seg_022->seg_026",
        ctx,
        stage="mix",
    )
    assert tr_route is not None
    assert tr_route.from_stage == "vo_synthesize"
    assert (
        classify_error_class(
            "edl", RuntimeError("edl: gap VO lines missing WAV: ['vo_layup_seg_012']")
        )
        == "vo_seated_coverage"
    )
    assert (
        classify_error_class(
            "mix",
            RuntimeError("mix: current transition pairs missing WAV: seg_022->seg_026"),
        )
        == "vo_seated_coverage"
    )


def test_bridge_mint_persists_under_hard_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MUX_FORENSICS=0: waived layup VO must not leave reorder seams unmintable.

    Hard freeze after vo_synthesize blocked mint persist (reason=edl). End-A
    bridge_completeness_mint lands pair-specific hinge text (often deferred
    beyond pair freeze) so bridge_completeness can clear.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    monkeypatch.setattr("interview_mux.nugget_layup.nugget_layup_enabled", lambda: True)
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_cfg",
        lambda: {
            "suppress_placeholder_seams_when_layup": True,
            "ban_canned_air": True,
            "authoritative_gap_report": True,
        },
    )

    from interview_mux.bridge_completeness import (
        assert_bridges_complete,
        missing_reorder_bridges,
    )
    from interview_mux.seat_authority import (
        hard_freeze_action_permitted,
        stamp_hard_seat_freeze,
        stamp_soft_seat_freeze,
    )

    assert hard_freeze_action_permitted("bridge_completeness_mint")

    ctx = isolated_run_ctx(tmp_path, "f4_bridge_freeze_mint")
    after, before = "seg_003k", "seg_005"
    segs = json.loads((_FIX / "segments.json").read_text(encoding="utf-8"))
    # Reuse fixture segment bodies under the campaign pair ids.
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {**segs[AFTER], "segment_id": after, "text": "to the show"},
                {
                    **segs[BEFORE],
                    "segment_id": before,
                    "text": "Historically, what happens is somehow you find something, then the",
                },
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": [after, before]},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/reorder_bridges.json",
        {
            "version": 1,
            "pairs": [
                {
                    "after_id": after,
                    "before_id": before,
                    "after_segment_id": after,
                    "before_segment_id": before,
                    "kind": "reorder",
                    "source_gap_ms": 63900,
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/transitions.json",
        {"transitions": []},
        skip_handoff=True,
    )
    # Pair freeze locked without this seam — mint lands as deferred durable text.
    ctx.write_json(
        "master/transitions_pair_freeze.json",
        {"version": 1, "pairs": [], "count": 0},
        skip_handoff=True,
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": [after, before],
            "layups": [
                {
                    "target_segment_id": before,
                    "text": "Hosted layup copy waived before synth.",
                    "word_count": 6,
                    "skip": False,
                    "line_id": "vo_layup_seg_005",
                }
            ],
        },
        skip_handoff=True,
    )
    gap = {
        "nugget_layup_authority": True,
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_005",
                "targets_segment_id": before,
                "prior_segment_id": after,
                "placement": "before",
                "delivery": "synthesize",
                "text": "Hosted layup copy waived before synth.",
                "skipped_optional": True,
                "air_script_omit": True,
                "skip_reason_code": "execution_contract_waive",
            }
        ],
    }
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)

    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")

    bridges = ctx.read_json("understanding/reorder_bridges.json")
    miss = missing_reorder_bridges(
        bridges,
        gap_report=gap,
        transitions={"transitions": []},
    )
    assert miss and miss[0]["after_segment_id"] == after

    doc = mint_missing_transitions(
        ctx,
        miss,
        transitions={"transitions": []},
        gap_report=gap,
    )
    # Persist must land under freeze (active or deferred durable).
    disk = ctx.read_json("master/transitions.json")
    assert isinstance(disk, dict)
    assert_bridges_complete(
        bridges,
        gap_report=gap,
        transitions=disk,
    )
    assert not missing_reorder_bridges(
        bridges, gap_report=gap, transitions=disk
    )
    # In-memory return also complete.
    assert_bridges_complete(bridges, gap_report=gap, transitions=doc)
