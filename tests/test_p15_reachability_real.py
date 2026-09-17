"""p15-reachability-real (§5.5): halt only on a *proven* severed ship path.

The asymmetry is the whole design. A false UNREACHABLE throws away a run that would
have shipped — exec_11871 only landed a master because it ground on through 54
patches. A false REACHABLE just keeps walking, which the caps, the no-delta guard and
the attempt memo already bound. So every unknown resolves to reachable, and the only
halt is "a required artifact with no surviving producer".

The contract pair this file exists for:

* ``test_defect_severing_a_master_required_artifact_halts``
* ``test_defect_on_a_cosmetic_artifact_never_halts``
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from interview_mux.artifact_ownership import write_permitted
from interview_mux.defect_ledger import record_defect
from interview_mux.run_context import RunContext
from interview_mux.ship_reachability import (
    REACHABILITY_REL,
    TERMINAL_BLOCKERS,
    Reachability,
    ShipUnreachable,
    critical_path,
    halt_enabled,
    halt_payload,
    producers_for_path,
    proven_unreachable,
    requirement_satisfied,
    severed_requirements,
    ship_reachable,
    unreachable_halt,
)
from run_fixtures import isolated_run_ctx


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    return ctx


def _declare_master_needs_assembly(monkeypatch) -> None:
    """Give ``master_finalize`` the hard input its contract does not declare yet.

    Both `master_finalize.yaml` and `mix.yaml` still carry `inputs.hard: []`, so on
    today's tree nothing about the master is provable. This patch simulates the
    contract the other worker is filling in, which is exactly how the analysis will
    strengthen — the module reads the contract, it does not carry a stage list.
    """
    from interview_mux import stage_contract
    from interview_mux.stage_contract import InputDep, StageContract

    real = stage_contract.load_contract

    def fake(stage_id: str):
        if stage_id == "master_finalize":
            return StageContract(
                stage_id="master_finalize",
                tier="process",
                inputs=[InputDep(path="master/assembly.wav", hard=True, producer="mix")],
            )
        return real(stage_id)

    monkeypatch.setattr(stage_contract, "load_contract", fake)


def _cap_defect(ctx: RunContext, stage: str, artifact: str = "") -> dict:
    return record_defect(
        ctx,
        stage=stage,
        blocker="max_mix_cycles" if stage == "mix" else "max_invokes_per_identity",
        artifact=artifact,
    )


def _kill_producer(ctx: RunContext, stage: str, artifact: str = "") -> dict:
    """Spend the stage's dispatch cap for real, then record the resulting defect.

    Severance needs a producer the door will refuse *now*, not just a ledger row, so
    tests that want a dead producer have to burn the cap the way the walk does.
    """
    from interview_mux.homunculus.ledger import append_ledger

    for _ in range(9):
        append_ledger(ctx, {"kind": "stage", "identity": stage, "status": "started"})
    return _cap_defect(ctx, stage, artifact)


# ---------------------------------------------------------------------------
# the load-bearing pair
# ---------------------------------------------------------------------------

def test_defect_severing_a_master_required_artifact_halts(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _ctx(tmp_path, "reach_severed")
    _declare_master_needs_assembly(monkeypatch)
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")

    _kill_producer(ctx, "mix", "master/assembly.wav")

    severed = severed_requirements(ctx)
    assert [s["artifact"] for s in severed] == ["master/assembly.wav"]
    reach = ship_reachable(ctx)
    assert (reach.reachable, reach.certain) == (False, True)
    assert proven_unreachable(ctx) is True

    payload = unreachable_halt(ctx)
    assert payload is not None
    # §10.2: the halt message is the product — unmet dep, its producer, resume pin.
    assert payload["blockers"] == ["master/assembly.wav"]
    assert payload["unmet"][0]["producers"] == ["mix"]
    assert payload["resume"] == "mix"
    assert ctx.artifact_exists(REACHABILITY_REL)


def test_defect_on_a_cosmetic_artifact_never_halts(tmp_path: Path, monkeypatch) -> None:
    """A dead SFX/cover producer is not on the master's critical path."""
    ctx = _ctx(tmp_path, "reach_cosmetic")
    _declare_master_needs_assembly(monkeypatch)
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")

    _kill_producer(ctx, "mmaudio_sfx", "master/sfx/manifest.json")
    _kill_producer(ctx, "episode_cover_generate", "publish/cover.jpg")

    assert severed_requirements(ctx) == []
    reach = ship_reachable(ctx)
    assert (reach.reachable, reach.certain) == (True, False)
    assert unreachable_halt(ctx) is None
    assert halt_payload(ctx) is None


# ---------------------------------------------------------------------------
# unknown never severs
# ---------------------------------------------------------------------------

def test_the_master_chain_is_now_declared_and_walkable(tmp_path: Path) -> None:
    """`master_finalize` declares the assembly, so the critical path is real.

    This test used to assert the opposite — that the master's contract was hollow
    and therefore nothing was provable. `master_finalize` now declares
    `master/assembly.wav` hard (its `master_wav` call raises `FileNotFoundError`
    without it) and `mix` declares `ingest/normalized.wav`, so the walk resolves
    master <- assembly <- mix <- source tape instead of stopping at an unknown.

    Killing mix's producer no longer leaves `master_finalize` unknown, and that
    is the whole point: an exhausted `mix` is now *provably* severing, where a
    hollow contract could only ever answer "uncertain, therefore reachable".
    """
    ctx = _ctx(tmp_path, "reach_hollow")
    _kill_producer(ctx, "mix", "master/assembly.wav")

    path = critical_path(ctx)
    required = {(r.path, r.required_by) for r in path.requirements}
    assert ("master/assembly.wav", "master_finalize") in required
    # The source tape is required, but `required_by` names the *first* consumer the
    # walk reaches — requirements dedupe by path. Since the selection chain became
    # walkable (`correctness`-marked soft deps, `test_ship_reachability_correctness.py`)
    # the walk gets to `transcribe` before `mix`, so pin the requirement and its
    # producer rather than which consumer happened to claim it.
    tape = path.by_path()["ingest/normalized.wav"]
    assert tape.producers == ("ingest",)
    assert "master_finalize" not in path.unknown_stages

    severed = severed_requirements(ctx)
    assert [r["artifact"] for r in severed] == ["master/assembly.wav"]
    assert severed[0]["producers"] == ["mix"]
    assert proven_unreachable(ctx) is True


def test_critical_path_root_is_derived_not_pinned() -> None:
    path = critical_path(None)
    assert path.root_producers == ("master_finalize",)
    assert producers_for_path("master/assembly.wav")[0] == "mix"
    assert producers_for_path("nonexistent/artifact.json") == ()


def test_unknown_producer_cannot_prove_severance(tmp_path: Path, monkeypatch) -> None:
    from interview_mux import ship_reachability

    ctx = _ctx(tmp_path, "reach_unknown_producer")
    _declare_master_needs_assembly(monkeypatch)
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")
    _kill_producer(ctx, "mix", "master/assembly.wav")
    # Producer resolution fails ⇒ no producers ⇒ no severance.
    monkeypatch.setattr(ship_reachability, "producers_for_path", lambda _rel: ())
    assert severed_requirements(ctx) == []


@pytest.mark.parametrize("blocker", ["no_delta", "attempt_memo"])
def test_soft_refusals_are_not_terminal(tmp_path: Path, monkeypatch, blocker: str) -> None:
    """no_delta means the outputs exist; the memo clears on the next state delta."""
    ctx = _ctx(tmp_path, f"reach_soft_{blocker}")
    _declare_master_needs_assembly(monkeypatch)
    record_defect(ctx, stage="mix", blocker=blocker, artifact="master/assembly.wav")
    assert blocker not in TERMINAL_BLOCKERS
    assert severed_requirements(ctx) == []


def test_open_operator_gate_keeps_the_path_alive(tmp_path: Path, monkeypatch) -> None:
    from interview_mux.homunculus import gates

    ctx = _ctx(tmp_path, "reach_gate")
    _declare_master_needs_assembly(monkeypatch)
    _kill_producer(ctx, "mix", "master/assembly.wav")
    monkeypatch.setattr(
        gates,
        "category_status",
        lambda _c: {"transcript_integrity": {"open": True}},
    )
    assert severed_requirements(ctx) == []


def test_repair_plan_pin_keeps_the_path_alive(tmp_path: Path, monkeypatch) -> None:
    from interview_mux import remediation_framework

    ctx = _ctx(tmp_path, "reach_repair")
    _declare_master_needs_assembly(monkeypatch)
    _kill_producer(ctx, "mix", "master/assembly.wav")
    monkeypatch.setattr(
        remediation_framework,
        "read_active_remediation_plan",
        lambda _c: {"allowed_rerun_stages": ["mix"], "resume_stage": "mix"},
    )
    assert severed_requirements(ctx) == []


# ---------------------------------------------------------------------------
# satisfaction: existing on disk is not satisfying
# ---------------------------------------------------------------------------

def test_hollow_artifact_on_disk_does_not_satisfy_the_requirement(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _ctx(tmp_path, "reach_hollow_wav")
    _declare_master_needs_assembly(monkeypatch)
    _kill_producer(ctx, "mix", "master/assembly.wav")

    assembly = ctx.path("master/assembly.wav")
    assembly.parent.mkdir(parents=True, exist_ok=True)
    assembly.write_bytes(b"")
    assert requirement_satisfied(ctx, "master/assembly.wav", "master_finalize") is False
    assert [s["artifact"] for s in severed_requirements(ctx)] == ["master/assembly.wav"]


def test_a_satisfied_requirement_is_never_severed(tmp_path: Path, monkeypatch) -> None:
    from interview_mux import ship_reachability

    ctx = _ctx(tmp_path, "reach_satisfied")
    _declare_master_needs_assembly(monkeypatch)
    _kill_producer(ctx, "mix", "master/assembly.wav")
    monkeypatch.setattr(
        ship_reachability, "requirement_satisfied", lambda *_a, **_k: True
    )
    assert severed_requirements(ctx) == []


# ---------------------------------------------------------------------------
# monotonicity: declaring more inputs may never flip reachable → unreachable
# ---------------------------------------------------------------------------

def _declare_master_needs(monkeypatch, paths: list[tuple[str, str]]) -> None:
    from interview_mux import stage_contract
    from interview_mux.stage_contract import InputDep, StageContract

    real = stage_contract.load_contract

    def fake(stage_id: str):
        if stage_id == "master_finalize":
            return StageContract(
                stage_id="master_finalize",
                tier="process",
                inputs=[
                    InputDep(path=rel, hard=True, producer=producer)
                    for rel, producer in paths
                ],
            )
        return real(stage_id)

    monkeypatch.setattr(stage_contract, "load_contract", fake)


def test_declaring_more_hard_inputs_cannot_flip_reachable_to_unreachable(
    tmp_path: Path, monkeypatch
) -> None:
    """Contract population is live; growing the declared set must stay reachable.

    Every one of these artifacts is absent on disk. Absence is work not yet done —
    only a producer that can no longer run makes it severance.
    """
    ctx = _ctx(tmp_path, "reach_monotonic")
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")
    declared: list[tuple[str, str]] = []
    for rel, producer in (
        ("master/assembly.wav", "mix"),
        ("master/edl.json", "edl"),
        ("master/selection.json", "full_master_ranking"),
        ("master/transitions.json", "transitions"),
        ("understanding/sound_design_plan.json", "sound_design_plan"),
    ):
        declared.append((rel, producer))
        _declare_master_needs(monkeypatch, declared)
        assert not ctx.artifact_exists(rel)
        assert severed_requirements(ctx) == [], f"absence of {rel} became severance"
        reach = ship_reachable(ctx)
        assert (reach.reachable, reach.certain) == (True, False)
        assert unreachable_halt(ctx) is None
    # The declarations did land — the requirements are being read, not ignored.
    assert len(critical_path(ctx).requirements) >= len(declared)


def test_a_stale_terminal_defect_row_alone_cannot_halt(tmp_path: Path, monkeypatch) -> None:
    """The ledger row is necessary but not sufficient — live budget state decides.

    Here `mix` carries an open spent-cap defect but has no dispatch attempts on the
    ledger, so the door would let it run. That is a runnable producer, so the missing
    artifact stays "not yet done".
    """
    from interview_mux.ship_reachability import producer_runnable

    ctx = _ctx(tmp_path, "reach_stale_row")
    _declare_master_needs(monkeypatch, [("master/assembly.wav", "mix")])
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")
    _cap_defect(ctx, "mix", "master/assembly.wav")  # row only — cap not actually spent

    assert producer_runnable(ctx, "mix") is True
    assert severed_requirements(ctx) == []
    assert unreachable_halt(ctx) is None


def test_producer_runnable_follows_the_live_cap(tmp_path: Path, monkeypatch) -> None:
    from interview_mux.homunculus.ledger import append_ledger
    from interview_mux.ship_reachability import producer_runnable

    ctx = _ctx(tmp_path, "reach_runnable")
    assert producer_runnable(ctx, "mix") is True
    for _ in range(9):
        append_ledger(ctx, {"kind": "stage", "identity": "mix", "status": "started"})
    assert producer_runnable(ctx, "mix") is False
    # An unknown identity is assumed runnable rather than dead.
    assert producer_runnable(ctx, "") is True


def test_committed_master_is_proven_reachable(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, "reach_committed")
    _declare_master_needs_assembly(monkeypatch)
    _cap_defect(ctx, "mix", "master/assembly.wav")
    ctx.final_path("master").mkdir(parents=True, exist_ok=True)
    ctx.final_path("master", "master.wav").write_bytes(b"RIFF" + b"\0" * 64)
    reach = ship_reachable(ctx)
    assert (reach.reachable, reach.certain, reach.reason) == (True, True, "master_committed")


# ---------------------------------------------------------------------------
# kill switch + walk wiring
# ---------------------------------------------------------------------------

def test_halt_defaults_off_and_records_the_verdict(tmp_path: Path, monkeypatch) -> None:
    """Safe default: prove it, log it, keep walking unless the operator opts in."""
    monkeypatch.delenv("MUX_SHIP_REACHABILITY_HALT", raising=False)
    ctx = _ctx(tmp_path, "reach_switch_off")
    _declare_master_needs_assembly(monkeypatch)
    _kill_producer(ctx, "mix", "master/assembly.wav")

    assert halt_enabled() is False
    assert proven_unreachable(ctx) is True
    assert unreachable_halt(ctx) is None
    doc = ctx.read_json(REACHABILITY_REL)
    assert doc["resume"] == "mix"
    assert doc["halt_enabled"] is False


def test_walk_halts_on_a_severed_path_only_with_the_switch_on(
    tmp_path: Path, monkeypatch
) -> None:
    """End to end through the walk: refuse, record, then halt only when armed."""
    from interview_mux import pipeline, stage_contract
    from interview_mux.homunculus import agenda
    from interview_mux.homunculus.ledger import append_ledger
    from interview_mux.stage_contract import InputDep, StageContract

    stage = "vernacular_segment_sanitize"
    artifact = "vernacular/resplit_report.json"
    real = stage_contract.load_contract

    def fake(stage_id: str):
        if stage_id == "master_finalize":
            return StageContract(
                stage_id="master_finalize",
                tier="process",
                inputs=[InputDep(path=artifact, hard=True, producer=stage)],
            )
        return real(stage_id)

    monkeypatch.setattr(stage_contract, "load_contract", fake)

    ctx = _ctx(tmp_path, "reach_walk")
    calls: list[str] = []
    monkeypatch.setattr(pipeline, "run_single_stage", lambda _c, sid: calls.append(sid))
    # Spend the stage's cap so the door refuses it on the walk.
    for _ in range(9):
        append_ledger(ctx, {"kind": "stage", "identity": stage, "status": "started"})

    monkeypatch.delenv("MUX_SHIP_REACHABILITY_HALT", raising=False)
    agenda.walk_seed_agenda(ctx, [stage], reason="delivery_walk_to_master")
    assert calls == []  # refused, defect recorded, walk advanced past it

    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")
    with pytest.raises(ShipUnreachable) as err:
        agenda.walk_seed_agenda(ctx, [stage], reason="delivery_walk_to_master")
    assert artifact in str(err.value)
    assert err.value.payload["resume"] == stage


# ---------------------------------------------------------------------------
# keep walking, but refuse to publish
# ---------------------------------------------------------------------------

def test_advancing_past_a_blocker_cannot_quietly_ship(tmp_path: Path) -> None:
    """Open ship-bar defect ⇒ publish_allowed false ⇒ the boundary blocks finalize."""
    from interview_mux import post_master_quality as pmq
    from interview_mux.publishability_boundary import validate_publishability

    ctx = _ctx(tmp_path, "reach_publish")
    record_defect(ctx, stage="mix", blocker="max_mix_cycles", artifact="master/assembly.wav")

    out = pmq.evaluate_post_master_quality(ctx)
    row = next(c for c in out["checks"] if c["check_id"] == "no_open_ship_bar_defects")
    assert row["passed"] is False
    assert out["publish_allowed"] is False

    ctx.write_json("master/post_master_quality.json", out, skip_handoff=True)
    report = validate_publishability(ctx, checkpoint="pre_finalize")
    codes = [v.code for v in report.violations]
    assert "pmq_not_publishable" in codes


def test_reachability_artifact_has_an_ownership_allow_row() -> None:
    ok, reason = write_permitted(None, REACHABILITY_REL, "ops", role="ops")
    assert ok, reason
    assert reason == "operational"


# ---------------------------------------------------------------------------
# signatures the solver worker composes with
# ---------------------------------------------------------------------------

def test_solver_facing_signatures_are_stable(tmp_path: Path) -> None:
    import inspect

    from interview_mux.dispatch_door import DispatchVerdict, evaluate_dispatch

    ctx = _ctx(tmp_path, "reach_signature")
    reach = ship_reachable(ctx)
    assert isinstance(reach, Reachability)
    assert set(reach.as_row()) == {"reachable", "certain", "reason", "blockers", "detail"}
    # Positional construction still works for callers built against the stub.
    assert Reachability(True, False, "x").blockers == ()

    sig = inspect.signature(evaluate_dispatch)
    assert list(sig.parameters) == ["ctx", "stage", "source", "layer"]
    verdict = evaluate_dispatch(ctx, "mix", source="driver", layer="walk")
    assert isinstance(verdict, DispatchVerdict)
    assert os.environ.get("MUX_DISPATCH_DOOR") in (None, "", "1", "true")
