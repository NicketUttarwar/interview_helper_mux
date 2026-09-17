"""p2-solver (§2.1): the admissible set is a function of on-disk state, nothing else.

Each test here pins one conjunct of the admissibility rule, plus the two traps the
plan calls out by name: a hollow ``.stage_done`` marker (§8.5) and an artifact that
exists only in another stage's staging directory (§8.6).
"""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux import solver
from interview_mux.run_context import RunContext
from interview_mux.stage_contract import PIPELINE_TIERS, load_contract
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw

# >1024 bytes so artifact_completeness reads it complete rather than header-only.
SUFFICIENT_WAV = b"RIFF" + b"\x00" * 4096
HOLLOW_WAV = b"RIFF" + b"\x00" * 32


def _ctx(tmp_path: Path, name: str, **meta: object) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    base = {"homunculus_version": "0.2.0", "homunculus_control_plane": "deterministic"}
    base.update(meta)
    ctx.write_json("run_meta.json", base, skip_handoff=True)
    return ctx


def _commit(ctx: RunContext, rel: str, payload: bytes | dict) -> Path:
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        dest.write_bytes(payload)
    else:
        dest.write_text(json.dumps(payload), encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# tier — 72, not 90 (§8.4)
# ---------------------------------------------------------------------------

def test_solver_only_considers_the_72_pipeline_stages() -> None:
    stages = solver.dispatchable_stages()
    assert len(stages) == 72
    assert set(stages) == set(ANALYSIS_ORDER) | set(DELIVERY_ORDER)
    for sid in stages:
        contract = load_contract(sid)
        assert contract is None or str(contract.tier) in PIPELINE_TIERS


def test_non_stage_contracts_are_refused_by_tier(tmp_path: Path) -> None:
    """`gate` means an operator acts and `meta` is never dispatchable."""
    ctx = _ctx(tmp_path, "solver_tier")
    for sid in ("transcript_review", "g1_vo_pickup", "_arbiter", "sfx_brief"):
        if load_contract(sid) is None:
            continue
        verdict = solver.evaluate_stage(ctx, sid)
        assert verdict.admissible is False
        assert verdict.reason.startswith("tier_not_dispatchable:")


# ---------------------------------------------------------------------------
# done() — marker plus outputs (§8.5)
# ---------------------------------------------------------------------------

def test_a_done_stage_with_real_outputs_is_not_admissible(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "solver_done")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    _commit(ctx, "transcript/full.json", {"items": [{"text": "hi"}]})
    mark_done_raw(ctx, "transcribe")
    assert solver.stage_done(ctx, "transcribe") is True
    assert solver.evaluate_stage(ctx, "transcribe").reason == "already_done"


def test_a_hollow_done_marker_does_not_count_as_done(tmp_path: Path) -> None:
    """8 stages in the reference run had .stage_done with no artifact behind it."""
    ctx = _ctx(tmp_path, "solver_hollow_marker")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    mark_done_raw(ctx, "transcribe")
    assert ctx.is_done("transcribe") is True
    assert solver.stage_done(ctx, "transcribe") is False
    verdict = solver.evaluate_stage(ctx, "transcribe")
    assert verdict.admissible is True
    assert verdict.detail["hollow_done_marker"] is True


# ---------------------------------------------------------------------------
# hard inputs — committed and sufficient (§2.1, §8.6)
# ---------------------------------------------------------------------------

def test_missing_hard_input_names_the_path_and_its_producer(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "solver_missing_input")
    verdict = solver.evaluate_stage(ctx, "transcribe")
    assert verdict.admissible is False
    assert verdict.reason == "hard_input_missing:ingest/normalized.wav"
    assert verdict.detail["producers"]["ingest/normalized.wav"] == "ingest"


def test_satisfied_hard_input_makes_the_stage_admissible_and_confident(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path, "solver_satisfied")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    verdict = solver.evaluate_stage(ctx, "transcribe")
    assert (verdict.admissible, verdict.reasons) == (True, ())
    assert verdict.confident is True
    assert verdict.deferred is False


def test_an_artifact_that_exists_but_is_hollow_is_not_satisfied(tmp_path: Path) -> None:
    """The trap: existence is not sufficiency. A header-only WAV is not a transcript source."""
    ctx = _ctx(tmp_path, "solver_hollow_input")
    _commit(ctx, "ingest/normalized.wav", HOLLOW_WAV)
    verdict = solver.evaluate_stage(ctx, "transcribe")
    assert verdict.admissible is False
    assert verdict.reason == "hard_input_insufficient:ingest/normalized.wav"


def test_an_empty_json_artifact_is_not_satisfied(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "solver_hollow_json")
    _commit(ctx, "segments/boundaries.json", {"boundaries": []})
    ok, why = solver.input_satisfied(
        ctx, "segments/boundaries.json", consumer_stage="segment_classification"
    )
    assert (ok, why) == (False, "hard_input_insufficient:segments/boundaries.json")


def test_staged_but_uncommitted_input_does_not_satisfy(tmp_path: Path) -> None:
    """§8.6 — a peer stage's un-promoted staging must never open a downstream stage."""
    ctx = _ctx(tmp_path, "solver_staged_only")
    staged = ctx.final_path(".pending_writes", "ingest", "ingest", "normalized.wav")
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(SUFFICIENT_WAV)
    assert solver.committed(ctx, "ingest/normalized.wav") is False
    assert solver.evaluate_stage(ctx, "transcribe").reason == (
        "hard_input_missing:ingest/normalized.wav"
    )


def test_a_newer_pending_write_over_a_commit_is_not_committed(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "solver_pending_newer")
    _commit(ctx, "transcript/full.json", {"items": [{"text": "old"}]})
    staged = ctx.final_path(
        ".pending_writes", "transcribe", "transcript", "full.json"
    )
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(json.dumps({"items": [{"text": "new"}]}), encoding="utf-8")
    import os
    import time

    now = time.time() + 5
    os.utime(staged, (now, now))
    assert solver.committed(ctx, "transcript/full.json") is False
    ok, why = solver.input_satisfied(
        ctx, "transcript/full.json", consumer_stage="transcript_review_build"
    )
    assert (ok, why) == (False, "hard_input_uncommitted:transcript/full.json")


# ---------------------------------------------------------------------------
# partial contract truth — a hollow contract must not block (design requirement)
# ---------------------------------------------------------------------------

def test_a_hollow_contract_defers_instead_of_blocking(tmp_path: Path) -> None:
    """Nothing declared is *unknown*, never "no prerequisites" and never "blocked"."""
    ctx = _ctx(tmp_path, "solver_hollow_contract")
    hollow = [
        sid
        for sid in solver.dispatchable_stages()
        if not [d for d in (load_contract(sid).inputs if load_contract(sid) else []) if d.hard]
    ]
    assert hollow, "fixture assumes contract population is still in flight"
    for sid in hollow:
        verdict = solver.evaluate_stage(ctx, sid)
        assert "hard_inputs_undeclared" in verdict.unknowns
        assert not any(r.startswith("hard_input_") for r in verdict.reasons)
        if verdict.admissible:
            assert verdict.deferred is True
            assert verdict.confident is False


def test_contract_population_census_only_ever_improves(tmp_path: Path) -> None:
    """How many of the 72 the solver can decide confidently, as a ratchet.

    33/72 declared a hard input when p2-solver landed; contract population (p1) is
    still in flight upstream-first, so this is a floor, never an equality — a group
    finishing its contracts must not fail this test.
    """
    ctx = _ctx(tmp_path, "solver_census")
    decision = solver.admissible_set(ctx)
    with_hard_inputs = [
        v.stage for v in decision.verdicts if v.detail.get("declared_hard_inputs")
    ]
    with_outputs = [v.stage for v in decision.verdicts if v.detail.get("declared_outputs")]
    assert len(decision.verdicts) == 72
    assert len(with_hard_inputs) >= 33
    assert len(with_outputs) == 72
    # On a fresh run nothing is gated or leased, so every stage the solver cannot
    # decide confidently is deferred to the walk rather than reported blocked.
    assert all(v.admissible for v in decision.verdicts if not v.confident)
    assert len(decision.deferred) == 72 - len(with_hard_inputs)


def test_no_stage_is_excluded_for_a_reason_the_contract_did_not_state(
    tmp_path: Path,
) -> None:
    """Every exclusion is a positive blocker; "unknown" is never one."""
    ctx = _ctx(tmp_path, "solver_positive_blockers")
    decision = solver.admissible_set(ctx)
    for verdict in decision.verdicts:
        for reason in verdict.reasons:
            assert not reason.endswith("_indeterminate")
            assert "undeclared" not in reason
            assert "unknown" not in reason


# ---------------------------------------------------------------------------
# outputs writable (§4.2)
# ---------------------------------------------------------------------------

def test_an_output_without_write_permission_excludes_the_stage(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _ctx(tmp_path, "solver_ownership")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    assert solver.evaluate_stage(ctx, "transcribe").admissible is True

    from interview_mux import artifact_ownership

    monkeypatch.setattr(
        artifact_ownership,
        "write_permitted",
        lambda *_a, **_k: (False, "unknown_path"),
    )
    verdict = solver.evaluate_stage(ctx, "transcribe")
    assert verdict.admissible is False
    assert verdict.reason.startswith("output_write_denied:transcript/full.json:")


# ---------------------------------------------------------------------------
# lease + audio serialization (§8.3)
# ---------------------------------------------------------------------------

def test_a_fresh_gui_lease_stops_the_solver_from_proposing_anything(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path, "solver_lease", full_auto=True, run_mode="full-auto")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    assert solver.lease_permits_acting(ctx) is True

    from interview_mux.automation_run import take_gate_advance_lease

    take_gate_advance_lease(ctx, source="gui", gate_id="handle_gate")
    assert solver.lease_permits_acting(ctx) is False
    decision = solver.admissible_set(ctx)
    assert decision.admissible == ()
    assert decision.halted is True
    assert all("lease_held_by_gui" in v.reasons for v in decision.verdicts)


def test_the_solver_never_takes_the_lease_itself(tmp_path: Path) -> None:
    """§8.3 — the solver decides; only a dispatcher may take the lease."""
    from interview_mux.automation_run import GATE_ADVANCE_LEASE_REL

    ctx = _ctx(tmp_path, "solver_lease_readonly")
    solver.admissible_set(ctx)
    assert ctx.final_path(*GATE_ADVANCE_LEASE_REL.split("/")).exists() is False


def test_an_inflight_audio_job_serializes_the_other_audio_stages(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "solver_audio_serialize")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    _commit(ctx, "gui_job.json", {"status": "running", "stage": "mix"})
    verdict = solver.evaluate_stage(ctx, "transcribe")
    assert verdict.detail["audio_mutating"] is True
    assert verdict.reason == "audio_serialize_inflight:mix"
    # A non-audio stage is untouched by the audio device lock.
    assert "audio_serialize_inflight:mix" not in solver.evaluate_stage(
        ctx, "speaker_roles"
    ).reasons


# ---------------------------------------------------------------------------
# composition with the dispatch door (never re-implemented)
# ---------------------------------------------------------------------------

def test_a_stage_the_door_would_refuse_is_not_admissible(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "solver_door", full_auto=True, run_mode="full-auto")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    assert solver.evaluate_stage(ctx, "transcribe").admissible is True

    from interview_mux.dispatch_delta import record_attempt

    record_attempt(ctx, "transcribe", outcome="failed", source="driver")
    verdict = solver.evaluate_stage(ctx, "transcribe")
    assert verdict.admissible is False
    assert verdict.reason == "door_refused:attempt_memo"


def test_solver_reuses_the_door_rather_than_its_own_caps(monkeypatch) -> None:
    """Regression guard: the door owns caps / no-delta / memo, the solver composes."""
    source = Path("src/interview_mux/solver.py").read_text(encoding="utf-8")
    assert "evaluate_dispatch" in source
    for reimplemented in ("max_invokes", "count_identity", "no_delta_refusal", "memo_skip"):
        assert reimplemented not in source


# ---------------------------------------------------------------------------
# the decision object
# ---------------------------------------------------------------------------

def test_decision_picks_the_lowest_seed_index_and_explains_every_exclusion(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path, "solver_decision")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    decision = solver.admissible_set(ctx)
    order = solver.seed_order()
    assert decision.would_choose == decision.admissible[0]
    assert decision.would_choose is not None
    picked = order.index(decision.would_choose)
    assert all(order.index(s) >= picked for s in decision.admissible)
    excluded = {v.stage for v in decision.verdicts if not v.admissible}
    assert excluded == set(decision.exclusions())
    assert all(reason for reason in decision.exclusions().values())


def test_halt_payload_names_the_unmet_dependency_and_its_producer(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path, "solver_halt")
    payload = solver.halt_payload(solver.admissible_set(ctx))
    blockers = {b["stage"]: b for b in payload["blockers"]}
    assert blockers["transcribe"]["reason"] == "hard_input_missing:ingest/normalized.wav"
    assert blockers["transcribe"]["producers"]["ingest/normalized.wav"] == "ingest"
