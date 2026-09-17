"""p3-promote (§7): the switch works, so promotion is one flag rather than a rewrite.

The mirror image of ``tests/test_solver_inert.py``. Everything here runs with
``MUX_SOLVER_AUTHORITATIVE=1``, which is NOT the recommended setting — see that file
and the module docstring of ``solver.py`` for why. The point of these tests is that
when the evidence does justify flipping it, the path underneath is already proven,
and that the rails the solver composes with are all still in force on it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from interview_mux import solver
from interview_mux.homunculus.agenda import _walk_sequence, walk_seed_agenda
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw, parse_log_detail

SUFFICIENT_WAV = b"RIFF" + b"\x00" * 4096


@pytest.fixture(autouse=True)
def _authoritative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_SOLVER_AUTHORITATIVE", "1")


def _ctx(tmp_path: Path, name: str, **meta: object) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    base = {"homunculus_version": "0.2.0", "homunculus_control_plane": "deterministic"}
    base.update(meta)
    ctx.write_json("run_meta.json", base, skip_handoff=True)
    return ctx


def _commit(ctx: RunContext, rel: str, payload: bytes | dict) -> None:
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        dest.write_bytes(payload)
    else:
        dest.write_text(json.dumps(payload), encoding="utf-8")


def _log_entries(ctx: RunContext) -> list[dict[str, Any]]:
    path = ctx.final_path("gui_log.jsonl")
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _log_text(ctx: RunContext) -> str:
    return "\n".join(str(e.get("message") or "") for e in _log_entries(ctx))


def _entry_saying(ctx: RunContext, token: str) -> dict[str, Any]:
    hits = [e for e in _log_entries(ctx) if token in str(e.get("message") or "")]
    assert hits, f"no operator log line contains {token!r}"
    return hits[-1]


def _refuse_at_the_door(ctx: RunContext, stage: str) -> None:
    """Make the door genuinely refuse ``stage``: a failed attempt at unchanged state.

    Not a stub. ``attempt_memo`` is one of the three refusals ``evaluate_dispatch``
    composes, and the seed-walk marker is what ``door_applies`` looks for — the same
    one ``walk_seed_agenda`` sets on itself.
    """
    from interview_mux.dispatch_delta import record_attempt
    from interview_mux.dispatch_door import evaluate_dispatch

    setattr(ctx, "_homunculus_seed_walk", True)
    record_attempt(ctx, stage, outcome="failed", source="test")
    assert evaluate_dispatch(ctx, stage, layer="walk").reason == "attempt_memo"


def _stub_verdicts(monkeypatch: pytest.MonkeyPatch, **kinds: str) -> None:
    verdicts = {
        sid: solver.StageVerdict(
            stage=sid,
            admissible=kind != "blocked",
            reasons=() if kind != "blocked" else ("hard_input_missing:x",),
            unknowns=() if kind != "deferred" else ("inputs_undeclared",),
            seed_index=idx,
        )
        for idx, (sid, kind) in enumerate(kinds.items())
    }
    monkeypatch.setattr(solver, "evaluate_stage", lambda _ctx, sid, **_k: verdicts[sid])


# ---------------------------------------------------------------------------
# order now comes from the solver
# ---------------------------------------------------------------------------

def test_the_solver_reorders_the_walk_when_it_can_justify_the_pick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seed order offers `a` first; the solver proves only `b` is runnable."""
    ctx = _ctx(tmp_path, "auth_reorder")
    _stub_verdicts(monkeypatch, transcribe="blocked", speaker_roles="confident")

    assert list(_walk_sequence(ctx, ["transcribe", "speaker_roles"], reason="t")) == [
        "speaker_roles"
    ]


def test_a_deferred_stage_falls_back_to_the_walks_own_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """39 of 72 contracts declare no hard inputs — those stay the walk's decision."""
    ctx = _ctx(tmp_path, "auth_deferred")
    _stub_verdicts(monkeypatch, transcribe="deferred", speaker_roles="deferred")

    assert list(_walk_sequence(ctx, ["transcribe", "speaker_roles"], reason="t")) == [
        "transcribe",
        "speaker_roles",
    ]


def test_a_confident_pick_outranks_an_earlier_deferred_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, "auth_confident_first")
    _stub_verdicts(monkeypatch, transcribe="deferred", speaker_roles="confident")

    assert list(_walk_sequence(ctx, ["transcribe", "speaker_roles"], reason="t")) == [
        "speaker_roles",
        "transcribe",
    ]


