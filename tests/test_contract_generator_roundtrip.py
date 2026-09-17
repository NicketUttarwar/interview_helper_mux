"""Contracts on disk equal what the generator would write.

`tools/bootstrap_stage_contracts.py` **overwrites** every
`docs/cross-cutting/stage-contracts/*.yaml`, and it is step 1 of
`scripts/verify_artifact_contract.sh`. So a hand edit to a contract file is
silently reverted on the next verify run — the biggest footgun in the contract
migration of `.cursor/plans/solver_brain_020.plan.md`.

This test closes it: it renders each contract in-memory via the generator's own
`_contract_for()` and compares against the committed YAML. A drift means either
someone hand-edited a contract (put the data in
`tools/contract_dependency_data.py` instead) or the generator changed without a
regeneration in the same commit.

Nothing is written; the generator's `main()` is not called.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from interview_mux.stage_contract import contracts_dir

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import bootstrap_stage_contracts as gen  # noqa: E402
from contract_dependency_data import GROUP_DEPS, populated_groups  # noqa: E402


@pytest.mark.parametrize("stage_id", gen._all_stage_ids())
def test_committed_contract_matches_generator_output(stage_id: str):
    path = contracts_dir() / f"{stage_id}.yaml"
    assert path.is_file(), f"{stage_id}.yaml missing — run tools/bootstrap_stage_contracts.py"
    on_disk = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert on_disk == gen._contract_for(stage_id), (
        f"{stage_id}.yaml drifted from the generator. Hand edits are reverted by "
        "scripts/verify_artifact_contract.sh — declare the data in "
        "tools/contract_dependency_data.py and re-run the generator."
    )


# Contract files the generator does NOT write, so hand edits survive a verify
# run. All are `gate` or `meta` non-stages (plan §8.4) with no seed position, and
# `_GATES` in the generator is dead code for exactly this reason —
# `transcript_review` / `g1_vo_pickup` are not in `_all_stage_ids()`.
HAND_AUTHORED_CONTRACTS: frozenset[str] = frozenset(
    {
        "connector_seam_adjudicate",
        "edl_narrative_refine",
        "g1_vo_pickup",
        "island_cluster_structure_adjudicate",
        "junction_feel_audit",
        "junction_thought_complete",
        "narrative_arc_refine",
        "optimal_questions",
        "podcast_sfx_brief",
        "ranking_refine",
        "sdp_intent_refine",
        "sfx_brief",
        "transcript_review",
        "transitions_refine",
    }
)


def test_hand_authored_contract_set_is_pinned():
    """Which files the generator owns, and which round-trip untouched.

    Everything the generator writes must have its data in
    `tools/contract_dependency_data.py`; everything here may be hand-edited.
    Moving a file between the two sets is a reviewed change.
    """
    generated = set(gen._all_stage_ids())
    committed = {p.stem for p in contracts_dir().glob("*.yaml") if p.stem != "_contract-schema"}
    assert committed - generated == HAND_AUTHORED_CONTRACTS
    assert generated - committed == set(), (
        f"generator writes contracts that are not committed: {sorted(generated - committed)}"
    )


def test_hand_authored_contracts_are_all_non_stages():
    """A pipeline stage must never be hand-authored — it would drift from the code."""
    from interview_mux.stage_contract import PIPELINE_TIERS, load_contract

    leaked = {
        sid
        for sid in HAND_AUTHORED_CONTRACTS
        if (c := load_contract(sid)) and c.tier in PIPELINE_TIERS
    }
    assert leaked == set(), f"pipeline stages with hand-authored contracts: {sorted(leaked)}"


# ---------------------------------------------------------------------------
# The dependency data itself
# ---------------------------------------------------------------------------

def test_dependency_data_groups_are_real_phases():
    from interview_mux.v2.phases import PHASES

    known = {str(p.get("id")) for p in PHASES}
    assert set(GROUP_DEPS) <= known


def test_dependency_data_stages_belong_to_their_group():
    from interview_mux.v2.phases import phase_stage_ids

    misplaced: list[str] = []
    for group, stages in GROUP_DEPS.items():
        allowed = set(phase_stage_ids(group))
        misplaced.extend(f"{group}/{sid}" for sid in stages if sid not in allowed)
    assert misplaced == [], f"dependency data filed under the wrong group: {misplaced}"


def test_populated_groups_are_a_contiguous_upstream_first_prefix():
    """Plan §3.3: population runs upstream-first, so the populated set is a prefix.

    Declaring a stage's `inputs.hard` before its producers declare `outputs`
    yields phantom blockers, which is why the order is not negotiable.
    """
    order = [
        "prepare",
        "understand-a",
        "understand-b",
        "understand-c",
        "fill_gaps",
        "plan_rank",
        "sound",
        "build",
        "ship",
    ]
    done = [g for g in order if g in set(populated_groups())]
    assert done == order[: len(done)], (
        f"populated groups are not an upstream-first prefix: {done}"
    )


def test_strict_groups_are_populated_groups():
    """A group may only be enforced after its dependency data lands."""
    from interview_mux import contract_conformance as cc

    assert set(cc.STRICT_GROUPS) <= set(populated_groups())


def test_every_declared_input_names_a_producer_or_is_operator_supplied():
    """A dep with no producer cannot be healed, so the omission must be provable.

    The rule is not a list of blessed paths — that grows forever and hides
    mistakes. A producer may be omitted only when the ownership catalog can
    justify it:

    * no pipeline stage may write the path at all (operator-, GUI- or
      ops-supplied: `transcript/disfluencies.json` comes from the G0 review UI,
      `understanding/value_features.json` is `ops`);
    * or no permitted writer sits *upstream* of the declaring stage in seed
      order. `sound_design_palettes` is the first of five stages that mutate
      `understanding/sound_design_plan.json`, so it reads its own prior state
      and there is no producer that could heal it — naming one would make the
      stage its own blocker.
    """
    from interview_mux.artifact_ownership import owners_of
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    order = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    index = {sid: i for i, sid in enumerate(order)}
    orphans: list[str] = []
    for group, stages in GROUP_DEPS.items():
        for sid, row in stages.items():
            for kind in ("hard", "soft"):
                for dep in (row.get("inputs") or {}).get(kind) or []:
                    if dep.get("producer"):
                        continue
                    # Read-modify-write: the stage is itself a permitted writer,
                    # so it reads its own prior state. Naming one of the other
                    # writers as producer would route a heal away from the stage
                    # that actually owns the artifact — `junction_snip_qa` is
                    # authoritative for the air order and both ledgers even
                    # though `edl` and `mix` also write them.
                    if sid in owners_of(dep["path"]):
                        continue
                    upstream = {
                        o
                        for o in owners_of(dep["path"])
                        if o in index and index[o] < index.get(sid, -1)
                    }
                    if not upstream:
                        continue
                    orphans.append(
                        f"{group}/{sid}: {dep['path']} (upstream writer {sorted(upstream)})"
                    )
    assert orphans == [], f"declared inputs with no producer: {orphans}"


def test_hard_inputs_are_produced_by_an_earlier_seed_position():
    """A hard dep on a *later* stage is a phantom blocker by construction."""
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    order = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    index = {sid: i for i, sid in enumerate(order)}
    bad: list[str] = []
    for stages in GROUP_DEPS.values():
        for sid, row in stages.items():
            for dep in (row.get("inputs") or {}).get("hard") or []:
                producer = dep.get("producer")
                if not producer or sid not in index or producer not in index:
                    continue
                if index[producer] >= index[sid]:
                    bad.append(f"{sid}.inputs.hard[{dep['path']}] <- {producer}")
    assert bad == [], f"hard inputs pinned to a downstream producer: {bad}"
