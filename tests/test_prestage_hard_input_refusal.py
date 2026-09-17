"""A declared hard input must not be able to crash a live stage.

`pipeline.run_single_stage` turns any error returned by
`artifact_lifecycle.run_phase_checks` at `PRESTAGE` into a `ValueError`, and
`MUX_CONTRACT_REQUIRES` does not gate that path. So while contract population is
in flight, one declaration on a conditionally produced artifact — say a hard input
on `preclean/isolated.wav`, which is absent on every run where the operator skipped
preclean even though `audio_preclean` is marked done — would hard-fail that stage on
the live default brain.

The split these tests pin:

* **absent** artifact → refusal, recorded in the defect ledger and the resilience
  report, never fatal (unless `MUX_CONTRACT_HARD_INPUT_STRICT=1`).
* **stale stamp** → still fatal. Produced-then-invalidated is a real ordering
  problem, and `delivery_guardrails.upstream_stale_blockers` raises for it on the
  same code path anyway.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux import artifact_lifecycle as al
from interview_mux import stage_contract as sc
from interview_mux.artifact_lifecycle import LifecyclePhase, run_phase_checks
from interview_mux.defect_ledger import read_defect_ledger
from interview_mux.file_store import write_json as fs_write_json
from interview_mux.run_context import RunContext
from interview_mux.stage_contract import is_path_spec
from interview_mux.stage_resilience import RESILIENCE_REPORT_REL
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw

ALL_STAGES = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
CONDITIONAL_INPUT = "preclean/isolated.wav"


def _ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    _seed(ctx, "run_meta.json", {"homunculus_version": "0.2.0", "run_mode": "full-auto"})
    return ctx


def _seed(ctx: RunContext, rel: str, doc: dict) -> None:
    """Write an artifact without stage attribution — ownership is not under test."""
    dest = Path(ctx.run_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(dest, doc)


def _declare(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    *,
    path: str,
    hard: bool = True,
    producer: str | None = None,
) -> None:
    """Pretend `stage`'s contract declares `path`, the way population would."""
    contract = sc.StageContract(
        stage_id=stage,
        inputs=[sc.InputDep(path=path, hard=hard, producer=producer)],
    )
    monkeypatch.setattr(sc, "load_contract", lambda sid: contract if sid == stage else None)


# ---------------------------------------------------------------------------
# The regression this module exists for
# ---------------------------------------------------------------------------

def test_hard_input_on_a_conditional_artifact_cannot_hard_fail_a_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, "prestage_conditional")
    # The shape of the trap: producer done, primary absent because it was skipped.
    _seed(ctx, "preclean/skip.json", {"skipped": True})
    mark_done_raw(ctx, "audio_preclean")
    _declare(monkeypatch, "content_context", path=CONDITIONAL_INPUT, producer="audio_preclean")

    assert not ctx.artifact_exists(CONDITIONAL_INPUT)
    assert run_phase_checks(ctx, "content_context", LifecyclePhase.PRESTAGE) == []


def test_the_refusal_is_recorded_not_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, "prestage_recorded")
    _declare(monkeypatch, "content_context", path=CONDITIONAL_INPUT, producer="audio_preclean")

    run_phase_checks(ctx, "content_context", LifecyclePhase.PRESTAGE)

    defects = (read_defect_ledger(ctx).get("defects") or {}).values()
    rows = [
        row
        for row in defects
        if row.get("blocker") == al.MISSING_HARD_INPUT_BLOCKER
        and row.get("artifact") == CONDITIONAL_INPUT
    ]
    assert rows, "an absent hard input must leave a defect row, not pass unnoticed"
    assert rows[0].get("stage") == "content_context"
    assert (rows[0].get("detail") or {}).get("producer") == "audio_preclean"

    report = ctx.read_json(RESILIENCE_REPORT_REL)
    events = [
        ev
        for ev in (report.get("events") or [])
        if ev.get("event") == "prestage_missing_hard_input"
    ]
    assert events and events[0].get("action") == "refuse"


def test_strict_mode_restores_todays_fatal_behaviour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, "prestage_strict")
    _declare(monkeypatch, "content_context", path=CONDITIONAL_INPUT, producer="audio_preclean")
    monkeypatch.setenv("MUX_CONTRACT_HARD_INPUT_STRICT", "1")

    errors = run_phase_checks(ctx, "content_context", LifecyclePhase.PRESTAGE)
    assert errors and CONDITIONAL_INPUT in errors[0]


