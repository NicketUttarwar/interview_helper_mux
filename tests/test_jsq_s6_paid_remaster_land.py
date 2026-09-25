"""junction_snip_qa S6(B): junction-owned remaster is paid land."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.done_authority import unpaid_land_reason
from interview_mux.mix_junction_seat import begin_remaster, clear_remaster, remaster_owner
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "jsq_s6b")


def test_s6b_junction_owner_paid_mix_unpaid(ctx) -> None:
    begin_remaster(ctx, owner="junction")
    assert remaster_owner(ctx) == "junction"
    assert unpaid_land_reason(ctx, "junction_snip_qa") is None
    assert unpaid_land_reason(ctx, "mix") is not None
    # Mid-flight still incomplete (hollow promote refuse) without unpaid taxonomy.
    reason = stage_artifact_incompleteness(ctx, "junction_snip_qa")
    assert reason is not None
    assert "remaster in flight" in reason
    assert "paid land" in reason
    clear_remaster(ctx)
    assert unpaid_land_reason(ctx, "mix") is None


def test_s6b_music_epoch_still_unpaid_both(ctx) -> None:
    begin_remaster(ctx, owner="music_epoch")
    assert unpaid_land_reason(ctx, "mix") is not None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is not None
