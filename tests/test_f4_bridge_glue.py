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
    with pytest.raises(LoudStageFailure, match="Reorder seam missing"):
        mint_missing_transitions(ctx, MISSING, transitions={"transitions": []})


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
