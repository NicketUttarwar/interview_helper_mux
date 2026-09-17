"""Does the solver's OWN sequence reach the end? — the gate replay structurally cannot give.

``tools/solver_replay.py`` asks, at every dispatch a completed run actually made, "what
would the solver have picked here". That is pick-by-pick agreement, and its own fidelity
list names the hole it leaves::

    Replay proves what the solver would have DECIDED given reconstructed state. It
    cannot prove what the run would have DONE: a refused dispatch changes every
    subsequent state, and the replay always follows the driver's actual path. **No
    counterfactual trajectory is explored.**

That hole is not academic, because ``authoritative_sequence`` *ends the walk* when
nothing is admissible (``solver.py`` §7, the §2.1 structural halt). One over-declared
``inputs.hard`` entry therefore retires its stage permanently — where the unpromoted
walk would hand the stage over and let the pre-stage checks decide — and every consumer
downstream of it retires with it. Pick-by-pick comparison cannot see that, because it
never follows the solver's own path forward.

So this module does follow it. For each run in the replay corpus it drains
``authoritative_sequence`` end to end against a reconstruction of that run's opening
state, applying the counterfactual "this stage ran and succeeded" after every yielded
stage, and asserts two properties:

1. **Ordered superset.** Every stage the driver's history *proves it needed* appears in
   the solver's sequence, and no stage is yielded before a producer it declares a hard
   input from.
2. **No premature termination.** The sequence does not end while proven-needed work
   remained. This is the direct test for early retirement.

**Legitimate skip vs genuine omission is the whole difficulty.** The corpus contains 590
dispatches of an already-complete stage, 359 of them conductor-sourced; refusing to
re-run finished work is *correct*, and a test that counted dispatches rather than stages
would fail on the solver being right. The witness for "genuinely needed" is therefore
the driver's own history, to the same standard ``solver_replay.regression_proof``
already sets for D12's second condition — reused by calling that function, not
reimplemented: the ledger recorded the stage ``done``, nothing invalidated it after
that, and the driver never started it again. A completion that stuck is work that was
needed; a dispatch that failed, was invalidated, or was re-attempted forever proves
nothing and is never held against the solver.

**What the counterfactual can and cannot model.** The effect of a yielded stage is
simulated by materialising that stage's declared outputs *from the run's own final
bytes* — so a stage whose outputs no longer exist in the corpus cannot be simulated at
all, and everything blocked behind it is unreachable for reasons that have nothing to
do with the solver. Those halts are classified ``evidence_limited`` and excluded from
the assertion, but only when the corpus genuinely does not hold the bytes
(``_corpus_holds``). A blocker naming an artifact the corpus *does* hold is never
excused — that is the early-retirement signature, and
``test_the_evidence_limited_excuse_cannot_cover_an_artifact_the_corpus_holds`` pins the
escape hatch shut.

Two further concessions, both narrow and both inherited from the replay's own model:

* ``run_meta.json`` is pinned to final content (posture, brain id, automation mode are
  run-level constants).
* ``.stage_done`` markers that are **not** pipeline stages — the operator's G0 sign-off
  (``transcript_review``) and retired substep markers — are pinned as answered from the
  start, because a counterfactual walk cannot ask the operator a gate question. Every
  marker for one of the 72 *pipeline* stages still has to be earned by the trajectory.
  Without this, 8 of the 22 substantive runs halt after four stages on
  ``gate_open:transcript_review``, which measures the absence of an operator, not the
  solver.

**What these properties do NOT cover**, stated here rather than left to be assumed:

* Order is checked only where the *contracts force it* (``producer_precedence``). The
  driver's full sequence is deliberately not the expectation: the solver runs
  ``listen_delight_audit`` before ``podcast_publish`` where the driver ran it after, and
  demanding the driver's order would fail on the solver being right.
* An over-declared hard input naming an artifact the run *does* eventually produce is
  much milder than one naming an artifact nothing produces: the stage is deferred until
  its bogus dependency lands, so the sequence still covers everything and only the order
  moves. These properties are sharp on permanent retirement, blunt on that.
* A stage the driver never completed leaves no witness either way, so this is sound but
  not exhaustive — the same asymmetry the replay's regression check already carries.
* The corpus cannot settle a halt whose blocking bytes it no longer holds, and one run
  (``exec_5409``) has exactly that shape. Those are printed, never counted.

**Runtime.** One full 72-stage drain costs ~2.6k stage evaluations and ~15s, so the
whole-corpus version is opt-in behind ``MUX_SOLVER_TRAJECTORY_CORPUS=1`` (the same
shape as the ``slow`` marker's opt-in for live MusicGen). The default suite drains the
richest single run, ``exec_11871``, once per module and asserts against that.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterator

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import solver_replay as replay  # noqa: E402

from interview_mux import solver  # noqa: E402
from interview_mux.run_context import RunContext  # noqa: E402

# Opt-in for the whole corpus. 22 substantive runs × ~15s is not a default-suite cost,
# and a slow test on the default path gets deleted or skipped wholesale, which loses the
# property entirely. Precedent: `conftest._slow_enabled` gates the live-MusicGen tests.
EXHAUSTIVE_ENV = "MUX_SOLVER_TRAJECTORY_CORPUS"

# The pinned run: 299 decision points, 64 distinct stages, reached master/master.wav.
REPRESENTATIVE = "exec_11871"

# `regression_proof` takes the instant to prove unrunnability at. Evaluated at the end
# of the run it answers a different question with the same evidence: did this stage's
# completion *stick*.
END_OF_RUN = float("inf")

# A halt this far into the pipeline is a halt worth reading; a two-stage sequence would
# satisfy "no omission" against a corpus run that never got going.
MIN_SEQUENCE_FOR_A_REAL_WALK = 60


# ---------------------------------------------------------------------------
# the witness: which stages did the driver PROVE it needed
# ---------------------------------------------------------------------------

def needed_stages(spec: Any, entries: list[dict[str, Any]]) -> dict[str, str]:
    """``{stage: proof}`` for stages the driver's own history proves were needed.

    Two calls to ``solver_replay.regression_proof``, the function D12's
    ``no_regression_against_driver`` condition already rests on, so the standard for
    "the driver proves something about this stage" is one implementation and not two:

    * at the stage's **last completion** — the clause "and never started it again" is
      live there, so a stage the driver kept re-attempting after it finished is not
      counted. The driver itself did not treat that completion as settled.
    * at the **end of the run** — the invalidation clause is live there, so a
      completion that was later invalidated and never redone is not counted either.

    Their conjunction is exactly the stated witness: recorded ``done``, nothing
    invalidated it in between, never started again. Anything weaker would let a failed
    or abandoned dispatch be scored against the solver as an omission; anything stronger
    would drop work the driver plainly did need.

    Dispatch *counts* are deliberately not part of this. The corpus holds 590
    re-dispatches of an already-complete stage; the solver skipping them is correct, and
    keying on the stage rather than the dispatch is what keeps that correctness from
    reading as a failure.
    """
    dones = replay.done_timeline(entries)
    invalidations = replay.invalidation_timeline(spec.path)
    starts = replay.started_epochs(entries)
    last_done: dict[str, float] = {}
    for at, stage in dones:
        last_done[stage] = at

    out: dict[str, str] = {}
    for point in replay.decision_points(entries):
        stage = point.stage
        if stage in out or stage not in last_done:
            continue
        settled = replay.regression_proof(
            stage,
            last_done[stage],
            dones=dones,
            invalidations=invalidations,
            starts=starts,
        )
        survived = replay.regression_proof(
            stage,
            END_OF_RUN,
            dones=dones,
            invalidations=invalidations,
            starts=starts,
        )
        if settled and survived:
            out[stage] = settled
    return out


# ---------------------------------------------------------------------------
# corpus evidence: can this artifact be produced at all in a counterfactual?
# ---------------------------------------------------------------------------

def _corpus_holds(source: Path, rel: str) -> bool:
    """Does the run's surviving tree hold ``rel`` in any form?

    The effect model replays a stage's success by copying that stage's declared outputs
    out of this tree. When the bytes are gone — invalidated, cleaned, or never committed
    in a run that never shipped — no counterfactual can advance past a consumer of them,
    and the resulting halt is a fact about the corpus. When the bytes *are* here, a halt
    on them is a fact about the solver, and nothing in this module may excuse it.
    """
    if not rel:
        return False
    if "*" in rel:
        try:
            return any(p.is_file() for p in source.glob(rel))
        except OSError:
            return False
    target = source / rel
    if target.is_dir():
        try:
            return any(p.is_file() for p in target.rglob("*"))
        except OSError:
            return False
    return target.is_file()


def evidence_limited_stages(source: Path, verdicts: tuple[Any, ...]) -> frozenset[str]:
    """Stopped stages whose halt the corpus caused, transitively.

    A stage is evidence-limited when its blocking artifact is **absent from the run's
    tree**, or when that artifact's declared producer is itself evidence-limited. The
    transitive clause is what makes the class usable: in ``exec_5409`` a single missing
    ``analysis/connector_fuse_rounds.json`` retires 13 stages, and listing only the
    first would leave 12 unexplained omissions that are not the solver's doing.

    Only ``hard_input_missing`` can be excused. ``hard_input_insufficient`` and
    ``hard_input_uncommitted`` name bytes that *are* present, so a halt on them is the
    solver's reading of real artifacts and stays a finding.
    """
    limited: set[str] = set()
    behind: dict[str, str] = {}
    for verdict in verdicts:
        if verdict.admissible:
            continue
        family, _, rel = str(verdict.reason).partition(":")
        if family != "hard_input_missing" or not rel:
            continue
        if not _corpus_holds(source, rel):
            limited.add(verdict.stage)
            continue
        producer = str((verdict.detail.get("producers") or {}).get(rel) or "")
        if producer:
            behind[verdict.stage] = producer
    changed = True
    while changed:
        changed = False
        for stage, producer in behind.items():
            if stage not in limited and producer in limited:
                limited.add(stage)
                changed = True
    return frozenset(limited)


# ---------------------------------------------------------------------------
# the drain
# ---------------------------------------------------------------------------

@dataclass
class Trajectory:
    """One counterfactual walk: what the solver's own sequence did, end to end."""

    run_id: str
    scope: tuple[str, ...]
    sequence: tuple[str, ...]
    initially_done: frozenset[str]
    needed: dict[str, str]
    stopped: tuple[str, ...]
    blockers: dict[str, str]
    evidence_limited: frozenset[str]
    driver_order: tuple[str, ...]
    seconds: float
    evaluations: int
    source_before: dict[str, tuple[float, int]] = field(default_factory=dict)
    source_after: dict[str, tuple[float, int]] = field(default_factory=dict)

    @property
    def reached(self) -> frozenset[str]:
        return frozenset(self.sequence) | self.initially_done

    @property
    def needed_in_scope(self) -> dict[str, str]:
        return {s: p for s, p in self.needed.items() if s in set(self.scope)}

    @property
    def omitted(self) -> tuple[str, ...]:
        """Proven-needed stages the solver's own sequence never reached.

        Ordered by the driver's own dispatch order so the failure message reads as "it
        stopped here", and filtered by ``evidence_limited`` so a halt the corpus caused
        is reported rather than blamed.
        """
        return tuple(
            s
            for s in self.driver_order
            if s in self.needed_in_scope
            and s not in self.reached
            and s not in self.evidence_limited
        )

    @property
    def excused(self) -> tuple[str, ...]:
        return tuple(
            s
            for s in self.driver_order
            if s in self.needed_in_scope
            and s not in self.reached
            and s in self.evidence_limited
        )

    def why(self, stage: str) -> str:
        return self.blockers.get(stage, "(never evaluated at the halt)")

    def report(self) -> str:
        lines = [
            f"{self.run_id}: yielded {len(self.sequence)}/{len(self.scope)} in "
            f"{self.seconds:.1f}s ({self.evaluations} stage evaluations); "
            f"{len(self.needed_in_scope)} stage(s) proven needed"
        ]
        for stage in self.omitted:
            lines.append(f"  OMITTED  {stage}: {self.why(stage)}")
        for stage in self.excused:
            lines.append(f"  excused  {stage}: {self.why(stage)} (corpus lacks the bytes)")
        return "\n".join(lines)


