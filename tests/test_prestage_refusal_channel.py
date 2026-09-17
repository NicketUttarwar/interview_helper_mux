"""A recorded pre-stage refusal must be able to *stop* the stage, not just log itself.

`artifact_lifecycle` learned to record an absent declared hard input as a refusal
instead of raising, but `pipeline.run_single_stage` had one channel for a
lifecycle verdict: return errors, get a `ValueError`. So the refused stage
recorded its defect and ran on anyway, and whether it stopped depended on the
downstream rails catching the same absence a second time.

`prestage_refused` is the second, non-fatal channel: it returns `True`, and
`run_single_stage` returns without a done marker. What these tests pin:

* the stage body does not run and no done marker appears — a refusal is not a pass;
* the refusal lands in every ledger a dispatch-door refusal lands in;
* the decision is re-derived per attempt, so the still-open defect row cannot
  keep a stage refused after its input arrives;
* strict mode is unchanged, and the downstream rails still fire for everything
  this channel does not cover.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from interview_mux import artifact_lifecycle as al
from interview_mux import pipeline
from interview_mux import stage_contract as sc
from interview_mux.artifact_lifecycle import LifecyclePhase, run_phase_checks
from interview_mux.defect_ledger import read_defect_ledger
from interview_mux.dispatch_delta import memo_row
from interview_mux.file_store import write_json as fs_write_json
from interview_mux.homunculus.ledger import read_ledger
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx

STAGE = "content_context"
MISSING = "preclean/isolated.wav"
PRESENT = "understanding/source_topology.json"


@pytest.fixture()
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    run = isolated_run_ctx(tmp_path, "prestage_channel")
    # 0.0.0 keeps `run_single_stage` on the plain `run_wrapped_stage` path, so the
    # refusal is the only thing that can stop the stage in these tests.
    _seed(run, "run_meta.json", {"homunculus_version": "0.0.0", "run_mode": "full-auto"})
    return run


def _seed(run: RunContext, rel: str, doc: dict) -> None:
    dest = Path(run.run_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(dest, doc)


def _declare(monkeypatch: pytest.MonkeyPatch, stage: str, path: str) -> None:
    contract = sc.StageContract(
        stage_id=stage,
        inputs=[sc.InputDep(path=path, hard=True, producer="audio_preclean")],
    )
    monkeypatch.setattr(sc, "load_contract", lambda sid: contract if sid == stage else None)


def _spy_body(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    ran: list[str] = []
    monkeypatch.setattr(
        pipeline, "_run_single_stage_impl", lambda _ctx, stage: ran.append(stage)
    )
    return ran


def _let_the_body_be_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence the downstream rails so "did the stage run?" is about this channel alone.

    On an empty run `run_wrapped_stage` raises `StageInputError` and
    `llm_flow_hardening` raises `SystemExit` long before any stage body — which is
    exactly what they are for. Both are pinned live in the last section.
    """
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.require_stage_inputs", lambda _ctx, _stage: None
    )
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.maybe_require_upstream_llm_progress",
        lambda _ctx, _stage: None,
    )


# ---------------------------------------------------------------------------
# the channel
# ---------------------------------------------------------------------------

def test_a_refused_stage_does_not_run_and_does_not_raise(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, STAGE, MISSING)
    ran = _spy_body(monkeypatch)

    pipeline.run_single_stage(ctx, STAGE)

    assert ran == [], "the stage body ran after its declared hard input was refused"
    assert not ctx.is_done(STAGE), "a refusal must never leave a done marker"


def test_the_refusal_lands_in_every_ledger(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, STAGE, MISSING)
    _spy_body(monkeypatch)

    pipeline.run_single_stage(ctx, STAGE)

    rows = [
        row
        for row in (read_defect_ledger(ctx).get("defects") or {}).values()
        if row.get("blocker") == al.MISSING_HARD_INPUT_BLOCKER and row.get("stage") == STAGE
    ]
    # Two rows, one per fact: the input that is absent, and the output that will
    # not appear because of it. `record_defect` keys on (stage, blocker, artifact).
    assert {str(r.get("artifact") or "") for r in rows} >= {MISSING}
    assert len(rows) == 2, f"expected input + output rows, got {rows}"

    assert memo_row(ctx, STAGE).get("outcome") == "refused", (
        "without an attempt-memo row the walk re-offers a stage that cannot proceed"
    )
    ledger = [r for r in read_ledger(ctx) if r.get("identity") == STAGE]
    assert [r for r in ledger if r.get("status") == "refused"]
    assert not [r for r in ledger if r.get("status") in {"started", "done"}]


def test_the_blocker_can_never_sever_reachability(ctx: RunContext) -> None:
    from interview_mux.ship_reachability import TERMINAL_BLOCKERS, ship_reachable

    assert al.MISSING_HARD_INPUT_BLOCKER not in TERMINAL_BLOCKERS
    al._missing_hard_input(ctx, STAGE, MISSING, producer="audio_preclean")
    assert ship_reachable(ctx).reachable, "a spurious declaration severed the ship path"


