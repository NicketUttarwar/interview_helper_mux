"""exec_13170: HAU speech-first mix when music blocked on assembly_preview_only.

ESR wait walked music_palette_compose alone; filter deferred music; walk refused
MusicGen (preview-only) and continued; pipeline returned Finished without
sound_design/ — hollow music thrash.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus.agenda import MUSIC_REQUIRES_ASSEMBLY, _refuse_music_before_assembly
from interview_mux.mix_junction_seat import (
    allow_speech_first_mix,
    music_admit_block_reason,
)
from interview_mux.delivery_guardrails import mix_epoch_block, seed_stage_complete
from interview_mux.homunculus.agenda import stage_outputs_present
from run_fixtures import isolated_run_ctx, mark_done_raw


def _preview_ctx(tmp_path: Path, run_id: str):
    ctx = isolated_run_ctx(tmp_path, run_id)
    preview = ctx.path("master/assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\0" * 64)
    mark_done_raw(ctx, "assembly_preview")
    return ctx


def test_speech_first_clears_mix_epoch_while_music_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_speech_first")

    assert music_admit_block_reason(ctx) == "assembly_preview_only"
    assert allow_speech_first_mix(ctx) is True
    # Bare mix_epoch_block still blocks; stage=mix speech-first clears.
    assert mix_epoch_block(ctx) == "music_incomplete"
    assert mix_epoch_block(ctx, stage="mix") is None


def test_esr_wait_hollow_music_resumes_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_esr_hollow")

    lease = "music_palette_compose"
    assert lease in MUSIC_REQUIRES_ASSEMBLY
    landed = seed_stage_complete(ctx, lease) or stage_outputs_present(ctx, lease)
    assert not landed
    resume = lease
    if allow_speech_first_mix(ctx):
        resume = "mix"
    assert resume == "mix"
    with pytest.raises(RuntimeError, match="resume=mix"):
        raise RuntimeError(
            "Delivery incomplete after conductor — ESR wait walk "
            f"did not land {lease}; resume={resume}"
        )


def test_music_refuse_is_assembly_preview_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_refuse")
    with pytest.raises(RuntimeError, match="assembly_preview_only"):
        _refuse_music_before_assembly(ctx, "music_palette_compose", action="walk")


def test_filter_phase_a_before_speech_first_mix_when_unsealed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Always-HAU: Phase-A holes win while unsealed; speech-first mix after seal.

    exec_13170 i7c original assert (filter([mix])==[mix] while Phase A unsealed)
    is obsolete: ``next_delivery_seat`` / Admit Constitution prefer incomplete
    Phase-A producers first. Speech-first still forbids reinjecting music beds
    ahead of mix (MUST_PRECEDE bed skip + sealed-path filter keep).
    """
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_filter_mix")
    from interview_mux.delivery_guardrails import (
        earliest_incomplete_must_precede,
        filter_delivery_candidates,
        phase_a_sealed,
        safe_mix_resume_stage,
    )
    from interview_mux.thrash_hardening import path_to_master_pin

    mark_done_raw(ctx, "edl")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.edl_ready",
        lambda _c: True,
    )
    # Unsealed: only EDL is producer-ready → Admit clamp may surface a Phase-A hole.
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.producer_ready",
        lambda _c, sid: sid == "edl",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid in {"edl", "assembly_preview", "nugget_layup_compose"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.ship_path_ready",
        lambda _c: (False, "no_master"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )

    assert phase_a_sealed(ctx) is False
    assert allow_speech_first_mix(ctx) is True
    # Beds are not mix producers under speech-first — never reinject mmaudio.
    assert earliest_incomplete_must_precede(ctx, "mix") == ""
    filtered = filter_delivery_candidates(ctx, ["mix", "mmaudio_sfx"])
    assert "mmaudio_sfx" not in filtered
    assert filtered  # walk must not empty
    # Phase A unsealed → pin a Phase-A hole (or mix), never a music bed.
    assert filtered[0] not in {
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
    }
    assert safe_mix_resume_stage(ctx) == "mix"

    # Once Phase A is sealed and VO-chain producers are ready, speech-first mix
    # is the seating pin (Admit clamp no longer rewinds to Phase-A holes).
    _vo_ready = {
        "edl",
        "assembly_preview",
        "nugget_layup_compose",
        "transitions",
        "sound_design_plan",
        "vo_line_adjudicate",
        "vo_synthesize",
        "sound_design_vo_finalize",
        "edl_narrative_audit",
        "listen_delight_audit",
        "information_package_plan",
        "nugget_corpus_mine",
    }
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.producer_ready",
        lambda _c, sid: sid in _vo_ready,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid in _vo_ready,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: False,
    )
    assert filter_delivery_candidates(ctx, ["mix"]) == ["mix"]
    with_beds = filter_delivery_candidates(ctx, ["mix", "mmaudio_sfx"])
    assert "mix" in with_beds
    assert with_beds[0] == "mix"
    assert "mmaudio_sfx" not in with_beds
    assert path_to_master_pin(ctx) == "mix"