@contextmanager
def _authoritative_env() -> Iterator[None]:
    """Drain under the promotion switch — ``include_door`` differs on it.

    ``evaluate_stage`` step 8 drops the dispatch-door term once the solver is
    authoritative, so a trajectory measured with the switch off would be measuring a
    rule that will not be in force. Set through ``os.environ`` rather than
    ``monkeypatch`` so a module-scoped fixture can use it.
    """
    previous = {k: os.environ.get(k) for k in ("MUX_SOLVER_AUTHORITATIVE", "MUX_SOLVER_SHADOW")}
    os.environ["MUX_SOLVER_AUTHORITATIVE"] = "1"
    os.environ["MUX_SOLVER_SHADOW"] = "0"
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _fingerprint(paths: list[tuple[float, Path]]) -> dict[str, tuple[float, int]]:
    out: dict[str, tuple[float, int]] = {}
    for _mtime, path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        out[str(path)] = (stat.st_mtime, stat.st_size)
    return out


def drain(spec: Any, workdir: Path, *, scope: tuple[str, ...] | None = None) -> Trajectory:
    """Follow the solver's own sequence from the run's opening state to wherever it ends.

    The state model is the replay's ``Snapshot`` — a throwaway copy, media as same-size
    sparse placeholders, nothing linked back into ``ASSETS/executions`` — advanced to the
    driver's *first* dispatch and then moved forward only by the trajectory itself:

    * a yielded stage's declared outputs are materialised from the run's final bytes,
      which is the counterfactual "it ran and succeeded";
    * its ``.stage_done`` marker is set, so the stage reads complete to everything
      downstream that asks.

    Nothing else advances. In particular the file clock does **not** run forward with
    wall time, because that would hand the solver artifacts whose producer it never
    chose, and a halt could then be masked by bytes the counterfactual never earned.
    """
    entries = replay.read_ledger_entries(spec.path)
    points = replay.decision_points(entries)
    if not points:
        raise ValueError(f"{spec.run_id}: no dispatches recorded")

    dones = replay.done_timeline(entries)
    invalidations = replay.invalidation_timeline(spec.path)
    markers = replay.marker_mtimes(spec.path)
    outputs = replay.stage_output_paths()
    pipeline = set(solver.dispatchable_stages())
    candidates = tuple(scope) if scope else solver.dispatchable_stages()

    dest = workdir / spec.run_id
    snapshot = replay.Snapshot.build(spec.path, dest)
    before = _fingerprint(snapshot.files)
    opening = points[0].epoch
    snapshot.advance_to(opening)

    done = set(replay.done_at(opening, dones, invalidations, markers))
    # Operator answers and retired substep markers are pinned; pipeline stages are not.
    done |= {m for m in markers if m not in pipeline}
    for stage in done:
        snapshot.materialise_outputs(outputs.get(stage, ()))
    snapshot.set_done(done)
    by_seq = sorted(entries, key=lambda r: int(r.get("seq") or 0))
    snapshot.write_ledger([r for r in by_seq if int(r.get("seq") or 0) < points[0].seq])

    ctx = RunContext(spec.run_id, create=False)
    ctx.run_dir = dest

    sequence: list[str] = []
    counted = [0]
    real_evaluate = solver.evaluate_stage

    def _counting(c: Any, sid: str, **kw: Any) -> Any:
        counted[0] += 1
        return real_evaluate(c, sid, **kw)

    started = time.time()
    with _authoritative_env():
        solver.evaluate_stage = _counting  # type: ignore[assignment]
        try:
            for pick in solver.authoritative_sequence(ctx, candidates):
                sequence.append(pick)
                snapshot.materialise_outputs(outputs.get(pick, ()))
                done.add(pick)
                snapshot.set_done(done)
            stopped = tuple(s for s in candidates if s not in set(sequence))
            verdicts: tuple[Any, ...] = ()
            if stopped:
                verdicts = solver.admissible_set(ctx, stages=stopped).verdicts
        finally:
            solver.evaluate_stage = real_evaluate  # type: ignore[assignment]
    seconds = time.time() - started

    return Trajectory(
        run_id=spec.run_id,
        scope=candidates,
        sequence=tuple(sequence),
        initially_done=frozenset(done - set(sequence)),
        needed=needed_stages(spec, entries),
        stopped=stopped,
        blockers={v.stage: str(v.reason) for v in verdicts if not v.admissible},
        evidence_limited=evidence_limited_stages(spec.path, verdicts),
        driver_order=tuple(dict.fromkeys(p.stage for p in points)),
        seconds=seconds,
        evaluations=counted[0],
        source_before=before,
        source_after=_fingerprint(snapshot.files),
    )


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _spec(prefix: str) -> Any:
    hits = [s for s in replay.select_corpus(limit=100) if s.run_id.startswith(prefix)]
    if not hits:
        pytest.skip(f"replay corpus has no run matching {prefix!r}")
    return hits[0]


