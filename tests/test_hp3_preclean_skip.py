"""HP-3: operator preclean skip must not be hollow-unmarked.

skip.json is a finished skip. Without skip, any of isolated/provider/lineage
still counts (2B). isolated.wav wins if both skip and WAV exist (3A).
Do not start a run. HP-2 G0 build stays closed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus.agenda import (
    prepare_outputs_present,
    unmark_hollow_prepare_stages,
)
from interview_mux.run_context import RunContext
from interview_mux.stages.audio_preclean import ensure_preclean_skipped
from run_fixtures import isolated_run_ctx, mark_done_raw

_STAGE = "audio_preclean"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hp3_preclean")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hp3_skip_json_is_present_and_not_unmarked(ctx: RunContext) -> None:
    ensure_preclean_skipped(
        ctx, checkpoint="before_ingest", scope="ingest", reason="operator_dismissed"
    )
    assert ctx.artifact_exists("preclean/skip.json")
    assert ctx.is_done(_STAGE)
    assert prepare_outputs_present(ctx, _STAGE) is True
    cleared = unmark_hollow_prepare_stages(ctx)
    assert _STAGE not in cleared
    assert ctx.is_done(_STAGE)


def test_hp3_provider_alone_still_counts(ctx: RunContext) -> None:
    dest = ctx.final_path("preclean", "provider.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('{"status":"skipped","provider":"fixture"}', encoding="utf-8")
    mark_done_raw(ctx, _STAGE)
    assert prepare_outputs_present(ctx, _STAGE) is True
    cleared = unmark_hollow_prepare_stages(ctx)
    assert _STAGE not in cleared
    assert ctx.is_done(_STAGE)


def test_hp3_isolated_wav_wins_over_stale_skip(ctx: RunContext) -> None:
    wav = ctx.final_path("preclean", "isolated.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    ctx.write_json(
        "preclean/skip.json",
        {"status": "skipped", "reason": "stale"},
        skip_handoff=True,
    )
    mark_done_raw(ctx, _STAGE)
    assert prepare_outputs_present(ctx, _STAGE) is True
    cleared = unmark_hollow_prepare_stages(ctx)
    assert _STAGE not in cleared
    assert ctx.is_done(_STAGE)


def test_hp3_done_without_outputs_still_unmarks(ctx: RunContext) -> None:
    mark_done_raw(ctx, _STAGE)
    assert prepare_outputs_present(ctx, _STAGE) is False
    cleared = unmark_hollow_prepare_stages(ctx)
    assert _STAGE in cleared
    assert not ctx.is_done(_STAGE)
