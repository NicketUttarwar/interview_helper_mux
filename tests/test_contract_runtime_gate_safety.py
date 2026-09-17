"""Contract fields are read by live gates outside the dependency graph.

`MUX_CONTRACT_REQUIRES` gates the *graph*. It does not gate these, which read
contract fields directly on the dispatch path:

* `artifact_lifecycle.run_phase_checks` — `pipeline.run_single_stage` calls it at
  `PRESTAGE`, and a returned error becomes a `ValueError`. An **absent** hard input
  is now a recorded refusal rather than an exception (see
  `tests/test_prestage_hard_input_refusal.py`); a **stale stamp** is still fatal.
  A hard input the stage cannot ever satisfy is therefore no longer a crash, but it
  is still a wrong declaration — it refuses the stage forever, which is what the
  first test below prevents.
* `ship_reachability` — declared hard inputs feed the reachability predicate.
* `dispatch_delta.hard_input_paths` — the no-delta guard and attempt memo (already
  hardened to union with the fallback table rather than replace it).
* `artifact_root_cause._PROPAGATION_FROM` — built at **import time** from
  `propagation_map()`, so contract `propagation` reaches ITR routing.

These tests pin the safe direction for each, so contract population cannot quietly
change runtime behaviour. Same lesson as `tests/test_contract_input_declaration_safety.py`.
"""

from __future__ import annotations

from interview_mux.artifact_dependency_graph import (
    _PROPAGATION_SEEDS,
    _producer_of_path,
    propagation_map,
)
from interview_mux.stage_contract import is_path_spec, load_contract
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

SEED_ORDER = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
_INDEX = {sid: i for i, sid in enumerate(SEED_ORDER)}


def test_every_declared_hard_input_is_produced_upstream() -> None:
    """A hard input from the future can never be satisfied.

    `run_phase_checks` wants the artifact on disk *before* the stage runs, so a hard
    input whose producer is the stage itself or a later stage refuses the stage on
    every pass — a permanent `missing_hard_input` defect instead of the old crash.
    """
    violations: list[str] = []
    for sid in SEED_ORDER:
        contract = load_contract(sid)
        if contract is None:
            continue
        for inp in contract.inputs:
            if not inp.hard or not inp.path or is_path_spec(inp.path):
                continue
            producer = inp.producer or _producer_of_path(inp.path)
            if not producer:
                violations.append(f"{sid}: {inp.path} has no known producer")
                continue
            if producer == sid:
                # Read-modify-write: legal as a *soft* input, never as a hard one.
                violations.append(f"{sid}: {inp.path} is its own output, declared hard")
                continue
            if producer in _INDEX and _INDEX[producer] >= _INDEX[sid]:
                violations.append(
                    f"{sid}: hard input {inp.path} is produced downstream by {producer}"
                )
    assert violations == [], (
        "these declarations refuse forever at PRESTAGE in pipeline.run_single_stage: "
        f"{violations}"
    )


def test_contract_propagation_only_widens_itr_routing() -> None:
    """`artifact_root_cause` freezes `propagation_map()` at import time.

    Contract `propagation` may add targets (more downstream stages offered for
    re-run — wasteful at worst) but may never remove a legacy seed target.
    """
    live = propagation_map()
    lost = {
        stage: sorted(set(seeds) - set(live.get(stage) or ()))
        for stage, seeds in _PROPAGATION_SEEDS.items()
        if set(seeds) - set(live.get(stage) or ())
    }
    assert lost == {}, f"contract propagation dropped legacy seed targets: {lost}"
