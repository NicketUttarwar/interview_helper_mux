"""i10: orphan promote must not hollow-stamp mix while music_epoch remaster owed."""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.delivery_guardrails import (
    mix_epoch_block,
    promote_complete_orphan_stage_done,
)
from interview_mux.mix_junction_seat import (
    clear_remaster,
    ensure_speech_first_remaster,
    maybe_remaster_after_music_epoch,
    mix_is_seed_complete,
    music_epoch_pre_beds_seat,
    note_speech_first_mix,
    remaster_owner,
    speech_first_remaster_owed,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_i10_remaster")


def _write_assembly(ctx: RunContext) -> Path:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    return path


def test_i10_orphan_promote_refuses_pre_beds_mix(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Speech-first seat + music remaster: orphan promote must not restamp mix."""
    asm = _write_assembly(ctx)
    # Age assembly so it predates the remaster stamp.
    old = time.time() - 120
    os.utime(asm, (old, old))

    note_speech_first_mix(ctx)
    marker = ctx.final_path(".stage_done", "mix")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("done")

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
    assert not ctx.is_done("mix")
    assert music_epoch_pre_beds_seat(ctx) is True
    assert speech_first_remaster_owed(ctx) is True

    reason = stage_artifact_incompleteness(ctx, "mix")
    assert reason is not None
    assert "remaster owed" in reason

    promoted = promote_complete_orphan_stage_done(ctx, ("mix",))
    assert promoted == []
    assert not ctx.is_done("mix")
    assert mix_is_seed_complete(ctx) is False
    assert mix_epoch_block(ctx, stage="junction_snip_qa") == "speech_first_remaster_pending"
    assert mix_epoch_block(ctx, stage="mix") is None


def test_i10_post_beds_assembly_allows_mark_and_clear(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Land Honesty: mtime bump alone does not clear remaster; clear_remaster does."""
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"

    # Remaster land candidate: assembly newer than remaster stamp — still unpaid
    # until clear_remaster (mtime defeat must not greenwash).
    time.sleep(0.05)
    _write_assembly(ctx)
    assert music_epoch_pre_beds_seat(ctx) is False
    reason = stage_artifact_incompleteness(ctx, "mix")
    assert reason is not None
    assert "remaster owed" in str(reason)
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []

    clear_remaster(ctx)
    assert remaster_owner(ctx) == ""
    assert speech_first_remaster_owed(ctx) is False
    assert mix_epoch_block(ctx, stage="junction_snip_qa") is None
    reason_after = stage_artifact_incompleteness(ctx, "mix")
    assert reason_after is None or "remaster owed" not in str(reason_after)