def test_the_verdict_is_re_derived_once_the_input_arrives(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect row stays open until the stage produces — reading it would strand."""
    _declare(monkeypatch, STAGE, PRESENT)
    ran = _spy_body(monkeypatch)
    _let_the_body_be_reached(monkeypatch)

    pipeline.run_single_stage(ctx, STAGE)
    assert ran == []

    _seed(ctx, PRESENT, {"speakers": []})
    pipeline.run_single_stage(ctx, STAGE)

    assert ran == [STAGE], "the stage stayed refused after its hard input landed"
    assert al.prestage_refusals(ctx, STAGE) == ()


def test_a_stage_with_nothing_missing_is_untouched(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, STAGE, PRESENT)
    _seed(ctx, PRESENT, {"speakers": []})
    ran = _spy_body(monkeypatch)
    _let_the_body_be_reached(monkeypatch)

    pipeline.run_single_stage(ctx, STAGE)

    assert ran == [STAGE]
    assert not [
        r
        for r in (read_defect_ledger(ctx).get("defects") or {}).values()
        if r.get("blocker") == al.MISSING_HARD_INPUT_BLOCKER
    ]


def test_strict_mode_still_raises_instead_of_refusing(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declare(monkeypatch, STAGE, MISSING)
    monkeypatch.setenv("MUX_CONTRACT_HARD_INPUT_STRICT", "1")
    ran = _spy_body(monkeypatch)

    with pytest.raises(ValueError, match="Pre-stage lifecycle failed"):
        pipeline.run_single_stage(ctx, STAGE)

    assert ran == []
    assert al.prestage_refusals(ctx, STAGE) == (), "strict mode must not also refuse"


def test_the_channel_sits_immediately_after_the_lifecycle_call() -> None:
    """Ordering is the contract: refuse before anything else can act on the stage."""
    src = inspect.getsource(pipeline.run_single_stage)
    lifecycle = src.index("pre_errors = run_phase_checks")
    refusal = src.index("prestage_refused(ctx, stage)")
    reuse = src.index("_guard_stage_reuse(ctx, stage)")
    assert lifecycle < refusal < reuse
    assert "return" in src[refusal : src.index("\n", src.index("\n", refusal) + 1) + 1]


# ---------------------------------------------------------------------------
# the safety net this must not weaken
# ---------------------------------------------------------------------------

def test_the_channel_does_not_replace_the_input_rail(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract satisfied, real inputs absent — `run_single_stage` must still stop.

    The declared input exists, so the refusal channel passes the stage through.
    What stops it is `run_wrapped_stage` → `require_stage_inputs`, the rail that
    already protected every stage before this channel existed.
    """
    from interview_mux.stage_input_checks import StageInputError

    _declare(monkeypatch, STAGE, PRESENT)
    _seed(ctx, PRESENT, {"speakers": []})
    ran = _spy_body(monkeypatch)

    with pytest.raises(StageInputError):
        pipeline.run_single_stage(ctx, STAGE)

    assert ran == []
    assert not ctx.is_done(STAGE)


def test_the_channel_does_not_replace_the_llm_progress_rail(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second rail behind it: an incomplete upstream LLM stage still halts."""
    _declare(monkeypatch, STAGE, PRESENT)
    _seed(ctx, PRESENT, {"speakers": []})
    ran = _spy_body(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.require_stage_inputs", lambda _ctx, _stage: None
    )

    with pytest.raises(SystemExit, match="not complete"):
        pipeline.run_single_stage(ctx, STAGE)

    assert ran == []


def test_stage_input_checks_still_refuses_what_no_contract_declares(
    ctx: RunContext,
) -> None:
    """The real protection today: typed `StageInputError`, handled as an operator pause.

    Nothing above declares `edl`'s inputs, so this rail is the only thing standing
    between an empty run and a stage body reading a file that is not there. It must
    keep firing for every case the contract channel does not cover.
    """
    from interview_mux.stage_input_checks import StageInputError, require_stage_inputs

    with pytest.raises(StageInputError):
        require_stage_inputs(ctx, "edl")

    handler = inspect.getsource(
        __import__("interview_mux.web.runner", fromlist=["runner"])
    )
    assert "StageInputError" in handler, "the soft operator pause for this rail is gone"


def test_a_stale_hard_input_is_still_fatal(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Produced-then-invalidated is an ordering bug; the refusal channel must not eat it."""
    _seed(
        ctx,
        PRESENT,
        {"speakers": [], "_meta": {"stale": True, "stale_reason": "invalidated_by:transcribe"}},
    )
    _declare(monkeypatch, STAGE, PRESENT)
    ran = _spy_body(monkeypatch)

    assert run_phase_checks(ctx, STAGE, LifecyclePhase.PRESTAGE)
    with pytest.raises(ValueError):
        pipeline.run_single_stage(ctx, STAGE)
    assert ran == []