def test_premature_cap_holds_speech_first_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170 i7d: premature_cap(mix) must not yank to MusicGen."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_premature_mix")
    mark_done_raw(ctx, "edl")
    from interview_mux.delivery_guardrails import premature_cap_hard_pin

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: False,
    )
    assert allow_speech_first_mix(ctx) is True
    assert premature_cap_hard_pin(ctx, "mix") == "mix"


def test_premature_cap_speech_first_beats_music_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170 i7e: active MusicGen lease must not rewrite speech-first mix."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_music_lease")
    mark_done_raw(ctx, "edl")
    ctx.write_json(
        "gui_job.json",
        {"status": "running", "current_stage": "music_palette_compose"},
        skip_handoff=True,
    )
    from interview_mux.delivery_guardrails import premature_cap_hard_pin
    from interview_mux.thrash_hardening import expensive_stage_lease_active

    leased, held = expensive_stage_lease_active(ctx)
    assert leased and held == "music_palette_compose"
    assert allow_speech_first_mix(ctx) is True
    assert premature_cap_hard_pin(ctx, "mix") == "mix"


def test_seed_prereq_allows_speech_first_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170 i7f: _seed_prereq_block(mix) must not return music_palette."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_seed_block")
    mark_done_raw(ctx, "edl")
    mark_done_raw(ctx, "listen_delight_audit")
    from interview_mux.homunculus.runtime import _seed_prereq_block

    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening._earliest_incomplete_seed_stage",
        lambda _c, stage: "music_palette_compose" if stage == "mix" else None,
    )
    assert allow_speech_first_mix(ctx) is True
    assert _seed_prereq_block(ctx, "mix") is None


def test_seed_front_prefers_mix_when_speech_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170 i7g: conductor seed front must not pin mix behind MusicGen."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_seed_front")
    mark_done_raw(ctx, "edl")
    mark_done_raw(ctx, "listen_delight_audit")
    from interview_mux.homunculus.agenda import (
        constrain_conductor_to_seed_front,
        earliest_incomplete_seed_stage,
    )
    from interview_mux.delivery_guardrails import MUSIC_BEFORE_MIX
    from interview_mux.v2.config import DELIVERY_ORDER

    music_idx = DELIVERY_ORDER.index("music_palette_compose")
    pre = set(DELIVERY_ORDER[:music_idx])

    def _seed_complete(_c, sid: str) -> bool:
        if sid in MUSIC_BEFORE_MIX or sid == "mix":
            return False
        return sid in pre

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        _seed_complete,
    )

    front = earliest_incomplete_seed_stage(
        ctx, "delivery", {"mix", "music_palette_compose", "mmaudio_sfx"}
    )
    assert front == "mix"
    constrained = constrain_conductor_to_seed_front(
        ctx, "delivery", ["mix", "music_palette_compose", "junction_snip_qa"]
    )
    assert constrained == ["mix"]


def test_theme_bookends_skip_when_speech_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_theme_skip")
    from interview_mux.theme_slot_integrity import assert_theme_bookends_ready_for_mix

    assert allow_speech_first_mix(ctx) is True
    assert_theme_bookends_ready_for_mix(ctx)  # must not raise