@pytest.fixture(scope="module")
def representative(tmp_path_factory: pytest.TempPathFactory) -> Trajectory:
    """One full 72-stage drain of the richest run, shared by every assertion on it."""
    spec = _spec(REPRESENTATIVE)
    return drain(spec, tmp_path_factory.mktemp("trajectory"))


# The non-vacuity A/B pair runs against a narrow scope so the proof costs a second
# rather than a minute. The prefix ends at `segment_classification`, which is deep
# enough that a retirement early in it cascades visibly.
SCOPED_END = "segment_classification"


def _scoped() -> tuple[str, ...]:
    order = solver.dispatchable_stages()
    return order[: order.index(SCOPED_END) + 1]


@pytest.fixture(scope="module")
def scoped_control(tmp_path_factory: pytest.TempPathFactory) -> Trajectory:
    """The same drain over an analysis-prefix scope, with nothing broken.

    The control half of the non-vacuity proof: whatever the injected runs show has to be
    read against a scope where the property demonstrably passes, or "it failed" says
    nothing about the injection.
    """
    return drain(_spec(REPRESENTATIVE), tmp_path_factory.mktemp("trajectory_scoped"), scope=_scoped())


@contextmanager
def over_declared_hard_input(stage: str, rel: str, producer: str) -> Iterator[None]:
    """Give ``stage`` one ``inputs.hard`` entry it should never have declared.

    The exact failure mode promotion introduces, injected at the contract rather than
    faked at the verdict: ``evaluate_stage`` re-imports ``load_contract`` per call, so
    patching the module attribute reaches the real rule, hard-input resolution, producer
    attribution and halt payload alike. ``dataclasses.replace`` keeps the injection out
    of any contract cache.
    """
    from interview_mux import stage_contract

    real = stage_contract.load_contract

    def _patched(stage_id: str):  # type: ignore[no-untyped-def]
        contract = real(stage_id)
        if contract is None or stage_id != stage:
            return contract
        extra = stage_contract.InputDep(path=rel, hard=True, producer=producer)
        return replace(contract, inputs=list(contract.inputs) + [extra])

    stage_contract.load_contract = _patched  # type: ignore[assignment]
    try:
        yield
    finally:
        stage_contract.load_contract = real  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 1. ordered superset — the solver may be more efficient, never less complete
