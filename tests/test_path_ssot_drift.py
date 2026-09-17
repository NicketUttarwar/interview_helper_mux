"""Stage -> artifact-path has one direction of truth; this test fails on drift.

P0 precondition of `.cursor/plans/solver_brain_020.plan.md` §8.7. Three places
claim stage -> primary artifact path:

1. `STAGE_ARTIFACT_DISK_PATHS` (`src/interview_mux/prompt_validation.py`)
2. the `artifact_ownership.py` catalog (`primary_path_for_stage`, `disk_paths_view`)
3. stage contract `outputs` (`docs/cross-cutting/stage-contracts/*.yaml`)

**Declared direction of truth: (1) `STAGE_ARTIFACT_DISK_PATHS`.** It is the
oldest, is what `tools/bootstrap_stage_contracts.py` generates contract
`outputs` from, and is what the ownership catalog derives its primary view from.
(2) and (3) follow it. Populating contracts must not mint a fourth truth, so
this test asserts all three agree rather than letting each side drift.
"""

from __future__ import annotations

import pytest

from interview_mux import artifact_ownership as ownership
from interview_mux.artifact_dependency_graph import build_graph
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.stage_contract import (
    PIPELINE_TIERS,
    all_contract_stage_ids,
    is_path_spec,
    load_contract,
)
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

PIPELINE_STAGES = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)

# Contract outputs that are real writes but have no row in the ownership
# catalog. Fixing these requires an `artifact_ownership.py` ALLOW/catalog row,
# which is owned elsewhere — the set is pinned so it can only shrink.
KNOWN_UNOWNED_CONTRACT_OUTPUTS: frozenset[tuple[str, str]] = frozenset()


@pytest.fixture(autouse=True)
def _clear_graph_cache():
    """`build_graph()` is @lru_cache(maxsize=1) over contract YAML."""
    build_graph.cache_clear()
    yield
    build_graph.cache_clear()


def test_disk_paths_cover_exactly_the_pipeline_stages():
    assert sorted(STAGE_ARTIFACT_DISK_PATHS) == sorted(PIPELINE_STAGES)


def test_ownership_primary_view_matches_disk_paths():
    assert ownership.disk_paths_view() == dict(STAGE_ARTIFACT_DISK_PATHS)

    drift = {
        stage: (rel, ownership.primary_path_for_stage(stage))
        for stage, rel in STAGE_ARTIFACT_DISK_PATHS.items()
        if ownership.primary_path_for_stage(stage) != rel
    }
    assert drift == {}, f"ownership catalog disagrees with STAGE_ARTIFACT_DISK_PATHS: {drift}"


def test_every_primary_path_names_its_stage_as_a_producer():
    drift = {
        stage: ownership.owners_of(rel)
        for stage, rel in STAGE_ARTIFACT_DISK_PATHS.items()
        if stage not in ownership.owners_of(rel)
    }
    assert drift == {}, f"stage is not a declared producer of its primary artifact: {drift}"


def test_contract_outputs_declare_the_primary_path():
    missing: list[str] = []
    drift: list[str] = []
    for stage, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        contract = load_contract(stage)
        assert contract is not None, f"no contract for pipeline stage {stage}"
        paths = [o.path for o in contract.outputs]
        if not paths:
            missing.append(stage)
        elif rel not in paths:
            drift.append(f"{stage}: disk_path={rel} contract_outputs={paths}")
    assert missing == [], f"pipeline stages whose contract declares no outputs: {missing}"
    assert drift == [], f"contract outputs disagree with STAGE_ARTIFACT_DISK_PATHS: {drift}"


def test_contract_outputs_are_owned_or_pinned_as_known_gaps():
    """Every concrete contract output of a pipeline stage resolves in the catalog.

    Output *families* (`master/transitions/`, `glob:...`) are skipped:
    `write_permitted` takes a concrete path and can only answer `unknown_path`
    for a spec. `tests/test_contract_ownership_xcheck.py` reports the families
    that still want a catalog row.
    """
    unowned: set[tuple[str, str]] = set()
    for stage in all_contract_stage_ids():
        contract = load_contract(stage)
        if not contract or contract.tier not in PIPELINE_TIERS:
            continue
        for out in contract.outputs:
            if is_path_spec(out.path):
                continue
            ok, _reason = ownership.write_permitted(None, out.path, stage)
            if not ok:
                unowned.add((stage, out.path))
    assert unowned == set(KNOWN_UNOWNED_CONTRACT_OUTPUTS), (
        "contract outputs without an ownership row changed; add the ALLOW row in "
        "artifact_ownership.py (preferred) or update KNOWN_UNOWNED_CONTRACT_OUTPUTS"
    )


def test_retired_contracts_are_flagged():
    """A retired contract keeps historical outputs, so it must say it is retired."""
    retired = {
        stage
        for stage in all_contract_stage_ids()
        if (c := load_contract(stage)) and bool(c.raw.get("retired"))
    }
    assert retired == {"optimal_questions"}


def test_non_stage_contracts_do_not_claim_a_pipeline_stage_primary_path():
    """A live gate/meta contract must not claim a path a pipeline stage owns."""
    primaries = {rel: stage for stage, rel in STAGE_ARTIFACT_DISK_PATHS.items()}
    conflicts: list[str] = []
    for stage in all_contract_stage_ids():
        contract = load_contract(stage)
        if not contract or contract.tier in PIPELINE_TIERS:
            continue
        if contract.raw.get("retired"):
            continue  # historical claim, not a live writer — see test above
        for out in contract.outputs:
            owner = primaries.get(out.path)
            if owner and stage not in ownership.owners_of(out.path):
                conflicts.append(f"{stage} declares {out.path} owned by {owner}")
    assert conflicts == [], f"non-stage contract claims a stage primary path: {conflicts}"
