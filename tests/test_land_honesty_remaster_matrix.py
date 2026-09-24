"""Land Honesty remaster matrix (i10): speech-first / orphan promote never hollow-lands mix.

Focused matrix so unpaid remaster under music_epoch / junction owners cannot
recur via mtime bump, orphan promote, or seed-complete greenwash.

MUX_FORENSICS=0. Uses isolated_run_ctx + mark_done_raw.
"""

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
from interview_mux.done_authority import unpaid_land_reason
from interview_mux.mix_junction_seat import (
    begin_remaster,
    clear_remaster,
    demote_hollow_mix_done,
    ensure_speech_first_remaster,
    mix_is_seed_complete,
    note_speech_first_mix,
    remaster_in_flight,
    remaster_owner,
    speech_first_remaster_owed,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_land_honesty_remaster_matrix")


def _write_assembly(ctx: RunContext) -> Path:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    return path


def _mock_seated_and_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )


def _music_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: True,
    )


# ---------------------------------------------------------------------------
# 1. music_epoch owner blocks unpaid_land_reason for mix AND junction_snip_qa
# ---------------------------------------------------------------------------


def test_music_epoch_owner_blocks_unpaid_land_for_mix_and_junction(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="music_epoch")
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)

    mix_reason = unpaid_land_reason(ctx, "mix")
    jsq_reason = unpaid_land_reason(ctx, "junction_snip_qa")
    assert mix_reason is not None
    assert jsq_reason is not None
    assert "remaster owed" in mix_reason
    assert "remaster owed" in jsq_reason
    assert "music_epoch" in mix_reason
    assert "music_epoch" in jsq_reason
    assert remaster_owner(ctx) == "music_epoch"
    assert remaster_in_flight(ctx) is True


# ---------------------------------------------------------------------------
# 2. mtime bump of assembly.wav does NOT clear remaster_in_flight / unpaid land
# ---------------------------------------------------------------------------


def test_assembly_mtime_bump_does_not_clear_remaster_or_unpaid(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_speech_first_mix(ctx)
    _music_complete(monkeypatch)
    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert remaster_in_flight(ctx) is True

    time.sleep(0.05)
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)

    assert remaster_in_flight(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert unpaid_land_reason(ctx, "mix") is not None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is not None
    assert speech_first_remaster_owed(ctx) is True


# ---------------------------------------------------------------------------
# 3. clear_remaster is the ONLY clear path; unpaid_land_reason None after clear
# ---------------------------------------------------------------------------


def test_clear_remaster_only_path_clears_unpaid_land(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="music_epoch")
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)
    assert unpaid_land_reason(ctx, "mix") is not None

    # Defeat paths that must NOT clear unpaid land.
    time.sleep(0.05)
    asm = _write_assembly(ctx)
    os.utime(asm, None)
    assert remaster_in_flight(ctx) is True
    assert unpaid_land_reason(ctx, "mix") is not None

    clear_remaster(ctx)
    assert remaster_owner(ctx) == ""
    assert remaster_in_flight(ctx) is False
    assert unpaid_land_reason(ctx, "mix") is None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is None


def test_clear_remaster_after_speech_first_music_epoch_stamp(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After ensure stamps music_epoch_remaster_at, clear_remaster pays the land."""
    note_speech_first_mix(ctx)
    _music_complete(monkeypatch)
    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert unpaid_land_reason(ctx, "mix") is not None

    clear_remaster(ctx)
    assert remaster_owner(ctx) == ""
    assert remaster_in_flight(ctx) is False
    assert speech_first_remaster_owed(ctx) is False
    assert unpaid_land_reason(ctx, "mix") is None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is None


# ---------------------------------------------------------------------------
# 4. promote_complete_orphan_stage_done skips mix while remaster owed
# ---------------------------------------------------------------------------


def test_orphan_promote_skips_mix_while_music_epoch_remaster_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="music_epoch")
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)
    assert not ctx.is_done("mix")

    promoted = promote_complete_orphan_stage_done(ctx, ("mix",))
    assert promoted == []
    assert not ctx.is_done("mix")
    assert unpaid_land_reason(ctx, "mix") is not None


def test_orphan_promote_skips_mix_and_junction_while_junction_remaster_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="junction")
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)

    promoted = promote_complete_orphan_stage_done(
        ctx, ("mix", "junction_snip_qa")
    )
    assert promoted == []
    assert not ctx.is_done("mix")
    assert not ctx.is_done("junction_snip_qa")


# ---------------------------------------------------------------------------
# 5. demote_hollow_mix_done / mix_is_seed_complete false while remaster owed
# ---------------------------------------------------------------------------


def test_demote_hollow_and_seed_complete_false_while_remaster_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="music_epoch")
    mark_done_raw(ctx, "mix")
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)

    assert ctx.is_done("mix")
    assert mix_is_seed_complete(ctx) is False
    assert demote_hollow_mix_done(ctx) is True
    assert not ctx.is_done("mix")
    assert mix_is_seed_complete(ctx) is False


def test_mix_is_seed_complete_false_under_junction_remaster(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="junction")
    mark_done_raw(ctx, "mix")
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)

    assert mix_is_seed_complete(ctx) is False
    assert demote_hollow_mix_done(ctx) is True
    assert not ctx.is_done("mix")


# ---------------------------------------------------------------------------
# 6. mix_epoch_block: junction pending; mix None after speech-first + music
# ---------------------------------------------------------------------------


def test_mix_epoch_block_junction_pending_mix_none_after_speech_first_music(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_speech_first_mix(ctx)
    _write_assembly(ctx)
    _music_complete(monkeypatch)
    _mock_seated_and_present(monkeypatch)

    assert mix_epoch_block(ctx, stage="junction_snip_qa") == (
        "speech_first_remaster_pending"
    )
    assert mix_epoch_block(ctx, stage="mix") is None
    assert remaster_owner(ctx) == "music_epoch"
    assert speech_first_remaster_owed(ctx) is True


# ---------------------------------------------------------------------------
# 7. ensure_speech_first_remaster stamps owner before unpaid land can be paid
# ---------------------------------------------------------------------------


def test_ensure_speech_first_remaster_stamps_owner_before_land_payable(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_speech_first_mix(ctx)
    _music_complete(monkeypatch)
    mark_done_raw(ctx, "mix")
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)

    assert remaster_owner(ctx) == ""
    assert speech_first_remaster_owed(ctx) is True
    # Pre-stamp: unpaid already (speech_first owed) — land not payable.
    assert unpaid_land_reason(ctx, "mix") is not None

    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert remaster_in_flight(ctx) is True
    # Still unpaid after stamp — promote / seed cannot pay without clear_remaster.
    assert unpaid_land_reason(ctx, "mix") is not None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is not None
    assert not ctx.is_done("mix")  # demoted hollow marker
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []
    assert mix_is_seed_complete(ctx) is False


# ---------------------------------------------------------------------------
# 8. begin_remaster(junction) and begin_remaster(music_epoch) both unpaid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("owner", ["junction", "music_epoch"])
def test_begin_remaster_both_owners_unpaid(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch, owner: str
) -> None:
    begin_remaster(ctx, owner=owner)
    _write_assembly(ctx)
    _mock_seated_and_present(monkeypatch)

    assert remaster_owner(ctx) == owner
    assert remaster_in_flight(ctx) is True
    mix_reason = unpaid_land_reason(ctx, "mix")
    jsq_reason = unpaid_land_reason(ctx, "junction_snip_qa")
    assert mix_reason is not None
    assert jsq_reason is not None
    assert "remaster owed" in mix_reason
    assert owner in mix_reason
    assert owner in jsq_reason
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []
