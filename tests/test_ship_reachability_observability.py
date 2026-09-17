"""A failed contract READ is loud; a contract that declares nothing stays quiet.

`_contract_requirements` used to answer `hollow=True` for both, and `critical_path`
resolves hollow toward *reachable*. Since the root's requirements come solely from
its own contract, one failed read emptied the entire critical path and reported a
clean `no_proven_severance` — the wrong-master protection switched itself off and
the run still looked healthy. That is the finding-6 fail-open
(`docs/cross-cutting/ship-safety-findings.md`), and it already misled an agent into
reading 2 requirements off a marker-less tree and concluding a work item was blocked.

The fix is **observability only**. Nothing here may make a run refuse or halt: a
false UNREACHABLE throws away a shippable tape, which is the more expensive mistake
by the module's own doctrine. So these tests pin two things at once — that a read
failure is now visible, and that it still changes no verdict.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.ship_reachability import (
    REACHABILITY_REL,
    analysis_health,
    critical_path,
    halt_enabled,
    reset_swallow_telemetry,
    ship_reachable,
    swallow_telemetry,
    unreachable_halt,
)
from run_fixtures import isolated_run_ctx

LOGGER_NAME = "interview_mux.ship_reachability"

# The verified clean measurement — see finding 6. Pinned so the collapse-to-empty
# failure mode fails a test instead of passing quietly.
EXPECTED_REQUIREMENTS = 22
SELECTION_CHAIN = ("master/selection.json", "master/edl.json", "master/transitions.json")


@pytest.fixture(autouse=True)
def _clean_telemetry():
    """The counters are process-level, so a stale count must not leak in or out."""
    reset_swallow_telemetry()
    yield
    reset_swallow_telemetry()


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    return ctx


def _break_the_read(monkeypatch, *, only: str | None = None) -> None:
    """Make the contract read raise — a missing symbol or unparseable YAML."""
    from interview_mux import stage_contract

    real = stage_contract.load_contract

    def fake(stage_id: str):
        if only is None or stage_id == only:
            raise ImportError("cannot import name 'correctness_required'")
        return real(stage_id)

    monkeypatch.setattr(stage_contract, "load_contract", fake)


def _kill_producer(ctx: RunContext, stage: str) -> None:
    """Spend the stage's dispatch cap for real, then record the resulting defect.

    Needed to get the analysis to run at all: `severed_requirements` short-circuits
    before `critical_path` unless some producer is already terminally blocked.
    """
    from interview_mux.defect_ledger import record_defect
    from interview_mux.homunculus.budget import attempt_cap
    from interview_mux.homunculus.ledger import append_ledger

    cap, blocker = attempt_cap(stage)
    for _ in range(cap + 1):
        append_ledger(ctx, {"kind": "stage", "identity": stage, "status": "started"})
    record_defect(ctx, stage=stage, blocker=str(blocker), artifact="")


def _declare_nothing(monkeypatch, stage: str) -> None:
    """Serve a real contract with every correctness-required row cleared.

    This is genuine hollowness: the contract was read, and it asks for nothing.
    """
    from interview_mux import stage_contract

    real = stage_contract.load_contract

    def fake(stage_id: str):
        contract = real(stage_id)
        if contract is None or stage_id != stage:
            return contract
        return replace(
            contract,
            inputs=[replace(dep, hard=False, correctness=False) for dep in contract.inputs],
        )

    monkeypatch.setattr(stage_contract, "load_contract", fake)


# ---------------------------------------------------------------------------
# the clean measurement, pinned
# ---------------------------------------------------------------------------

def test_the_healthy_tree_reads_every_contract_and_stays_quiet() -> None:
    path = critical_path(None)

    assert len(path.requirements) == EXPECTED_REQUIREMENTS
    assert path.root_producers == ("master_finalize",)
    for rel in SELECTION_CHAIN:
        assert rel in path.by_path(), f"{rel} fell off the critical path"

    # Hollow stages are expected and fine; unreadable ones are not.
    assert path.unknown_stages, "some contracts are legitimately hollow"
    assert path.unreadable_stages == ()
    assert path.degraded is False
    assert analysis_health()["unresolved"] is False
    assert swallow_telemetry()["counts"] == {}, "a healthy tree must swallow nothing"


# ---------------------------------------------------------------------------
# unreadable is loud
# ---------------------------------------------------------------------------

def test_a_failed_contract_read_is_reported_as_unreadable(monkeypatch, caplog) -> None:
    _break_the_read(monkeypatch, only="master_finalize")

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        path = critical_path(None)

    assert path.degraded is True
    assert [row.stage for row in path.unreadable_stages] == ["master_finalize"]
    assert "ImportError" in path.unreadable_stages[0].error

    # `unknown_stages` keeps its existing meaning: an unreadable stage is still
    # hollow, so callers reading it do not shift underneath.
    assert "master_finalize" in path.unknown_stages

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "a failed contract read must not be silent"
    assert "could not READ the contract for master_finalize" in warnings[0].getMessage()


def test_a_contract_that_declares_nothing_is_hollow_but_not_unreadable(
    monkeypatch, caplog
) -> None:
    """The distinction the fix exists to draw."""
    _declare_nothing(monkeypatch, "master_finalize")

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        path = critical_path(None)

    assert "master_finalize" in path.unknown_stages
    assert path.unreadable_stages == ()
    assert path.degraded is False
    assert analysis_health()["unresolved"] is False
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_the_root_read_failing_empties_the_path_which_is_why_it_must_be_loud(
    monkeypatch,
) -> None:
    """The blast radius, pinned: one failed read at the root loses everything.

    `_graph_requirements('master_finalize')` is empty, so the root contributes
    requirements only through its contract. Without the signal this looks
    indistinguishable from a run with nothing left to prove.
    """
    _break_the_read(monkeypatch)
    path = critical_path(None)

    assert path.requirements == ()
    for rel in SELECTION_CHAIN:
        assert rel not in path.by_path()
    # ...and the reason is now on the record rather than inferred.
    assert path.degraded is True


# ---------------------------------------------------------------------------
# loud must not mean blocking
# ---------------------------------------------------------------------------

def test_a_failed_read_does_not_change_the_verdict(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MUX_SHIP_REACHABILITY_HALT", raising=False)
    ctx = _ctx(tmp_path, "exec_sr_obs_verdict")

    before = ship_reachable(ctx)
    reset_swallow_telemetry()
    _break_the_read(monkeypatch)
    after = ship_reachable(ctx)

    assert (after.reachable, after.certain, after.reason) == (
        before.reachable,
        before.certain,
        before.reason,
    )
    assert (after.reachable, after.certain) == (True, False)


def test_a_failed_read_never_halts_even_with_the_switch_armed(
    tmp_path: Path, monkeypatch
) -> None:
    """No new halt path: degraded analysis is recorded, then the walk advances.

    This is the finding-6 scenario end to end — a dead producer *and* a blind
    analysis. The guard finds nothing because it can read nothing, and the run is
    allowed to continue exactly as before. Only the record is new.
    """
    monkeypatch.setenv("MUX_SHIP_REACHABILITY_HALT", "1")
    ctx = _ctx(tmp_path, "exec_sr_obs_nohalt")
    _kill_producer(ctx, "mix")
    _break_the_read(monkeypatch)

    assert halt_enabled() is True
    assert unreachable_halt(ctx) is None  # armed, degraded, and still not halting
    reach = ship_reachable(ctx)
    assert (reach.reachable, reach.certain) == (True, False)


def test_halt_stays_defaulted_off(monkeypatch) -> None:
    monkeypatch.delenv("MUX_SHIP_REACHABILITY_HALT", raising=False)
    assert halt_enabled() is False


# ---------------------------------------------------------------------------
# the operator gets told
# ---------------------------------------------------------------------------

def test_degraded_analysis_is_recorded_for_the_operator(
    tmp_path: Path, monkeypatch
) -> None:
    """Finding-2 shape — `unresolved`, `error`, `operator_reason`."""
    monkeypatch.delenv("MUX_SHIP_REACHABILITY_HALT", raising=False)
    ctx = _ctx(tmp_path, "exec_sr_obs_recorded")
    _kill_producer(ctx, "mix")
    _break_the_read(monkeypatch)

    assert unreachable_halt(ctx) is None
    assert ctx.artifact_exists(REACHABILITY_REL)

    doc = ctx.read_json(REACHABILITY_REL)
    assert doc["reason"] == "analysis_degraded"
    assert doc["blockers"] == []
    health = doc["analysis"]
    assert health["unresolved"] is True
    assert "ImportError" in health["error"]
    assert "operator_reason" in health
    assert "master_finalize" in health["unreadable_contracts"]


def test_a_healthy_run_records_nothing_new(tmp_path: Path, monkeypatch) -> None:
    """The healthy path must be unchanged — no new artifact appears."""
    monkeypatch.delenv("MUX_SHIP_REACHABILITY_HALT", raising=False)
    ctx = _ctx(tmp_path, "exec_sr_obs_healthy")

    assert unreachable_halt(ctx) is None
    assert not ctx.artifact_exists(REACHABILITY_REL)


# ---------------------------------------------------------------------------
# report-only telemetry on the other fail-open sites
# ---------------------------------------------------------------------------

def test_a_swallowed_completeness_error_is_counted_but_still_answers_satisfied(
    tmp_path: Path, monkeypatch
) -> None:
    """`requirement_satisfied` resolves errors to True. Unchanged, now counted."""
    import json

    from interview_mux import artifact_completeness
    from interview_mux.ship_reachability import requirement_satisfied

    ctx = _ctx(tmp_path, "exec_sr_obs_satisfied")
    rel = "master/selection.json"
    # Written straight to disk: `write_json` would route through the air-order
    # boundary, and this test is about the swallow, not about selection validity.
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"ordered_segment_ids": []}), encoding="utf-8")
    assert ctx.artifact_exists(rel)

    def boom(*_a, **_k):
        raise RuntimeError("completeness rules unavailable")

    monkeypatch.setattr(artifact_completeness, "artifact_status_for_stage", boom)

    assert requirement_satisfied(ctx, rel, "master_finalize") is True
    assert swallow_telemetry()["counts"]["requirement_satisfied.completeness"] == 1
    assert "RuntimeError" in swallow_telemetry()["last_error"][
        "requirement_satisfied.completeness"
    ]


def test_a_swallowed_budget_error_is_counted_but_still_answers_runnable(
    tmp_path: Path, monkeypatch
) -> None:
    """`producer_runnable` resolves errors to True. Unchanged, now counted."""
    from interview_mux.homunculus import budget
    from interview_mux.ship_reachability import producer_runnable

    ctx = _ctx(tmp_path, "exec_sr_obs_runnable")

    def boom(*_a, **_k):
        raise RuntimeError("budget unavailable")

    monkeypatch.setattr(budget, "attempt_cap", boom)

    assert producer_runnable(ctx, "mix") is True
    assert swallow_telemetry()["counts"]["producer_runnable"] == 1


def test_telemetry_never_raises_on_an_unprintable_exception(monkeypatch) -> None:
    """Instrumentation that can break the walk is worse than the blindness."""
    from interview_mux import stage_contract

    class Nasty(Exception):
        def __str__(self) -> str:
            raise ValueError("cannot render")

    def fake(_stage_id: str):
        raise Nasty()

    monkeypatch.setattr(stage_contract, "load_contract", fake)

    path = critical_path(None)
    assert path.degraded is True
    assert path.unreadable_stages[0].error == "unprintable exception"
