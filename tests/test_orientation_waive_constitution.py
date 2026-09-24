"""Required opening-orientation waive constitution (MUX_FORENSICS=0).

Pins: durable omit = omitted+required=false; tier-D refuse while required;
orphan stamps ignored by policy_omit; remint clears stamps; playbook always revives.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.opening_orientation import (
    clear_stale_orientation_waive_stamps,
    ensure_episode_orientation,
    orientation_omitted,
)
from interview_mux.omit_ledger import revive_required_opening_orientation
from interview_mux.recovery_controller import playbook_opening_orientation_inaudible
from interview_mux.run_context import RunContext
from interview_mux.vo_contract import (
    ensure_gap_line_on_air,
    policy_omit_skip_reason,
)
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report

_LINE = "vo_preface_cta_open_seg_002"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "orient_waive_constitution")
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


def _waived_orientation_line() -> dict:
    return minimal_gap_line(
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
        skipped_optional=True,
        air_script_omit=True,
        skip_reason_code="execution_contract_waive",
        compensating_path="tier_d_logged_waive",
        omit_notes=["vo_contract:execution_contract_waive"],
    )


def test_orientation_omitted_requires_both_meta_flags() -> None:
    assert orientation_omitted(None) is False
    assert orientation_omitted({}) is False
    assert (
        orientation_omitted({"opening_orientation": {"required": False}}) is False
    )
    assert (
        orientation_omitted({"opening_orientation": {"omitted": True}}) is False
    )
    assert (
        orientation_omitted(
            {"opening_orientation": {"omitted": True, "required": True}}
        )
        is False
    )
    assert (
        orientation_omitted(
            {"opening_orientation": {"omitted": True, "required": False}}
        )
        is True
    )


def test_policy_omit_ignores_orphan_tier_d_when_required(ctx: RunContext) -> None:
    row = _waived_orientation_line()
    gap = minimal_gap_report(row)
    gap["opening_orientation"] = {
        "line_id": _LINE,
        "required": True,
        "target_segment_id": "seg_002",
    }
    # Without gap context, stamps still look like policy (legacy callers).
    assert policy_omit_skip_reason(row) is True
    # With required meta, orphan stamps are not durable policy.
    assert policy_omit_skip_reason(row, gap_report=gap) is False
    cleared = ensure_gap_line_on_air(row, gap_report=gap)
    assert not cleared.get("skipped_optional")
    assert not cleared.get("air_script_omit")
    assert str(cleared.get("compensating_path") or "") != "tier_d_logged_waive"
    assert str(cleared.get("skip_reason_code") or "") == ""


def test_ensure_episode_orientation_clears_waive_stamps(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.opening_orientation.native_open_already_orients",
        lambda *_a, **_k: False,
    )
    gap = minimal_gap_report(_waived_orientation_line())
    gap["opening_orientation"] = {
        "line_id": _LINE,
        "required": True,
        "target_segment_id": "seg_002",
    }
    out, actions = ensure_episode_orientation(
        ctx, gap, ["seg_002", "seg_037"]
    )
    row = next(
        ln
        for ln in (out.get("interviewer_lines") or [])
        if str(ln.get("line_id")) == _LINE
    )
    assert not row.get("skipped_optional")
    assert not row.get("air_script_omit")
    assert str(row.get("compensating_path") or "") != "tier_d_logged_waive"
    assert (out.get("opening_orientation") or {}).get("required") is True
    assert any(
        a.get("action") == "clear_stale_orientation_waive_stamps" for a in actions
    )


def test_clear_stale_orientation_waive_stamps_helper() -> None:
    row, changed = clear_stale_orientation_waive_stamps(_waived_orientation_line())
    assert changed is True
    assert not row.get("skipped_optional")
    assert str(row.get("compensating_path") or "") == ""


def test_playbook_orientation_inaudible_always_revives(ctx: RunContext) -> None:
    gap = minimal_gap_report(_waived_orientation_line())
    gap["opening_orientation"] = {
        "line_id": _LINE,
        "required": True,
        "target_segment_id": "seg_002",
    }
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "plan_status": "complete",
            "air_script": {
                "beats": [
                    {"beat_id": "b1", "segment_id": "seg_002", "montage_move": "vo"}
                ],
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_037"],
                    "omitted_line_ids": [_LINE],
                    "orientation_id": None,
                },
            },
        },
        skip_handoff=True,
    )
    # rebuild=False simulates resume pinning upstream of edl — must still revive.
    artifacts = playbook_opening_orientation_inaudible(ctx, rebuild=False)
    assert artifacts
    gap2 = ctx.read_json("understanding/gap_report.json")
    row = next(
        ln
        for ln in (gap2.get("interviewer_lines") or [])
        if str(ln.get("line_id")) == _LINE
    )
    assert not row.get("skipped_optional")
    assert str(row.get("compensating_path") or "") != "tier_d_logged_waive"
    plan = ctx.read_json("mastering/mastering_plan.json")
    seats = (plan.get("air_script") or {}).get("vo_seats") or {}
    assert _LINE in (seats.get("seated_line_ids") or [])
    assert seats.get("orientation_id") == _LINE


def test_revive_clears_tier_d_stamps(ctx: RunContext) -> None:
    gap = minimal_gap_report(_waived_orientation_line())
    gap["opening_orientation"] = {
        "line_id": _LINE,
        "required": True,
        "target_segment_id": "seg_002",
    }
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": [],
                    "omitted_line_ids": [_LINE],
                    "orientation_id": None,
                }
            }
        },
        skip_handoff=True,
    )
    out = revive_required_opening_orientation(ctx)
    assert out.get("changed") is True
    gap2 = ctx.read_json("understanding/gap_report.json")
    row = next(
        ln
        for ln in (gap2.get("interviewer_lines") or [])
        if str(ln.get("line_id")) == _LINE
    )
    assert not row.get("skipped_optional")
    assert str(row.get("compensating_path") or "") != "tier_d_logged_waive"
