"""Cascade: vo_path_ready SSOT (general improvements Workstream A)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from interview_mux.gap_vo_gates import (
    approved_voice_reference_usable,
    check_voice_reference_pending,
    mark_voice_reference_approved,
    require_gap_path_clear,
    require_vo_path_ready,
    set_gap_vo_delivery,
    synth_entry_may_auto_accept,
    vo_ladder_complete,
    vo_path_ready,
)
from interview_mux.operator_gate_view import resolve_framing_gate
from interview_mux.run_context import RunContext
from interview_mux.source_topology import check_pickup_speaker_pending, confirm_pickup_speaker
from run_fixtures import isolated_run_ctx, mark_done_raw


def _write_short_wav(path: Path, *, seconds: float = 4.0, rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nframes = int(rate * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * nframes)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "vo_path_ready")
    run.write_json(
        "run_meta.json",
        {"gap_framing_enabled": True},
        skip_handoff=True,
    )
    run.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_host", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_guest", "role": "interviewee", "confidence": 0.9},
            ]
        },
        skip_handoff=True,
    )
    run.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "pickup_eligible_speaker_id": "spk_host",
            "least_spoken_speaker_id": "spk_host",
            "speaker_stats": [
                {"speaker_id": "spk_host", "role": "interviewer", "talk_time_ms": 5_000},
                {"speaker_id": "spk_guest", "role": "interviewee", "talk_time_ms": 90_000},
            ],
        },
        skip_handoff=True,
    )
    run.write_json(
        "understanding/flow_adaptation.json",
        {
            "pickup_eligible_speaker_id": "spk_host",
            "operator_overrides": {"gap_framing_enabled": True},
        },
        skip_handoff=True,
    )
    from interview_mux.pipeline import ANALYSIS_ORDER

    for sid in ANALYSIS_ORDER:
        if sid == "missing_framing":
            break
        mark_done_raw(run, sid)
    return run


def test_voice_approved_pickup_unconfirmed_synth_not_ready(ctx: RunContext) -> None:
    mark_voice_reference_approved(ctx, "spk_host")
    assert check_voice_reference_pending(ctx) is False
    ok, reason = vo_path_ready(ctx, for_synthesize=False)
    assert ok is False
    assert reason == "pickup_speaker_pending"


def test_voice_approved_delivery_unset_not_ready(ctx: RunContext) -> None:
    confirm_pickup_speaker(ctx, speaker_id="spk_host")
    mark_voice_reference_approved(ctx, "spk_host")
    _write_short_wav(ctx.path("understanding", "speaker_samples", "spk_host.wav"))
    ctx.write_json(
        "understanding/voice_reference/spk_host.json",
        {
            "speaker_id": "spk_host",
            "approved": True,
            "wav": "understanding/speaker_samples/spk_host.wav",
        },
        skip_handoff=True,
    )
    ok, reason = vo_path_ready(ctx, for_synthesize=False)
    assert ok is False
    assert reason == "gap_delivery_pending"


def test_chatterbox_consent_open_refuses_ensure_and_view(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    confirm_pickup_speaker(ctx, speaker_id="spk_host")
    mark_voice_reference_approved(ctx, "spk_host")
    _write_short_wav(ctx.path("understanding", "speaker_samples", "spk_host.wav"))
    ctx.write_json(
        "understanding/voice_reference/spk_host.json",
        {
            "speaker_id": "spk_host",
            "approved": True,
            "wav": "understanding/speaker_samples/spk_host.wav",
        },
        skip_handoff=True,
    )
    set_gap_vo_delivery(ctx, "chatterbox")
    monkeypatch.setattr(
        "interview_mux.mastering_hardening_config.gate_blocks",
        lambda _g: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.maybe_auto_accept_gap_gate_defaults",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_voice_clone.consent_active",
        lambda _c: False,
    )
    ok, reason = vo_path_ready(ctx, for_synthesize=False)
    assert ok is False
    assert reason == "clone_consent_pending"

    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {"line_id": "L1", "delivery": "synthesize", "text": "Hello there."},
            ]
        },
        skip_handoff=True,
    )
    from interview_mux.delivery_recovery import ensure_g1_pickups

    out = ensure_g1_pickups(ctx, heal_spoken_copy=False)
    assert out.get("ok") is False
    assert out.get("reason_code") == "clone_consent_pending"

    view = resolve_framing_gate(ctx, ctx.read_json("run_meta.json"))
    assert view.open is True
    assert view.ui_mode == "clone_consent" or "consent" in view.message.lower()
    assert "not ready to generate" in view.message.lower() or view.ui_mode == "clone_consent"

def test_compose_from_stage_without_voice_ref_refuses(ctx: RunContext) -> None:
    confirm_pickup_speaker(ctx, speaker_id="spk_host")
    with pytest.raises(SystemExit, match="Voice reference"):
        require_gap_path_clear(ctx)


def test_pickup_pending_survives_missing_framing_done(ctx: RunContext) -> None:
    assert check_pickup_speaker_pending(ctx) is True
    mark_done_raw(ctx, "missing_framing")
    assert check_pickup_speaker_pending(ctx) is True
    ok, reason = vo_path_ready(ctx)
    assert ok is False
    assert reason == "pickup_speaker_pending"


def test_thin_missing_wav_after_approve_unusable(ctx: RunContext) -> None:
    confirm_pickup_speaker(ctx, speaker_id="spk_host")
    mark_voice_reference_approved(ctx, "spk_host")
    ctx.write_json(
        "understanding/voice_reference/spk_host.json",
        {
            "speaker_id": "spk_host",
            "approved": True,
            "wav": "understanding/speaker_samples/spk_host.wav",
        },
        skip_handoff=True,
    )
    set_gap_vo_delivery(ctx, "chatterbox")
    assert approved_voice_reference_usable(ctx) is False
    ok, reason = vo_path_ready(ctx, for_synthesize=False)
    assert ok is False
    assert reason == "voice_reference_unusable"


def test_framing_disabled_is_ready(ctx: RunContext) -> None:
    def patch(meta: dict) -> None:
        meta["gap_framing_enabled"] = False

    ctx.mutate_run_meta(patch)
    ok, reason = vo_path_ready(ctx)
    assert ok is True
    assert reason == ""


def _arm_path_ready(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    confirm_pickup_speaker(ctx, speaker_id="spk_host")
    mark_voice_reference_approved(ctx, "spk_host")
    _write_short_wav(ctx.path("understanding", "speaker_samples", "spk_host.wav"))
    ctx.write_json(
        "understanding/voice_reference/spk_host.json",
        {
            "speaker_id": "spk_host",
            "approved": True,
            "wav": "understanding/speaker_samples/spk_host.wav",
        },
        skip_handoff=True,
    )
    set_gap_vo_delivery(ctx, "chatterbox")
    monkeypatch.setattr(
        "interview_mux.mastering_hardening_config.gate_blocks",
        lambda _g: False,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_voice_clone.consent_active",
        lambda _c: True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {"line_id": "L1", "delivery": "synthesize", "text": "Hello there."},
            ]
        },
        skip_handoff=True,
    )


def test_vo_ladder_incomplete_without_adjudicate(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DP-VO1 A+: path ready ≠ ladder complete until adjudicate seals."""
    _arm_path_ready(ctx, monkeypatch)
    ok, reason = vo_path_ready(ctx, for_synthesize=True)
    assert ok is True
    ladder_ok, ladder_reason = vo_ladder_complete(ctx, for_synthesize=True)
    assert ladder_ok is False
    assert ladder_reason == "vo_line_adjudicate_incomplete"