# ---------------------------------------------------------------------------

def test_the_solver_reaches_every_stage_the_driver_proved_it_needed(
    representative: Trajectory,
) -> None:
    """The property replay cannot state: the solver's own path covers the driver's work.

    Skipping a re-dispatch of a finished stage is not an omission and cannot fail here —
    the witness is per stage, and ``needed_stages`` only counts a completion that stuck.
    """
    assert representative.omitted == (), representative.report()
    assert representative.needed_in_scope, "witness found no needed stage — it broke"


def producer_precedence(sequence: tuple[str, ...]) -> tuple[int, list[str]]:
    """``(pairs checked, inversions)`` against contract-declared producer order.

    Contract-declared precedence is the part of the driver's order that is *forced*.
    Everything else the solver may legitimately re-order, and does: it runs
    ``listen_delight_audit`` before ``podcast_publish`` where the driver ran it after,
    which is the ship gate landing in the right place rather than a defect — so
    demanding the driver's sequence be a subsequence of the solver's would fail on the
    solver being right. This is the strongest order property the corpus can support, and
    it is weaker than "same order"; see the module docstring.
    """
    from interview_mux.stage_contract import load_contract

    index = {stage: i for i, stage in enumerate(sequence)}
    inversions: list[str] = []
    pairs = 0
    for consumer in sequence:
        contract = load_contract(consumer)
        if contract is None:
            continue
        for dep in contract.inputs:
            producer = str(getattr(dep, "producer", "") or "")
            if not dep.hard or not producer or producer == consumer:
                continue
            if producer not in index:
                continue
            pairs += 1
            if index[producer] > index[consumer]:
                inversions.append(f"{consumer} ran before its declared producer {producer}")
    return pairs, inversions


