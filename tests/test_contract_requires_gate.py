"""`MUX_CONTRACT_REQUIRES` gates contract-derived `requires` edges (plan §3.4).

Todo `p1-gate-requires`. Of everything a contract can declare, only
`inputs[].producer` is live for the shipped brains: it mints `requires` edges,
which feed `upstream_closure()` -> `resolve_stage_plan().prereq_chain` -> heal
pins in `homunculus/agenda.py` and `publishability_boundary.py`. Populating the
45 hollow contracts would therefore silently re-route healing for 0.1.0 and the
current 0.2.0 walk.

The gate makes population provably inert: with the flag OFF (default) the graph
emits exactly `_BASELINE_REQUIRES_EDGES` — the frozen set HEAD produced before
any group was populated — in the same order, so both the edge set and
`upstream_closure()`'s return order are byte-identical to today.
"""

from __future__ import annotations

import pytest

from interview_mux import artifact_dependency_graph as adg
from interview_mux.artifact_dependency_graph import (
    _BASELINE_REQUIRES_EDGES,
    build_graph,
    contract_requires_enabled,
    downstream_consumers,
    propagation_map,
    transitive_invalidate,
    upstream_closure,
)
from interview_mux.stage_contract import all_contract_stage_ids, load_contract


@pytest.fixture(autouse=True)
def _fresh_graph():
    build_graph.cache_clear()
    yield
    build_graph.cache_clear()


def _requires(graph) -> list[tuple[str, str, str | None]]:
    return [(e.from_id, e.to_id, e.artifact_path) for e in graph if e.kind == "requires"]


def _graph_signature(graph) -> list[tuple[str, str, str, str | None]]:
    return [(e.kind, e.from_id, e.to_id, e.artifact_path) for e in graph]


# ---------------------------------------------------------------------------
# The flag
# ---------------------------------------------------------------------------

def test_flag_defaults_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(adg._ENV_CONTRACT_REQUIRES, raising=False)
    assert contract_requires_enabled() is False


@pytest.mark.parametrize("raw", ["0", "false", "off", "no", ""])
def test_flag_off_values(monkeypatch: pytest.MonkeyPatch, raw: str):
    monkeypatch.setenv(adg._ENV_CONTRACT_REQUIRES, raw)
    assert contract_requires_enabled() is False


@pytest.mark.parametrize("raw", ["1", "true", "ON", "yes"])
def test_flag_on_values(monkeypatch: pytest.MonkeyPatch, raw: str):
    monkeypatch.setenv(adg._ENV_CONTRACT_REQUIRES, raw)
    assert contract_requires_enabled() is True


# ---------------------------------------------------------------------------
# Inertness with the flag off
# ---------------------------------------------------------------------------

def test_flag_off_emits_exactly_the_frozen_baseline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(adg._ENV_CONTRACT_REQUIRES, raising=False)
    build_graph.cache_clear()
    assert _requires(build_graph()) == [
        (a, b, c) for a, b, c in _BASELINE_REQUIRES_EDGES
    ]


def test_flag_off_is_unaffected_by_newly_declared_contract_inputs(
    monkeypatch: pytest.MonkeyPatch,
):
    """This is the whole point: population cannot change 0.1.0 heal routing."""
    monkeypatch.delenv(adg._ENV_CONTRACT_REQUIRES, raising=False)
    build_graph.cache_clear()
    before = _graph_signature(build_graph())

    from interview_mux.stage_contract import InputDep, StageContract

    fake = StageContract(
        stage_id="mix",
        tier="process",
        inputs=[InputDep(path="master/edl.json", hard=True, producer="edl")],
        outputs=[],
    )
    real = load_contract

    def _patched(stage_id: str):
        return fake if stage_id == "mix" else real(stage_id)

    monkeypatch.setattr("interview_mux.artifact_dependency_graph.load_contract", _patched)
    build_graph.cache_clear()
    after = _graph_signature(build_graph())
    assert after == before, "a newly declared input leaked into the graph with the flag off"

    # ... and the same declaration IS consumed once the flag is on.
    monkeypatch.setenv(adg._ENV_CONTRACT_REQUIRES, "1")
    build_graph.cache_clear()
    assert ("mix", "edl", "master/edl.json") in _requires(build_graph())