def test_vo_ladder_blocked_by_g8_stability(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm_path_ready(ctx, monkeypatch)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid == "vo_line_adjudicate",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.vo_synthesize_stability_block",
        lambda _c, allow_rewrite=False: "nugget_layup_compose",
    )
    ok, reason = vo_ladder_complete(ctx, for_synthesize=True)
    assert ok is False
    assert reason == "vo_synth_stability:nugget_layup_compose"


def test_partial_synth_entry_never_auto_accepts(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json(
        "run_meta.json",
        {
            **ctx.read_json("run_meta.json"),
            "partial_auto": True,
            "run_mode": "partially-accelerated",
            "gap_framing_enabled": True,
        },
        skip_handoff=True,
    )
    assert synth_entry_may_auto_accept(ctx) is False
    stamped = {"n": 0}

    def _stamp(_c):
        stamped["n"] += 1
        return True

    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.maybe_auto_accept_gap_gate_defaults",
        _stamp,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.vo_ladder_complete",
        lambda _c, for_synthesize=False: (False, "pickup_speaker_pending"),
    )
    with pytest.raises(SystemExit, match="pickup"):
        require_vo_path_ready(ctx, for_synthesize=True, auto_accept=True)
    assert stamped["n"] == 0


def test_vo_ladder_g8_probe_error_fail_closed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm_path_ready(ctx, monkeypatch)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid == "vo_line_adjudicate",
    )

    def _boom(*_a, **_k):
        raise RuntimeError("stability boom")

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.vo_synthesize_stability_block",
        _boom,
    )
    ok, reason = vo_ladder_complete(ctx, for_synthesize=True)
    assert ok is False
    assert reason == "vo_synth_stability:probe_error"