def test_the_solver_never_runs_a_consumer_before_a_producer_it_declares(
    representative: Trajectory,
) -> None:
    pairs, inversions = producer_precedence(representative.sequence)
    assert pairs >= 40, f"only {pairs} declared producer pairs — the scrape broke"
    assert inversions == [], "\n".join(inversions)


def test_an_inverted_sequence_is_caught_by_the_order_check() -> None:
    """Non-vacuity for the order half: the effect model makes an inversion hard to
    provoke from the corpus, so the checker is shown to reject one directly."""
    pairs, inversions = producer_precedence(("edl", "full_master_ranking"))
    assert pairs >= 1
    assert inversions == ["edl ran before its declared producer full_master_ranking"]


# ---------------------------------------------------------------------------
# 2. no premature termination — the early-retirement test
# ---------------------------------------------------------------------------

def test_the_sequence_does_not_end_while_the_driver_was_still_productive(
    representative: Trajectory,
) -> None:
    """`authoritative_sequence` ends the walk on an empty admissible set. If it ends
    while proven-needed work is outstanding, one over-declared ``inputs.hard`` has
    retired a stage the run needed — the failure promotion introduces and the pick-by-
    pick replay cannot see.
    """
    outstanding = [s for s in representative.omitted]
    assert outstanding == [], (
        "sequence ended with proven-needed work outstanding:\n"
        + "\n".join(f"  {s}: {representative.why(s)}" for s in outstanding)
    )


