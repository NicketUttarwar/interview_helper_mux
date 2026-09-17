"""Populating a contract must never weaken the no-delta guard (plan §4.1 + §5.2).

`hard_input_paths` feeds the live no-delta guard and the attempt memo, and it prefers
declared truth. So the moment a hollow contract gains `inputs`, two ways to *lose* an
input open up, and both make the guard refuse a legitimate re-run:

1. the declared set replacing the deliberately over-inclusive `FALLBACK_HARD_INPUTS`;
2. a read-modify-write artifact (`vernacular_segment_sanitize` resplitting
   `segments/manifest.json`) being stripped as "the stage's own output" once the
   contract declares it as an output too.

These tests pin the safe direction: declaring more may only ever *add* inputs.
"""

from __future__ import annotations

from pathlib import Path

from interview_mux.dispatch_delta import FALLBACK_HARD_INPUTS, hard_input_paths
from interview_mux.run_context import RunContext
from interview_mux.stage_contract import load_contract
from run_fixtures import isolated_run_ctx


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    return ctx


def test_every_fallback_input_survives_contract_population(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "fallback_survives")
    for stage, fallback in FALLBACK_HARD_INPUTS.items():
        active = set(hard_input_paths(ctx, stage))
        missing = sorted(set(fallback) - active)
        assert not missing, f"{stage} lost fallback hard inputs {missing}"


def test_read_modify_write_artifact_stays_an_input(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "read_modify_write")
    stage = "vernacular_segment_sanitize"
    contract = load_contract(stage)
    assert contract is not None
    rel = "segments/manifest.json"
    assert rel in {o.path for o in contract.outputs}, "fixture assumes it is declared out"
    assert rel in {i.path for i in contract.inputs}, "fixture assumes it is declared in"
    assert rel in hard_input_paths(ctx, stage)


def test_an_undeclared_own_output_is_still_stripped(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "own_output_stripped")
    stage = "transcribe"
    contract = load_contract(stage)
    assert contract is not None
    own = {o.path for o in contract.outputs} - {i.path for i in contract.inputs}
    assert own, "fixture assumes transcribe writes something it does not read"
    assert own.isdisjoint(hard_input_paths(ctx, stage))
