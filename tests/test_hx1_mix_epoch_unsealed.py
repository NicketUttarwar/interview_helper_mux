"""HX-1: mix_epoch_block never no-ops while music is incomplete.

Unsealed + unstable returns music_incomplete (never None). mix / junction_snip_qa /
master_finalize honor the token. Heal pins MUSIC_BEFORE_MIX, not mix.
HX-4 mix-lease stays later.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    CHECKPOINT_REL,
    MIX_EPOCH_RUN_BLOCK,
    MUSIC_BEFORE_MIX,
    mix_epoch_block,
    safe_mix_resume_stage,
    stamp_delivery_epoch,
)
from interview_mux.homunculus.runtime import dispatch_stage
from interview_mux.pipeline import run_single_stage
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import producer_pin_for_token
from interview_mux.thrash_hardening import heal_navigate
from interview_mux.v2.config import SHIP_AFTER_MASTER
from run_fixtures import isolated_run_ctx


_CONSUMERS = ("mix", "junction_snip_qa", "master_finalize")


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hx1_mix_epoch")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _quiet_dispatch_except_mix_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.vo_synthesize_stability_block",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.collect_stage_input_issues",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime.check_dispatch",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime.check_audio_serialize",
        lambda *_a, **_k: None,
    )


def test_hx1_run_block_is_todays_three_consumers() -> None:
    assert MIX_EPOCH_RUN_BLOCK == frozenset(_CONSUMERS)
    assert not (MIX_EPOCH_RUN_BLOCK & set(SHIP_AFTER_MASTER))


def test_hx1_unsealed_unstable_is_music_incomplete(ctx: RunContext) -> None:
    from interview_mux.delivery_guardrails import delivery_stable_for_music, phase_a_sealed

    assert phase_a_sealed(ctx) is False
    stable, _reason = delivery_stable_for_music(ctx)
    assert stable is False
    assert mix_epoch_block(ctx) == "music_incomplete"


def test_hx1_sealed_still_music_incomplete_until_music_done(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json(
        CHECKPOINT_REL,
        {"phase": "A_sealed", "order_fingerprint": "abc", "selection_fingerprint": "abc"},
        skip_handoff=True,
    )
    stamp_delivery_epoch(ctx, phase_a_sealed_at="2026-08-31T00:00:00+00:00")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (True, ""),
    )
    assert mix_epoch_block(ctx) == "music_incomplete"


def test_hx1_music_complete_still_none(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json(
        CHECKPOINT_REL,
        {"phase": "A_sealed", "order_fingerprint": "abc", "selection_fingerprint": "abc"},
        skip_handoff=True,
    )
    stamp_delivery_epoch(
        ctx,
        phase_a_sealed_at="2026-08-31T00:00:00+00:00",
        music_complete_at="2026-08-31T01:00:00+00:00",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (True, ""),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: True,
    )
    assert mix_epoch_block(ctx) is None


def test_hx1_dispatch_blocks_mix_junction_finalize(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_dispatch_except_mix_epoch(monkeypatch)
    ran: list[str] = []

    def _impl(stage: str) -> None:
        ran.append(stage)

    for sid in _CONSUMERS:
        ran.clear()
        with pytest.raises(RuntimeError, match=r"delivery epoch music_incomplete"):
            dispatch_stage(ctx, sid, _impl)
        assert ran == []


def test_hx1_pipeline_blocks_mix_junction_finalize(ctx: RunContext) -> None:
    for sid in _CONSUMERS:
        with pytest.raises(ValueError, match=r"delivery epoch music_incomplete"):
            run_single_stage(ctx, sid)


def test_hx1_heal_pins_music_producer_not_mix(ctx: RunContext) -> None:
    err = "cannot run mix: delivery epoch music_incomplete (wait for mmaudio_sfx)"
    pin = producer_pin_for_token(err, ctx=ctx)
    assert pin in MUSIC_BEFORE_MIX
    assert pin != "mix"
    nav = heal_navigate(ctx, error=err, stage="mix")
    assert nav["from_stage"] in MUSIC_BEFORE_MIX
    assert nav["from_stage"] != "mix"


def test_hx1_safe_mix_resume_is_music_before_mix(ctx: RunContext) -> None:
    resume = safe_mix_resume_stage(ctx)
    assert resume in MUSIC_BEFORE_MIX
    assert resume != "mix"
    assert mix_epoch_block(ctx)
