"""p2-shadow (§6.2): log what the walk chose against what the solver would have.

The whole value of this mode is one number — non-deferred disagreements — so the
tests here are mostly about keeping that number honest. A *deferred* verdict is the
solver declining to have an opinion because its contract does not yet say enough, and
39 of the 72 stages are in that position today. Counting those as disagreements would
report ~39 problems that are not problems and hide the handful that are.

LIVE-RUN STATUS: the plan's success condition is "log disagreement on a live run
until zero". These tests prove the machinery and the summariser; they do not and
cannot substitute for a real tape. A forensics campaign is in flight, so no fresh
``exec_*`` was spawned. Live validation is pending the operator's next real run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import solver
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw

SUFFICIENT_WAV = b"RIFF" + b"\x00" * 4096


@pytest.fixture(autouse=True)
def _shadow_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_SOLVER_SHADOW", "1")
    monkeypatch.delenv("MUX_SOLVER_AUTHORITATIVE", raising=False)


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


def _shadow_rows(ctx: RunContext) -> list[dict]:
    return [r for r in solver.read_decisions(ctx, limit=500) if r.get("kind") == "shadow"]


def _stub_verdicts(monkeypatch: pytest.MonkeyPatch, **kinds: str) -> None:
    """Pin per-stage verdicts so an ordering rule can be tested on its own.

    Only ``prepare`` is a strict contract group today, so a real fixture cannot yet
    reach a state with two *confidently* admissible stages. The classification rule is
    the unit under test here, not contract population.
    """
    verdicts = {
        sid: solver.StageVerdict(
            stage=sid,
            admissible=kind != "blocked",
            reasons=() if kind != "blocked" else ("hard_input_missing:x",),
            unknowns=() if kind != "deferred" else ("inputs_undeclared",),
        )
        for sid, kind in kinds.items()
    }
    monkeypatch.setattr(
        solver, "evaluate_stage", lambda _ctx, sid, **_k: verdicts[sid]
    )


# ---------------------------------------------------------------------------
# the three verdicts
# ---------------------------------------------------------------------------

def test_agreement_when_the_walk_picks_the_stage_the_solver_would_have(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path, "shadow_agree")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)

    out = solver.observe_walk_choice(
        ctx, "transcribe", candidates=("transcribe", "speaker_roles"), source="test"
    )
    assert out is not None
    assert out.verdict == solver.AGREE
    assert out.solver_choice == "transcribe"
    assert out.reason == ""


def test_a_stage_the_solver_proved_blocked_is_a_real_disagreement(
    tmp_path: Path,
) -> None:
    """The valuable class: either the contract is wrong or a walk rule is not declarative."""
    ctx = _ctx(tmp_path, "shadow_disagree")
    # No normalized.wav on disk, so transcribe's hard input is provably unmet.
    out = solver.observe_walk_choice(ctx, "transcribe", candidates=("transcribe",))
    assert out is not None
    assert out.verdict == solver.DISAGREE
    assert out.reason == "hard_input_missing:ingest/normalized.wav"
    assert out.detail["reasons"] == [out.reason]


def test_a_deferred_verdict_is_not_counted_as_a_disagreement(tmp_path: Path) -> None:
    """39 of 72 stages declare no hard inputs — the solver has no opinion on them."""
    ctx = _ctx(tmp_path, "shadow_defer")
    deferred = [
        sid
        for sid in solver.dispatchable_stages()
        if solver.evaluate_stage(ctx, sid).deferred
    ]
    assert deferred, "expected at least one stage with an unpopulated contract"

    out = solver.observe_walk_choice(ctx, deferred[0], candidates=(deferred[0],))
    assert out is not None
    assert out.verdict == solver.DEFER
    assert out.disagrees is False
    assert out.reason.startswith("verdict_deferred:")
    assert solver.shadow_summary(ctx)["zero"] is True


def test_a_gate_pseudo_stage_the_walk_breaks_on_is_a_deferral_not_a_disagreement(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path, "shadow_nonstage")
    out = solver.observe_walk_choice(ctx, "transcript_review", candidates=())
    assert out is not None
    assert out.verdict == solver.DEFER
    assert out.reason == "chosen_not_dispatchable"


def test_an_ordering_disagreement_names_the_stage_the_solver_would_have_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both stages are confidently admissible; the walk skipped the earlier one."""
    ctx = _ctx(tmp_path, "shadow_prefers")
    _stub_verdicts(monkeypatch, transcribe="confident", speaker_roles="confident")

    out = solver.compare_walk_choice(ctx, "speaker_roles", ("transcribe", "speaker_roles"))
    assert out.verdict == solver.DISAGREE
    assert out.reason == "solver_prefers:transcribe"
    assert out.solver_choice == "transcribe"


