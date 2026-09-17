"""p15-defect-ledger (§5.5): advance-past telemetry, and PMQ refuses on ship-bar defects.

D1 says advance past a stage that cannot progress while ``master.wav`` is provably
reachable, recording a defect. The ledger is what stops that from shipping a hollow
master: PMQ refuses ``publish_allowed`` while a ship-bar-degrading defect is open.
"""

from __future__ import annotations

from pathlib import Path

from interview_mux.artifact_ownership import write_permitted
from interview_mux.defect_ledger import (
    DEFECT_LEDGER_REL,
    defect_summary,
    degrades_ship_bar,
    open_defects,
    open_ship_bar_defects,
    read_defect_ledger,
    record_defect,
    resolve_stage_defects,
)
from interview_mux.dispatch_door import DispatchVerdict, refuse_dispatch
from interview_mux.run_context import RunContext
from interview_mux.ship_reachability import ship_reachable
from run_fixtures import isolated_run_ctx


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    return ctx


def test_defect_records_stage_blocker_artifact_and_ship_bar(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "defect_row")
    row = record_defect(
        ctx,
        stage="mix",
        blocker="max_mix_cycles",
        artifact="master/assembly.wav",
        detail={"used": 3, "cap": 3},
    )
    assert row["stage"] == "mix"
    assert row["blocker"] == "max_mix_cycles"
    assert row["artifact"] == "master/assembly.wav"
    assert row["degrades_ship_bar"] is True
    assert row["state"] == "open"
    assert row["reachability"]["reachable"] is True
    doc = read_defect_ledger(ctx)
    assert list(doc["defects"]) == [row["defect_id"]]


def test_repeat_defect_increments_rather_than_duplicating(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "defect_repeat")
    record_defect(ctx, stage="mix", blocker="no_delta")
    row = record_defect(ctx, stage="mix", blocker="no_delta")
    assert row["count"] == 2
    assert len(open_defects(ctx)) == 1


def test_non_ship_bar_stage_does_not_block_publish(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "defect_nonship")
    assert degrades_ship_bar("mmaudio_sfx") is False
    record_defect(ctx, stage="mmaudio_sfx", blocker="no_delta")
    assert open_defects(ctx)
    assert open_ship_bar_defects(ctx) == []


def test_progress_resolves_the_defect(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "defect_resolve")
    record_defect(ctx, stage="edl", blocker="no_delta")
    assert resolve_stage_defects(ctx, "edl") == 1
    assert open_ship_bar_defects(ctx) == []
    assert read_defect_ledger(ctx)["defects"][
        list(read_defect_ledger(ctx)["defects"])[0]
    ]["state"] == "resolved"


def test_reachability_stub_never_halts_a_healthy_run(tmp_path: Path) -> None:
    """Unknown ⇒ reachable. Only a proven dead path may halt (plan §5.5)."""
    ctx = _ctx(tmp_path, "reach_stub")
    reach = ship_reachable(ctx)
    assert reach.reachable is True
    assert reach.certain is False
    assert reach.unknown is True
    ctx.final_path("master").mkdir(parents=True, exist_ok=True)
    ctx.final_path("master", "master.wav").write_bytes(b"RIFF")
    proven = ship_reachable(ctx)
    assert (proven.reachable, proven.certain) == (True, True)


def test_refusal_routes_to_the_ledger_instead_of_raising(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "defect_route")
    out = refuse_dispatch(
        ctx,
        "mix",
        DispatchVerdict(False, "max_mix_cycles", {"used": 3, "cap": 3}),
        source="delivery_walk_to_master",
    )
    assert out["refused"] is True
    assert out["reason"] == "max_mix_cycles"
    assert out["reachability"]["reachable"] is True
    blockers = defect_summary(ctx)["blockers"]
    assert blockers and blockers[0]["stage"] == "mix"
    # A no-delta refusal is recorded but is not a ship-bar blocker: the guard only
    # fires while the stage's own outputs are already present.
    refuse_dispatch(
        ctx,
        "transitions",
        DispatchVerdict(False, "no_delta", {"input_digest": "abc"}),
        source="delivery_walk_to_master",
    )
    assert [b["stage"] for b in defect_summary(ctx)["blockers"]] == ["mix"]


def test_pmq_refuses_publish_while_a_ship_bar_defect_is_open(tmp_path: Path) -> None:
    from interview_mux.aspirational_quality import is_structural_pmq_check

    ctx = _ctx(tmp_path, "defect_pmq")
    record_defect(ctx, stage="junction_snip_qa", blocker="max_invokes_per_identity")
    checks = [{"check_id": "master_exists_nonempty", "passed": True}]
    summary = defect_summary(ctx)
    checks.append(
        {
            "check_id": "no_open_ship_bar_defects",
            "passed": int(summary["open_ship_bar"]) == 0,
            "detail": summary,
        }
    )
    failed = [c["check_id"] for c in checks if not c["passed"]]
    assert failed == ["no_open_ship_bar_defects"]
    # And the check is structural, so aspirational policy cannot soften it.
    assert is_structural_pmq_check("no_open_ship_bar_defects") is True


def test_pmq_evaluation_wires_the_ledger(tmp_path: Path, monkeypatch) -> None:
    """The real evaluator emits the check, so publish_allowed follows the ledger."""
    from interview_mux import post_master_quality as pmq

    ctx = _ctx(tmp_path, "defect_pmq_live")
    record_defect(ctx, stage="master_finalize", blocker="no_delta")
    out = pmq.evaluate_post_master_quality(ctx)
    row = next(c for c in out["checks"] if c["check_id"] == "no_open_ship_bar_defects")
    assert row["passed"] is False
    assert "no_open_ship_bar_defects" in out["structural_failed_checks"]
    assert out["publish_allowed"] is False


def test_new_artifacts_have_ownership_allow_rows(tmp_path: Path) -> None:
    for rel in (DEFECT_LEDGER_REL, "operator/dispatch_memo.json"):
        ok, reason = write_permitted(None, rel, "ops", role="ops")
        assert ok, f"{rel}: {reason}"
        assert reason == "operational"
