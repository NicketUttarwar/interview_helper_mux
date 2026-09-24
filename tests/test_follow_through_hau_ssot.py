"""Always-HAU follow-through: next_delivery_seat SSOT + soft-gate / lease / End-A.

MUX_FORENSICS=0 cascades for exec_13170 incomplete follow-through (i4–i8).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    MUST_PRECEDE,
    MUSIC_BEFORE_MIX,
    MUSIC_REQUIRES_ASSEMBLY,
    apply_premature_cap_for_execute,
    premature_cap_hard_pin,
    safe_mix_resume_stage,
)
from interview_mux.delivery_recovery import (
    MUSIC_BEFORE_MIX as RECOVERY_MUSIC_BEFORE_MIX,
    resume_theme_generation,
    suggest_delivery_resume,
)
from interview_mux.homunculus.agenda import MUSIC_REQUIRES_ASSEMBLY as AGENDA_MUSIC
from interview_mux.mix_junction_seat import (
    beds_deferred_for_mix,
    next_delivery_seat,
    note_speech_first_mix,
)
from interview_mux.thrash_hardening import (
    FAIL_CLASS_MUSIC_EPOCH,
    canonical_resume_pin,
    expensive_stage_lease_active,
    note_sticky_heal_attempt,
    remutate_resume_allowed,
    sticky_pin_is_sealed,
)
from run_fixtures import isolated_run_ctx, mark_done_raw


def _preview_ctx(tmp_path: Path, run_id: str):
    ctx = isolated_run_ctx(tmp_path, run_id)
    preview = ctx.path("master/assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\0" * 64)
    mark_done_raw(ctx, "assembly_preview")
    mark_done_raw(ctx, "edl")
    return ctx


def _phase_a_sealed_speech_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase A sealed + music incomplete so SSOT reaches speech-first mix."""
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid
        not in {
            "music_palette_compose",
            "sfx_prompt_craft",
            "mmaudio_sfx",
            "mix",
            "junction_snip_qa",
            "master_finalize",
        },
    )


def test_dual_music_sets_are_aliases() -> None:
    assert frozenset(RECOVERY_MUSIC_BEFORE_MIX) == MUSIC_REQUIRES_ASSEMBLY
    assert frozenset(MUSIC_BEFORE_MIX) == MUSIC_REQUIRES_ASSEMBLY
    assert AGENDA_MUSIC == MUSIC_REQUIRES_ASSEMBLY


def test_must_precede_mix_has_no_beds() -> None:
    assert MUST_PRECEDE["mix"] == ("edl",)
    assert "mmaudio_sfx" not in MUST_PRECEDE["mix"]
    assert "music_palette_compose" not in MUST_PRECEDE["mix"]


def test_next_delivery_seat_speech_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "ft_ssot_sf")
    _phase_a_sealed_speech_first(monkeypatch)
    assert next_delivery_seat(ctx) == "mix"
    assert resume_theme_generation(ctx) == "mix"
    assert suggest_delivery_resume(ctx) == "mix"
    assert canonical_resume_pin(ctx, FAIL_CLASS_MUSIC_EPOCH) == "mix"
    assert safe_mix_resume_stage(ctx) == "mix"


def test_beds_deferred_after_speech_first_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "ft_beds_def")
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: False,
    )
    assert beds_deferred_for_mix(ctx) is True


def test_f1_music_complete_stamp_not_speech_first_forever(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "ft_f1")
    note_speech_first_mix(ctx)
    for sid in MUSIC_BEFORE_MIX:
        mark_done_raw(ctx, sid)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid != "mix",
    )
    pin = next_delivery_seat(ctx)
    assert pin in {"mix", "junction_snip_qa", "master_finalize"}


def test_sticky_seal_clears_at_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "ft_sticky")
    mark_done_raw(ctx, "vo_synthesize")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid == "vo_synthesize",
    )
    assert sticky_pin_is_sealed(ctx, "vo_synthesize") is True
    out = note_sticky_heal_attempt(
        ctx, kind="incomplete_after_conductor", pin="vo_synthesize"
    )
    assert out.get("cleared_sealed") is True
    assert out.get("halt") is False


def test_hollow_done_does_not_seal_sticky(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "ft_hollow_sticky")
    mark_done_raw(ctx, "mix")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: False,
    )
    assert sticky_pin_is_sealed(ctx, "mix") is False


def test_lease_sealed_music_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "ft_lease")
    mark_done_raw(ctx, "music_palette_compose")
    pending = ctx.run_dir / ".pending_writes" / "music_palette_compose"
    pending.mkdir(parents=True)
    (pending / "stub.txt").write_text("x", encoding="utf-8")
    ctx.write_json(
        "gui_job.json",
        {"status": "running", "current_stage": "music_palette_compose"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid == "music_palette_compose",
    )
    leased, stage = expensive_stage_lease_active(ctx)
    assert leased is False
    assert stage == ""


def test_premature_cap_helper_automation_vs_gui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "ft_cap")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.premature_cap_hard_pin",
        lambda _c, resume, message="": "edl",
    )
    auto = apply_premature_cap_for_execute(ctx, "mix", automation=True)
    assert auto["ok"] is True
    assert auto["rewritten"] is True
    assert auto["from_stage"] == "edl"
    gui = apply_premature_cap_for_execute(ctx, "mix", automation=False)
    assert gui["ok"] is False
    assert gui["pinned_to"] == "edl"


def test_premature_cap_speech_first_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "ft_cap_sf")
    assert premature_cap_hard_pin(ctx, "mix") == "mix"


def test_remutate_blocked_when_g1_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "ft_remutate")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: True,
    )
    assert remutate_resume_allowed(ctx) is False


def test_resolve_premature_cap_pin_f7(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "ft_resolve_cap")
    from interview_mux.delivery_guardrails import resolve_premature_cap_pin

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.premature_cap_hard_pin",
        lambda _c, resume, message="": "vo_synthesize",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid == "vo_synthesize",
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.next_delivery_seat",
        lambda _c: "edl",
    )
    assert resolve_premature_cap_pin(ctx, "mix") == "edl"


def test_remutate_playbook_skips_apply_when_g1_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "ft_remutate_skip")
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.remutate_resume_allowed",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_invariants.resolve_g1_vo_open_resume",
        lambda _c: "vo_synthesize",
    )
    applied = {"called": False}

    def _boom(*_a, **_k):
        applied["called"] = True
        raise AssertionError("apply must not run while G1 open")

    monkeypatch.setattr(
        "interview_mux.listen_delight_remutate.apply_listen_delight_remutate",
        _boom,
    )
    monkeypatch.setattr(
        "interview_mux.listen_delight.evaluate_listen_delight",
        lambda _c: {"failed_dimensions": ["x"]},
    )
    from interview_mux.recovery_controller import playbook_listen_delight_remutate

    out = playbook_listen_delight_remutate(ctx)
    assert out == ["vo_synthesize"]
    assert applied["called"] is False
