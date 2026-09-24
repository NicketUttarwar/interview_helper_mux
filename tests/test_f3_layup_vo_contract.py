"""F3 layup / VO contract: omit-wins unseat; producer CTA-scrap omit; proceed.

Fixture shape from exec_11165 ``vo_layup_seg_012`` seated+skip/omit and
``seg_066j`` empty post-CTA scrap. Does not resume that run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.media_ip_cta import omit_locked_degraded_cta_scraps
from interview_mux.vo_contract import (
    ensure_hosted_framing_vo_seats,
    repair_vo_contract_drift,
    sync_vo_contract_after_layup,
    validate_vo_contract,
)
from run_fixtures import isolated_run_ctx

_FIX = Path(__file__).resolve().parent / "fixtures" / "f3_layup_vo_contract"
LINE_ID = "vo_layup_seg_012"


def _homunculus(ctx) -> None:
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )


def _plant_seated_skip(ctx) -> dict:
    line = json.loads((_FIX / "gap_line_012.json").read_text(encoding="utf-8"))
    seats = json.loads((_FIX / "air_seats.json").read_text(encoding="utf-8"))
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.path("mastering").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [line]},
        skip_handoff=True,
    )
    ctx.write_json("mastering/mastering_plan.json", seats, skip_handoff=True)
    return line


def test_repair_unseats_seated_skip_omit_keeps_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    ctx = isolated_run_ctx(tmp_path, "f3_unseat")
    _plant_seated_skip(ctx)
    assert any("has skip/omit flags" in v for v in validate_vo_contract(ctx))
    changed = repair_vo_contract_drift(ctx)
    assert LINE_ID in changed
    fixed = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    assert fixed.get("skipped_optional")
    assert fixed.get("air_script_omit")
    assert str(fixed.get("skip_reason_code") or "") == "skip_omit_unseat"
    seats = ctx.read_json("mastering/mastering_plan.json")["air_script"]["vo_seats"]
    assert LINE_ID not in (seats.get("seated_line_ids") or [])
    assert LINE_ID in (seats.get("omitted_line_ids") or [])
    assert not any("has skip/omit flags" in v for v in validate_vo_contract(ctx))


def test_producer_omits_locked_degraded_cta_scrap_without_llm_need(
    tmp_path: Path,
) -> None:
    ctx = isolated_run_ctx(tmp_path, "f3_cta_scrap")
    _homunculus(ctx)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_065",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Real substance remains.",
                    "start_ms": 0,
                    "end_ms": 4000,
                },
                {
                    "segment_id": "seg_066j",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "",
                    "start_ms": 4000,
                    "end_ms": 6000,
                },
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_065", "seg_066j"],
            "excluded_segment_ids": [
                {"segment_id": "seg_066", "reason": "media_ip_cta"}
            ],
            "exclude_rationales": {"seg_066": "media_ip_cta"},
        },
        skip_handoff=True,
    )
    dropped = omit_locked_degraded_cta_scraps(ctx)
    order = ctx.read_json("master/selection.json").get("ordered_segment_ids") or []
    assert "seg_066j" in dropped
    assert "seg_065" not in dropped
    assert order == ["seg_065"]


def test_sync_after_layup_proceeds_when_skip_omit_leftovers_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    ctx = isolated_run_ctx(tmp_path, "f3_sync_proceed")
    _plant_seated_skip(ctx)
    from interview_mux.seat_authority import stamp_soft_seat_freeze

    stamp_soft_seat_freeze(ctx, reason="f3_test")
    remaining = sync_vo_contract_after_layup(ctx)
    assert not any("skip/omit" in v for v in remaining)
    seats = ctx.read_json("mastering/mastering_plan.json")["air_script"]["vo_seats"]
    assert LINE_ID not in (seats.get("seated_line_ids") or [])
    fixed = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    assert fixed.get("skipped_optional")
    assert str(fixed.get("skip_reason_code") or "") == "skip_omit_unseat"


def test_hosted_floor_does_not_reseat_omit_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    ctx = isolated_run_ctx(tmp_path, "f3_no_reseat")
    _plant_seated_skip(ctx)
    repair_vo_contract_drift(ctx)
    reseated = ensure_hosted_framing_vo_seats(ctx)
    assert LINE_ID not in reseated
    seats = ctx.read_json("mastering/mastering_plan.json")["air_script"]["vo_seats"]
    assert LINE_ID not in (seats.get("seated_line_ids") or [])
    fixed = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    assert fixed.get("skipped_optional")


def test_execution_contract_waive_survives_hosted_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170: tier-D waive must stay omit-wins even if flags were stripped."""
    from interview_mux.vo_contract import (
        ensure_gap_line_on_air,
        mark_gap_line_not_on_air,
        omit_wins_skip_reason,
        validate_vo_contract,
    )

    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    ctx = isolated_run_ctx(tmp_path, "f3_tier_d_waive")
    _homunculus(ctx)
    lid = "vo_context_seg_011"
    stamped = mark_gap_line_not_on_air(
        {
            "line_id": lid,
            "delivery": "synthesize",
            "gap_type": "missing_setup",
            "targets_segment_id": "seg_011",
            "placement": "before",
            "required": True,
            "text": "What changed for patients after the trial readout?",
            "severity": "high",
        },
        reason_code="execution_contract_waive",
        compensating_path="tier_d_logged_waive",
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [stamped],
            "opening_orientation": {
                "omitted": True,
                "waived_line_id": lid,
                "required": False,
            },
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "beats": [],
                "vo_seats": {
                    "seated_line_ids": [],
                    "omitted_line_ids": [lid],
                },
            }
        },
        skip_handoff=True,
    )
    assert omit_wins_skip_reason(stamped) is True
    # Simulate thrash that cleared flags but left durable waive markers.
    stripped = dict(stamped)
    stripped.pop("skipped_optional", None)
    stripped.pop("air_script_omit", None)
    stripped.pop("skip_reason_code", None)
    assert omit_wins_skip_reason(stripped) is True
    assert ensure_gap_line_on_air(stripped).get("omit_notes")
    reseated = ensure_hosted_framing_vo_seats(ctx)
    assert lid not in reseated
    seats = ctx.read_json("mastering/mastering_plan.json")["air_script"]["vo_seats"]
    assert lid not in (seats.get("seated_line_ids") or [])
    assert lid in (seats.get("omitted_line_ids") or [])
    repair_vo_contract_drift(ctx)
    assert not any("lacks skip/omit" in v for v in validate_vo_contract(ctx))
    fixed = next(
        r
        for r in ctx.read_json("understanding/gap_report.json")["interviewer_lines"]
        if r.get("line_id") == lid
    )
    assert fixed.get("skipped_optional") is True
    assert fixed.get("air_script_omit") is True
    assert str(fixed.get("skip_reason_code") or "") == "execution_contract_waive"
