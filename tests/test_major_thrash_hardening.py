"""Major thrash hardening — Waves 0–11 (post-exec_10066)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


def _touch_wav(ctx: RunContext, *parts: str, size: int = 2048) -> Path:
    path = ctx.final_path(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * (size - 4))
    return path

def _write_raw(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_committed_master_ignores_pending(tmp_path: Path) -> None:
    from interview_mux.delivery_invariants import committed_master_wav

    ctx = isolated_run_ctx(tmp_path, "inv_pending")
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "master_finalize"
        / "master"
        / "master.wav"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 2048)
    assert committed_master_wav(ctx) is False
    _touch_wav(ctx, "master", "master.wav")
    assert committed_master_wav(ctx) is True


def test_active_remutate_stages_unions_edl_narrative(tmp_path: Path) -> None:
    from interview_mux.delivery_invariants import active_remutate_stages

    ctx = isolated_run_ctx(tmp_path, "inv_rem")
    _write_raw(ctx, 
        "mastering/listen_delight_remutate.json",
        {
            "attempt": 1,
            "max_attempts": 3,
            "from_stages": ["air_script_seams", "transitions"],
            "exhausted": False,
        },
    )
    _write_raw(ctx, 
        "mastering/edl_narrative_remutate.json",
        {
            "attempt": 1,
            "max_attempts": 3,
            "from_stages": ["edl", "edl_narrative_audit"],
            "exhausted": False,
        },
    )
    stages = active_remutate_stages(ctx)
    assert "air_script_seams" in stages
    assert "edl" in stages


def test_seed_cycle_detect_and_ledger(tmp_path: Path) -> None:
    from interview_mux.delivery_invariants import (
        detect_seed_cycle,
        invariant_fire_summary,
        note_seed_resume,
    )

    ctx = isolated_run_ctx(tmp_path, "inv_cycle")
    fp = "abc"
    for stage in ["a", "b", "a", "b", "a", "b"]:
        note_seed_resume(ctx, from_stage=stage, because_of="other", fingerprint=fp)
    assert detect_seed_cycle(ctx, from_stage="a", because_of="b", fingerprint=fp)
    summary = invariant_fire_summary(ctx)
    assert summary.get("seed_cycle_detected", 0) >= 1


def test_resolve_g1_synth_only_pins_synthesize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_invariants import resolve_g1_vo_open_resume

    ctx = isolated_run_ctx(tmp_path, "inv_g1")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_record_open",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.gates.check_g1_vo",
        lambda _ctx: ["vo_layup_x"],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid == "vo_line_adjudicate",
    )
    assert resolve_g1_vo_open_resume(ctx) == "vo_synthesize"


def test_seed_order_restamp_live_sdp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_invariants import seed_order_heal_action

    ctx = isolated_run_ctx(tmp_path, "inv_sdp")
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.delivery_sdp_present",
        lambda _ctx: True,
    )
    action, resume = seed_order_heal_action(
        ctx,
        "sound_design_plan",
        message="complete sound_design_plan before running mix",
    )
    assert action == "restamp"
    assert resume in {"mix", "music_palette_compose"}


def test_seed_order_music_epoch_restamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_invariants import seed_order_heal_action

    ctx = isolated_run_ctx(tmp_path, "inv_music")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: True,
    )
    action, resume = seed_order_heal_action(ctx, "mmaudio_sfx")
    assert action == "restamp"
    assert resume == "mix"


def test_master_finalize_binary_accept(tmp_path: Path) -> None:
    from interview_mux.stage_acceptance import stage_acceptance_ok

    ctx = isolated_run_ctx(tmp_path, "inv_bin")
    _touch_wav(ctx, "master", "master.wav", size=4096)
    result = stage_acceptance_ok(
        ctx, "master_finalize", staged=False, include_cross_validate=False
    )
    assert result.ok is True


def test_tiny_wav_fails_binary_accept(tmp_path: Path) -> None:
    from interview_mux.stage_acceptance import stage_acceptance_ok

    ctx = isolated_run_ctx(tmp_path, "inv_tiny")
    path = ctx.final_path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 40)
    result = stage_acceptance_ok(
        ctx, "mix", staged=False, include_cross_validate=False
    )
    assert result.ok is False


def test_narrative_remutate_clears_edl_with_sonic(tmp_path: Path) -> None:
    from interview_mux.listen_delight_remutate import (
        apply_listen_delight_remutate,
        plan_listen_delight_remutate,
    )

    ctx = isolated_run_ctx(tmp_path, "inv_narr")
    _touch_wav(ctx, "master", "assembly_preview.wav")
    for sid in ("edl", "mix", "transitions", "air_script_seams"):
        (ctx.run_dir / ".stage_done" / sid).parent.mkdir(parents=True, exist_ok=True)
        (ctx.run_dir / ".stage_done" / sid).touch()
    plan = plan_listen_delight_remutate(
        ctx, failed_dimensions=["conversation_fit", "sonic_weave"]
    )
    assert plan["from_stage"] != "mix"
    assert "transitions" in (plan.get("from_stages") or [])
    applied = apply_listen_delight_remutate(ctx, plan)
    assert applied.get("ok") is True or applied.get("reason") == "refused_low_gain"
    if applied.get("ok"):
        assert not (ctx.run_dir / ".stage_done" / "edl").is_file()


def test_orphan_promote_skips_remutate_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import promote_complete_orphan_stage_done

    ctx = isolated_run_ctx(tmp_path, "inv_orphan")
    _write_raw(ctx, 
        "mastering/listen_delight_remutate.json",
        {
            "attempt": 1,
            "max_attempts": 3,
            "from_stages": ["edl"],
            "exhausted": False,
        },
    )
    _write_raw(ctx, "master/edl.json", {"clips": [{"segment_id": "seg_001"}]})
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _ctx, sid: sid == "edl",
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: None,
    )
    promoted = promote_complete_orphan_stage_done(ctx, ("edl",))
    assert "edl" not in promoted


def test_ship_path_ready_requires_commitment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import ship_path_ready

    ctx = isolated_run_ctx(tmp_path, "inv_ship")
    _touch_wav(ctx, "master", "assembly.wav", size=5000)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "junction_snip_qa", "listen_delight_audit"},
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda._junction_commitment_matches_assembly",
        lambda _ctx: False,
    )
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "junction_commitment_mismatch"


def test_ship_path_ready_soft_residuals_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import ship_path_ready

    ctx = isolated_run_ctx(tmp_path, "inv_soft_res")
    _touch_wav(ctx, "master", "assembly.wav", size=5000)
    _write_raw(ctx, 
        "master/junction_snip_qa.json",
        {"critical_residual_count": 0, "residuals": [{"soft": True}]},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "junction_snip_qa", "listen_delight_audit"},
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda._junction_commitment_matches_assembly",
        lambda _ctx: True,
    )
    ready, _ = ship_path_ready(ctx)
    assert ready is True


def test_filter_ship_needs_committed_master(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import (
        SHIP_AFTER_MASTER,
        filter_delivery_candidates,
    )

    ctx = isolated_run_ctx(tmp_path, "inv_filter")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.ship_path_ready",
        lambda _ctx: (False, "not_ready"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (True, ""),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.vo_synthesize_stability_block",
        lambda _ctx: None,
    )
    ship_stage = next(iter(SHIP_AFTER_MASTER))
    out = filter_delivery_candidates(ctx, [ship_stage])
    assert ship_stage not in out


def test_playbook_redundant_framing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.recovery_controller import (
        classify_error_class,
        playbook_redundant_framing_transitions,
    )

    ctx = isolated_run_ctx(tmp_path, "inv_redund")
    _write_raw(ctx, 
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_011",
                    "before_segment_id": "seg_019",
                    "text": "bridge",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.gap_framing.transition_redundant_with_framing",
        lambda *_a, **_k: True,
    )
    arts = playbook_redundant_framing_transitions(ctx)
    assert "master/transitions.json" in arts
    assert (
        classify_error_class(
            "transitions",
            RuntimeError("transition seg_011->seg_019 redundant with framing VO"),
        )
        == "redundant_framing_transitions"
    )


def test_identical_halt_resumes_playbook_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.identical_failures import failure_signature_by_class
    from interview_mux.recovery_controller import handle_stage_failure

    ctx = isolated_run_ctx(tmp_path, "inv_halt")
    sig = failure_signature_by_class(
        failed_stage="transitions",
        error_class="redundant_framing_transitions",
    )
    monkeypatch.setattr(
        "interview_mux.identical_failures.is_halted",
        lambda _ctx, s: s == sig,
    )
    result = handle_stage_failure(
        ctx,
        "transitions",
        RuntimeError("transition seg_011->seg_019 redundant with framing VO"),
    )
    assert result.playbook_id == "identical_failure_halt"
    assert result.resume_stage == "transitions"


def test_junction_commitment_size_mismatch(tmp_path: Path) -> None:
    from interview_mux.homunculus.agenda import _junction_commitment_matches_assembly

    ctx = isolated_run_ctx(tmp_path, "inv_autopsy")
    _touch_wav(ctx, "master", "assembly.wav", size=9000)
    _write_raw(ctx, 
        "master/seam_autopsy.json",
        {
            "commitment": {
                "status": "committed",
                "assembly": {"size": 100},
            }
        },
    )
    assert _junction_commitment_matches_assembly(ctx) is False


def test_remaining_includes_remutate_force(tmp_path: Path) -> None:
    from interview_mux.homunculus.agenda import remaining_stages

    ctx = isolated_run_ctx(tmp_path, "inv_remain")
    _write_raw(ctx, 
        "mastering/edl_narrative_remutate.json",
        {
            "attempt": 1,
            "max_attempts": 3,
            "from_stages": ["edl"],
            "exhausted": False,
        },
    )
    _write_raw(ctx, "master/edl.json", {"clips": []})
    rem = remaining_stages(ctx, "delivery")
    assert "edl" in rem
