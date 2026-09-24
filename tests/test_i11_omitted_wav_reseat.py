"""i11: omitted seat with rendered WAV reseats; clamp stamps gap omit flags."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.vo_contract import repair_vo_contract_drift, validate_vo_contract
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i11_omit_wav")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_repair_reseats_omitted_line_with_wav(ctx: RunContext) -> None:
    pickup = ctx.final_path("vo_pickup", "synthesized")
    pickup.mkdir(parents=True, exist_ok=True)
    (pickup / "vo_layup_seg_003b.wav").write_bytes(b"RIFF" + b"\x00" * 64)

    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_layup_seg_003b",
            text="Hosted layup about precision oncology for listeners.",
            targets_segment_id="seg_003",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_layup_seg_037",
            text="Another hosted layup covering clinical adoption stakes.",
            targets_segment_id="seg_037",
            delivery="synthesize",
        ),
    )
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_037"],
                    "omitted_line_ids": ["vo_layup_seg_003b"],
                    "orientation_id": None,
                }
            }
        },
        skip_handoff=True,
    )
    assert any("lacks skip/omit" in i for i in validate_vo_contract(ctx))
    changed = repair_vo_contract_drift(ctx)
    assert "vo_layup_seg_003b" in changed
    seats = (
        ctx.read_json("mastering/mastering_plan.json").get("air_script") or {}
    ).get("vo_seats") or {}
    assert "vo_layup_seg_003b" in (seats.get("seated_line_ids") or [])
    assert "vo_layup_seg_003b" not in (seats.get("omitted_line_ids") or [])
    assert not any("lacks skip/omit" in i for i in validate_vo_contract(ctx))
