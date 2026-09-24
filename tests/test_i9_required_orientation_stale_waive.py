"""i9: required opening orientation must not stay omitted via stale tier-D waive.

exec_13177: CTA-hole orientation scrap carried compensating_path=tier_d_logged_waive
while opening_orientation.required — build_vo_seats kept it in omitted_line_ids and
post_edl failed opening_orientation_count=0 even after skip flags were cleared.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.air_script import (
    build_vo_seats,
    filter_gap_lines_for_air_script,
)
from interview_mux.omit_ledger import revive_required_opening_orientation
from interview_mux.opening_orientation import validate_opening_orientation
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report

_LINE = "vo_preface_cta_open_seg_002"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i9_orient_waive")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    run.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_002", "seg_037"], "version": 1},
        skip_handoff=True,
    )
    return run


def _gap(*, required: bool = True, waived: bool = True) -> dict:
    line = minimal_gap_line(
        line_id=_LINE,
        text=(
            "Host Mohan Uttarwar opens on precision oncology — what listeners "
            "stand to gain from this cancer-science conversation."
        ),
        delivery="synthesize",
        required=True,
        episode_orientation=True,
        line_category="episode_preface",
        gap_type="media_ip_cta_hole",
        placement="before",
        targets_segment_id="seg_002",
        opening_sequence="intro_music_body",
        orientation_missions=[
            "guest_identity",
            "conversation_topic",
            "listener_stakes",
        ],
        clone_adjacency_exempt=True,
        allow_music_bed_overlap=True,
    )
    if waived:
        line["skipped_optional"] = True
        line["air_script_omit"] = True
        line["skip_reason_code"] = "execution_contract_waive"
        line["compensating_path"] = "tier_d_logged_waive"
        line["omit_notes"] = ["vo_contract:execution_contract_waive"]
    gap = minimal_gap_report(line)
    gap["opening_orientation"] = {
        "line_id": _LINE,
        "required": required,
        "target_segment_id": "seg_002",
        "sequence": "intro_music_body",
    }
    return gap


def _plan_with_omitted_orientation() -> dict:
    return {
        "version": 1,
        "plan_status": "complete",
        "air_script": {
            "beats": [{"beat_id": "b1", "segment_id": "seg_002", "montage_move": "vo"}],
            "vo_seats": {
                "seated_line_ids": ["vo_layup_seg_037"],
                "omitted_line_ids": [_LINE],
                "orientation_id": None,
            },
        },
    }


def test_required_orientation_not_waived_by_stale_tier_d(ctx: RunContext) -> None:
    gap = _gap(required=True, waived=True)
    seats = build_vo_seats(_plan_with_omitted_orientation(), gap)
    assert _LINE in seats["seated_line_ids"]
    assert _LINE not in seats["omitted_line_ids"]
    assert seats.get("orientation_id") == _LINE


def test_filter_and_revive_clear_stale_waive_for_required(
    ctx: RunContext,
) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        _gap(required=True, waived=True),
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        _plan_with_omitted_orientation(),
        skip_handoff=True,
    )
    plan = ctx.read_json("mastering/mastering_plan.json")
    gap = ctx.read_json("understanding/gap_report.json")

    filtered = filter_gap_lines_for_air_script(gap, plan, ctx=ctx)
    assert isinstance(filtered, dict)
    row = next(
        ln
        for ln in (filtered.get("interviewer_lines") or [])
        if str(ln.get("line_id")) == _LINE
    )
    assert not row.get("skipped_optional")
    assert not row.get("air_script_omit")
    assert str(row.get("skip_reason_code") or "") == ""
    assert str(row.get("compensating_path") or "") != "tier_d_logged_waive"

    seats = build_vo_seats(plan, filtered)
    assert _LINE in seats["seated_line_ids"]
    assert seats.get("orientation_id") == _LINE

    revived = revive_required_opening_orientation(ctx)
    assert revived.get("changed") is True
    gap2 = ctx.read_json("understanding/gap_report.json")
    row2 = next(
        ln
        for ln in (gap2.get("interviewer_lines") or [])
        if str(ln.get("line_id")) == _LINE
    )
    assert not row2.get("skipped_optional")
    assert str(row2.get("compensating_path") or "") != "tier_d_logged_waive"
    plan2 = ctx.read_json("mastering/mastering_plan.json")
    seats2 = (plan2.get("air_script") or {}).get("vo_seats") or {}
    assert _LINE in (seats2.get("seated_line_ids") or [])
    assert seats2.get("orientation_id") == _LINE
    assert "reseated_orientation" in " ".join(str(n) for n in (revived.get("notes") or []))

    edl = {
        "clips": [
            {
                "type": "vo_pickup",
                "line_id": _LINE,
                "targets_segment_id": "seg_002",
                "duration_ms": 3000,
            },
            {
                "type": "silence",
                "air_kind": "opening_music",
                "duration_ms": 500,
            },
            {"type": "speech", "segment_id": "seg_002", "duration_ms": 4000},
        ]
    }
    assert validate_opening_orientation(gap_report=gap2, edl=edl) == []


def test_non_required_waive_still_omits(ctx: RunContext) -> None:
    """Without required meta, tier-D waive may keep orientation out of seats."""
    gap = _gap(required=False, waived=True)
    gap.pop("opening_orientation", None)
    seats = build_vo_seats(_plan_with_omitted_orientation(), gap)
    assert _LINE not in seats["seated_line_ids"]
    assert _LINE in seats["omitted_line_ids"]
