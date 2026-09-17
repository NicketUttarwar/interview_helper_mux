"""End-E: heal / stamp pin discipline (MUX_FORENSICS=0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_invariants import (
    MIN_COMMITTED_MASTER_BYTES,
    committed_master_integrity_ok,
    committed_master_wav,
    parse_seed_order_producer,
    seed_order_heal_action,
)
from interview_mux.stage_completion import (
    PRODUCER_PIN_TABLE,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "ende_pin")


def test_ende_seed_order_parses_named_producer_not_edl(ctx) -> None:
    msg = "seed order: complete junction_snip_qa before running master_finalize"
    assert parse_seed_order_producer(msg) == "junction_snip_qa"
    assert producer_pin_for_token(msg, ctx=ctx) == "junction_snip_qa"
    assert producer_pin_for_token(msg, ctx=ctx) != "edl"
    assert "seed_order" not in PRODUCER_PIN_TABLE

    nav = heal_navigate(ctx, intent="seed_order_prereq", error=msg, stage="master_finalize")
    assert nav["from_stage"] == "junction_snip_qa"
    assert nav["from_stage"] not in {"edl", "mix", "master_finalize"}


def test_ende_bare_seed_order_refuses_sealed_default(ctx) -> None:
    pin = producer_pin_for_token("seed_order_prereq", default="edl", ctx=ctx)
    assert pin == ""


def test_ende_voice_stamp_stage_key_is_vo_synthesize_not_edl() -> None:
    """Driver contract: voice stamp writer is vo_synthesize (source grep fixture)."""
    src = Path(__file__).resolve().parents[1] / "tools" / "full_auto_driver.py"
    text = src.read_text(encoding="utf-8")
    assert 'stage_key="vo_synthesize"' in text
    # The chapter/voice heal block must not claim edl as gap writer.
    idx = text.find("stamped voice_speaker_id=")
    assert idx > 0
    window = text[max(0, idx - 400) : idx]
    assert 'stage_key="edl"' not in window
    assert 'stage_key="vo_synthesize"' in window


def test_ende_hollow_master_refuses_restamp_and_integrity(ctx) -> None:
    pending = (
        ctx.run_dir / ".pending_writes" / "master_finalize" / "master" / "master.wav"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 64)
    assert committed_master_wav(ctx) is False
    assert committed_master_integrity_ok(ctx) is False

    trunc = ctx.final_path("master", "master.wav")
    trunc.parent.mkdir(parents=True, exist_ok=True)
    trunc.write_bytes(b"RIFF" + b"\x00" * 64)
    assert trunc.stat().st_size < MIN_COMMITTED_MASTER_BYTES
    assert committed_master_integrity_ok(ctx) is False

    action, resume = seed_order_heal_action(
        ctx,
        "master_finalize",
        message="seed order: complete master_finalize before running master_transcript_build",
    )
    assert action == "unmark"
    assert resume == "master_finalize"

    reason = stage_artifact_incompleteness(ctx, "master_finalize")
    assert reason is not None
    assert "hollow" in reason or "truncated" in reason


def test_ende_integral_master_may_restamp(ctx) -> None:
    master = ctx.final_path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\x00" * MIN_COMMITTED_MASTER_BYTES)
    assert committed_master_integrity_ok(ctx) is True
    action, resume = seed_order_heal_action(
        ctx,
        "master_finalize",
        message="seed order: complete master_finalize before running master_transcript_build",
    )
    assert action == "restamp"
    assert resume == "master_transcript_build"


def test_ende_empty_pin_driver_contract_source() -> None:
    """Driver _heal_resume must refuse empty pin (no music_palette coalesce)."""
    src = Path(__file__).resolve().parents[1] / "tools" / "full_auto_driver.py"
    text = src.read_text(encoding="utf-8")
    fn = text.split("def _heal_resume", 1)[1].split("\ndef ", 1)[0]
    assert "empty_heal_pin" in fn or "pause_needs_operator" in fn
    assert "refuse_music_palette_coalesce" in fn
    assert 'or stage or "music_palette_compose"' not in fn


def test_ende_heal_pin_for_matches_ownership(ctx) -> None:
    from interview_mux.artifact_ownership import heal_pin_for

    assert heal_pin_for("seed_order_prereq", ctx=ctx) == ""
    assert heal_pin_for("hosted_vo_floor_unmet", ctx=ctx) == "nugget_layup_compose"
    assert heal_pin_for("master/transitions.json", ctx=ctx) == "transitions"