def test_an_empty_admissible_set_ends_the_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The §2.1 structural halt: nothing runnable means the walk stops, not spins."""
    ctx = _ctx(tmp_path, "auth_halt")
    _stub_verdicts(monkeypatch, transcribe="blocked", speaker_roles="blocked")

    assert list(_walk_sequence(ctx, ["transcribe", "speaker_roles"], reason="t")) == []


def test_every_stage_is_offered_at_most_once(tmp_path: Path) -> None:
    """Termination is structural, so a stage that fails cannot loop the walk."""
    ctx = _ctx(tmp_path, "auth_terminates")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    candidates = list(solver.dispatchable_stages())[:12]

    offered = list(_walk_sequence(ctx, candidates, reason="t"))
    assert len(offered) == len(set(offered))
    assert set(offered) <= set(candidates)


def test_the_solver_never_invents_a_stage_the_walk_did_not_offer(
    tmp_path: Path,
) -> None:
    """Candidates are the walk's filtered set — delivery guardrails still bind."""
    ctx = _ctx(tmp_path, "auth_no_invention")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)

    offered = set(_walk_sequence(ctx, ["speaker_roles", "utterance_segment"], reason="t"))
    assert offered <= {"speaker_roles", "utterance_segment"}


# ---------------------------------------------------------------------------
# the rails still bind
# ---------------------------------------------------------------------------

def test_a_done_stage_is_not_offered(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "auth_done")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    _commit(ctx, "transcript/full.json", {"items": [{"text": "hi"}]})
    mark_done_raw(ctx, "transcribe")

    assert "transcribe" not in set(_walk_sequence(ctx, ["transcribe"], reason="t"))


def _leased_ctx(tmp_path: Path, name: str) -> RunContext:
    from interview_mux.automation_run import take_gate_advance_lease

    ctx = _ctx(tmp_path, name, full_auto=True, run_mode="full-auto")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    take_gate_advance_lease(ctx, source="gui", gate_id="handle_gate")
    assert solver.lease_permits_acting(ctx) is False
    return ctx


def test_a_gui_lease_stops_the_solver_offering_anything(tmp_path: Path) -> None:
    """The lease is mirrored read-only, and it still refuses the whole set."""
    ctx = _leased_ctx(tmp_path, "auth_lease")
    assert list(_walk_sequence(ctx, ["transcribe"], reason="t")) == []


def test_the_walk_still_runs_the_dispatch_door_on_every_offered_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The solver composes with the door; it does not stand in for it."""
    ctx = _ctx(tmp_path, "auth_door")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)

    from interview_mux import dispatch_door

    real = dispatch_door.evaluate_dispatch
    asked: list[str] = []

    def _spy(c, stage, **kw):
        asked.append(stage)
        return real(c, stage, **kw)

    monkeypatch.setattr(dispatch_door, "evaluate_dispatch", _spy)
    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage", lambda c, s, **k: ran.append(s)
    )
    walk_seed_agenda(ctx, ["transcribe"], reason="auth_test")
    assert ran == ["transcribe"]
    assert set(asked) >= set(ran)


def test_a_solver_bug_mid_walk_falls_back_to_seed_order_instead_of_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generator raises inside the walk's loop, so the fallback has to live in it."""
    ctx = _ctx(tmp_path, "auth_bug")

    def _boom(*_a, **_k):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(solver, "admissible_set", _boom)
    stages = ["transcribe", "speaker_roles"]
    assert list(_walk_sequence(ctx, stages, reason="t")) == stages


# ---------------------------------------------------------------------------
# a door refusal keeps its side effects under authority
#
# Folding the door into admissibility (`evaluate_stage` step 8) would mean a
# door-refused stage is never yielded, so the walk's refusal path never runs — no
# defect ledger row, and `ShipUnreachable` becomes unreachable. These four tests are
# what the string-grep test they replaced could not say.
# ---------------------------------------------------------------------------

def test_the_authoritative_solver_hands_a_door_refused_stage_to_the_walk(
    tmp_path: Path,
) -> None:
    """The refusal is still real — the solver just is not the one acting on it."""
    ctx = _ctx(tmp_path, "auth_door_offers")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    _refuse_at_the_door(ctx, "transcribe")

    # What the fold would have done, kept here as the thing being avoided.
    excluded = solver.evaluate_stage(ctx, "transcribe", include_door=True)
    assert excluded.admissible is False
    assert excluded.reason == "door_refused:attempt_memo"

    verdict = solver.evaluate_stage(ctx, "transcribe")
    assert verdict.admissible is True
    assert verdict.confident is True
    assert verdict.detail["door_deferred_to_walk"] is True
    assert list(_walk_sequence(ctx, ["transcribe"], reason="t")) == ["transcribe"]


