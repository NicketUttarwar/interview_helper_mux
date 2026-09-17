"""R3 VO family residual closures (MUX_FORENSICS=0).

Covers exec_11630 #15–17 cousins without reopening End-A…F:
R3a hollow synth done · R3b End-B flush discard · R3c HV-5 unattended
· R3d/e owner resync + 005/020 · R3f fail_class denylist · R3g/h premature vo_g1.
Also re-pins HV-4 (G1 skip vs hollow seats) and HV-1 (VO contract ladder spin).
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from interview_mux.artifact_ownership import write_permitted
from interview_mux.artifact_sanitize.vo_synthesize import vo_sanitary_errors
from interview_mux.delivery_guardrails import (
    G1_CONSUMERS,
    premature_cap_hard_pin,
    seed_stage_complete,
)
from interview_mux.execution_contract import run_edl_vo_coverage_ladder
from interview_mux.heal_routing import classify_heal_error
from interview_mux.operator_gate_view import g1_journey_clear, resolve_g1_vo_gate
from interview_mux.operator_gates import should_stamp_needs_operator
from interview_mux.recovery_controller import classify_error_class
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    stage_artifact_incompleteness,
)
from interview_mux.stages.assembly import resync_required_synthesize_wavs
from interview_mux.thrash_hardening import (
    FAIL_CLASS_PHASE_A_EDL,
    FAIL_CLASS_VO_G1,
    fail_class_for_failure,
    premature_fail_class,
)
from interview_mux.vo_synthesis_audit import record_synthesis, wav_content_sha256
from interview_mux.write_staging import (
    _commit_stage_writes,
    active_stage_id,
    enter_stage_staging,
    exit_stage_staging,
    flush_stage_writes,
    promote_owner_vo_pickup,
)
from run_fixtures import isolated_run_ctx, mark_done_raw, patch_merged_config

_LIDS = ("vo_layup_seg_005", "vo_layup_seg_020")


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "1")
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled", lambda: False
    )
    return isolated_run_ctx(tmp_path, "r3_vo_family")


def _wav(path: Path, *, duration_ms: int = 300, tag: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48_000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = b"\x00\x00" * int(rate * duration_ms / 1000)
        handle.writeframes(frames + tag)


def _patch_vo_qc_off(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            },
            "artifact_sanitize": {"block_consumers": True},
        },
    )
    monkeypatch.setattr(
        "interview_mux.vo_speech_qa.vo_passes_speech_qa",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.analyze_vo_wav",
        lambda *_a, **_k: {"pass": True, "reasons": []},
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda *_a, **_k: False,
    )


def _gap_line(lid: str, *, seg: str, text: str = "Why does that matter?") -> dict:
    return {
        "line_id": lid,
        "text": text,
        "delivery": "synthesize",
        "severity": "medium",
        "placement": "before",
        "targets_segment_id": seg,
        "gap_type": "missing_framing",
        "origin": "nugget_layup",
    }


def _plant_seated_lines(
    ctx: RunContext,
    lids: tuple[str, ...] = _LIDS,
    *,
    with_wav: bool = False,
    bind_stale: bool = False,
) -> None:
    lines = [
        _gap_line(lid, seg=f"seg_{lid.rsplit('_', 1)[-1]}", text=f"Layup cue {lid}.")
        for lid in lids
    ]
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": lines},
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "plan_status": "complete",
            "air_script": {
                "beats": [{"beat_id": "b1"}],
                "vo_seats": {
                    "seated_line_ids": list(lids),
                    "omitted_line_ids": [],
                },
            },
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/vo_synthesize.json",
        {"version": 1, "lines": [{"line_id": lid} for lid in lids]},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/transitions.json",
        {"version": 1, "transitions": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": [f"seg_{lid.rsplit('_', 1)[-1]}" for lid in lids]},
        skip_handoff=True,
    )
    if not with_wav and not bind_stale:
        return
    for i, lid in enumerate(lids):
        good = ctx.path("vo_pickup", "synthesized", f"{lid}.wav")
        _wav(good, duration_ms=280 + i * 20, tag=b"GOOD")
        record_synthesis(ctx, lines[i], backend="chatterbox", out_wav=good)
        if bind_stale:
            # Overwrite committed bytes so audit sha no longer matches.
            _wav(good, duration_ms=900 + i * 10, tag=b"STALE_BYTES!!")


# --- R3a: mark_done / incompleteness while bind stale or missing WAV ---------


def test_r3a_missing_wav_refuses_mark_done(ctx: RunContext) -> None:
    _plant_seated_lines(ctx, with_wav=False)
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    assert reason is not None
    assert (
        "missing" in reason.lower()
        or "g1" in reason.lower()
        or "wav" in reason.lower()
    )
    out = heal_or_refuse_mark(ctx, "vo_synthesize", force=True)
    assert out.get("marked") is not True
    assert out.get("refused") is True or out.get("unmarked") is True
    assert not ctx.is_done("vo_synthesize")
    ctx.mark_done("vo_synthesize")
    assert not ctx.is_done("vo_synthesize")
    mark_done_raw(ctx, "vo_synthesize")
    assert seed_stage_complete(ctx, "vo_synthesize") is False


def test_r3a_seated_bind_stale_refuses_mark_done(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_vo_qc_off(monkeypatch)
    _plant_seated_lines(ctx, lids=("vo_layup_seg_012",), bind_stale=True)
    errs = vo_sanitary_errors(ctx)
    assert any("seated_bind_stale" in e for e in errs)
    # Bind mismatch makes resolve_vo_pickup_path miss → G1 may surface first;
    # pin the sanitary gate so incompleteness names seated_bind_stale.
    monkeypatch.setattr("interview_mux.gates.check_g1_vo", lambda _ctx: [])
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    assert reason is not None
    assert "seated_bind_stale" in reason or "vo_unsanitary" in reason or "stale" in reason or "missing WAV" in reason
    out = heal_or_refuse_mark(ctx, "vo_synthesize", force=True)
    assert out.get("marked") is not True
    assert out.get("refused") is True or out.get("unmarked") is True
    assert not ctx.is_done("vo_synthesize")
    mark_done_raw(ctx, "vo_synthesize")
    assert seed_stage_complete(ctx, "vo_synthesize") is False


# --- R3b: End-B flush discard cousin -----------------------------------------


def test_r3b_endb_flush_discards_stale_pending_over_audited(
    ctx: RunContext,
) -> None:
    lid = "vo_layup_seg_020"
    syn = ctx.run_dir / "vo_pickup" / "synthesized"
    syn.mkdir(parents=True)
    good = syn / f"{lid}.wav"
    good.write_bytes(b"RIFF" + b"\x00" * 100 + b"GOOD_AUDITED_TAKE")
    want = wav_content_sha256(good)
    (ctx.run_dir / "vo_pickup" / "synthesis_report.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "line_id": lid,
                        "script_hash": "abc",
                        "context_hash": "def",
                        "wav_sha256": want,
                        "backend": "chatterbox",
                        "qc_pass": True,
                        "out_wav": f"vo_pickup/synthesized/{lid}.wav",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "vo_synthesize"
        / "vo_pickup"
        / "synthesized"
        / f"{lid}.wav"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 100 + b"STALE_PENDING_BYTES!!")
    rel = f"vo_pickup/synthesized/{lid}.wav"

    assert rel not in promote_owner_vo_pickup(ctx)
    assert wav_content_sha256(good) == want
    assert not pending.is_file()

    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 100 + b"STALE_PENDING_BYTES!!")
    assert rel not in flush_stage_writes(ctx, "vo_synthesize")
    assert wav_content_sha256(good) == want
    assert not pending.is_file()

    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 100 + b"STALE_PENDING_BYTES!!")
    assert rel not in _commit_stage_writes(ctx, "vo_synthesize")
    assert wav_content_sha256(good) == want

    # Foreign promote DENY (ownership cousin).
    ok, reason = write_permitted(
        ctx,
        f"vo_pickup/synthesized/{lid}.wav",
        "edl",
        role="producer",
        verb="promote_pending",
    )
    assert not ok
    assert "non_owner" in reason or "deny" in reason or "not_allow" in reason


# --- R3c: HV-5 automation_pending --------------------------------------------


def test_r3c_hv5_unattended_stays_automation_pending(ctx: RunContext) -> None:
    meta = {"partial_auto": True, "homunculus_version": "0.1.0"}
    assert (
        should_stamp_needs_operator(
            "vo_synthesize",
            "vo_unsanitary — resume vo_synthesize: seated_bind_stale:vo_line_1",
            meta=meta,
        )
        is False
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                _gap_line("vo_line_1", seg="seg_1", text="Can you expand on that?")
            ]
        },
        skip_handoff=True,
    )
    full_meta = {
        "homunculus_version": "0.1.0",
        "partial_auto": True,
        "partial_auto_driver_active": True,
        "gap_framing_enabled": True,
        "gap_vo_delivery": "chatterbox",
        "voice_reference_approved_at": "2026-01-01T00:00:00Z",
        "needs_operator": True,
        "needs_operator_stage": "g1_vo_pickup",
        "needs_operator_reason": "vo_unsanitary — resume vo_synthesize: seated_bind_stale",
    }
    ctx.write_json("run_meta.json", full_meta, skip_handoff=True)
    view = resolve_g1_vo_gate(ctx, None, full_meta)
    assert view.severity == "automation_pending"
    assert view.operator_must_act is False
    assert g1_journey_clear(ctx, full_meta) is True


# --- R3d/e: 005/020 missing WAV + resync owner staging -----------------------


def test_r3de_two_lids_missing_wav_fail_class_and_heal_pin(ctx: RunContext) -> None:
    _plant_seated_lines(ctx, _LIDS, with_wav=False)
    reason = (
        "edl: gap VO lines missing WAV: "
        f"['{_LIDS[0]}', '{_LIDS[1]}']"
    )
    assert classify_error_class("edl", RuntimeError(reason)) == "vo_seated_coverage"
    assert fail_class_for_failure(stage="edl", reason=reason) == FAIL_CLASS_VO_G1
    assert fail_class_for_failure(stage="edl", reason=reason) != FAIL_CLASS_PHASE_A_EDL
    route = classify_heal_error(reason, ctx, stage="edl")
    assert route is not None
    assert route.from_stage == "vo_synthesize"
    assert route.from_stage not in {"edl", "mix", "master_finalize"}


def test_r3de_resync_enters_vo_synthesize_staging_under_edl(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nested EDL resync must stage under vo_synthesize (owner), not edl pending."""
    _patch_vo_qc_off(monkeypatch)
    line = _gap_line(_LIDS[1], seg="seg_020", text="Why does counting cells leave clinicians uncertain?")
    line["required"] = True
    stages: list[str | None] = []

    def _fake_synth(_ctx, row, *, mode="synthesize"):
        stages.append(active_stage_id())
        out = _ctx.path("vo_pickup", "synthesized", f"{row['line_id']}.wav")
        _wav(out, duration_ms=250)
        record_synthesis(
            _ctx, row, backend="chatterbox", out_wav=out, wav_just_rendered=True
        )
        return out

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _fake_synth)
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.resolve_gap_vo_delivery",
        lambda _ctx: "chatterbox",
    )
    enter_stage_staging("edl")
    try:
        notes = resync_required_synthesize_wavs(ctx, {"interviewer_lines": [line]})
    finally:
        exit_stage_staging()
    assert notes == [_LIDS[1]]
    assert stages == ["vo_synthesize"]
    committed = ctx.run_dir / "vo_pickup" / "synthesized" / f"{_LIDS[1]}.wav"
    assert committed.is_file()
    # Must not leave owner bytes under EDL pending (would be discarded).
    edl_pending = (
        ctx.run_dir
        / ".pending_writes"
        / "edl"
        / "vo_pickup"
        / "synthesized"
        / f"{_LIDS[1]}.wav"
    )
    assert not edl_pending.is_file()


