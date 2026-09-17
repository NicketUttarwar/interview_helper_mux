"""R4 residual closures (#21/#22) under MUX_FORENSICS=0.

soft_pass refuse + brief · phase_a_edl VO carve-out · music disk progress
blocks sticky HARD · empty heal pin never coalesces to music_palette.
HX-1 / HX-4 remain importable cousins.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from interview_mux.artifact_ownership import heal_pin_for
from interview_mux.delivery_guardrails import MUSIC_BEFORE_MIX, premature_cap_hard_pin
from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import (
    FAIL_CLASS_PHASE_A_EDL,
    FAIL_CLASS_VO_G1,
    STICKY_HEAL_HALT_AFTER,
    fail_class_for_failure,
    note_sticky_heal_attempt,
    stage_predicate_token,
)
from run_fixtures import isolated_run_ctx

_ROOT = Path(__file__).resolve().parents[1]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import full_auto_driver as driver  # noqa: E402

_MARK_STAGES = (
    "nugget_corpus_mine",
    "information_package_plan",
    "nugget_layup_compose",
    "refinement_agenda",
    "gap_framing_recompose",
    "selection_framing_apply",
    "transitions",
    "sound_design_plan",
    "sound_design_vo_finalize",
    "edl_narrative_audit",
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("INTERVIEW_MUX_E2E_LAST_RESORT_SOFT", raising=False)
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    run = isolated_run_ctx(tmp_path, "r4_premature")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    run.path("master").mkdir(parents=True, exist_ok=True)
    run.path("understanding").mkdir(parents=True, exist_ok=True)
    return run


def test_r4a_soft_pass_refuses_writes_brief_no_marks(ctx: RunContext) -> None:
    """#22: soft_pass_pre_edl_delivery → [] + e2e brief; no stage_done."""
    notes = driver.soft_pass_pre_edl_delivery(ctx)
    assert notes == []
    brief_path = Path(ctx.run_dir) / "e2e_failure_brief.json"
    assert brief_path.is_file()
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    assert brief.get("suggested_fix_class") == "e2e_stub"
    assert "LAST_RESORT" in str(brief.get("error") or "")
    for sid in _MARK_STAGES:
        assert not ctx.is_done(sid), f"stage marked done: {sid}"


def test_r4b_gap_vo_bind_never_phase_a_edl() -> None:
    """#22/#16 cousin: gap VO / bind classify vo_g1, never phase_a_edl."""
    reasons = (
        "edl: gap VO lines missing WAV: ['vo_layup_seg_005']",
        "vo_unsanitary — resume vo_synthesize: seated_bind_stale:vo_layup_seg_012",
        "g1_missing",
        "vo_seated_coverage incomplete",
    )
    for reason in reasons:
        cls = fail_class_for_failure(stage="edl", reason=reason)
        assert cls == FAIL_CLASS_VO_G1, reason
        assert cls != FAIL_CLASS_PHASE_A_EDL, reason


def test_r4c_music_disk_progress_blocks_sticky_hard(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#21: disk progress keeps sticky halt False; pin stays MUSIC_BEFORE_MIX."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    assets = ctx.final_path("sound_design", "assets")
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "bed_a.wav").write_bytes(b"RIFF" + b"\x00" * 96)

    ctx.write_json(
        "gui_job.json",
        {"status": "running", "current_stage": "mix"},
        skip_handoff=True,
    )
    pin = premature_cap_hard_pin(ctx, "mix")
    assert pin in MUSIC_BEFORE_MIX
    assert pin != "mix"

    tok = stage_predicate_token(ctx, pin)
    assert "sfx=" in tok
    last = None
    for _ in range(STICKY_HEAL_HALT_AFTER + 2):
        last = note_sticky_heal_attempt(
            ctx,
            kind="premature",
            pin=pin,
            intent="music_epoch",
            predicate_token=tok,
        )
    assert last is not None
    # Fresh disk / ESR progress must not escalate to HARD halt.
    assert last.get("halt") is False
    assert last.get("progress_stale") is False or last.get("progress_why") == "esr_fresh"

    # Disk growth flips predicate and resets count.
    (assets / "bed_b.wav").write_bytes(b"RIFF" + b"\x00" * 128)
    tok2 = stage_predicate_token(ctx, pin)
    assert tok2 != tok
    flipped = note_sticky_heal_attempt(
        ctx,
        kind="premature",
        pin=pin,
        intent="music_epoch",
        predicate_token=tok2,
    )
    assert flipped.get("halt") is False
    assert int(flipped.get("count") or 0) == 1
    assert premature_cap_hard_pin(ctx, "junction_snip_qa") in MUSIC_BEFORE_MIX


def test_r4d_empty_heal_pin_never_coalesces_to_music(ctx: RunContext) -> None:
    """#21: empty ownership pin stays empty; driver refuses music_palette coalesce."""
    assert heal_pin_for("", ctx=ctx) == ""
    assert heal_pin_for("seed_order_prereq", ctx=ctx) == ""
    assert heal_pin_for("unknown_token_xyz", ctx=ctx) == ""

    src = _ROOT / "tools" / "full_auto_driver.py"
    text = src.read_text(encoding="utf-8")
    fn = text.split("def _heal_resume", 1)[1].split("\ndef ", 1)[0]
    assert "empty_heal_pin" in fn or "pause_needs_operator" in fn
    assert "refuse_music_palette_coalesce" in fn
    assert 'or stage or "music_palette_compose"' not in fn
    # Phase A incomplete gate must appear before music execute.
    assert "music_palette_compose" in fn
    assert "incomplete=" in fn


def test_r4_hx1_hx4_cousins_importable() -> None:
    """HX-1 / HX-4 stay loadable cousins for music-epoch premature pins."""
    import test_hx1_mix_epoch_unsealed as hx1
    import test_hx4_mix_lease_pin as hx4

    assert callable(hx1.test_hx1_unsealed_unstable_is_music_incomplete)
    assert callable(hx4.test_hx4_running_mix_lease_pins_music_not_mix)
    assert hx4._MIX_LEASE == ("mix", "junction_snip_qa", "master_finalize")
