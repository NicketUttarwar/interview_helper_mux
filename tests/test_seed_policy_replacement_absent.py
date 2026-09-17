"""H-08 is not ready: nothing in the contract system replaces `seed_policy.py`.

[subtraction-holes.md](../docs/cross-cutting/subtraction-holes.md) H-08 proposes deleting
`seed_policy.py` (104L) on the grounds that "the solver picks the lowest seed index", and
concedes in the same row that `ensure_sticky_seed_mark` "has no equivalent". The
subtraction bar asks for a test that *proves* the replacement enforces what the deleted
guard enforced, and fails when the replacement is disabled. No such test can be written
here, and these three pin why.

What `seed_policy` enforces: under a hard seat freeze with `edl` already done,
`selection_framing_apply` and `gap_framing_recompose` are *intentional no-ops*. Because
they produce nothing, HF-1's pass-2 hollow-done rule refuses to mark them, and the seed
walk therefore blocks `mix` / `junction_snip_qa` / `master_finalize` on work that must
never run. `seed_policy` is the one mechanism that resolves that: it writes a
`hard_freeze_edl` skip stub, which makes the mark legal, and then marks.

The candidate replacements name in H-08 and plan §2.3 are the admissible-set solver and
the contract `inputs`/`outputs` declarations. `test_every_candidate_replacement_is_inert`
shows both are off by default; the two behavioural tests show what the run loses today if
the module goes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from interview_mux import seed_policy
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, isolated_run_ctx, mark_done_raw

APPLY_REL = "understanding/selection_framing_apply.json"
RECOMPOSE_REL = "understanding/gap_framing_recompose.json"
FREEZE_STAGES = ("selection_framing_apply", "gap_framing_recompose")
CONTRACTS = Path("docs/cross-cutting/stage-contracts")


def _frozen_ctx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> RunContext:
    """Hard seat freeze with `edl` done — the state the freeze no-ops exist for."""
    from interview_mux import seat_authority as sa

    ctx = isolated_run_ctx(tmp_path, name)
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda _ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda _ctx: [],
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "delivery": "synthesize",
                    "text": "Hello.",
                    "required": True,
                }
            ]
        },
        skip_handoff=True,
    )
    mark_done_raw(ctx, "edl")
    sa.stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    return ctx


@pytest.fixture()
def frozen_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    return _frozen_ctx(tmp_path, monkeypatch, "exec_seed_policy_replacement")


def _neutralise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exactly what deleting the module does to its callers.

    Every call site imports inside a `try` and swallows on failure, so a deleted module
    degrades to "the skip was never granted" rather than to an ImportError. Patching the
    two exported entry points reproduces that without a raising shim — the shadowing trap
    from delivery-invariants-anomaly.md §3.3.
    """
    monkeypatch.setattr(seed_policy, "seal_freeze_sticky_stages", lambda _ctx: [])
    monkeypatch.setattr(
        seed_policy, "apply_seed_policy_skips", lambda *_a, **_k: False
    )


def test_the_freeze_seal_is_what_makes_the_no_op_stages_completable(
    frozen_ctx: RunContext,
) -> None:
    """With the module live: stub first, then mark, and seed-order is satisfied."""
    from interview_mux.delivery_guardrails import seed_stage_complete
    from interview_mux.stage_completion import stage_artifact_incompleteness

    sealed = seed_policy.seal_freeze_sticky_stages(frozen_ctx)

    assert set(sealed) == set(FREEZE_STAGES)
    for rel in (APPLY_REL, RECOMPOSE_REL):
        assert frozen_ctx.read_json(rel).get("skip_reason") == "hard_freeze_edl"
    for stage in FREEZE_STAGES:
        assert frozen_ctx.is_done(stage) is True
        assert stage_artifact_incompleteness(frozen_ctx, stage) is None
        assert seed_stage_complete(frozen_ctx, stage) is True


