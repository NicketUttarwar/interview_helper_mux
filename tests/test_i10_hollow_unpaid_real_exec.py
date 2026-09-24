"""Dig #2 real-exec reconstitution: exec_13183 hollow unpaid remaster (i10)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.delivery_guardrails import promote_complete_orphan_stage_done
from interview_mux.done_authority import unpaid_land_reason
from interview_mux.mix_junction_seat import (
    ensure_speech_first_remaster,
    maybe_remaster_after_music_epoch,
    music_epoch_pre_beds_seat,
    note_speech_first_mix,
    remaster_owner,
)
from run_fixtures import init_run_meta_for_test, isolated_run_ctx

FIXTURE = Path(__file__).parent / "fixtures" / "exec_13183_hollow_unpaid"
SOURCE_RUN_ID = "exec_13183_d19c15b58ab4_20260924T001619Z"


def test_hollow_unpaid_fixture_package_complete() -> None:
    assert (FIXTURE / "forensics_excerpt.json").is_file()
    assert (FIXTURE / "README.md").is_file()
    excerpt = json.loads((FIXTURE / "forensics_excerpt.json").read_text(encoding="utf-8"))
    assert excerpt.get("source_run") == SOURCE_RUN_ID
    assert excerpt.get("dig") == 2
    fp = str(excerpt["fingerprints"][0]["detail"])
    assert "speech_first_remaster_pending" in fp


def test_i10_real_reconstitution_orphan_promote_refuses_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror exec_13183: aged speech-first assembly + music remaster → no promote."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_13183_hollow_unpaid")
    init_run_meta_for_test(ctx)

    asm = ctx.path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\x00" * 64)
    old = time.time() - 180
    os.utime(asm, (old, old))

    note_speech_first_mix(ctx)
    marker = ctx.final_path(".stage_done", "mix")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("done", encoding="utf-8")

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )

    assert maybe_remaster_after_music_epoch(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert music_epoch_pre_beds_seat(ctx) is True
    assert not ctx.is_done("mix")  # demoted on remaster begin

    why = unpaid_land_reason(ctx, "mix")
    assert why and "remaster owed" in why

    promoted = promote_complete_orphan_stage_done(ctx, ("mix",))
    assert "mix" not in promoted
    assert not ctx.is_done("mix")

    # ensure path demotes again if somehow restamped hollow
    marker.write_text("done", encoding="utf-8")
    assert ensure_speech_first_remaster(ctx) is True
    assert not ctx.is_done("mix")
