"""i13: seated bind heal must not omit when WAV exists after false-fail synth."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.vo_bind_authority import heal_seated_bind_mismatch
from interview_mux.vo_contract import repair_vo_contract_drift, validate_vo_contract
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report, write_fixture_vo_wav


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i13_bind_wav_accept")


def test_heal_accepts_existing_wav_instead_of_omit(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_003c.wav")
    write_fixture_vo_wav(wav)
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_layup_seg_003c",
            text="Hosted layup that already has chatterbox bytes on disk.",
            targets_segment_id="seg_003",
            delivery="synthesize",
        )
    )
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_003c"],
                    "omitted_line_ids": [],
                    "orientation_id": None,
                }
            }
        },
        skip_handoff=True,
    )

    monkeypatch.setattr(
        "interview_mux.stage_input_checks.compact_vo_coverage_stale_or_missing",
        lambda _ctx: ["vo_layup_seg_003c"],
    )

    def _boom(*_a, **_k):
        raise RuntimeError("false fail after wav write")

    monkeypatch.setattr(
        "interview_mux.s2s_runner.synthesize_line",
        _boom,
    )

    heal = heal_seated_bind_mismatch(ctx, attempt_synth=True)
    assert "vo_layup_seg_003c" in heal["resynthesized"]
    assert heal["omitted"] == []
    seats = (
        ctx.read_json("mastering/mastering_plan.json").get("air_script") or {}
    ).get("vo_seats") or {}
    assert "vo_layup_seg_003c" in (seats.get("seated_line_ids") or [])
    assert "vo_layup_seg_003c" not in (seats.get("omitted_line_ids") or [])


def test_repair_reseats_bind_failed_omit_when_wav_exists(ctx: RunContext) -> None:
    wav = ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_003c.wav")
    write_fixture_vo_wav(wav)
    line = minimal_gap_line(
        line_id="vo_layup_seg_003c",
        text="Falsely omitted after chatterbox JSON parse fail.",
        targets_segment_id="seg_003",
        delivery="synthesize",
    )
    line["skipped_optional"] = True
    line["air_script_omit"] = True
    line["skip_reason_code"] = "seated_bind_synth_failed"
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(line),
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_037"],
                    "omitted_line_ids": ["vo_layup_seg_003c"],
                    "orientation_id": None,
                }
            }
        },
        skip_handoff=True,
    )
    changed = repair_vo_contract_drift(ctx)
    assert "vo_layup_seg_003c" in changed
    seats = (
        ctx.read_json("mastering/mastering_plan.json").get("air_script") or {}
    ).get("vo_seats") or {}
    assert "vo_layup_seg_003c" in (seats.get("seated_line_ids") or [])
    assert "vo_layup_seg_003c" not in (seats.get("omitted_line_ids") or [])
    gap = ctx.read_json("understanding/gap_report.json")
    row = next(
        r
        for r in gap["interviewer_lines"]
        if isinstance(r, dict) and r.get("line_id") == "vo_layup_seg_003c"
    )
    assert not row.get("skipped_optional")
    assert not row.get("air_script_omit")
    assert not any("003c" in i and "skip/omit" in i for i in validate_vo_contract(ctx))
