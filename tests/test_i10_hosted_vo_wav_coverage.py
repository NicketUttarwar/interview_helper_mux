"""i10: hard-freeze hosted floor with active copy pins vo_synthesize, not layup.

exec_13177: wav_backed=1 < need=3 while gap already had ≥3 active synth lines.
protect_hosted_vo_floor_reseat is End-A forbidden; reseating those already-active
lines is WAV paperwork (reseated_active_hosted_vo_for_wav) so G1 can render.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_ownership import heal_pin_for
from interview_mux.artifact_sanitize.air_script import sanitize_air_contract
from interview_mux.run_context import RunContext
from interview_mux.seat_authority import (
    HARD_FREEZE_ALLOWLIST_ACTIONS,
    hard_freeze_action_permitted,
    stamp_hard_seat_freeze,
)
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i10_wav_floor")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    run.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_002", "seg_003"], "version": 1},
        skip_handoff=True,
    )
    return run


def _stamp_hard(ctx: RunContext) -> None:
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")


def test_reseated_active_hosted_vo_allowlisted() -> None:
    assert hard_freeze_action_permitted("reseated_active_hosted_vo_for_wav")
    assert "reseated_active_hosted_vo_for_wav" in HARD_FREEZE_ALLOWLIST_ACTIONS
    assert heal_pin_for("hosted_vo_wav_coverage") == "vo_synthesize"


def test_hard_freeze_reseats_active_copy_for_wav_coverage(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    # Only vo_a has a pickup stem — wav floor unmet; vo_b/vo_c are active copy.
    monkeypatch.setattr(
        "interview_mux.vo_contract._gap_row_has_pickup_stem",
        lambda _ctx, row: str(row.get("line_id") or "") == "vo_a",
    )
    _stamp_hard(ctx)
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_a",
            text="Hosted line A about the guest and topic for listeners.",
            targets_segment_id="seg_001",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_b",
            text="Hosted line B about stakes and why this conversation matters.",
            targets_segment_id="seg_002",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_c",
            text="Hosted line C connects the opening to the clinical arc ahead.",
            targets_segment_id="seg_003",
            delivery="synthesize",
        ),
    )
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_b", "vo_c"],
                "orientation_id": None,
            }
        }
    }
    result = sanitize_air_contract(ctx, {"plan": plan, "gap": gap, "omit": {"entries": []}})
    assert any(
        a.get("action") == "reseated_active_hosted_vo_for_wav" for a in result.actions
    )
    assert not any(
        a.get("action") == "protect_hosted_vo_floor_reseat_refused_hard_freeze"
        for a in result.actions
    )
    seats = (result.doc.get("air_script") or {}).get("vo_seats") or {}
    seated = set(seats.get("seated_line_ids") or [])
    assert "vo_a" in seated
    assert "vo_b" in seated
    assert "vo_c" in seated
    assert result.ok
    from interview_mux.artifact_sanitize.air_script import _floor_unmet_pin

    pin = _floor_unmet_pin([], list(result.actions or []))
    assert pin is not None and "hosted_vo_wav_coverage" in pin
    assert "vo_synthesize" in pin