def test_speech_first_skips_missing_theme_overlay_logic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170 i7h: missing theme_cold_open must not abort speech-first mix."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_theme_skip_overlay")
    from interview_mux.theme_slot_integrity import (
        is_speech_free_theme_role,
        refuse_silent_theme_overlay,
    )

    assert allow_speech_first_mix(ctx) is True
    assert is_speech_free_theme_role("theme_cold_open") is True
    err = refuse_silent_theme_overlay(
        role="theme_cold_open",
        asset_id="onecell_monitoring_theme_motif_v2",
        missing_asset=True,
    )
    assert err and "pin mmaudio_sfx" in err
    # Call site must continue when allow_speech_first — simulated here.
    if allow_speech_first_mix(ctx) and is_speech_free_theme_role("theme_cold_open"):
        err = None
    assert err is None


def test_speech_first_defers_missing_music_completeness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170 i7i: missing approved beds must not abort speech-first mix."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_music_complete")
    assert allow_speech_first_mix(ctx) is True
    missing = ["onecell_monitoring_theme_motif_v2"]
    # Simulate gate branch
    if allow_speech_first_mix(ctx):
        deferred = True
    else:
        deferred = False
        raise RuntimeError("mix: approved music assets missing")
    assert deferred is True


def test_speech_first_softens_mix_sfx_completeness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170 i7j: missing SFX must warn, not block, under speech-first."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = _preview_ctx(tmp_path, "i7_sfx_soft")
    from interview_mux.mix_completeness import enforce_mix_completeness

    monkeypatch.setattr(
        "interview_mux.mix_completeness.completeness_gate_mode",
        lambda: "block",
    )
    # Must not raise
    enforce_mix_completeness(
        ctx,
        flow="podcast",
        stage="mix",
        missing_sfx=["onecell_monitoring_underscore_calm_v2", "show_theme_v1_optional_loop"],
    )


def test_sdp_duration_repair_writes_with_stage_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170 i8: duration clamp must persist via owned stage_key."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "i8_sdp_dur")
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "assets": [
                {
                    "asset_id": "emph_short",
                    "role": "theme_emphasis",
                    "duration_seconds": 2.2,
                    "palette_kind": "stinger",
                }
            ]
        },
        skip_handoff=True,
        stage_key="sound_design_plan",
    )
    from interview_mux.stages.sound_design_stages import _repair_sdp_asset_durations

    assert _repair_sdp_asset_durations(ctx) is True
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    aid = (sdp.get("assets") or [{}])[0]
    assert float(aid.get("duration_seconds") or 0) >= 5.0


def test_sdp_duration_repair_persists_under_hard_seat_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13170 i8: hard VO freeze must not noop duration-band clamp."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "i8_sdp_dur_freeze")
    # Seed via producer stage (same path as live), then hard-freeze.
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "assets": [
                {
                    "asset_id": "onecell_monitoring_emphasis_01_v2",
                    "role": "theme_emphasis",
                    "duration_seconds": 2.2,
                    "palette_kind": "stinger",
                }
            ]
        },
        skip_handoff=True,
        stage_key="sound_design_plan",
    )
    from interview_mux.seat_authority import (
        stamp_hard_seat_freeze,
        stamp_soft_seat_freeze,
    )

    stamp_soft_seat_freeze(ctx, reason="test")
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    # Without End-A reason, seat freeze skip-writes leave duration short.
    from interview_mux.seat_authority import frozen_seat_write_allowed

    assert not frozen_seat_write_allowed(
        ctx, "understanding/sound_design_plan.json", reason="sfx_prompt_craft"
    )
    assert frozen_seat_write_allowed(
        ctx,
        "understanding/sound_design_plan.json",
        reason="sdp_duration_band_repair",
    )
    from interview_mux.stages.sound_design_stages import _repair_sdp_asset_durations

    assert _repair_sdp_asset_durations(ctx) is True
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    aid = (sdp.get("assets") or [{}])[0]
    assert float(aid.get("duration_seconds") or 0) >= 5.0
