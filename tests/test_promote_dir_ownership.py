"""Directory promotes must consult ownership per child (MUX_FORENSICS=0).

`promote_staged_side_effects` gated ownership on the file branch only, so a
DENY row on a directory artifact was documented and never imposed. These tests
pin the per-child verdict, the armed `master/transitions/` ratchet, and owner
vs glue vs foreign stages.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    PROMOTE_DIR_STRICT_PREFIXES,
    clear_dir_promote_refusals,
    observed_dir_promote_refusals,
    promote_dir_refusal_is_fatal,
    promote_dir_strict_prefixes,
    promote_owner_vo_pickup,
    promote_staged_side_effects,
)
from run_fixtures import init_run_meta_for_test, isolated_run_ctx

TRANSITION_WAV = "master/transitions/tr_seg_055_seg_058.wav"
FOREIGN_STAGE = "podcast_publish"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled", lambda: False
    )
    clear_dir_promote_refusals()
    run = isolated_run_ctx(tmp_path, "promote_dir_ownership")
    init_run_meta_for_test(run)
    yield run
    clear_dir_promote_refusals()


def _plant_staged_transition(ctx: RunContext, stage_id: str) -> Path:
    staged = ctx.run_dir / ".pending_writes" / stage_id / "master" / "transitions"
    staged.mkdir(parents=True, exist_ok=True)
    wav = staged / Path(TRANSITION_WAV).name
    wav.write_bytes(b"RIFF" + b"\x00" * 2048 + b"TRANSITION_BYTES")
    return wav


def test_ratchet_includes_transitions_by_default() -> None:
    assert PROMOTE_DIR_STRICT_PREFIXES == ("master/transitions/",)
    assert promote_dir_strict_prefixes() == ("master/transitions/",)
    assert promote_dir_refusal_is_fatal("master/transitions/") is True
    assert promote_dir_refusal_is_fatal("master/edl.json") is False


def test_strict_prefixes_come_from_the_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MUX_PROMOTE_DIR_STRICT_PREFIXES", " master/transitions/ , vo_pickup/ "
    )
    assert promote_dir_strict_prefixes() == ("master/transitions/", "vo_pickup/")
    assert promote_dir_refusal_is_fatal("master/transitions/") is True
    assert promote_dir_refusal_is_fatal("master/edl.json") is False


def test_empty_env_override_disarms_the_ratchet(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_PROMOTE_DIR_STRICT_PREFIXES", "")
    staged = _plant_staged_transition(ctx, FOREIGN_STAGE)

    flushed = promote_staged_side_effects(
        ctx, ("master/transitions/",), stage_id=FOREIGN_STAGE
    )

    assert TRANSITION_WAV in flushed
    assert ctx.final_path(*TRANSITION_WAV.split("/")).is_file()
    assert staged.is_file()
    refusals = observed_dir_promote_refusals()
    assert [r["child"] for r in refusals] == [TRANSITION_WAV]
    assert refusals[0]["fatal"] is False


def test_foreign_dir_promote_is_refused_by_default(ctx: RunContext) -> None:
    staged = _plant_staged_transition(ctx, FOREIGN_STAGE)

    flushed = promote_staged_side_effects(
        ctx, ("master/transitions/",), stage_id=FOREIGN_STAGE
    )

    assert flushed == []
    assert not ctx.final_path(*TRANSITION_WAV.split("/")).is_file()
    assert not staged.is_file()
    assert observed_dir_promote_refusals()[0]["fatal"] is True
    assert observed_dir_promote_refusals()[0]["stage_id"] == FOREIGN_STAGE


def test_glue_stage_promote_is_allowed(ctx: RunContext) -> None:
    """`edl_narrative_audit` is not a WAV producer; it has a promote_pending ALLOW."""
    _plant_staged_transition(ctx, "edl_narrative_audit")

    flushed = promote_staged_side_effects(
        ctx, ("master/transitions/",), stage_id="edl_narrative_audit"
    )

    assert TRANSITION_WAV in flushed
    assert ctx.final_path(*TRANSITION_WAV.split("/")).is_file()
    assert observed_dir_promote_refusals() == []


def test_owner_promote_succeeds(ctx: RunContext) -> None:
    _plant_staged_transition(ctx, "vo_synthesize")

    flushed = promote_staged_side_effects(
        ctx, ("master/transitions/",), stage_id="vo_synthesize"
    )

    assert TRANSITION_WAV in flushed
    assert ctx.final_path(*TRANSITION_WAV.split("/")).is_file()
    assert observed_dir_promote_refusals() == []


def test_vo_pickup_owner_guard_is_preserved(ctx: RunContext) -> None:
    rel = "vo_pickup/synthesized/vo_layup_seg_020.wav"
    staged = ctx.run_dir / ".pending_writes" / "vo_synthesize" / Path(rel).parent
    staged.mkdir(parents=True, exist_ok=True)
    (staged / Path(rel).name).write_bytes(b"RIFF" + b"\x00" * 2048 + b"TAKE")

    assert promote_owner_vo_pickup(ctx) == [rel]
    assert ctx.final_path(*rel.split("/")).is_file()
    # The owner is in the catalog, so nothing is reported for it.
    assert observed_dir_promote_refusals() == []


def test_non_owner_vo_pickup_guard_short_circuits_before_ownership(
    ctx: RunContext,
) -> None:
    """The `vo_pickup` guard still wins, and does not masquerade as a refusal."""
    rel = "vo_pickup/synthesized/vo_layup_seg_020.wav"
    staged = ctx.run_dir / ".pending_writes" / "edl" / Path(rel).parent
    staged.mkdir(parents=True, exist_ok=True)
    (staged / Path(rel).name).write_bytes(b"RIFF" + b"\x00" * 2048 + b"TAKE")

    assert promote_staged_side_effects(ctx, ("vo_pickup/",), stage_id="edl") == []
    assert not ctx.final_path(*rel.split("/")).is_file()
    assert observed_dir_promote_refusals() == []


def test_edl_staged_transitions_still_flush_on_stage_commit(ctx: RunContext) -> None:
    """`run_edl` renders transition WAVs into its own staging tree.

    `edl` declares `master/transitions/` in its StageInfo, so those WAVs reach
    the committed tree through `flush_stage_writes`, which this change does not
    touch. The promote gate must not be mistaken for the only path in.
    """
    from interview_mux.write_staging import flush_stage_writes

    _plant_staged_transition(ctx, "edl")

    assert TRANSITION_WAV in flush_stage_writes(ctx, "edl")
    assert ctx.final_path(*TRANSITION_WAV.split("/")).is_file()
