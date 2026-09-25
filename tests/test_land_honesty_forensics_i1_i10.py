"""Forensics Cluster A (exec_13183): i1 stamp-alone + i10 orphan remaster.

MUX_FORENSICS=0. Unit scenarios only — no real execution folder.
Encodes hollow-done / orphan-promote lies from
``.cursor/plans/full_auto_forensics_cluster_dig_exec_13183.md`` Cluster A.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.artifact_repairs import repair_gap_report
from interview_mux.delivery_guardrails import (
    mix_epoch_block,
    promote_complete_orphan_stage_done,
    seed_stage_complete,
)
from interview_mux.done_authority import (
    land_honest,
    layup_authority_without_plan,
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.mix_junction_seat import (
    begin_remaster,
    clear_remaster,
    ensure_speech_first_remaster,
    note_speech_first_mix,
    remaster_owner,
    speech_first_remaster_owed,
)
from interview_mux.nugget_layup import PLAN_REL
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_raise, stage_artifact_incompleteness
from interview_mux.stages.gaps import _heal_gap_framing_compose_if_complete
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_forensics_i1_i10")


def _enable_layup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )


def _stamp_alone_authority(ctx: RunContext) -> None:
    """i1: nugget_layup_authority without a real layup plan."""
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )


def _write_assembly(ctx: RunContext) -> Path:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    return path


def _mock_mix_presence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )


# ---------------------------------------------------------------------------
# i1 — Orphan layup stamp / authority without plan
# ---------------------------------------------------------------------------


def test_i1_authority_stamp_without_plan_finished_must_not_stick(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """i1: stamp-alone → land_honest false, heal raises, promote blocked."""
    _enable_layup(monkeypatch)
    _stamp_alone_authority(ctx)
    assert not ctx.artifact_exists(PLAN_REL)
    assert layup_authority_without_plan(ctx) is True

    mark_done_raw(ctx, "gap_framing_compose")
    assert ctx.is_done("gap_framing_compose")

    reason = unpaid_land_reason(ctx, "gap_framing_compose")
    assert reason is not None
    assert "stamp-alone" in reason
    assert land_honest(ctx, "gap_framing_compose") is False
    assert seed_stage_complete(ctx, "gap_framing_compose") is False
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is True

    with pytest.raises(RuntimeError):
        heal_or_raise(ctx, "gap_framing_compose")
    assert land_honest(ctx, "gap_framing_compose") is False

    mark_done_raw(ctx, "gap_framing_compose")
    with pytest.raises(RuntimeError):
        _heal_gap_framing_compose_if_complete(ctx)
    assert land_honest(ctx, "gap_framing_compose") is False
    assert seed_stage_complete(ctx, "gap_framing_compose") is False

    promoted = promote_complete_orphan_stage_done(
        ctx, ("gap_framing_compose", "nugget_layup_compose")
    )
    assert "gap_framing_compose" not in promoted
    assert "nugget_layup_compose" not in promoted
    assert not ctx.is_done("nugget_layup_compose")


# ---------------------------------------------------------------------------
# i10 — Music remaster: orphan promote must not hollow-land mix
# ---------------------------------------------------------------------------


def test_i10_orphan_promote_blocked_while_remaster_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """i10: mix under remaster without clear_remaster → promote blocked; junction pending."""
    asm = _write_assembly(ctx)
    old = time.time() - 120
    os.utime(asm, (old, old))

    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    _mock_mix_presence(monkeypatch)

    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert speech_first_remaster_owed(ctx) is True
    assert not ctx.is_done("mix")

    reason = unpaid_land_reason(ctx, "mix")
    assert reason is not None
    assert "remaster owed" in reason
    assert unpaid_land_blocks_promote(ctx, "mix") is True

    promoted = promote_complete_orphan_stage_done(ctx, ("mix",))
    assert promoted == []
    assert not ctx.is_done("mix")

    assert (
        mix_epoch_block(ctx, stage="junction_snip_qa")
        == "speech_first_remaster_pending"
    )
    assert mix_epoch_block(ctx, stage="mix") is None


# ---------------------------------------------------------------------------
# Cheap residuals (same Cluster A class)
# ---------------------------------------------------------------------------


def test_residual_mtime_defeat_does_not_clear_remaster(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assembly newer than remaster stamp must not greenwash unpaid remaster."""
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"

    time.sleep(0.05)
    _write_assembly(ctx)
    _mock_mix_presence(monkeypatch)

    reason = unpaid_land_reason(ctx, "mix")
    assert reason is not None
    assert "remaster owed" in reason
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []
    assert not ctx.is_done("mix")

    clear_remaster(ctx)
    assert unpaid_land_reason(ctx, "mix") is None
    assert mix_epoch_block(ctx, stage="junction_snip_qa") is None


def test_residual_junction_paid_under_junction_remaster_owner(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S6(B): junction remaster owner is paid land for junction; mix stays unpaid.

    Orphan promote of junction still refused via remaster-in-flight incompleteness.
    """
    begin_remaster(ctx, owner="junction")
    _write_assembly(ctx)
    _mock_mix_presence(monkeypatch)
    for rel in ("master/junction_snip_qa.json", "master/seam_autopsy.json"):
        p = ctx.path(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"version":1,"generated_at":"t"}', encoding="utf-8")

    assert unpaid_land_reason(ctx, "mix") is not None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is None
    assert promote_complete_orphan_stage_done(ctx, ("mix", "junction_snip_qa")) == []


def test_residual_speech_first_owed_before_owner_blocks_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-owner speech_first remaster owed still blocks orphan promote."""
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    _write_assembly(ctx)
    _mock_mix_presence(monkeypatch)

    assert remaster_owner(ctx) == ""
    assert speech_first_remaster_owed(ctx) is True
    assert unpaid_land_reason(ctx, "mix") is not None
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []


def test_residual_repair_clears_orphan_layup_authority(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """artifact_repairs clear orphan nugget_layup_authority when plan missing."""
    _enable_layup(monkeypatch)
    assert not ctx.artifact_exists(PLAN_REL)
    out: dict = {"nugget_layup_authority": True, "interviewer_lines": []}
    patched, applied = repair_gap_report(ctx, out)
    assert patched.get("nugget_layup_authority") is False
    assert any(
        a.get("action") == "clear_orphan_nugget_layup_authority" for a in applied
    )
    ctx.write_json("understanding/gap_report.json", patched)
    assert layup_authority_without_plan(ctx) is False
    assert unpaid_land_reason(ctx, "gap_framing_compose") is None


def test_i10_incompleteness_mentions_remaster_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stage_artifact_incompleteness agrees with unpaid_land under music_epoch."""
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    assert ensure_speech_first_remaster(ctx) is True
    _write_assembly(ctx)
    _mock_mix_presence(monkeypatch)

    inc = stage_artifact_incompleteness(ctx, "mix")
    assert inc is not None
    assert "remaster owed" in str(inc)
