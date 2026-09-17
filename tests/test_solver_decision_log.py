"""p2-observability (§10.2): ``operator/solver_decision.jsonl`` + an API read path.

When the admissible set is empty the run halts, so the halt message *is* the product.
The valuable half is the **per-stage exclusion reason** — it is what makes "why is
nothing runnable" answerable and it is the input to the later GUI halt panel.

The path now carries its own ALLOW row in `artifact_ownership.py`, and the writer still
asks the matrix every time: if the catalog ever refuses, skip the write, never write
around the matrix, never raise.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from interview_mux import solver
from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, isolated_run_ctx, patch_executions_root


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "homunculus_control_plane": "deterministic",
            "run_mode": "full-auto",
            "full_auto": True,
        },
        skip_handoff=True,
    )
    return ctx


def _allow_the_row(monkeypatch) -> None:
    """Pin the permission locally so these tests exercise the writer, not the catalog."""
    from interview_mux import artifact_ownership

    real = artifact_ownership.write_permitted

    def _patched(ctx, path, stage_key, *a, **k):
        if str(path) == solver.SOLVER_DECISION_REL:
            return True, "operational"
        return real(ctx, path, stage_key, *a, **k)

    monkeypatch.setattr(artifact_ownership, "write_permitted", _patched)


# ---------------------------------------------------------------------------
# missing ALLOW row must not crash and must not write
# ---------------------------------------------------------------------------

def test_the_decision_log_has_an_explicit_allow_row(tmp_path: Path) -> None:
    """The catalog pins the owner: the write no longer rides the generic `operator/`
    fallback, so the reason is `operational`, not `operational_unregistered`."""
    ctx = _ctx(tmp_path, "decision_row_owned")
    ok, reason = solver.decision_log_writable(ctx)
    assert (ok, reason) == (True, "operational")
    assert solver.decision_log_registered() is True

    from interview_mux import artifact_ownership

    assert artifact_ownership.owners_of(solver.SOLVER_DECISION_REL) == ("ops",)


def test_an_unwritable_path_skips_the_write_without_raising(
    tmp_path: Path, monkeypatch
) -> None:
    """If the catalog ever refuses this path, the writer goes quiet — never illegal."""
    ctx = _ctx(tmp_path, "decision_unowned")
    decision = solver.admissible_set(ctx)

    from interview_mux import artifact_ownership

    monkeypatch.setattr(
        artifact_ownership, "write_permitted", lambda *_a, **_k: (False, "unknown_path")
    )
    assert solver.decision_log_writable(ctx) == (False, "unknown_path")
    assert solver.log_decision(ctx, decision) is False
    assert ctx.final_path(*solver.SOLVER_DECISION_REL.split("/")).exists() is False
    assert solver.read_decisions(ctx) == []


def test_ownership_lookup_failure_is_not_a_crash(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, "decision_ownership_boom")
    decision = solver.admissible_set(ctx)

    from interview_mux import artifact_ownership

    def _boom(*_a, **_k):
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(artifact_ownership, "write_permitted", _boom)
    ok, reason = solver.decision_log_writable(ctx)
    assert ok is False
    assert "catalog unavailable" in reason
    assert solver.log_decision(ctx, decision) is False


def test_the_writer_never_writes_around_the_ownership_matrix() -> None:
    """No `skip_ownership` / raw-open escape hatch in the logging path."""
    source = Path("src/interview_mux/solver.py").read_text(encoding="utf-8")
    assert "decision_log_writable" in source
    assert "skip_ownership" not in source
    assert "set_fail_closed_default" not in source


# ---------------------------------------------------------------------------
# the row itself
# ---------------------------------------------------------------------------

def test_one_row_per_evaluation_records_the_set_the_pick_and_every_exclusion(
    tmp_path: Path, monkeypatch
) -> None:
    _allow_the_row(monkeypatch)
    ctx = _ctx(tmp_path, "decision_row")
    wav = ctx.final_path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 4096)

    decision = solver.admissible_set(ctx)
    assert solver.log_decision(ctx, decision) is True

    rows = solver.read_decisions(ctx)
    assert len(rows) == 1
    row = rows[0]
    assert row["posture"] == "full-auto"
    assert row["admissible"] == list(decision.admissible)
    assert row["would_choose"] == decision.would_choose
    assert row["lease_ok"] is True
    assert row["halted"] is False

    # Every excluded stage carries its own specific reason — the valuable part.
    excluded = {r["stage"]: r for r in row["excluded"]}
    assert excluded, "fixture expects at least one blocked stage"
    assert all(r.get("reason") for r in excluded.values())
    assert "transcribe" in row["admissible"], "its one hard input is on disk"
    assert excluded["speaker_roles"]["reason"].startswith("hard_input_missing:")
    assert excluded["speaker_roles"]["confident"] is True


def test_rows_distinguish_confident_picks_from_deferred_ones(
    tmp_path: Path, monkeypatch
) -> None:
    """Partial contract truth is visible in the artifact, not hidden behind a boolean."""
    _allow_the_row(monkeypatch)
    ctx = _ctx(tmp_path, "decision_deferred")
    solver.log_decision(ctx, solver.admissible_set(ctx))
    row = solver.read_decisions(ctx)[-1]
    assert row["deferred"], "hollow contracts should show up as deferred, not blocked"
    assert set(row["deferred"]) <= set(row["admissible"])
    for stage in row["deferred"]:
        detail = next(r for r in row["admissible_detail"] if r["stage"] == stage)
        assert detail["confident"] is False
        assert detail["unknowns"]


def test_appending_keeps_history_and_caps_growth(tmp_path: Path, monkeypatch) -> None:
    _allow_the_row(monkeypatch)
    ctx = _ctx(tmp_path, "decision_append")
    decision = solver.admissible_set(ctx)
    for _ in range(3):
        solver.log_decision(ctx, decision)
    assert len(solver.read_decisions(ctx, limit=99)) == 3

    dest = ctx.final_path(*solver.SOLVER_DECISION_REL.split("/"))
    with dest.open("w", encoding="utf-8") as fh:
        for i in range(solver.MAX_DECISION_ROWS + 20):
            fh.write(json.dumps({"at": str(i)}) + "\n")
    solver.log_decision(ctx, decision)
    lines = dest.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == solver.MAX_DECISION_ROWS


def test_a_halt_row_carries_the_blockers_that_explain_it(
    tmp_path: Path, monkeypatch
) -> None:
    _allow_the_row(monkeypatch)
    ctx = _ctx(tmp_path, "decision_halt")
    from interview_mux.automation_run import take_gate_advance_lease

    take_gate_advance_lease(ctx, source="gui", gate_id="handle_gate")
    decision = solver.admissible_set(ctx)
    assert decision.halted is True
    solver.log_decision(ctx, decision)
    row = solver.read_decisions(ctx)[-1]
    assert row["halted"] is True
    assert row["admissible"] == []
    assert row["would_choose"] is None
    assert all("lease_held_by_gui" in r["reasons"] for r in row["excluded"])


def test_shadow_observe_logs_when_the_flag_is_on(tmp_path: Path, monkeypatch) -> None:
    _allow_the_row(monkeypatch)
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    ctx = _ctx(tmp_path, "decision_shadow_on")
    solver.shadow_observe(ctx)
    assert len(solver.read_decisions(ctx)) == 1


# ---------------------------------------------------------------------------
# API read path
# ---------------------------------------------------------------------------

def test_api_exposes_the_decision_and_the_halt_payload(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_solver_decision_api", create=True)
    init_run_meta_for_test(ctx)
    client = TestClient(create_app())

    res = client.get(f"/api/runs/{ctx.run_id}/solver-decision")
    assert res.status_code == 200
    body = res.json()
    assert body["artifact"] == solver.SOLVER_DECISION_REL
    assert body["authoritative"] is False
    assert body["shadow_logging"] is True
    assert body["shadow"]["zero"] is True
    assert body["live"]["posture"] in solver.POSTURES
    blockers = {b["stage"]: b for b in body["halt"]["blockers"]}
    assert blockers, "an empty run has blocked stages to explain"
    assert all(b["reason"] for b in blockers.values())
    assert blockers["transcribe"]["producers"]["ingest/normalized.wav"] == "ingest"


def test_api_read_path_is_a_get_and_needs_no_operator_guard() -> None:
    from interview_mux.web.route_guard_registry import (
        GUARDED_RUN_ROUTE_KEYS,
        GUARD_EXEMPT_RUN_ROUTE_KEYS,
    )

    key = "/api/runs/{run_id}/solver-decision"
    assert not any(k[1] == key for k in GUARDED_RUN_ROUTE_KEYS)
    assert not any(k[1] == key for k in GUARD_EXEMPT_RUN_ROUTE_KEYS)
    app = create_app()
    methods = {
        tuple(sorted(r.methods)) for r in app.routes if getattr(r, "path", "") == key
    }
    assert methods == {("GET",)}