def test_strict_is_off_by_default() -> None:
    """The safe setting for a live 0.2.0 run is refusal, not exception."""
    assert al.hard_input_strict() is False


def test_pipeline_only_raises_on_a_returned_lifecycle_error() -> None:
    """Why an empty return above is the whole proof.

    `run_single_stage` raises at PRESTAGE when — and only when — `run_phase_checks`
    hands it a non-empty list. A refusal instead takes the non-fatal channel
    (`prestage_refused`, pinned in `test_prestage_refusal_channel.py`) and the
    downstream rails (`stage_input_checks`, seed order, `llm_flow_hardening`) still
    refuse without a lifecycle exception. So this pins the raise coupling.
    """
    import inspect

    from interview_mux import pipeline

    src = inspect.getsource(pipeline.run_single_stage)
    assert "pre_errors = run_phase_checks(ctx, stage, LifecyclePhase.PRESTAGE)" in src
    body = src.split("pre_errors = run_phase_checks", 1)[1]
    guard = body.split("\n\n", 1)[0]
    assert "if pre_errors:" in guard and "raise ValueError" in guard, (
        "the PRESTAGE raise moved — re-check what an absent hard input now does"
    )


# ---------------------------------------------------------------------------
# The protection that must survive
# ---------------------------------------------------------------------------

def test_a_stale_stamp_is_still_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Produced then invalidated is an ordering problem, and refusing to run is right."""
    ctx = _ctx(tmp_path, "prestage_stale")
    _seed(
        ctx,
        "understanding/content_context.json",
        {"summary": "x", "_meta": {"stale": True, "stale_reason": "invalidated_by:transcribe"}},
    )
    _declare(
        monkeypatch,
        "talking_points_compose",
        path="understanding/content_context.json",
        producer="content_context",
    )

    errors = run_phase_checks(ctx, "talking_points_compose", LifecyclePhase.PRESTAGE)
    assert errors, "a stale hard input must still stop the stage"


def test_a_present_input_is_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, "prestage_present")
    _seed(ctx, "understanding/content_context.json", {"summary": "x"})
    _declare(
        monkeypatch,
        "talking_points_compose",
        path="understanding/content_context.json",
        producer="content_context",
    )

    assert run_phase_checks(ctx, "talking_points_compose", LifecyclePhase.PRESTAGE) == []
    ledger = read_defect_ledger(ctx).get("defects") or {}
    assert not [r for r in ledger.values() if r.get("blocker") == al.MISSING_HARD_INPUT_BLOCKER]


def test_a_declared_family_is_never_treated_as_a_required_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`vo_pickup/` and `glob:` specs can never satisfy `artifact_exists`."""
    ctx = _ctx(tmp_path, "prestage_family")
    for spec in ("master/transitions/", "glob:transcript/review_clips/*.wav"):
        _declare(monkeypatch, "transitions", path=spec)
        assert run_phase_checks(ctx, "transitions", LifecyclePhase.PRESTAGE) == []
        ledger = read_defect_ledger(ctx).get("defects") or {}
        assert not [
            r for r in ledger.values() if r.get("blocker") == al.MISSING_HARD_INPUT_BLOCKER
        ], f"{spec} was treated as a missing file"


def test_a_soft_input_is_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, "prestage_soft")
    _declare(monkeypatch, "content_context", path=CONDITIONAL_INPUT, hard=False)

    assert run_phase_checks(ctx, "content_context", LifecyclePhase.PRESTAGE) == []
    ledger = read_defect_ledger(ctx).get("defects") or {}
    assert not [r for r in ledger.values() if r.get("blocker") == al.MISSING_HARD_INPUT_BLOCKER]


def test_todays_declarations_are_unaffected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every hard input declared right now still refuses when absent — recorded, not raised."""
    ctx = _ctx(tmp_path, "prestage_live_contracts")
    declared = 0
    for sid in ALL_STAGES:
        contract = sc.load_contract(sid)
        if contract is None:
            continue
        declared += sum(
            1 for i in contract.inputs if i.hard and i.path and not i.when and not is_path_spec(i.path)
        )
        assert run_phase_checks(ctx, sid, LifecyclePhase.PRESTAGE) == [], (
            f"{sid} would hard-fail on an empty run"
        )
    rows = [
        r
        for r in (read_defect_ledger(ctx).get("defects") or {}).values()
        if r.get("blocker") == al.MISSING_HARD_INPUT_BLOCKER
    ]
    assert len(rows) >= min(declared, 1), "the refusals must be recorded, not swallowed"