def test_the_drain_is_a_whole_walk_and_not_a_two_stage_stub(
    representative: Trajectory,
) -> None:
    """Both properties above are satisfiable by a sequence that goes nowhere, so the
    depth of the walk is asserted rather than assumed."""
    assert len(representative.sequence) >= MIN_SEQUENCE_FOR_A_REAL_WALK
    assert len(set(representative.sequence)) == len(representative.sequence)
    assert representative.evaluations > 1000
    # The ship path specifically: a trajectory that stops before the master proves
    # nothing about a pipeline whose north star is master/master.wav.
    assert {"master_finalize", "master_transcript_build"} <= representative.reached


def test_replaying_a_trajectory_never_writes_into_the_executions_tree(
    representative: Trajectory,
) -> None:
    """The corpus is a read-only forensic artifact and this drain mutates state per pick."""
    assert representative.source_before
    assert representative.source_after == representative.source_before


# ---------------------------------------------------------------------------
# 3. non-vacuity — the test must be able to fail
# ---------------------------------------------------------------------------

def test_the_scoped_control_passes_so_the_injections_below_mean_something(
    scoped_control: Trajectory,
) -> None:
    assert scoped_control.omitted == (), scoped_control.report()
    assert len(scoped_control.sequence) == len(scoped_control.scope)
    assert scoped_control.needed_in_scope


#: A real artifact ``exec_11871`` holds that **no pipeline stage produces** — the
#: homunculus writes it outside the stage graph. Over-declaring it is therefore a
#: permanent retirement, which is the failure promotion actually introduces. An
#: over-declaration naming an artifact the run *does* eventually produce turns out to be
#: much milder: the stage is merely deferred until its bogus dependency lands, so the
#: sequence still covers everything and only the order moves. Worth knowing, and the
#: reason the injection below names an unproducible path.
UNPRODUCIBLE_ARTIFACT = "mastering/homunculus/speaker_dossier.json"


def test_an_over_declared_hard_input_is_caught_as_a_premature_halt(
    tmp_path: Path, scoped_control: Trajectory
) -> None:
    """The failure mode the whole module exists for, injected and then caught.

    ``speaker_roles`` is given one hard input it should never declare. Under authority
    that retires it for the rest of the run, and everything consuming its outputs
    retires with it. The unpromoted walk would have dispatched it and let the pre-stage
    checks decide — which is exactly why the pick-by-pick replay cannot see this.
    """
    with over_declared_hard_input("speaker_roles", UNPRODUCIBLE_ARTIFACT, "speaker_roles"):
        broken = drain(_spec(REPRESENTATIVE), tmp_path, scope=_scoped())

    assert "speaker_roles" in broken.omitted, broken.report()
    assert broken.blockers["speaker_roles"] == f"hard_input_missing:{UNPRODUCIBLE_ARTIFACT}"
    # Not excused: the corpus holds those bytes, so the halt is the solver's.
    assert "speaker_roles" not in broken.evidence_limited
    assert _corpus_holds(_spec(REPRESENTATIVE).path, UNPRODUCIBLE_ARTIFACT)
    # And it cascades — one bad declaration is never one lost stage.
    assert len(broken.omitted) > 1, broken.report()
    assert len(broken.sequence) < len(scoped_control.sequence)