# --- R3f: fail_class denylist cousin (keep/extend) ---------------------------


def test_r3f_gap_vo_and_bind_never_phase_a_edl() -> None:
    gap = "edl: gap VO lines missing WAV: ['vo_layup_seg_005', 'vo_layup_seg_020']"
    bind = "vo_unsanitary — resume vo_synthesize: seated_bind_stale:vo_layup_seg_012"
    for reason in (gap, bind, "G1 VO pickup missing for: vo_layup_seg_001"):
        assert fail_class_for_failure(stage="edl", reason=reason) == FAIL_CLASS_VO_G1
        assert fail_class_for_failure(stage="edl", reason=reason) != FAIL_CLASS_PHASE_A_EDL


# --- R3g/h: premature edl + coverage ladder ----------------------------------


def test_r3g_g1_missing_premature_edl_pins_vo_synthesize(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_seated_lines(ctx, _LIDS, with_wav=False)
    # Upstream Phase-A producers look complete so the hard pin is the VO hole.
    for sid in (
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "nugget_layup_compose",
        "transitions",
        "vo_line_adjudicate",
    ):
        mark_done_raw(ctx, sid)

    def _seed(_ctx: RunContext, sid: str) -> bool:
        if sid in {"vo_synthesize", "edl", "edl_narrative_audit", "assembly_preview"}:
            return False
        return True

    import interview_mux.delivery_guardrails as dg

    monkeypatch.setattr(dg, "seed_stage_complete", _seed)
    monkeypatch.setattr(dg, "vo_synthesize_stability_block", lambda _ctx: None)
    monkeypatch.setattr(dg, "_g1_open", lambda _ctx: list(_LIDS))
    assert premature_fail_class("edl") == FAIL_CLASS_PHASE_A_EDL
    # With g1 missing, hard pin must leave EDL consumers for vo_synthesize.
    pinned = premature_cap_hard_pin(ctx, "edl", message="g1_missing")
    assert pinned in {"vo_synthesize", "vo_line_adjudicate"}
    assert pinned not in G1_CONSUMERS
    pinned_vo = premature_cap_hard_pin(ctx, "vo_synthesize", message="g1_missing")
    assert pinned_vo in {"vo_synthesize", "vo_line_adjudicate", "nugget_layup_compose"}
    assert pinned_vo not in G1_CONSUMERS


def test_r3h_coverage_ladder_does_not_claim_recovered_edl(ctx: RunContext) -> None:
    _plant_seated_lines(ctx, (_LIDS[0],), with_wav=False)
    mark_done_raw(ctx, "vo_synthesize")
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_005"],
            "timeline_duration_ms": 1000,
            "clips": [],
        },
        skip_handoff=True,
    )
    mark_done_raw(ctx, "edl")
    result = run_edl_vo_coverage_ladder(ctx, consumer_stage="edl")
    assert result.recovered is False
    assert result.resume_stage == "vo_synthesize"
    assert result.resume_stage not in G1_CONSUMERS
    assert seed_stage_complete(ctx, "edl") is False
    assert seed_stage_complete(ctx, "vo_synthesize") is False