def test_the_observing_solver_still_treats_a_door_refusal_as_a_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shadow keeps the door, or it would report preferring a stage the walk refuses."""
    monkeypatch.delenv("MUX_SOLVER_AUTHORITATIVE", raising=False)
    ctx = _ctx(tmp_path, "auth_door_shadow")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    _refuse_at_the_door(ctx, "transcribe")

    assert solver.evaluate_stage(ctx, "transcribe").reason == "door_refused:attempt_memo"


def test_a_door_refused_stage_still_writes_its_defect_row_under_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1's advance-past ledger is the run's record that a stage was skipped."""
    from interview_mux.defect_ledger import read_defect_ledger

    ctx = _ctx(tmp_path, "auth_door_defect", full_auto=True, run_mode="full-auto")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    _refuse_at_the_door(ctx, "transcribe")
    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage", lambda c, s, **k: ran.append(s)
    )

    walk_seed_agenda(ctx, ["transcribe"], reason="auth_defect")

    assert ran == []
    rows = list((read_defect_ledger(ctx).get("defects") or {}).values())
    assert [(r["stage"], r["blocker"]) for r in rows] == [("transcribe", "attempt_memo")]


def test_the_ship_severance_halt_still_fires_under_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The halt only runs on a stage the walk was handed, so reachability is the claim.

    The severance analysis has its own tests; what promotion could break — and what a
    grep for the literal cannot show — is whether the walk still reaches it at all.
    """
    from interview_mux.ship_reachability import ShipUnreachable

    ctx = _ctx(tmp_path, "auth_door_halt", full_auto=True, run_mode="full-auto")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    _refuse_at_the_door(ctx, "transcribe")
    severed = {"blockers": ["producer_dead"], "resume": "transcribe", "unmet": []}
    monkeypatch.setattr(
        "interview_mux.ship_reachability.unreachable_halt", lambda _c: severed
    )
    monkeypatch.setattr("interview_mux.pipeline.run_single_stage", lambda c, s, **k: None)

    with pytest.raises(ShipUnreachable) as raised:
        walk_seed_agenda(ctx, ["transcribe"], reason="auth_severed")

    assert raised.value.payload["blockers"] == ["producer_dead"]


# ---------------------------------------------------------------------------
# a lease is a pause, not a halt
#
# `lease_held_by_gui` is run-level but applied per stage, so on its own it empties the
# admissible set. "Another session is walking this run" and "this run cannot proceed"
# need opposite operator responses, so they must not arrive as the same event.
# ---------------------------------------------------------------------------

def test_a_gui_lease_pauses_the_sequence_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    ctx = _leased_ctx(tmp_path, "auth_lease_pause")

    assert list(_walk_sequence(ctx, ["transcribe", "speaker_roles"], reason="t")) == []

    entry = _entry_saying(ctx, "the GUI holds a fresh lease")
    detail = parse_log_detail(entry)
    assert detail["kind"] == solver.PAUSE_LEASE
    assert detail["reason_code"] == solver.LEASE_REASON
    assert detail["waiting"] == ["transcribe", "speaker_roles"]
    assert "structural halt" not in _log_text(ctx)

    row = [r for r in solver.read_decisions(ctx, limit=50) if r["kind"] == "decision"][-1]
    assert row["halt_kind"] == solver.PAUSE_LEASE
    assert row["paused"] is True


def test_a_structural_halt_is_a_different_event_from_a_lease_pause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    ctx = _ctx(tmp_path, "auth_structural_halt")
    _stub_verdicts(monkeypatch, transcribe="blocked")

    assert list(_walk_sequence(ctx, ["transcribe"], reason="t")) == []

    assert "structural halt" in _log_text(ctx)
    assert "fresh lease" not in _log_text(ctx)
    row = [r for r in solver.read_decisions(ctx, limit=50) if r["kind"] == "decision"][-1]
    assert row["halt_kind"] == solver.HALT_STRUCTURAL
    assert row["paused"] is False


def test_a_lease_pause_costs_no_stage_evaluations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run-level answer must not be paid for 72 times per tick."""
    ctx = _leased_ctx(tmp_path, "auth_lease_cheap")
    evaluated: list[str] = []
    real = solver.evaluate_stage
    monkeypatch.setattr(
        solver,
        "evaluate_stage",
        lambda c, sid, **kw: (evaluated.append(sid), real(c, sid, **kw))[1],
    )

    assert list(_walk_sequence(ctx, list(solver.dispatchable_stages()), reason="t")) == []
    assert evaluated == []