def test_a_stage_the_solver_never_admits_is_caught_as_an_omission(
    tmp_path: Path, scoped_control: Trajectory
) -> None:
    """The other half: not a halt, a hole. The sequence keeps going, one needed stage
    silently never appears, and the coverage property has to notice on its own."""
    dropped = "content_context"
    assert dropped in scoped_control.reached
    real = solver.evaluate_stage

    def _blank(ctx: Any, sid: str, **kw: Any) -> Any:
        verdict = real(ctx, sid, **kw)
        if sid != dropped:
            return verdict
        return solver.StageVerdict(
            stage=sid,
            admissible=False,
            reasons=("hard_input_insufficient:analysis/pretend.json",),
            seed_index=verdict.seed_index,
        )

    solver.evaluate_stage = _blank  # type: ignore[assignment]
    try:
        holed = drain(_spec(REPRESENTATIVE), tmp_path, scope=_scoped())
    finally:
        solver.evaluate_stage = real  # type: ignore[assignment]

    assert dropped in holed.omitted, holed.report()
    assert dropped in holed.needed_in_scope


def test_the_evidence_limited_excuse_cannot_cover_an_artifact_the_corpus_holds(
    tmp_path: Path,
) -> None:
    """The escape hatch is the one place this module could go quietly vacuous, so both
    directions are pinned: absent bytes excuse a halt, present bytes never do."""
    source = tmp_path / "run"
    (source / "master").mkdir(parents=True)
    (source / "master" / "selection.json").write_text("{}", encoding="utf-8")

    present = solver.StageVerdict(
        stage="edl",
        admissible=False,
        reasons=("hard_input_missing:master/selection.json",),
        detail={"producers": {"master/selection.json": "full_master_ranking"}},
    )
    absent = solver.StageVerdict(
        stage="mix",
        admissible=False,
        reasons=("hard_input_missing:master/assembly.wav",),
        detail={"producers": {"master/assembly.wav": "edl"}},
    )
    limited = evidence_limited_stages(source, (present, absent))
    assert "mix" in limited
    assert "edl" not in limited


def test_a_halt_behind_a_missing_artifact_is_excused_transitively(tmp_path: Path) -> None:
    """One absent artifact retired 13 stages in ``exec_5409``; excusing only the first
    would leave 12 omissions that are the corpus's fault, not the solver's."""
    source = tmp_path / "run"
    source.mkdir()
    root = solver.StageVerdict(
        stage="full_master_ranking",
        admissible=False,
        reasons=("hard_input_missing:analysis/connector_fuse_rounds.json",),
        detail={"producers": {"analysis/connector_fuse_rounds.json": "connector_fuse_pass"}},
    )
    behind = solver.StageVerdict(
        stage="edl",
        admissible=False,
        reasons=("hard_input_missing:master/selection.json",),
        detail={"producers": {"master/selection.json": "full_master_ranking"}},
    )
    assert evidence_limited_stages(source, (root, behind)) == {"full_master_ranking", "edl"}


def test_an_insufficient_artifact_is_never_excused_as_missing_evidence(
    tmp_path: Path,
) -> None:
    """`hard_input_insufficient` names bytes that are present. Excusing it would let a
    real sufficiency defect hide behind the corpus."""
    source = tmp_path / "run"
    source.mkdir()
    verdict = solver.StageVerdict(
        stage="edl",
        admissible=False,
        reasons=("hard_input_insufficient:master/selection.json",),
    )
    assert evidence_limited_stages(source, (verdict,)) == frozenset()


# ---------------------------------------------------------------------------
# 4. the witness itself — legitimate skip vs genuine omission
# ---------------------------------------------------------------------------

def _run(tmp_path: Path, *rows: dict[str, Any]) -> Any:
    """A minimal on-disk run whose ledger is exactly ``rows``."""
    import json

    root = tmp_path / "executions"
    run = root / "exec_00042_20260101T000000Z"
    (run / "mastering" / "homunculus").mkdir(parents=True)
    (run / "mastering" / "homunculus" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [dict(row, seq=i + 1) for i, row in enumerate(rows)],
            }
        ),
        encoding="utf-8",
    )
    return replay.select_corpus(limit=5, root=root)[0]


def _stage(identity: str, status: str, at: str) -> dict[str, Any]:
    return {"kind": "stage", "identity": identity, "status": status, "at": at}


