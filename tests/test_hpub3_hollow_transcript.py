"""HPUB-3: empty cues / header-only VTT cannot complete or package.

Schema still allows cue_count 0. Seed and package treat 0 / header-only as
incomplete and pin master_transcript_build. Cover/package_ready (HPUB-2) stays.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.asset_transcripts import (
    MASTER_JSON_REL,
    MASTER_VTT_REL,
    cues_to_vtt,
    master_transcript_ship_incompleteness,
    require_packagable_master_transcript,
    run_master_transcript_build,
    vtt_has_cue_bodies,
    write_master_transcript_files,
)
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import unmark_hollow_delivery_producers
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw


def _write_header_only_vtt(ctx: RunContext) -> None:
    payload = "WEBVTT\n\n"
    for dest in (
        ctx.path(*MASTER_VTT_REL.split("/")),
        ctx.final_path(*MASTER_VTT_REL.split("/")),
    ):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(payload, encoding="utf-8")


def _plant_master_inputs(ctx: RunContext) -> None:
    dest = ctx.final_path("master", "master.wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"RIFF" + b"\x00" * 64)
    edl = {
        "version": 1,
        "ordered_segment_ids": [],
        "timeline_duration_ms": 0,
        "clips": [],
    }
    for target in (
        ctx.path("master", "edl.json"),
        ctx.final_path("master", "edl.json"),
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(edl), encoding="utf-8")


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hpub3_transcript")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hpub3_empty_cues_refuse_mark_done(ctx: RunContext) -> None:
    _plant_master_inputs(ctx)
    with pytest.raises(RuntimeError, match="cue_count_zero"):
        run_master_transcript_build(ctx)
    assert ctx.is_done("master_transcript_build") is False
    doc = ctx.read_json(MASTER_JSON_REL)
    assert doc.get("cue_count") == 0
    reason = stage_artifact_incompleteness(ctx, "master_transcript_build")
    assert reason is not None
    assert "cue_count_zero" in reason
    assert seed_stage_complete(ctx, "master_transcript_build") is False


def test_hpub3_header_only_vtt_incompleteness(ctx: RunContext) -> None:
    write_master_transcript_files(
        ctx,
        [{"start_ms": 0, "end_ms": 500, "speaker_name": "Ada", "text": "Hello."}],
    )
    _write_header_only_vtt(ctx)
    reason = master_transcript_ship_incompleteness(ctx)
    assert reason is not None
    assert "header_only_vtt" in reason
    assert vtt_has_cue_bodies("WEBVTT\n\n") is False
    assert vtt_has_cue_bodies(
        cues_to_vtt(
            [{"start_ms": 0, "end_ms": 500, "speaker_name": "Ada", "text": "Hello."}]
        )
    ) is True


def test_hpub3_package_refuses_header_only(ctx: RunContext) -> None:
    write_master_transcript_files(ctx, [])
    with pytest.raises(RuntimeError, match="cue_count_zero"):
        require_packagable_master_transcript(ctx)
    write_master_transcript_files(
        ctx,
        [{"start_ms": 0, "end_ms": 500, "speaker_name": "Ada", "text": "Hello."}],
    )
    _write_header_only_vtt(ctx)
    with pytest.raises(RuntimeError, match="header_only_vtt"):
        require_packagable_master_transcript(ctx)


def test_hpub3_spoken_cues_complete(ctx: RunContext) -> None:
    write_master_transcript_files(
        ctx,
        [{"start_ms": 0, "end_ms": 500, "speaker_name": "Ada", "text": "Hello."}],
    )
    assert master_transcript_ship_incompleteness(ctx) is None
    require_packagable_master_transcript(ctx)
    out = heal_or_refuse_mark(ctx, "master_transcript_build")
    assert out.get("marked") is True
    assert seed_stage_complete(ctx, "master_transcript_build") is True


def test_hpub3_hollow_done_unmarks_and_pins(ctx: RunContext) -> None:
    write_master_transcript_files(ctx, [])
    mark_done_raw(ctx, "master_transcript_build")
    cleared = unmark_hollow_delivery_producers(ctx, {"master_transcript_build"})
    assert "master_transcript_build" in cleared
    assert ctx.is_done("master_transcript_build") is False
    reason = stage_artifact_incompleteness(ctx, "master_transcript_build")
    assert reason is not None
    assert producer_pin_for_token(reason) == "master_transcript_build"
    heal = heal_or_refuse_mark(ctx, "master_transcript_build")
    assert heal.get("refused") is True
    assert producer_pin_for_token("header_only_vtt") == "master_transcript_build"