def test_without_seed_policy_the_freeze_no_ops_deadlock_the_seed_walk(
    frozen_ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure mode H-08 would ship, and it is a hard block, not a silent hole.

    `llm_flow_hardening` has one fallback behind the `apply_seed_policy_skips` call — a
    forced `heal_or_refuse_mark` on `selection_framing_apply`. It *refuses*, correctly,
    because HF-1 will not stamp a pass-2 stage with no producer sidecar; the stub is the
    only thing that makes the mark legal, and `seed_policy` is the only writer of it.
    `gap_framing_recompose` has no fallback at all. Both stages therefore stay incomplete
    forever, and every stage that seed-orders after them is unreachable.
    """
    from interview_mux.delivery_guardrails import seed_stage_complete
    from interview_mux.stage_completion import heal_or_refuse_mark

    _neutralise(monkeypatch)

    assert seed_policy.seal_freeze_sticky_stages(frozen_ctx) == []

    outcome = heal_or_refuse_mark(frozen_ctx, "selection_framing_apply", force=True)
    assert outcome.get("refused") is True
    assert outcome.get("marked") is False

    for stage in FREEZE_STAGES:
        assert frozen_ctx.is_done(stage) is False
        assert seed_stage_complete(frozen_ctx, stage) is False
    assert frozen_ctx.artifact_exists(APPLY_REL) is False
    assert frozen_ctx.artifact_exists(RECOMPOSE_REL) is False


def test_the_live_seed_walk_depends_on_the_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_earliest_incomplete_seed_stage` seals via `seed_policy` on every walk.

    Asserted on the walk entry point rather than on `seal_freeze_sticky_stages` directly,
    so the test covers the wiring and not just the helper. The walk's return value is not
    the observable: an unrelated earlier stage may be the reported blocker. What matters
    is that walking at all clears the freeze pair, and stops clearing it when the module
    is gone.
    """
    from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage

    live = _frozen_ctx(tmp_path, monkeypatch, "exec_seed_walk_live")
    _earliest_incomplete_seed_stage(live, "mix")
    assert all(live.is_done(stage) for stage in FREEZE_STAGES)

    dead = _frozen_ctx(tmp_path, monkeypatch, "exec_seed_walk_no_policy")
    _neutralise(monkeypatch)
    _earliest_incomplete_seed_stage(dead, "mix")
    assert not any(dead.is_done(stage) for stage in FREEZE_STAGES)


def test_the_contract_layer_cannot_express_a_policy_satisfied_stage() -> None:
    """A contract says what a stage must produce. There is no "no-op is fine" form.

    Both freeze stages declare their primary output and an empty `sufficiency` list, so
    reading the contract can only ever conclude "the artifact is missing" — the exact
    conclusion `seed_policy` exists to override. The waiver is keyed on runtime state
    (hard freeze plus `edl` done), which no contract field references.
    """
    for stage in FREEZE_STAGES:
        raw = yaml.safe_load((CONTRACTS / f"{stage}.yaml").read_text(encoding="utf-8"))
        outputs = {str(o.get("path")) for o in raw.get("outputs") or []}
        assert f"understanding/{stage}.json" in outputs
        assert (raw.get("sufficiency") or []) == []
        assert "freeze" not in yaml.safe_dump(raw)


def test_every_candidate_replacement_is_inert() -> None:
    """Off by default is not a replacement (audit rule 3).

    `MUX_SOLVER_AUTHORITATIVE` off means the solver's seed index cannot select a stage —
    `tests/test_solver_inert.py` pins that from four directions. `MUX_CONTRACT_REQUIRES`
    off means the dependency graph emits only its frozen baseline edges, so no contract
    declaration can reroute the walk. Neither can be reading `seed_policy`'s waiver.
    """
    from interview_mux import artifact_dependency_graph as adg
    from interview_mux import solver

    assert solver.solver_authoritative() is False
    assert adg.contract_requires_enabled() is False
