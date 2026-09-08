"""HDT remaster research harness — stub conductor tool sequences + invariants (R1d/R4).

No live LLM. Covers host legality for 0.1.0 conductor tools, filters, invalidate modes,
ADG impact chains, and preventable break classes from the remaster-path research plan.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from interview_mux.artifact_dependency_graph import transitive_invalidate
from interview_mux.delivery_guardrails import (
    HEAL_ONLY_PRODUCERS,
    INVALIDATION_BLAST_RADIUS,
    current_delivery_phase,
    filter_delivery_candidates,
    invalidation_allowed_downstream,
    invalidation_is_structural,
    music_epoch_complete,
    seed_stage_complete,
)
from interview_mux.homunculus.agenda import (
    invalidate_downstream,
    request_walk_seed_remainder,
    resolve_stage_plan,
    rerun_with_impact,
    unmark_stage_only,
)
from interview_mux.homunculus.gates import CATEGORIES
from interview_mux.homunculus.loop import run_conductor
from interview_mux.homunculus.registry import stage_tool_specs
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER, SHIP_AFTER_MASTER


def _ctx_010() -> RunContext:
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
    )
    return ctx


def _stub_client(tool_sequence: list[tuple[str, dict]]) -> SimpleNamespace:
    """Return a fake OpenAI client that emits one tool call per turn then stops."""
    calls = list(tool_sequence)
    state = {"i": 0}

    class _Fn:
        def __init__(self, name: str, arguments: str) -> None:
            self.name = name
            self.arguments = arguments

    class _Tc:
        def __init__(self, name: str, args: dict) -> None:
            self.id = f"call_{state['i']}"
            self.function = _Fn(name, json.dumps(args))

    class _Completions:
        def create(self, **kwargs):  # noqa: ANN003
            if state["i"] >= len(calls):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="done", tool_calls=[])
                        )
                    ]
                )
            name, args = calls[state["i"]]
            state["i"] += 1
            tc = _Tc(name, args)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="", tool_calls=[tc])
                    )
                ]
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))


# --- R0 / inventory invariants -------------------------------------------------


def test_hdt_every_analysis_delivery_stage_has_run_stage_tool() -> None:
    names = {s.name for s in stage_tool_specs() if s.name.startswith("run_stage_")}
    for sid in (*ANALYSIS_ORDER, *DELIVERY_ORDER):
        assert f"run_stage_{sid}" in names, sid


def test_hdt_ship_stages_subset_of_delivery_order() -> None:
    for sid in SHIP_AFTER_MASTER:
        assert sid in DELIVERY_ORDER


def test_hdt_gate_categories_stable() -> None:
    assert "transcript_integrity" in CATEGORIES
    assert "framing_consent" in CATEGORIES
    assert "vo_pickup" in CATEGORIES


def test_hdt_heal_only_producers_documented() -> None:
    assert "nugget_layup_compose" in HEAL_ONLY_PRODUCERS
    assert "vo_line_adjudicate" in HEAL_ONLY_PRODUCERS


def test_hdt_blast_radius_defined_but_policy_incomplete() -> None:
    """R0 finding: table exists; wiring is durable Wave 1 work."""
    assert "nugget_layup_compose" in INVALIDATION_BLAST_RADIUS
    assert "junction_snip_qa" in INVALIDATION_BLAST_RADIUS
    # Policy helper exists
    assert invalidation_allowed_downstream("nugget_layup_compose", "vo_synthesize") is True
    assert invalidation_allowed_downstream("nugget_layup_compose", "mmaudio_sfx") is False


# --- 1-step tool family legal / refuse -----------------------------------------


def test_hdt_1step_walk_seed_remainder_legal() -> None:
    ctx = _ctx_010()
    client = _stub_client([("walk_seed_remainder", {"reason": "test"})])
    out = run_conductor(ctx, user_message="walk", client=client, max_turns=3)
    assert out.get("ok") is True
    assert request_walk_seed_remainder(ctx, reason="direct")["ok"] is True


def test_hdt_1step_resolve_stage_plan() -> None:
    ctx = _ctx_010()
    plan = resolve_stage_plan(ctx, "edl")
    assert plan["stage"] == "edl"
    assert "invalidate_set" in plan
    assert "recommended_next" in plan or "blockers" in plan


def test_hdt_1step_illegal_unknown_tool_soft_error() -> None:
    ctx = _ctx_010()
    client = _stub_client([("not_a_real_tool", {})])
    out = run_conductor(ctx, user_message="bad", client=client, max_turns=3)
    assert out.get("ok") is True  # unknown tool returns error payload, does not crash


# --- Invalidate modes ---------------------------------------------------------


def test_hdt_heal_only_when_fingerprints_match_checkpoint() -> None:
    ctx = _ctx_010()
    from interview_mux.delivery_guardrails import (
        CHECKPOINT_REL,
        fingerprints_match_checkpoint,
        selection_order_fingerprints,
    )

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_002"]},
        skip_handoff=True,
    )
    fps = selection_order_fingerprints(ctx)
    order_fp = str(fps.get("order") or "")
    ctx.write_json(
        CHECKPOINT_REL,
        {"order_fingerprint": order_fp, "sealed_at": "2020-01-01T00:00:00Z"},
        skip_handoff=True,
    )
    dest = ctx.path("master/assembly_preview.wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"RIFF....")
    ctx.mark_done("nugget_layup_compose", force=True)
    assert fingerprints_match_checkpoint(ctx) is True
    assert invalidation_is_structural(ctx, "nugget_layup_compose") is False
    # Unlock epoch so structural refuse does not fire if seal stamps lock
    from interview_mux.delivery_guardrails import unlock_delivery_epoch

    unlock_delivery_epoch(ctx, "test_heal_only")
    result = invalidate_downstream(ctx, "nugget_layup_compose")
    assert result.get("mode") == "heal_only"


def test_hdt_structural_invalidate_non_heal_producer() -> None:
    ctx = _ctx_010()
    from interview_mux.delivery_guardrails import unlock_delivery_epoch

    unlock_delivery_epoch(ctx, "test_structural")
    assert invalidation_is_structural(ctx, "edl") is True
    ctx.mark_done("edl", force=True)
    ctx.mark_done("mix", force=True)
    result = invalidate_downstream(ctx, "edl")
    assert result.get("ok") is True
    assert result.get("mode") != "heal_only"
    assert not ctx.is_done("edl")


def test_hdt_epoch_locked_refuses_structural_invalidate() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "delivery_epoch": {
                "locked": True,
                "phase_a_sealed_at": "2020-01-01T00:00:00Z",
                "structural_bump_at": "2020-01-01T00:00:00Z",
            },
        },
    )
    from interview_mux.delivery_guardrails import delivery_epoch_locked

    assert delivery_epoch_locked(ctx) is True
    with pytest.raises(RuntimeError, match="epoch locked|unlock"):
        invalidate_downstream(ctx, "edl")


# --- Filter / skip-then-consume -----------------------------------------------


def test_hdt_filter_defers_music_without_assembly() -> None:
    ctx = _ctx_010()
    remaining = ["music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx", "topic_coverage_audit"]
    filtered = filter_delivery_candidates(ctx, remaining)
    for sid in ("music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx"):
        assert sid not in filtered


def test_hdt_2step_skip_then_consume_consumer_still_incomplete() -> None:
    """skip producer should not make consumer seed-complete."""
    ctx = _ctx_010()
    # Mark edl done hollow — no edl.json
    ctx.mark_done("edl", force=True)
    assert seed_stage_complete(ctx, "edl") is False
    client = _stub_client(
        [
            ("skip_stage", {"stage": "vo_synthesize", "reason": "test", "compensating_fact": "x"}),
            ("run_stage_edl", {"stage": "edl"}),
        ]
    )
    run_conductor(ctx, user_message="skip then edl", client=client, max_turns=6)
    # Consumer must not become complete without artifacts
    assert seed_stage_complete(ctx, "edl") is False


# --- Remaster cascades / ADG --------------------------------------------------


def test_hdt_adg_impact_chain_length_layup() -> None:
    inv = transitive_invalidate("nugget_layup_compose")
    assert len(inv) >= 3
    # Depth budget for stub: min(max(len,3), 8)
    budget = min(max(len(inv), 3), 8)
    assert 3 <= budget <= 8


def test_hdt_3step_rerun_with_impact_clears_and_pins_earliest() -> None:
    ctx = _ctx_010()
    from interview_mux.delivery_guardrails import unlock_delivery_epoch

    unlock_delivery_epoch(ctx, "test_impact")
    for sid in ("transitions", "vo_synthesize", "edl", "mix"):
        ctx.mark_done(sid, force=True)
    # Use transitions (not heal-only) so impact does structural clear
    out = rerun_with_impact(ctx, "transitions")
    assert out.get("ok") is True
    assert "invalidate_set" in out
    assert len(out["invalidate_set"]) >= 1
    assert not ctx.is_done("transitions")


def test_hdt_delivery_phase_axis_values() -> None:
    ctx = _ctx_010()
    assert current_delivery_phase(ctx) in {"A", "B", "C", "D", "E"}
    dest = ctx.path("master/master.wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"RIFF")
    ctx.mark_done("master_finalize", force=True)
    assert current_delivery_phase(ctx) == "E"


# --- Walk reasons vocabulary --------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        "walk_seed_remainder",
        "delivery_needs_analysis",
        "delivery_walk_to_master",
        "delivery_walk_unpublishable_master",
        "delivery_walk_to_publish",
        "analysis_fill_delivery_prereqs",
    ],
)
def test_hdt_walk_reason_strings_are_stable(reason: str) -> None:
    """Contract: agenda uses these reason= strings — harness must keep them reachable."""
    agenda = Path("src/interview_mux/homunculus/agenda.py").read_text(encoding="utf-8")
    assert f'reason="{reason}"' in agenda or f"reason='{reason}'" in agenda or reason in agenda


# --- Docs deliverables exist --------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "docs/v2/homunculus-010-hdt-axes.md",
        "docs/v2/homunculus-010-gate-combo-matrix.md",
        "docs/v2/homunculus-010-input-variance.md",
        "docs/v2/homunculus-010-stage-edge-matrix.md",
        "docs/v2/homunculus-010-flow-pattern-breaks.md",
        "docs/v2/homunculus-010-prompt-host-parity.md",
        "docs/v2/homunculus-010-hdt-coverage-ledger.md",
        ".cursor/plans/homunculus-010-hdt-coverage-ledger.json",
    ],
)
def test_hdt_research_artifacts_exist(rel: str) -> None:
    assert Path(rel).is_file(), rel


def test_hdt_stage_edge_matrix_lists_every_stage() -> None:
    text = Path("docs/v2/homunculus-010-stage-edge-matrix.md").read_text(encoding="utf-8")
    for sid in (*ANALYSIS_ORDER, *DELIVERY_ORDER):
        assert f"`{sid}`" in text, sid


def test_hdt_coverage_ledger_has_high_severity_backlog() -> None:
    doc = json.loads(
        Path(".cursor/plans/homunculus-010-hdt-coverage-ledger.json").read_text(encoding="utf-8")
    )
    rows = doc["high_severity_uncovered_for_durable"]
    assert any(r["id"] == "blast-radius-unwired" for r in rows)
    assert doc["counts"]["blast_radius_wired"] is False


def test_hdt_music_epoch_incomplete_without_assets() -> None:
    ctx = _ctx_010()
    assert music_epoch_complete(ctx) is False


def test_hdt_unmark_stage_only_does_not_clear_others() -> None:
    ctx = _ctx_010()
    ctx.mark_done("edl", force=True)
    ctx.mark_done("mix", force=True)
    unmark_stage_only(ctx, "edl")
    assert not ctx.is_done("edl")
    assert ctx.is_done("mix")
