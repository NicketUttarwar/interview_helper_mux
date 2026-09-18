"""`correctness`-marked soft inputs: reachability sees the selection chain.

`ship_reachability.critical_path()` used to walk *hard* inputs only, and stages
between the source tape and the master declared almost everything soft. The
whole path was therefore:

    ingest/normalized.wav   producer=ingest  required_by=mix
    master/assembly.wav     producer=mix     required_by=master_finalize

No EDL, no selection, no transitions — so a dead `full_master_ranking` could not
sever anything, and the run would walk on to build a master out of whatever
`mix` found lying around.

MIX-B1 promotes mix's EDL + SDP to hard (matches `_check_mix`). Remaining
`correctness` soft markers on other stages still widen the critical path for
rows that must stay soft on the dispatch path (e.g. master_finalize←edl was
already hard; transitions←edl soft+correctness). `ship_reachability` reads
`stage_contract.correctness_required`; every dispatch consumer still filters on
`dep.hard` alone.

What this does *not* do: reachability answers "is the goal still attainable", not
"did the required work happen". A live `full_master_ranking` that writes a bad
selection is the defect-on-bad-output sweep's problem, not this module's.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from interview_mux.defect_ledger import record_defect
from interview_mux.run_context import RunContext
from interview_mux.ship_reachability import (
    critical_path,
    producer_runnable,
    producers_for_path,
    severed_requirements,
    ship_reachable,
)
from interview_mux.stage_contract import (
    all_contract_stage_ids,
    correctness_required,
    load_contract,
)
from run_fixtures import MINIMAL_WAV_BYTES, isolated_run_ctx

# Correctness soft markers after MIX-B1 / edl+finalize promotions:
# JSQ-B4 keeps junction←selection soft+correctness (matches `_check`).
EXPECTED_MARKERS: set[tuple[str, str]] = {
    ("junction_snip_qa", "master/selection.json"),
}

# Stages whose dispatch posture hard-vs-correctness must stay stable.
MARKED_STAGES = ("mix", "master_finalize", "junction_snip_qa", "edl")


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    return ctx


def _kill_producer(ctx: RunContext, stage: str) -> None:
    """Spend the stage's dispatch cap for real, then record the resulting defect.

    Severance needs a producer the door refuses *now*: `producer_runnable` reads
    live budget state, so a ledger row on its own proves nothing.
    """
    from interview_mux.homunculus.budget import attempt_cap
    from interview_mux.homunculus.ledger import append_ledger

    cap, blocker = attempt_cap(stage)
    for _ in range(cap + 1):
        append_ledger(ctx, {"kind": "stage", "identity": stage, "status": "started"})
    record_defect(ctx, stage=stage, blocker=str(blocker), artifact="")
    assert producer_runnable(ctx, stage) is False, stage


def _markers_stripped(monkeypatch) -> None:
    """Serve every contract with `correctness` cleared — the pre-marker tree."""
    from interview_mux import stage_contract

    real = stage_contract.load_contract

    def fake(stage_id: str):
        contract = real(stage_id)
        if contract is None:
            return None
        return replace(
            contract,
            inputs=[replace(dep, correctness=False) for dep in contract.inputs],
        )

    monkeypatch.setattr(stage_contract, "load_contract", fake)


# ---------------------------------------------------------------------------
# the chain is visible
# ---------------------------------------------------------------------------

def test_the_selection_chain_is_on_the_critical_path() -> None:
    path = critical_path(None)
    by_path = path.by_path()

    for rel, producer in (
        ("master/selection.json", "full_master_ranking"),
        ("master/edl.json", "edl"),
        ("master/transitions.json", "transitions"),
        ("master/assembly.wav", "mix"),
    ):
        assert rel in by_path, f"{rel} is not on the critical path"
        assert producer in by_path[rel].producers, f"{producer} does not produce {rel}"

    # The producers themselves were walked, which is what makes them severable.
    walked = {p for req in path.requirements for p in req.producers}
    assert {"full_master_ranking", "edl", "transitions", "mix"} <= walked


def test_marked_rows_are_exactly_the_declared_minimum() -> None:
    found = {
        (sid, dep.path)
        for sid in all_contract_stage_ids()
        if (contract := load_contract(sid)) is not None
        for dep in contract.inputs
        if dep.correctness
    }
    assert found == EXPECTED_MARKERS


def test_the_render_ledger_is_deliberately_not_marked() -> None:
    """`render_ledger_exists` is advisory under the default aspirational policy.

    A missing render ledger does not block publish by the project's own contract,
    so `junction_snip_qa` must not be pulled onto the path as a required producer.
    """
    from interview_mux.aspirational_quality import RUBRIC_PMQ_CHECKS

    assert "render_ledger_exists" in RUBRIC_PMQ_CHECKS
    contract = load_contract("master_finalize")
    assert contract is not None
    ledger = next(d for d in contract.inputs if d.path == "master/render_ledger.json")
    assert ledger.correctness is False
    assert "master/render_ledger.json" not in critical_path(None).by_path()


# ---------------------------------------------------------------------------
# a dead selection producer can now halt the run
# ---------------------------------------------------------------------------

def test_a_dead_selection_chain_is_a_real_severance(tmp_path: Path, monkeypatch) -> None:
    """Every producer of the selection dead ⇒ proven unreachable, not "reachable"."""
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")
    ctx = _ctx(tmp_path, "corr_severed")

    producers = producers_for_path("master/selection.json")
    assert "full_master_ranking" in producers
    for stage in producers:
        _kill_producer(ctx, stage)

    severed = severed_requirements(ctx)
    assert "master/selection.json" in [row["artifact"] for row in severed]
    row = next(r for r in severed if r["artifact"] == "master/selection.json")
    assert row["resume"] == "full_master_ranking"

    reach = ship_reachable(ctx)
    assert (reach.reachable, reach.certain) == (False, True)
    assert "master/selection.json" in reach.blockers


def test_one_surviving_selection_producer_keeps_the_path_alive(
    tmp_path: Path, monkeypatch
) -> None:
    """Severance needs *every* producer dead — `producer_runnable` semantics."""
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")
    ctx = _ctx(tmp_path, "corr_survivor")

    producers = producers_for_path("master/selection.json")
    for stage in producers[1:]:
        _kill_producer(ctx, stage)
    assert producer_runnable(ctx, producers[0]) is True

    severed = [row["artifact"] for row in severed_requirements(ctx)]
    assert "master/selection.json" not in severed


# ---------------------------------------------------------------------------
# monotonicity: marking more may never flip reachable -> unreachable
# ---------------------------------------------------------------------------

def test_the_markers_alone_cannot_make_a_run_unreachable(tmp_path: Path, monkeypatch) -> None:
    """Nothing on the chain exists on a fresh run, and that is not severance.

    This is the same direction `test_declaring_more_hard_inputs_cannot_flip_
    reachable_to_unreachable` pins for hard inputs: absence is work not yet done.
    Every producer is runnable here, so the enlarged requirement set must stay
    reachable — with the markers *and* without them.
    """
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")
    ctx = _ctx(tmp_path, "corr_monotonic")

    for rel in ("master/selection.json", "master/edl.json", "master/transitions.json"):
        assert not ctx.artifact_exists(rel)

    with_markers = ship_reachable(ctx)
    assert severed_requirements(ctx) == []
    assert (with_markers.reachable, with_markers.certain) == (True, False)

    marked_path = critical_path(ctx)
    _markers_stripped(monkeypatch)
    plain_path = critical_path(ctx)
    plain = ship_reachable(ctx)

    # Markers may be empty (MIX-B1 + _CORRECTNESS_TO_HARD): path is monotone
    # non-decreasing when markers are stripped, never smaller with markers.
    assert set(plain_path.by_path()) <= set(marked_path.by_path())
    assert (plain.reachable, plain.certain) == (with_markers.reachable, with_markers.certain)


def test_a_marked_requirement_severs_only_with_a_dead_producer(
    tmp_path: Path, monkeypatch
) -> None:
    """A terminal defect elsewhere does not make the marked rows severing."""
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")
    ctx = _ctx(tmp_path, "corr_elsewhere")
    _kill_producer(ctx, "episode_cover_generate")

    assert severed_requirements(ctx) == []
    reach = ship_reachable(ctx)
    assert (reach.reachable, reach.certain) == (True, False)


# ---------------------------------------------------------------------------
# dispatch must not notice
# ---------------------------------------------------------------------------

def test_every_marked_row_is_still_soft() -> None:
    for sid in all_contract_stage_ids():
        contract = load_contract(sid)
        if contract is None:
            continue
        for dep in contract.inputs:
            if not dep.correctness:
                continue
            assert dep.hard is False, f"{sid}:{dep.path} was promoted to hard"
            assert correctness_required(dep) is True


def test_mix_declares_tape_selection_edl_sdp_hard() -> None:
    """MIX-B1: hard matches `_check_mix` (tape + selection + edl + SDP)."""
    contract = load_contract("mix")
    assert contract is not None
    assert [d.path for d in contract.inputs if d.hard] == [
        "ingest/normalized.wav",
        "master/selection.json",
        "master/edl.json",
        "understanding/sound_design_plan.json",
    ]


def test_mix_contract_lifecycle_is_non_llm() -> None:
    """MIX-B5: mix is a deterministic host — contract must not claim llm_execute."""
    contract = load_contract("mix")
    assert contract is not None
    assert contract.tier == "process"
    assert "llm_execute" not in contract.lifecycle_phases
    assert "execute" in contract.lifecycle_phases


def test_master_finalize_contract_lifecycle_is_non_llm() -> None:
    """MF-B4: process host — contract must not claim llm_execute."""
    contract = load_contract("master_finalize")
    assert contract is not None
    assert contract.tier == "process"
    assert "llm_execute" not in contract.lifecycle_phases
    assert "execute" in contract.lifecycle_phases


def test_master_finalize_stageinfo_mentions_pmq_and_delight() -> None:
    """MF-B1: StageInfo must name PMQ + authoritative listen-delight, not loudness-only."""
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID["master_finalize"]
    desc = info.description.lower()
    assert "post-master quality" in desc or "pmq" in desc
    assert "listen-delight" in desc or "listen delight" in desc
    assert "−16 lufs" in desc or "-16 lufs" in desc or "loudness" in desc


def test_dispatch_delta_hash_set_is_unchanged(tmp_path: Path, monkeypatch) -> None:
    """`hard_input_paths` — including the read-modify-write stripping.

    The `declared` set it strips against is built from *all* `inputs`, hard and
    soft, which is exactly why the marker had to live on the existing soft row
    rather than in a third list.
    """
    from interview_mux.dispatch_delta import hard_input_paths

    ctx = _ctx(tmp_path, "corr_delta")
    stages = all_contract_stage_ids()
    marked = {sid: hard_input_paths(ctx, sid) for sid in stages}
    _markers_stripped(monkeypatch)
    plain = {sid: hard_input_paths(ctx, sid) for sid in stages}
    assert marked == plain


def test_prestage_checks_are_unchanged(tmp_path: Path, monkeypatch) -> None:
    """`artifact_lifecycle.run_phase_checks` — the PRESTAGE refusal door."""
    from interview_mux.artifact_lifecycle import LifecyclePhase, run_phase_checks

    ctx = _ctx(tmp_path, "corr_prestage")
    tape = ctx.path("ingest/normalized.wav")
    tape.parent.mkdir(parents=True, exist_ok=True)
    tape.write_bytes(MINIMAL_WAV_BYTES)

    marked = {
        sid: run_phase_checks(ctx, sid, LifecyclePhase.PRESTAGE) for sid in MARKED_STAGES
    }
    # Lenient PRESTAGE: absent hard inputs refuse via `prestage_refused`, they do
    # not return fatal errors. MIX-B1 hard EDL must not change that posture —
    # junction_recut_precedes_mix still flips seed order while incomplete cuts live.
    assert marked["mix"] == []
    assert marked["junction_snip_qa"] == []

    _markers_stripped(monkeypatch)
    plain = {
        sid: run_phase_checks(ctx, sid, LifecyclePhase.PRESTAGE) for sid in MARKED_STAGES
    }
    assert marked == plain


def test_the_runtime_gate_safety_filter_sees_no_new_rows() -> None:
    """`tests/test_contract_runtime_gate_safety.py`'s view, recomputed here.

    That test walks every declared hard input and demands an upstream producer.
    A marked row that leaked into the hard set would show up as a downstream
    producer conflict; pinning the filtered set is the direct proof.
    """
    from interview_mux.stage_contract import is_path_spec

    for sid in all_contract_stage_ids():
        contract = load_contract(sid)
        if contract is None:
            continue
        hard = {d.path for d in contract.inputs if d.hard and d.path and not is_path_spec(d.path)}
        marked = {d.path for d in contract.inputs if d.correctness}
        assert not (hard & marked), f"{sid}: {hard & marked} is both hard and marked"


@pytest.mark.parametrize("stage", MARKED_STAGES)
def test_correctness_required_is_the_only_widening(stage: str) -> None:
    contract = load_contract(stage)
    assert contract is not None
    hard = {d.path for d in contract.inputs if d.hard}
    widened = {d.path for d in contract.inputs if correctness_required(d)}
    assert hard <= widened
    assert widened - hard == {
        rel for sid, rel in EXPECTED_MARKERS if sid == stage
    }