# --- HV-4 / HV-1 re-pins (call existing behavior) ----------------------------


def test_r3_hv4_g1_skip_never_waives_hollow_seats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HV-4 cousin: optional G1 skip must not allow-stub empty seats."""
    from test_hv4_g1_skip_hollow_vo_seed import (
        _plant_vo_seed,
        test_hv4_g1_skip_refuses_allow_stub_when_seats_empty,
    )

    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: True)
    hv4_ctx = isolated_run_ctx(tmp_path, "r3_hv4_cousin")
    _plant_vo_seed(hv4_ctx, seated=[])
    # Drive the same assertions as the HV-4 fixture (shared plant).
    test_hv4_g1_skip_refuses_allow_stub_when_seats_empty(hv4_ctx)


def test_r3_hv1_vo_contract_ladder_spin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HV-1 cousin: exhausted ladder pins vo_synthesize and does not spin."""
    from test_hv1_vo_contract_ladder_spin import (
        test_hv1_exhaust_pins_vo_synthesize_and_keeps_plan_open,
    )
    from run_fixtures import patch_executions_root

    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    hv1_ctx = RunContext("r3_hv1_cousin", create=True)
    test_hv1_exhaust_pins_vo_synthesize_and_keeps_plan_open(hv1_ctx, monkeypatch)