def test_upstream_closure_order_is_unchanged_with_the_flag_off(
    monkeypatch: pytest.MonkeyPatch,
):
    """`upstream_closure()` returns a list; `prereq_chain` consumes its order."""
    monkeypatch.delenv(adg._ENV_CONTRACT_REQUIRES, raising=False)
    build_graph.cache_clear()
    # Frozen expectations recorded at HEAD, before any group was populated.
    # `segment_classification` appears in its own closure because the seeds make
    # `content_brief_reanchor` a consumer of `segments/manifest.json`; the point
    # here is that the order does not move, not that it is pretty.
    assert upstream_closure("segment_classification") == [
        "segment_classification",
        "boundary_detection",
        "content_context",
        "speaker_roles",
    ]
    assert upstream_closure("nugget_layup_compose") == [
        "information_package_plan",
        "nugget_corpus_mine",
        "air_script_compose",
        "full_master_ranking",
        "connector_fuse_pass_pre_ranking",
        "mastering_plan_synthesize",
        "segment_classification",
        "boundary_detection",
        "content_context",
        "speaker_roles",
        "talking_points_compose",
        "ideal_cuts_propose",
    ]


def test_invalidation_and_consumer_views_do_not_depend_on_the_flag(
    monkeypatch: pytest.MonkeyPatch,
):
    """`propagation` / `consumers` were already inert (plan §3.4); prove it stays so."""
    monkeypatch.delenv(adg._ENV_CONTRACT_REQUIRES, raising=False)
    build_graph.cache_clear()
    off = (propagation_map(), transitive_invalidate("edl"), downstream_consumers("mix"))
    monkeypatch.setenv(adg._ENV_CONTRACT_REQUIRES, "1")
    build_graph.cache_clear()
    on = (propagation_map(), transitive_invalidate("edl"), downstream_consumers("mix"))
    assert off == on


def test_cache_is_keyed_on_the_flag(monkeypatch: pytest.MonkeyPatch):
    """No cache_clear between toggles — the lru_cache key must include the flag."""
    monkeypatch.delenv(adg._ENV_CONTRACT_REQUIRES, raising=False)
    build_graph.cache_clear()
    off = len(build_graph())
    monkeypatch.setenv(adg._ENV_CONTRACT_REQUIRES, "1")
    on = len(build_graph())
    monkeypatch.delenv(adg._ENV_CONTRACT_REQUIRES, raising=False)
    assert len(build_graph()) == off
    assert on >= off


def test_cache_clear_and_info_are_still_reachable_by_name():
    """Existing contract tests call `build_graph.cache_clear()`."""
    build_graph.cache_clear()
    build_graph()
    assert build_graph.cache_info().currsize >= 1


# ---------------------------------------------------------------------------
# The baseline itself
# ---------------------------------------------------------------------------

def test_baseline_is_deduplicated_and_well_formed():
    assert len(set(_BASELINE_REQUIRES_EDGES)) == len(_BASELINE_REQUIRES_EDGES)
    assert all(a and b and c for a, b, c in _BASELINE_REQUIRES_EDGES)


def test_baseline_consumers_are_real_contract_ids():
    known = set(all_contract_stage_ids())
    unknown = {a for a, _b, _c in _BASELINE_REQUIRES_EDGES if a not in known}
    assert unknown == set()


def test_baseline_edges_are_still_declared_by_some_contract():
    """The baseline may only shrink; it must never fossilise a deleted edge.

    Every frozen edge must still be derivable from a contract, so the baseline
    stays an honest snapshot rather than a private second dependency table.
    """
    declared: set[tuple[str, str, str]] = set()
    for sid in all_contract_stage_ids():
        contract = load_contract(sid)
        if not contract:
            continue
        for dep in contract.inputs:
            if dep.producer:
                declared.add((sid, dep.producer, dep.path))
    orphans = set(_BASELINE_REQUIRES_EDGES) - declared
    assert orphans == set(), (
        "frozen baseline edges no longer declared by any contract — shrink the "
        f"baseline in the same change that drops them: {sorted(orphans)}"
    )