def test_a_completion_that_stuck_is_proven_needed(tmp_path: Path) -> None:
    spec = _run(
        tmp_path,
        _stage("edl", "started", "2026-01-01T00:00:01Z"),
        _stage("edl", "done", "2026-01-01T00:00:02Z"),
    )
    needed = needed_stages(spec, replay.read_ledger_entries(spec.path))
    assert "edl" in needed
    assert "never started it again" in needed["edl"]


def test_an_already_complete_redispatch_does_not_multiply_the_requirement(
    tmp_path: Path,
) -> None:
    """590 such dispatches are in the corpus and the solver skips them correctly. The
    witness is per stage, so 'ran it once' is all this can ever ask for."""
    spec = _run(
        tmp_path,
        _stage("edl", "started", "2026-01-01T00:00:01Z"),
        _stage("edl", "done", "2026-01-01T00:00:02Z"),
        _stage("edl", "started", "2026-01-01T00:00:03Z"),
        _stage("edl", "done", "2026-01-01T00:00:04Z"),
    )
    needed = needed_stages(spec, replay.read_ledger_entries(spec.path))
    assert list(needed) == ["edl"]


def test_a_dispatch_that_never_completed_is_not_held_against_the_solver(
    tmp_path: Path,
) -> None:
    spec = _run(
        tmp_path,
        _stage("edl", "started", "2026-01-01T00:00:01Z"),
        _stage("edl", "failed", "2026-01-01T00:00:02Z"),
    )
    assert needed_stages(spec, replay.read_ledger_entries(spec.path)) == {}


def test_a_stage_the_driver_kept_re_attempting_after_it_finished_proves_nothing(
    tmp_path: Path,
) -> None:
    """The driver itself did not treat that completion as settled, so neither does this.
    Same clause as D12's regression proof, and the same reason for it."""
    spec = _run(
        tmp_path,
        _stage("edl", "started", "2026-01-01T00:00:01Z"),
        _stage("edl", "done", "2026-01-01T00:00:02Z"),
        _stage("edl", "started", "2026-01-01T00:00:03Z"),
    )
    assert needed_stages(spec, replay.read_ledger_entries(spec.path)) == {}


def test_an_invalidated_completion_is_not_proven_needed(tmp_path: Path) -> None:
    import json

    spec = _run(
        tmp_path,
        _stage("edl", "started", "2026-01-01T00:00:01Z"),
        _stage("edl", "done", "2026-01-01T00:00:02Z"),
    )
    log = spec.path / replay.INVALIDATION_REL
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps({"ts": "2026-01-01T00:00:03Z", "invalidated": ["edl"]}) + "\n",
        encoding="utf-8",
    )
    assert needed_stages(spec, replay.read_ledger_entries(spec.path)) == {}


def test_the_witness_is_the_replays_own_function_and_not_a_second_copy() -> None:
    """Two implementations of "the driver proves it" would drift, and the drift would
    show up as either a fake omission or a laundered one."""
    source = Path(__file__).read_text(encoding="utf-8")
    assert "replay.regression_proof(" in source
    assert ("def " + "regression_proof") not in source


# ---------------------------------------------------------------------------
# 5. the whole corpus — opt-in, because 22 drains is a minutes-long test
# ---------------------------------------------------------------------------

def _exhaustive_enabled() -> bool:
    return str(os.environ.get(EXHAUSTIVE_ENV) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@pytest.mark.skipif(
    not _exhaustive_enabled(),
    reason=f"whole-corpus trajectory drain: set {EXHAUSTIVE_ENV}=1 (~4 min)",
)
def test_every_run_in_the_corpus_reaches_the_end_of_its_own_needed_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exhaustive version of both properties, one drain per execution folder.

    Prints a per-run line either way: the numbers are the deliverable, and a green
    assertion that reports nothing is how a trajectory test goes quietly vacuous.
    """
    specs = [s for s in replay.select_corpus(limit=100) if s.substantive]
    if not specs:
        pytest.skip("replay corpus holds no substantive run")
    failures: list[str] = []
    for spec in specs:
        try:
            trajectory = drain(spec, tmp_path)
        except ValueError:
            continue
        finally:
            # 22 snapshot trees at once is gigabytes of copied JSON.
            shutil.rmtree(tmp_path / spec.run_id, ignore_errors=True)
        with capsys.disabled():
            print(trajectory.report())
        if trajectory.omitted:
            failures.append(trajectory.report())
    assert failures == [], "\n\n".join(failures)