def test_the_structural_halt_logs_enough_to_spot_a_bad_hard_input_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One over-declared `inputs.hard` retires a stage under authority, silently.

    A sibling owns the trajectory test for that. What has to be true here is that when
    it happens the halt is diagnosable from what the run wrote down.
    """
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    ctx = _ctx(tmp_path, "auth_halt_diagnosis")
    verdict = solver.StageVerdict(
        stage="edl",
        admissible=False,
        reasons=("hard_input_missing:master/selection.json",),
        detail={
            "producers": {"master/selection.json": "full_master_ranking"},
            "declared_hard_inputs": 3,
        },
        seed_index=40,
    )
    monkeypatch.setattr(solver, "evaluate_stage", lambda _c, _sid, **_k: verdict)

    assert list(_walk_sequence(ctx, ["edl"], reason="t")) == []

    detail = parse_log_detail(_entry_saying(ctx, "structural halt"))
    assert detail["reason_families"] == {"hard_input_missing": 1}
    assert detail["hard_input_blockers"] == [
        {
            "stage": "edl",
            "artifact": "master/selection.json",
            "blocker": "hard_input_missing",
            "producer": "full_master_ranking",
            "declared_hard_inputs": 3,
        }
    ]
    assert "hard_input_missing×1" in str(_entry_saying(ctx, "structural halt")["message"])


# ---------------------------------------------------------------------------
# the LLM is demoted to content-only
# ---------------------------------------------------------------------------

def test_the_conductor_loses_stage_selection_on_every_brain(tmp_path: Path) -> None:
    """0.1.0 still picks stages normally — but not while the solver is authoritative."""
    from interview_mux.homunculus.runtime import conductor_owns_control_flow

    ctx = _ctx(tmp_path, "auth_llm_010", homunculus_version="0.1.0")
    assert conductor_owns_control_flow(ctx) is False


def test_the_conductor_keeps_stage_selection_when_the_switch_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MUX_SOLVER_AUTHORITATIVE", raising=False)
    from interview_mux.homunculus.runtime import conductor_owns_control_flow

    ctx = _ctx(tmp_path, "auth_llm_010_off", homunculus_version="0.1.0")
    assert conductor_owns_control_flow(ctx) is True


def test_content_tier_brain_features_are_untouched_by_the_demotion(
    tmp_path: Path,
) -> None:
    """Content-only means the LLM keeps its content job, not that it is switched off."""
    from interview_mux.homunculus.runtime import (
        has_dispatch_ledger,
        has_homunculus_features,
    )

    ctx = _ctx(tmp_path, "auth_llm_features", homunculus_version="0.1.0")
    assert has_homunculus_features(ctx) is True
    assert has_dispatch_ledger(ctx) is True


# ---------------------------------------------------------------------------
# observability of the authoritative path
# ---------------------------------------------------------------------------

def test_the_authoritative_picks_are_logged_for_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    ctx = _ctx(tmp_path, "auth_logged")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)

    list(_walk_sequence(ctx, ["transcribe", "speaker_roles"], reason="t"))
    rows = [r for r in solver.read_decisions(ctx, limit=50) if r["kind"] == "decision"]
    assert rows
    assert rows[0]["would_choose_confident"] == "transcribe"


def test_the_halt_payload_names_what_is_blocking_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§10.2 — an empty set must arrive as a reason, not as a silent stop."""
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    ctx = _ctx(tmp_path, "auth_halt_payload")
    _stub_verdicts(monkeypatch, transcribe="blocked")

    assert list(_walk_sequence(ctx, ["transcribe"], reason="t")) == []
    rows = [r for r in solver.read_decisions(ctx, limit=50) if r["kind"] == "decision"]
    assert rows[-1]["admissible"] == []
    excluded = {row["stage"]: row["reason"] for row in rows[-1]["excluded"]}
    assert excluded == {"transcribe": "hard_input_missing:x"}