def test_an_ordering_opinion_the_contracts_cannot_justify_is_never_a_disagreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deferred pick must not be dressed up as `solver_prefers` — that inflates zero."""
    ctx = _ctx(tmp_path, "shadow_prefers_unconfident")
    _stub_verdicts(monkeypatch, transcribe="deferred", speaker_roles="confident")

    out = solver.compare_walk_choice(ctx, "speaker_roles", ("transcribe", "speaker_roles"))
    assert out.verdict == solver.AGREE
    assert out.reason == ""


def test_a_blocked_stage_the_walk_passed_over_is_not_a_preference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, "shadow_prefers_blocked")
    _stub_verdicts(monkeypatch, transcribe="blocked", speaker_roles="confident")

    out = solver.compare_walk_choice(ctx, "speaker_roles", ("transcribe", "speaker_roles"))
    assert out.verdict == solver.AGREE


def test_the_comparison_is_scoped_to_the_candidates_the_walk_actually_had(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The walk cannot choose a stage its own filters removed — nor can the solver."""
    ctx = _ctx(tmp_path, "shadow_scope")
    _stub_verdicts(monkeypatch, transcribe="confident", speaker_roles="confident")

    # transcribe is admissible but was not on offer, so it is not a preference.
    out = solver.observe_walk_choice(ctx, "speaker_roles", candidates=("speaker_roles",))
    assert out is not None
    assert out.candidates == 1
    assert out.verdict == solver.AGREE
    assert out.solver_choice == "speaker_roles"


# ---------------------------------------------------------------------------
# the summariser — "is it zero yet?" without parsing the log
# ---------------------------------------------------------------------------

def test_the_summariser_counts_agreement_disagreement_and_deferral_apart(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path, "shadow_summary")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
    solver.observe_walk_choice(ctx, "transcribe", candidates=("transcribe",))  # agree

    deferred = next(
        sid
        for sid in solver.dispatchable_stages()
        if solver.evaluate_stage(ctx, sid).deferred
    )
    solver.observe_walk_choice(ctx, deferred, candidates=(deferred,))  # defer

    mark_done_raw(ctx, "transcribe")
    _commit(ctx, "transcript/full.json", {"items": [{"text": "hi"}]})
    solver.observe_walk_choice(ctx, "transcribe", candidates=("transcribe",))  # disagree

    summary = solver.shadow_summary(ctx)
    assert summary["observations"] == 3
    assert summary["agree"] == 1
    assert summary["defer"] == 1
    assert summary["disagree"] == 1
    assert summary["zero"] is False
    assert summary["agreement_rate"] == 0.5
    assert set(summary["disagreement_families"]) == {"already_done"}
    assert summary["disagreements"][-1]["walk_chose"] == "transcribe"


def test_zero_is_keyed_on_disagreement_alone_so_deferrals_cannot_block_promotion(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path, "shadow_zero")
    for sid in solver.dispatchable_stages():
        if solver.evaluate_stage(ctx, sid).deferred:
            solver.observe_walk_choice(ctx, sid, candidates=(sid,))

    summary = solver.shadow_summary(ctx)
    assert summary["defer"] > 0
    assert summary["disagree"] == 0
    assert summary["zero"] is True


def test_shadow_rows_land_in_the_one_decision_artifact(tmp_path: Path) -> None:
    """`solver_shadow.jsonl` and `solver_decision.jsonl` were one file named twice."""
    ctx = _ctx(tmp_path, "shadow_one_file")
    solver.observe_walk_choice(ctx, "ingest", candidates=("ingest",))

    path = Path(ctx.run_dir) / solver.SOLVER_DECISION_REL
    assert path.is_file()
    assert not (Path(ctx.run_dir) / "operator/solver_shadow.jsonl").exists()

    rows = _shadow_rows(ctx)
    assert len(rows) == 1
    assert rows[0]["walk_chose"] == "ingest"
    assert rows[0]["verdict"] in solver.SHADOW_VERDICTS
    assert "solver_would_choose" in rows[0]


def test_the_summariser_ignores_plain_decision_rows(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "shadow_mixed")
    solver.log_decision(ctx, solver.admissible_set(ctx))
    solver.observe_walk_choice(ctx, "ingest", candidates=("ingest",))
    assert solver.shadow_summary(ctx)["observations"] == 1


# ---------------------------------------------------------------------------
# the walk seam
# ---------------------------------------------------------------------------

def test_the_walk_records_one_observation_per_stage_it_commits_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook sits where the walk has decided, immediately before dispatch."""
    from interview_mux.homunculus import agenda

    ctx = _ctx(tmp_path, "shadow_walk_seam")
    _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)

    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage",
        lambda c, s, **k: ran.append(s),
    )
    agenda.walk_seed_agenda(ctx, ["transcribe", "speaker_roles"], reason="test")

    observed = [r["walk_chose"] for r in _shadow_rows(ctx)]
    assert observed == ran, (observed, ran)


def test_the_walk_is_unchanged_by_shadow_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same stages, same order, shadow armed or silenced."""
    from interview_mux.homunculus import agenda

    def _walk(name: str, shadow: str) -> list[str]:
        monkeypatch.setenv("MUX_SOLVER_SHADOW", shadow)
        ctx = _ctx(tmp_path, name)
        _commit(ctx, "ingest/normalized.wav", SUFFICIENT_WAV)
        ran: list[str] = []
        monkeypatch.setattr(
            "interview_mux.pipeline.run_single_stage",
            lambda c, s, **k: ran.append(s),
        )
        agenda.walk_seed_agenda(ctx, ["transcribe", "speaker_roles"], reason="test")
        return ran

    assert _walk("shadow_off_walk", "0") == _walk("shadow_on_walk", "1")


def test_shadow_mode_is_armed_without_anyone_setting_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The operator's next campaign run must collect this data unattended."""
    monkeypatch.delenv("MUX_SOLVER_SHADOW", raising=False)
    ctx = _ctx(tmp_path, "shadow_default_on")
    assert solver.observe_walk_choice(ctx, "ingest", candidates=("ingest",)) is not None
    assert solver.shadow_summary(ctx)["observations"] == 1
