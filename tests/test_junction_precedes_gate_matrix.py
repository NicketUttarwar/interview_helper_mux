"""A1/A5: junction_recut_precedes_mix agrees across gates; commitment skip only if missing assembly."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus.runtime import _seed_prereq_block
from interview_mux.junction_snip_qa import junction_recut_precedes_mix
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "junction_precedes_matrix")


def _pin_mix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening._earliest_incomplete_seed_stage",
        lambda _ctx, _stage: "mix",
    )


def _no_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )


def _not_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.air_order.mix_stale_versus_live",
        lambda _ctx: False,
    )


def _live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )


def _write_assembly(ctx: RunContext) -> None:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)


def _hardening_allowed_junction(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> bool:
    """True when maybe_require_upstream_llm_progress does not demand mix."""
    called: list[str] = []
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.flow_hardening_enabled", lambda *a, **k: True
    )
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.require_llm_stage_progress",
        lambda _ctx, stage: called.append(str(stage)),
    )
    from interview_mux.llm_flow_hardening import maybe_require_upstream_llm_progress

    maybe_require_upstream_llm_progress(ctx, "junction_snip_qa")
    return "mix" not in called


def _conductor_front(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.filter_delivery_candidates",
        lambda _ctx, remaining: list(remaining),
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.earliest_incomplete_seed_stage",
        lambda _ctx, _phase, _rem: "mix",
    )
    from interview_mux.homunculus.agenda import constrain_conductor_to_seed_front

    out = constrain_conductor_to_seed_front(
        ctx, "delivery", ["mix", "junction_snip_qa"]
    )
    return str(out[0] if out else "")


def test_matrix_live_cuts_all_gates_allow_junction(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_mix(monkeypatch)
    _live(monkeypatch)
    assert junction_recut_precedes_mix(ctx) is True
    assert _seed_prereq_block(ctx, "junction_snip_qa") is None
    assert _hardening_allowed_junction(ctx, monkeypatch) is True
    assert _conductor_front(ctx, monkeypatch) == "junction_snip_qa"


def test_matrix_remaster_requires_explicit_owner(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seat authority: assembly + unmarked mix without remaster_owner → mix first."""
    from interview_mux.mix_junction_seat import begin_remaster, clear_remaster

    _pin_mix(monkeypatch)
    _no_live(monkeypatch)
    _not_stale(monkeypatch)
    _write_assembly(ctx)
    assert not ctx.is_done("mix")
    clear_remaster(ctx)
    assert junction_recut_precedes_mix(ctx) is False
    assert _seed_prereq_block(ctx, "junction_snip_qa") == "mix"
    assert _hardening_allowed_junction(ctx, monkeypatch) is False
    assert _conductor_front(ctx, monkeypatch) == "mix"

    begin_remaster(ctx, owner="junction")
    assert junction_recut_precedes_mix(ctx) is True
    assert _seed_prereq_block(ctx, "junction_snip_qa") is None
    assert _hardening_allowed_junction(ctx, monkeypatch) is True
    assert _conductor_front(ctx, monkeypatch) == "junction_snip_qa"


def test_matrix_remaster_assembly_present_mix_unmarked(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backward name: remaster_in_flight (explicit owner) → SSOT True; all gates agree."""
    from interview_mux.mix_junction_seat import begin_remaster

    _pin_mix(monkeypatch)
    _no_live(monkeypatch)
    _not_stale(monkeypatch)
    _write_assembly(ctx)
    begin_remaster(ctx, owner="junction")
    assert not ctx.is_done("mix")
    assert junction_recut_precedes_mix(ctx) is True
    assert _seed_prereq_block(ctx, "junction_snip_qa") is None
    assert _hardening_allowed_junction(ctx, monkeypatch) is True
    assert _conductor_front(ctx, monkeypatch) == "junction_snip_qa"


def test_matrix_mix_done_assembly_clean_keeps_mix_first(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_mix(monkeypatch)
    _no_live(monkeypatch)
    _not_stale(monkeypatch)
    _write_assembly(ctx)
    ctx._mark_done_raw = True
    ctx.mark_done("mix")
    ctx._mark_done_raw = False
    assert junction_recut_precedes_mix(ctx) is False
    assert _seed_prereq_block(ctx, "junction_snip_qa") == "mix"
    assert _hardening_allowed_junction(ctx, monkeypatch) is False
    assert _conductor_front(ctx, monkeypatch) == "mix"


def test_a5_commitment_skip_only_when_assembly_missing(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.air_order import assert_consumer

    _no_live(monkeypatch)
    _not_stale(monkeypatch)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "air_order_generation": 1},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "clips": [],
            "ordered_segment_ids": ["seg_001"],
            "air_order_generation": 2,
            "timeline_duration_ms": 1000,
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.order_hash.order_drift_heal_action",
        lambda *_a, **_k: "ok",
    )
    # Missing assembly: skip generation mismatch.
    assert_consumer(ctx, "junction_snip_qa")
    _write_assembly(ctx)
    with pytest.raises(SystemExit, match="assembly_not_rendered_from_current_edl"):
        assert_consumer(ctx, "junction_snip_qa")
