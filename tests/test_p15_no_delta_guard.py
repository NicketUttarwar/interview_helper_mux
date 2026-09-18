"""p15-no-delta (§5.2): unchanged hard inputs cannot produce a different outcome.

Regression target, measured in exec_11871: ``junction_snip_qa`` 28 + ``mix`` 27
dispatches ping-ponging for ~7 h with no input change between iterations — 55 of the
193 driver excess dispatches.

The trap this file also pins: 45 of 90 contracts declare no hard inputs. An empty
hash set must leave the guard *inactive*, never refuse everything.
"""

from __future__ import annotations

from pathlib import Path

from interview_mux.defect_ledger import open_defects, open_ship_bar_defects
from interview_mux.dispatch_delta import (
    CONVERGENCE_INPUTS,
    FALLBACK_HARD_INPUTS,
    hard_input_paths,
    input_digest,
    input_hash_set,
    memo_row,
    no_delta_refusal,
    record_attempt,
)
from interview_mux.dispatch_door import evaluate_dispatch, refuse_dispatch
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    return ctx


def _write(ctx: RunContext, rel: str, body: bytes) -> None:
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)


def _seed_delivery(ctx: RunContext) -> None:
    _write(ctx, "master/edl.json", b'{"clips": [{"segment_id": "seg_001"}]}')
    _write(ctx, "master/selection.json", b'{"ordered_segment_ids": ["seg_001"]}')
    _write(ctx, "master/assembly.wav", b"RIFF-assembly-v1")
    _write(ctx, "master/junction_snip_qa.json", b'{"residual_findings": []}')


def _outputs_on_disk(monkeypatch) -> None:
    """Report outputs present iff the primary artifact exists (fixture-honest)."""
    from interview_mux.homunculus import agenda

    primaries = {
        "mix": "master/assembly.wav",
        "junction_snip_qa": "master/junction_snip_qa.json",
        "edl": "master/edl.json",
    }

    def _present(ctx: RunContext, stage: str) -> bool:
        rel = primaries.get(stage)
        return bool(rel) and ctx.final_path(*rel.split("/")).is_file()

    monkeypatch.setattr(agenda, "stage_outputs_present", _present)


def test_guard_is_inactive_when_nothing_is_known_about_the_inputs(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "delta_inactive")
    # A hollow contract with no fallback entry: no inputs known, guard off.
    assert "mastering_research_waves" not in FALLBACK_HARD_INPUTS
    assert hard_input_paths(ctx, "mastering_research_waves") == ()
    assert input_hash_set(ctx, "mastering_research_waves") is None
    assert input_digest(ctx, "mastering_research_waves") is None
    assert no_delta_refusal(ctx, "mastering_research_waves") is None


def test_declared_and_fallback_hard_inputs_are_unioned(tmp_path: Path) -> None:
    """`mix` hard inputs union with FALLBACK_HARD_INPUTS for the delta set.

    MIX-B1 declares tape + selection + edl + SDP hard (matches `_check_mix`).
    Fallback still supplies transitions / omit / stem globs the contract leaves soft.
    """
    from interview_mux.stage_contract import load_contract

    ctx = _ctx(tmp_path, "delta_fallback")
    contract = load_contract("mix")
    assert contract is not None
    assert [d.path for d in contract.inputs if d.hard] == [
        "ingest/normalized.wav",
        "master/selection.json",
        "master/edl.json",
        "understanding/sound_design_plan.json",
    ]
    paths = hard_input_paths(ctx, "mix")
    assert "ingest/normalized.wav" in paths
    assert "master/edl.json" in paths
    # A stage never hashes its own output, or the guard could never refuse.
    assert "master/assembly.wav" not in paths
    # And mix does not consume the junction report, which is what makes the
    # mix ⇄ junction fixpoint hold rather than oscillate.
    assert "master/junction_snip_qa.json" not in paths


