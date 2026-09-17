"""p2-posture-tests (§8.2): the admissible set is a function of ``(state, posture)``.

A solver that ignores ``run_mode`` auto-advances ``transcript_review`` in
partially-accelerated mode and silently destroys the G0 contract. So every phase group
is exercised in all three postures, and ``PARTIAL_MUST_ACT_GATES`` /
``PARTIAL_MAY_PAUSE_GATES`` are pinned in parity with the frontend SSOT they mirror.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from interview_mux import solver
from interview_mux.automation_run import (
    PARTIAL_MAY_PAUSE_GATES,
    PARTIAL_MUST_ACT_GATES,
)
from interview_mux.run_context import RunContext
from interview_mux.v2.phases import PHASES
from run_fixtures import isolated_run_ctx, mark_done_raw

POSTURE_META: dict[str, dict[str, object]] = {
    solver.MANUAL: {"run_mode": "manual"},
    solver.PARTIAL: {"run_mode": "partially-accelerated", "partial_auto": True},
    solver.FULL_AUTO: {"run_mode": "full-auto", "full_auto": True},
}

# Phases that own at least one dispatchable stage — start / fix_transcript / edit
# are operator surfaces with no stages of their own.
STAGED_PHASES: tuple[str, ...] = tuple(
    str(p["id"]) for p in PHASES if p.get("stages")
)


def _ctx(tmp_path: Path, name: str, posture: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    meta: dict[str, object] = {
        "homunculus_version": "0.2.0",
        "homunculus_control_plane": "deterministic",
    }
    meta.update(POSTURE_META[posture])
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    return ctx


def _open_g0(ctx: RunContext) -> None:
    """G0 is open while a review queue exists and ``transcript_review`` is not done."""
    dest = ctx.final_path("transcript", "review_queue.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"chunks": [{"chunk_id": "c1"}]}), encoding="utf-8")


def _phase_stages(phase_id: str) -> list[str]:
    dispatchable = set(solver.dispatchable_stages())
    for phase in PHASES:
        if str(phase.get("id")) == phase_id:
            return [s for s in (phase.get("stages") or []) if s in dispatchable]
    return []


# ---------------------------------------------------------------------------
# frontend parity (§8.2 second SSOT warning)
# ---------------------------------------------------------------------------

def _ts_gate_list(name: str) -> list[str]:
    src = Path("frontend/src/utils/partialOperatorGates.ts").read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = \[(.*?)\] as const;", src, re.DOTALL)
    assert match, f"{name} not found in partialOperatorGates.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


def test_partial_gate_sets_match_the_frontend_ssot() -> None:
    """`PARTIAL_*_GATES` is a mirror — drift means GUI and solver disagree on who acts."""
    assert list(PARTIAL_MUST_ACT_GATES) == _ts_gate_list("PARTIAL_MUST_ACT_GATES")
    assert list(PARTIAL_MAY_PAUSE_GATES) == _ts_gate_list("PARTIAL_MAY_PAUSE_GATES")


def test_partial_gate_sets_are_disjoint_and_cover_the_solver_gates() -> None:
    assert not set(PARTIAL_MUST_ACT_GATES) & set(PARTIAL_MAY_PAUSE_GATES)
    known = set(PARTIAL_MUST_ACT_GATES) | set(PARTIAL_MAY_PAUSE_GATES)
    # `source_preclean` is deliberately absent from both: it is never auto-run, so it
    # is not an automation decision in any posture.
    assert set(solver.SOLVER_GATES) - known == {solver.G_PRECLEAN}


# ---------------------------------------------------------------------------
# gate enforcement per posture
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("posture", solver.POSTURES)
def test_g0_enforcement_follows_the_posture(posture: str) -> None:
    expected = "auto_accept" if posture == solver.FULL_AUTO else "block"
    assert solver.gate_enforcement(solver.G0, posture) == expected


@pytest.mark.parametrize("posture", solver.POSTURES)
def test_preclean_is_never_auto_run_in_any_posture(posture: str) -> None:
    assert solver.gate_enforcement(solver.G_PRECLEAN, posture) == "block"


@pytest.mark.parametrize("posture", solver.POSTURES)
def test_partial_may_pause_gates_never_hard_block(posture: str) -> None:
    for gate in PARTIAL_MAY_PAUSE_GATES:
        mode = solver.gate_enforcement(gate, posture)
        if posture == solver.MANUAL:
            assert mode == "block"
        elif posture == solver.PARTIAL:
            assert mode == "may_pause"
        else:
            assert mode == "auto_accept"


def test_posture_is_read_from_the_automation_run_ssot(tmp_path: Path) -> None:
    for posture in solver.POSTURES:
        ctx = _ctx(tmp_path, f"posture_{posture.replace('-', '_')}", posture)
        assert solver.posture_for(ctx) == posture
    assert solver.posture_for_meta({}) == solver.MANUAL


# ---------------------------------------------------------------------------
# the matrix: every phase group × every posture
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase_id", STAGED_PHASES)
@pytest.mark.parametrize("posture", solver.POSTURES)
def test_every_phase_stage_gets_a_specific_verdict(phase_id: str, posture: str, tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, f"matrix_{phase_id}_{posture}".replace("-", "_"), posture)
    for sid in _phase_stages(phase_id):
        verdict = solver.evaluate_stage(ctx, sid, posture=posture)
        assert verdict.phase == phase_id
        assert verdict.tier in {"process", "deterministic", "llm_full"}
        if not verdict.admissible:
            assert verdict.reason, f"{sid} excluded without a reason"
            assert ":" in verdict.reason or verdict.reason == "already_done"


@pytest.mark.parametrize("phase_id", STAGED_PHASES)
@pytest.mark.parametrize("posture", solver.POSTURES)
def test_open_g0_blocks_analysis_unless_full_auto(
    phase_id: str, posture: str, tmp_path: Path
) -> None:
    """G0 is mandatory in manual *and* partial; only full-auto auto-accepts it."""
    ctx = _ctx(tmp_path, f"g0_{phase_id}_{posture}".replace("-", "_"), posture)
    _open_g0(ctx)
    blocked = "gate_open:transcript_review"
    for sid in _phase_stages(phase_id):
        verdict = solver.evaluate_stage(ctx, sid, posture=posture)
        if sid in solver.G0_EXEMPT_STAGES:
            assert blocked not in verdict.reasons
            continue
        if posture == solver.FULL_AUTO:
            assert blocked not in verdict.reasons
        else:
            assert blocked in verdict.reasons


def test_partial_never_auto_advances_transcript_review(tmp_path: Path) -> None:
    """The G0 contract partial-auto must not destroy (§8.2)."""
    ctx = _ctx(tmp_path, "partial_g0", solver.PARTIAL)
    _open_g0(ctx)
    decision = solver.admissible_set(ctx, posture=solver.PARTIAL)
    for sid in decision.admissible:
        assert sid in solver.G0_EXEMPT_STAGES
    assert "gate_open:transcript_review" in (
        decision.verdict_for("speaker_roles").reasons
    )


def test_g_publish_blocks_publish_in_manual_and_partial_only(tmp_path: Path) -> None:
    results: dict[str, bool] = {}
    for posture in solver.POSTURES:
        ctx = _ctx(tmp_path, f"gpub_{posture}".replace("-", "_"), posture)
        master = ctx.final_path("master", "master.wav")
        master.parent.mkdir(parents=True, exist_ok=True)
        master.write_bytes(b"RIFF" + b"\x00" * 4096)
        assert solver.gate_open(ctx, solver.G_PUBLISH) is True
        verdict = solver.evaluate_stage(ctx, "podcast_publish", posture=posture)
        results[posture] = "gate_open:g_publish" in verdict.reasons
    assert results == {
        solver.MANUAL: True,
        solver.PARTIAL: True,
        solver.FULL_AUTO: False,
    }


def test_g_framing_gates_only_the_gap_consent_stages(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "gframing_scope", solver.MANUAL)
    assert solver.gates_blocking("missing_framing")[-1:] or True
    assert solver.G_FRAMING in solver.gates_blocking("missing_framing")
    assert solver.G_FRAMING in solver.gates_blocking("gap_framing_compose")
    assert solver.G_FRAMING not in solver.gates_blocking("edl")
    assert solver.gate_open(ctx, solver.G_FRAMING) is False


def test_preclean_enabled_without_an_operator_decision_is_refused(
    tmp_path: Path,
) -> None:
    """Never auto-run: an enable with no decision behind it did not come from a human."""
    ctx = isolated_run_ctx(tmp_path, "preclean_auto")
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "run_mode": "full-auto",
            "full_auto": True,
            "audio_preclean": {"enabled": True, "scope": "full_source"},
        },
        skip_handoff=True,
    )
    verdict = solver.evaluate_stage(ctx, "audio_preclean")
    assert verdict.admissible is False
    assert verdict.reason == "gate_open:source_preclean"

    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "run_mode": "full-auto",
            "full_auto": True,
            "audio_preclean": {
                "enabled": True,
                "scope": "full_source",
                "requested_at": "2026-01-01T00:00:00Z",
                "decisions": [{"action": "accept", "checkpoint": "before_ingest"}],
            },
        },
        skip_handoff=True,
    )
    assert solver.gate_open(ctx, solver.G_PRECLEAN) is False


@pytest.mark.parametrize("phase_id", STAGED_PHASES)
def test_posture_only_moves_gate_terms_not_contract_terms(
    phase_id: str, tmp_path: Path
) -> None:
    """Contract-derived exclusions are posture-invariant; only gates react to posture."""
    per_posture: dict[str, dict[str, tuple[str, ...]]] = {}
    for posture in solver.POSTURES:
        ctx = _ctx(tmp_path, f"inv_{phase_id}_{posture}".replace("-", "_"), posture)
        _open_g0(ctx)
        per_posture[posture] = {
            sid: tuple(
                r
                for r in solver.evaluate_stage(ctx, sid, posture=posture).reasons
                if not r.startswith("gate_")
            )
            for sid in _phase_stages(phase_id)
        }
    reference = per_posture[solver.MANUAL]
    for posture in solver.POSTURES:
        assert per_posture[posture] == reference


def test_a_done_run_is_admissible_nowhere_in_any_posture(tmp_path: Path) -> None:
    """Termination is structural: every stage done ⇒ the admissible set is empty."""
    for posture in solver.POSTURES:
        ctx = _ctx(tmp_path, f"terminal_{posture}".replace("-", "_"), posture)
        for sid in solver.dispatchable_stages():
            mark_done_raw(ctx, sid)
        # Hollow markers are not done (§8.5), so patch the outputs predicate to the
        # "everything landed" case this test is about.
        import interview_mux.solver as solver_mod

        original = solver_mod.stage_done
        try:
            solver_mod.stage_done = lambda _ctx, _sid: True  # type: ignore[assignment]
            decision = solver.admissible_set(ctx, posture=posture)
        finally:
            solver_mod.stage_done = original  # type: ignore[assignment]
        assert decision.admissible == ()
        assert decision.would_choose is None
        assert set(decision.exclusions().values()) == {"already_done"}