def test_vo_ladder_never_trusts_hollow_adjudicate_is_done(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _arm_path_ready(ctx, monkeypatch)
    mark_done_raw(ctx, "vo_line_adjudicate")

    def _seed_boom(_c, sid):
        raise RuntimeError("seed boom")

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        _seed_boom,
    )
    ok, reason = vo_ladder_complete(ctx, for_synthesize=True)
    assert ok is False
    assert reason == "vo_line_adjudicate_incomplete"


def test_partial_mint_requires_ladder_not_path_only(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.gap_vo_gates import vo_synth_mint_allowed

    _arm_path_ready(ctx, monkeypatch)
    ctx.write_json(
        "run_meta.json",
        {
            **ctx.read_json("run_meta.json"),
            "partial_auto": True,
            "run_mode": "partially-accelerated",
        },
        skip_handoff=True,
    )
    path_ok, _ = vo_path_ready(ctx, for_synthesize=True)
    assert path_ok is True
    mint_ok, mint_reason = vo_synth_mint_allowed(ctx)
    assert mint_ok is False
    assert mint_reason == "vo_line_adjudicate_incomplete"


def test_partial_nested_skips_when_path_ready_ladder_open(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.gap_vo_gates import nested_synth_may_mint

    _arm_path_ready(ctx, monkeypatch)
    ctx.write_json(
        "run_meta.json",
        {
            **ctx.read_json("run_meta.json"),
            "partial_auto": True,
            "run_mode": "partially-accelerated",
            "gap_vo_delivery": "chatterbox",
        },
        skip_handoff=True,
    )
    ok, note = nested_synth_may_mint(ctx)
    assert ok is False
    assert "vo_line_adjudicate_incomplete" in note


def test_g8_ladder_probe_does_not_rewrite(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import vo_synthesize_stability_block

    rewritten = {"n": 0}

    def _rewrite(_c):
        rewritten["n"] += 1

    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.rewrite_full_auto_record_lines_to_synth",
        _rewrite,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_record_open",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._layup_escalation_blocking",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, _sid: True,
    )
    ctx.write_json("master/transitions.json", {"pairs": []}, skip_handoff=True)
    vo_synthesize_stability_block(ctx, allow_rewrite=False)
    assert rewritten["n"] == 0
    vo_synthesize_stability_block(ctx, allow_rewrite=True)
    assert rewritten["n"] == 1
