"""End-D: junction commitment seating + hollow seed refuse (MUX_FORENSICS=0)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import (
    _junction_commitment_matches_assembly,
    stage_outputs_present,
    stage_required_outputs,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx, mark_done_raw

_WAV = b"RIFF" + (b"\x00" * 2048)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "endd_commitment")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _write_raw(ctx: RunContext, rel: str, doc: dict) -> None:
    path = ctx.final_path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _stub_commitment_seat_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENDD-2: commitment success mocks must report mix_outputs_seated True."""
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _ctx: True,
    )


def test_endd_commitment_bypasses_budget_and_low_gain(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import junction_snip_qa

    calls: list[str] = []

    monkeypatch.setattr(
        "interview_mux.timeline_reopen_meta_gate.decide_timeline_reopen",
        lambda *_a, **_k: {"allow": False, "refuse_reason": "low_gain_test"},
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.junction_remaster_budget_ok",
        lambda _ctx: (False, 9),
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.junction_budget_exhaust_hard_pin",
        lambda _ctx: "needs_operator",
    )
    monkeypatch.setattr(
        junction_snip_qa,
        "remaster_mix_only",
        lambda _ctx: calls.append("remaster"),
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.note_junction_remaster",
        lambda _ctx: 10,
    )
    _stub_commitment_seat_ok(monkeypatch)

    ok_feel, _ = junction_snip_qa._budgeted_remaster_mix(ctx, path="feel")
    assert ok_feel is False
    assert calls == []

    ok_commit, used = junction_snip_qa._budgeted_remaster_mix(ctx, path="commitment")
    assert ok_commit is True
    assert used == 10
    assert calls == ["remaster"]


def test_endd1_unseated_triggers_commitment_despite_mtime(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENDD-1: gen/ledger unseated with asm mtime ≥ edl still needs commitment path."""
    from interview_mux import junction_snip_qa

    edl = ctx.final_path("master", "edl.json")
    asm = ctx.final_path("master", "assembly.wav")
    edl.parent.mkdir(parents=True, exist_ok=True)
    edl.write_text("{}", encoding="utf-8")
    asm.write_bytes(_WAV)
    # Assembly newer than EDL (mtime would not alone trigger).
    import os
    import time

    now = time.time()
    os.utime(edl, (now - 100, now - 100))
    os.utime(asm, (now, now))

    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _ctx: False,
    )
    assert junction_snip_qa.commitment_remaster_needed(ctx) is True

    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _ctx: True,
    )
    assert junction_snip_qa.commitment_remaster_needed(ctx) is False


def test_endd2_commitment_unseated_after_remaster_is_refuse(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import junction_snip_qa

    monkeypatch.setattr(junction_snip_qa, "remaster_mix_only", lambda _ctx: None)
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.junction_remaster_budget_ok",
        lambda _ctx: (True, 0),
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.note_junction_remaster",
        lambda _ctx: 1,
    )
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _ctx: False,
    )
    ok, used = junction_snip_qa._budgeted_remaster_mix(ctx, path="commitment")
    assert ok is False
    assert used == 1


def test_endd5_begin_remaster_defers_music_epoch(ctx: RunContext) -> None:
    from interview_mux.mix_junction_seat import (
        begin_remaster,
        junction_remaster_blocked_by_music_epoch,
        remaster_owner,
    )

    assert begin_remaster(ctx, owner="music_epoch") is True
    assert remaster_owner(ctx) == "music_epoch"
    assert junction_remaster_blocked_by_music_epoch(ctx) is True
    assert begin_remaster(ctx, owner="junction") is False
    assert remaster_owner(ctx) == "music_epoch"


def test_endd5_ordering_exempt_false_when_music_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import ordering_authority as oa
    from interview_mux.mix_junction_seat import begin_remaster

    begin_remaster(ctx, owner="music_epoch")
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.ordering_authority._junction_recut_precedes_mix",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.speech_first_remaster_owed",
        lambda _ctx: True,
    )
    assert oa.ordering_exempt(ctx, "junction_snip_qa", "mix") is None


def test_endd3_ordering_exempt_commitment_reseat(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import ordering_authority as oa

    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.ordering_authority._junction_recut_precedes_mix",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.speech_first_remaster_owed",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.remaster_owner",
        lambda _ctx: "",
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    assert (
        oa.ordering_exempt(ctx, "junction_snip_qa", "mix")
        == "junction_commitment_reseat"
    )


def test_endd6_aspirational_keeps_commitment_diverge_hard() -> None:
    from interview_mux import junction_snip_qa

    src = inspect.getsource(junction_snip_qa.run_junction_snip_qa)
    assert '"junction_commitment_diverged"' in src
    assert '"junction_commitment_remaster_refused"' in src
    assert '"assembly_not_rendered_from_current_edl"' in src


def test_endd7_match_requires_mix_outputs_seated(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(_WAV)
    size = asm.stat().st_size
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "commitment": {
                "status": "committed",
                "assembly": {"size": size},
            },
        },
    )
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _ctx: False,
    )
    assert _junction_commitment_matches_assembly(ctx) is False
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated",
        lambda _ctx: True,
    )
    assert _junction_commitment_matches_assembly(ctx) is True


def test_endd4_no_write_live_edl_after_run_mix() -> None:
    from interview_mux import junction_snip_qa

    src = inspect.getsource(junction_snip_qa.remaster_mix_only)
    mix_idx = src.find("run_nested_staged_stage")
    assert mix_idx > 0
    after = src[mix_idx:]
    # Comment may mention write_live_edl; forbid actual calls after mix.
    assert "write_live_edl(" not in after


def test_endd_hollow_junction_not_seed_complete(ctx: RunContext) -> None:
    """QA + autopsy files without matching commitment must not seed-complete."""
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {"version": 1, "generated_at": "2026-01-01T00:00:00Z", "findings": []},
    )
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "commitment": {
                "status": "diverged",
                "assembly": {"size": 1, "sha256": "dead"},
            },
            "blocking_reasons": ["junction_commitment_diverged"],
        },
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(_WAV)

    assert stage_outputs_present(ctx, "junction_snip_qa") is False
    reason = stage_artifact_incompleteness(ctx, "junction_snip_qa")
    assert reason is not None
    assert "junction commitment" in reason
    assert "resume junction_snip_qa" in reason

    mark_done_raw(ctx, "junction_snip_qa")
    assert seed_stage_complete(ctx, "junction_snip_qa") is False


def test_endd_committed_junction_is_seed_complete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(_WAV)
    size = asm.stat().st_size
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {"version": 1, "generated_at": "2026-01-01T00:00:00Z", "findings": []},
    )
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "commitment": {
                "status": "committed",
                "assembly": {"size": size},
            },
            "blocking_reasons": [],
        },
    )
    for rel in stage_required_outputs("junction_snip_qa"):
        if not ctx.artifact_exists(rel):
            if rel.endswith(".json"):
                _write_raw(ctx, rel, {"version": 1, "generated_at": "2026-01-01T00:00:00Z"})
            else:
                p = ctx.final_path(*rel.split("/"))
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(_WAV)
    _stub_commitment_seat_ok(monkeypatch)

    assert stage_outputs_present(ctx, "junction_snip_qa") is True
    assert stage_artifact_incompleteness(ctx, "junction_snip_qa") is None
    mark_done_raw(ctx, "junction_snip_qa")
    assert seed_stage_complete(ctx, "junction_snip_qa") is True


def test_endd_hollow_done_refuses_seed_complete_for_finalize(ctx: RunContext) -> None:
    """Hollow .stage_done/junction must keep finalize seed-blocked (no seed mock)."""
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {"version": 1, "generated_at": "2026-01-01T00:00:00Z", "findings": []},
    )
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {"version": 1, "commitment": {"status": "pending"}, "blocking_reasons": []},
    )
    mark_done_raw(ctx, "junction_snip_qa")
    assert ctx.is_done("junction_snip_qa")
    assert stage_outputs_present(ctx, "junction_snip_qa") is False
    assert seed_stage_complete(ctx, "junction_snip_qa") is False
    reason = stage_artifact_incompleteness(ctx, "junction_snip_qa")
    assert reason is not None and "resume junction_snip_qa" in reason