def test_mix_junction_ping_pong_is_refused(tmp_path: Path, monkeypatch) -> None:
    """The 55-dispatch loop: second mix with an unchanged EDL is refused."""
    ctx = _ctx(tmp_path, "delta_pingpong")
    _seed_delivery(ctx)
    _outputs_on_disk(monkeypatch)

    # Iteration 1: mix runs and completes.
    assert evaluate_dispatch(ctx, "mix", source="delivery_walk_to_master").allowed
    record_attempt(ctx, "mix", outcome="done", source="delivery_walk_to_master")

    # Junction runs its ladder and finds nothing it can change — the EDL is untouched.
    record_attempt(ctx, "junction_snip_qa", outcome="done", source="delivery_walk_to_master")

    # Iteration 2: the driver re-offers mix. Inputs are byte-identical.
    verdict = evaluate_dispatch(ctx, "mix", source="delivery_walk_to_master")
    assert verdict.refused
    assert verdict.reason == "no_delta"

    # And the refusal is telemetry, not an exception. It is also not a ship-bar
    # defect: the guard only fires while mix's own output is already on disk, so
    # refusing the remix cannot make the master hollow and must not block publish.
    out = refuse_dispatch(ctx, "mix", verdict, source="delivery_walk_to_master")
    assert out["refused"] is True
    assert [d["stage"] for d in open_defects(ctx)] == ["mix"]
    assert open_ship_bar_defects(ctx) == []


def test_a_junction_recut_of_the_edl_reopens_mix(tmp_path: Path, monkeypatch) -> None:
    """A real state delta must still get through — the guard is not a cycle cap."""
    ctx = _ctx(tmp_path, "delta_recut")
    _seed_delivery(ctx)
    _outputs_on_disk(monkeypatch)
    record_attempt(ctx, "mix", outcome="done")
    assert evaluate_dispatch(ctx, "mix", source="walk").refused
    # Junction recuts: the EDL changes, so mix has new work to do.
    _write(ctx, "master/edl.json", b'{"clips": [{"segment_id": "seg_001_recut"}]}')
    assert evaluate_dispatch(ctx, "mix", source="walk").allowed


def test_missing_outputs_reopen_a_stage_even_with_unchanged_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    """A stage whose artifact vanished is productive to re-run — never strand it."""
    ctx = _ctx(tmp_path, "delta_missing_out")
    _seed_delivery(ctx)
    _outputs_on_disk(monkeypatch)
    record_attempt(ctx, "mix", outcome="done")
    assert no_delta_refusal(ctx, "mix") is not None
    ctx.final_path("master", "assembly.wav").unlink()
    assert no_delta_refusal(ctx, "mix") is None


def test_a_failed_attempt_does_not_arm_the_no_delta_guard(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, "delta_failed")
    _seed_delivery(ctx)
    _outputs_on_disk(monkeypatch)
    record_attempt(ctx, "mix", outcome="failed")
    assert memo_row(ctx, "mix")["outcome"] == "failed"
    assert no_delta_refusal(ctx, "mix") is None


def test_iterating_stages_pass_a_changed_input_via_a_convergence_metric(
    tmp_path: Path, monkeypatch
) -> None:
    """§2.2: legitimate iteration declares a metric instead of weakening the rule."""
    ctx = _ctx(tmp_path, "delta_convergence")
    _seed_delivery(ctx)
    _outputs_on_disk(monkeypatch)
    assert CONVERGENCE_INPUTS["junction_snip_qa"] == ("operator/delivery_residuals.json",)
    _write(ctx, "operator/delivery_residuals.json", b'{"generation": 1, "rows": []}')
    record_attempt(ctx, "junction_snip_qa", outcome="done")
    # No ladder progress: same residual generation ⇒ correctly refused.
    assert evaluate_dispatch(ctx, "junction_snip_qa", source="walk").refused
    # Ladder advanced the generation ⇒ the next pass is a real delta.
    _write(ctx, "operator/delivery_residuals.json", b'{"generation": 2, "rows": []}')
    assert evaluate_dispatch(ctx, "junction_snip_qa", source="walk").allowed


def test_guard_is_off_for_manual_runs_and_behind_an_env_switch(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _ctx(tmp_path, "delta_switch")
    _seed_delivery(ctx)
    _outputs_on_disk(monkeypatch)
    record_attempt(ctx, "mix", outcome="done")
    assert evaluate_dispatch(ctx, "mix", source="walk").refused
    monkeypatch.setenv("MUX_DISPATCH_NO_DELTA", "0")
    assert evaluate_dispatch(ctx, "mix", source="walk").allowed
    monkeypatch.delenv("MUX_DISPATCH_NO_DELTA")
    monkeypatch.setenv("MUX_DISPATCH_DOOR", "0")
    assert evaluate_dispatch(ctx, "mix", source="walk").allowed
