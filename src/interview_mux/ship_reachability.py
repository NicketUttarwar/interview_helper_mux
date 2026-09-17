"""Is ``master/master.wav`` still reachable? (plan §5.5 — real critical-path analysis.)

D1 makes progress toward ``master.wav`` the objective: a refused or blocked stage
advances with a defect, and only a **proven** unreachable ship path halts a run.

The two failure directions are not symmetric, and this module is built around that:

* A false UNREACHABLE halts a run that would have shipped. exec_11871 only reached
  a master because it ground on through 54 human patches — a trigger-happy halt
  would have thrown that tape away. This is the error we refuse to make.
* A false REACHABLE just keeps the walk going, which is the status quo and is now
  bounded by the caps, the no-delta guard and the attempt memo (§5.2–§5.3).

So severance must be *proven*: a required artifact with no surviving producer, on a
requirement the master strictly needs, with nothing in flight that could revive it.
Every unknown — hollow contract, unreadable artifact, unresolved producer — resolves
to "not severed". The critical path is read from ``artifact_dependency_graph`` and
the stage contracts on every call, so the analysis strengthens by itself as another
worker fills contracts in; nothing here is a hand-maintained stage list.

**Absence is not severance.** Because this module reads declared requirements and
contract population is happening live, a stage gaining a declared input instantly
adds a requirement whose artifact is not written yet. A missing artifact whose
producer is still runnable is work not yet done, so ``producer_runnable`` must be
false for *every* producer before severance is even considered — and it is evaluated
against live budget state, so a stale defect row cannot halt a run by itself.
Declaring more inputs can therefore never flip a reachable run to unreachable
(``tests/test_p15_reachability_real.py`` pins that direction).

**Unknown and unreadable are not the same thing.** Resolving every unknown toward
reachable is right for a contract that genuinely declares nothing, and wrong for a
contract we simply failed to *read*: a missing symbol or unparseable YAML used to
empty the critical path and read as "nothing to prove", which is a fail-open that
silently switches this protection off (``docs/cross-cutting/ship-safety-findings.md``,
finding 6). The two are now told apart. A failed read still never severs and still
never halts — a false UNREACHABLE remains the expensive mistake — but it is counted,
logged and recorded in ``operator/ship_reachability.json`` instead of passing
quietly. Every other swallow in this module carries report-only telemetry for the
same reason: each one resolves toward *reachable*, so we need to know whether they
fire in practice before anyone changes what they return.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from interview_mux.run_context import RunContext

logger = logging.getLogger(__name__)

MASTER_REL = "master/master.wav"

_ENV_HALT = "MUX_SHIP_REACHABILITY_HALT"

# Blockers that prove a producer will not run again in this run. A spent cap is the
# only refusal that qualifies: ``no_delta`` fires only when the outputs are already
# on disk, and ``attempt_memo`` clears on the next real state delta.
TERMINAL_BLOCKERS: frozenset[str] = frozenset(
    {
        "max_invokes_per_identity",
        "max_mix_cycles",
        "max_complete_masters",
        "producer_dead",
    }
)

# Gates an operator can still act on. While one is open the walk is waiting for a
# human, not out of paths — a producer behind one of these is not dead.
_REVIVING_GATES: tuple[str, ...] = ("transcript_integrity", "framing_consent", "vo_pickup")

_MAX_DEPTH = 24


# ---------------------------------------------------------------------------
# observability — every swallow in this module resolves toward *reachable*
# ---------------------------------------------------------------------------
# Report-only, process-level, and deliberately not part of any verdict. Nothing
# below may raise: instrumentation that can break the walk is worse than the
# blindness it measures.

_SWALLOW_COUNTS: dict[str, int] = {}
_SWALLOW_LAST_ERROR: dict[str, str] = {}
_UNREADABLE_CONTRACTS: dict[str, str] = {}


def _detail(exc: BaseException | None) -> str:
    if exc is None:
        return ""
    try:
        return f"{type(exc).__name__}: {exc}"[:200]
    except Exception:
        return "unprintable exception"


def _note_swallow(site: str, exc: BaseException | None = None) -> None:
    """Count one swallowed error. Does not change what the caller returns."""
    try:
        _SWALLOW_COUNTS[site] = _SWALLOW_COUNTS.get(site, 0) + 1
        detail = _detail(exc)
        if detail:
            _SWALLOW_LAST_ERROR[site] = detail
        logger.debug("ship_reachability swallowed at %s: %s", site, detail or "-")
    except Exception:
        pass


def _note_unreadable(stage: str, exc: BaseException) -> None:
    """A contract we could not READ — the finding-6 fail-open. Logged loudly.

    Warned once per distinct (stage, error) so a walk that re-reads the same broken
    contract on every tick does not bury the log it is trying to surface.
    """
    detail = _detail(exc)
    _note_swallow("contract_read", exc)
    try:
        already = _UNREADABLE_CONTRACTS.get(stage) == detail
        _UNREADABLE_CONTRACTS[stage] = detail
        if not already:
            logger.warning(
                "ship_reachability could not READ the contract for %s (%s) — its "
                "required artifacts are missing from the critical path, so "
                "wrong-master protection is degraded for that stage. This is a "
                "failed read, not a stage that declares nothing. The verdict is "
                "unchanged and no run was halted.",
                stage,
                detail,
            )
    except Exception:
        pass


def swallow_telemetry() -> dict[str, Any]:
    """Which fail-open paths fired in this process, and the last error from each."""
    return {
        "counts": dict(_SWALLOW_COUNTS),
        "last_error": dict(_SWALLOW_LAST_ERROR),
        "unreadable_contracts": dict(_UNREADABLE_CONTRACTS),
    }


def reset_swallow_telemetry() -> None:
    """Clear the process-level counters (test hook)."""
    _SWALLOW_COUNTS.clear()
    _SWALLOW_LAST_ERROR.clear()
    _UNREADABLE_CONTRACTS.clear()


def analysis_health() -> dict[str, Any]:
    """Say plainly when the analysis could not be trusted.

    Same shape as the finding-2 remedy in ``post_master_quality`` — ``unresolved``,
    ``error``, ``operator_reason`` — but *advisory*: this is carried alongside the
    verdict, never folded into it. An unreadable contract must not halt a walk.
    """
    unreadable = dict(_UNREADABLE_CONTRACTS)
    row: dict[str, Any] = {
        "unresolved": bool(unreadable),
        "unreadable_contracts": unreadable,
        "swallowed": dict(_SWALLOW_COUNTS),
        "swallowed_last_error": dict(_SWALLOW_LAST_ERROR),
    }
    if unreadable:
        row["error"] = "; ".join(
            f"{stage}: {err}" for stage, err in sorted(unreadable.items())
        )[:400]
        row["operator_reason"] = (
            f"Reachability could not read {len(unreadable)} stage contract(s), so "
            "their required artifacts are absent from the critical path and the "
            "wrong-master protection is degraded. No verdict was changed and no run "
            "was halted. Fix the contract read — a missing symbol in the contract "
            "stack, or unparseable YAML under docs/cross-cutting/stage-contracts/ — "
            "and re-run."
        )
    return row


@dataclass(frozen=True)
class Reachability:
    """``reachable`` is the answer; ``certain`` says whether it was proven.

    ``reachable=False`` with ``certain=False`` is not representable through
    ``ship_reachable`` on purpose — an indeterminate answer is reported reachable.
    """

    reachable: bool
    certain: bool
    reason: str
    blockers: tuple[str, ...] = field(default_factory=tuple)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def unknown(self) -> bool:
        return not self.certain

    def as_row(self) -> dict[str, Any]:
        return {
            "reachable": self.reachable,
            "certain": self.certain,
            "reason": self.reason,
            "blockers": list(self.blockers),
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class Requirement:
    """One artifact the master strictly requires, and who can still write it."""

    path: str
    producers: tuple[str, ...]
    required_by: str


@dataclass(frozen=True)
class UnreadableContract:
    """A contract the walk could not READ, and why.

    Distinct from a hollow contract on purpose: hollow means "declares nothing",
    which is a real answer, while this means "we do not know what it declares".
    """

    stage: str
    error: str

    def as_row(self) -> dict[str, str]:
        return {"stage": self.stage, "error": self.error}


@dataclass(frozen=True)
class CriticalPath:
    requirements: tuple[Requirement, ...]
    root_producers: tuple[str, ...]
    unknown_stages: tuple[str, ...]
    # Subset of ``unknown_stages`` whose hollowness is a failed *read* rather than
    # an empty declaration. ``unknown_stages`` keeps its existing meaning so
    # existing callers do not shift underneath; this is additive.
    unreadable_stages: tuple[UnreadableContract, ...] = ()

    def by_path(self) -> dict[str, Requirement]:
        return {r.path: r for r in self.requirements}

    @property
    def degraded(self) -> bool:
        """True when a contract could not be read, so requirements are missing."""
        return bool(self.unreadable_stages)


class ShipUnreachable(RuntimeError):
    """Raised at the walk boundary when the ship path is provably severed."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        blockers = ", ".join(str(b) for b in payload.get("blockers") or []) or "unknown"
        super().__init__(f"ship_unreachable: {blockers}")


def halt_enabled() -> bool:
    """Default OFF: the analysis always runs, the halt is opt-in.

    0.2.0 is the live default brain, and a false halt is the expensive mistake, so
    the shipped default records the verdict and keeps walking. Set
    ``MUX_SHIP_REACHABILITY_HALT=1`` to let a proven severance stop the walk.
    """
    raw = str(os.environ.get(_ENV_HALT) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def master_committed(ctx: RunContext) -> bool:
    """Committed master only — a pending finalize write must not look shipped."""
    try:
        from interview_mux.delivery_invariants import committed_master_wav

        return bool(committed_master_wav(ctx))
    except Exception as exc:
        _note_swallow("master_committed.committed_master_wav", exc)
        try:
            return ctx.final_path("master", "master.wav").is_file()
        except Exception as exc2:
            _note_swallow("master_committed.final_path", exc2)
            return False


# ---------------------------------------------------------------------------
# critical path — derived, never hand-listed
# ---------------------------------------------------------------------------

def producers_for_path(rel: str) -> tuple[str, ...]:
    """Every stage that may write ``rel``, from the graph then the ownership catalog."""
    path = str(rel or "").strip()
    if not path:
        return ()
    out: list[str] = []
    try:
        from interview_mux.artifact_dependency_graph import build_graph

        for edge in build_graph():
            if edge.kind == "produces" and edge.artifact_path == path:
                if edge.from_id not in out:
                    out.append(edge.from_id)
    except Exception as exc:
        _note_swallow("producers_for_path.graph", exc)
    try:
        from interview_mux.artifact_ownership import row_for_path

        row = row_for_path(path)
        if row is not None:
            for producer in row.producers:
                if producer and producer not in out:
                    out.append(producer)
    except Exception as exc:
        _note_swallow("producers_for_path.ownership", exc)
    try:
        from interview_mux.stage_contract import contract_for_artifact_path

        contract = contract_for_artifact_path(path)
        if contract is not None and contract.stage_id not in out:
            out.append(contract.stage_id)
    except Exception as exc:
        _note_swallow("producers_for_path.contract", exc)
    return tuple(out)


def _graph_requirements(stage: str) -> list[tuple[str, str]]:
    """``(artifact_path, producer)`` pairs this stage requires, per the graph."""
    rows: list[tuple[str, str]] = []
    try:
        from interview_mux.artifact_dependency_graph import build_graph

        for edge in build_graph():
            if edge.kind not in {"requires", "consumes"}:
                continue
            if edge.from_id != stage or not edge.artifact_path:
                continue
            rows.append((str(edge.artifact_path), str(edge.to_id or "")))
    except Exception as exc:
        _note_swallow("graph_requirements", exc)
        return []
    return rows


def _contract_requirements(
    stage: str, ctx: RunContext | None
) -> tuple[list[tuple[str, str]], bool, str]:
    """Correctness-required contract inputs for ``stage``, hollowness, read error.

    The second value is the honest part: a stage with no contract, or a contract
    that declares no correctness-required input, is *unknown*. Unknown never severs.

    The third value separates the two things that used to share ``hollow=True``. A
    non-empty string means the contract could not be *read* at all, so "declares
    nothing" was never established — see the module docstring and finding 6. It is
    reported, not enforced: ``hollow`` is still True in that case, so the verdict
    and ``unknown_stages`` are exactly what they were before.

    Hardness is the wrong filter on its own here. ``mix`` reads the EDL and the
    selection softly — it does not refuse without them — yet a master built from
    neither is not the master the run was asked for: ``air_order.assert_consumer``
    returns early when either is absent, so the T0-3 ordering invariant simply
    goes unenforced. Those rows carry ``correctness`` (``stage_contract``), which
    only this walk reads: dispatch still filters on ``dep.hard`` alone, so marking
    a row adds a reachability requirement without adding a PRESTAGE refusal.
    """
    try:
        from interview_mux.stage_contract import (
            correctness_required,
            evaluate_when,
            is_path_spec,
            load_contract,
        )

        contract = load_contract(stage)
    except Exception as exc:
        _note_unreadable(stage, exc)
        return [], True, _detail(exc)
    if contract is None:
        return [], True, ""  # genuinely absent — hollow, and quiet
    rows: list[tuple[str, str]] = []
    for dep in contract.inputs:
        if not correctness_required(dep) or not dep.path or is_path_spec(dep.path):
            continue
        if dep.when:
            if ctx is None:
                continue  # cannot evaluate the condition — treat as not required
            try:
                if not evaluate_when(dep.when, ctx):
                    continue
            except Exception as exc:
                _note_swallow("contract_requirements.when", exc)
                continue
        rows.append((str(dep.path), str(dep.producer or "")))
    return rows, not rows, ""  # declares nothing ⇒ hollow, and quiet


def critical_path(ctx: RunContext | None = None) -> CriticalPath:
    """Artifacts the master strictly requires, walked back from whoever writes it.

    Root is resolved from the graph rather than pinned to ``master_finalize``, and
    the walk only follows *hard* requirements. Stages whose contracts are still
    hollow contribute nothing and are reported in ``unknown_stages``: an empty
    requirement set means "we cannot prove anything", which is the safe answer.

    That safe answer is only honest when the emptiness was *read*. A stage whose
    contract could not be read at all is reported separately in
    ``unreadable_stages`` (and stays in ``unknown_stages``, unchanged), because the
    root's requirements come solely from its contract — one failed read there empties
    the whole path while still looking like a clean "nothing to prove".
    """
    roots = producers_for_path(MASTER_REL)
    seen_stages: set[str] = set()
    unknown: list[str] = []
    unreadable: dict[str, str] = {}
    requirements: dict[str, Requirement] = {}
    frontier = [(stage, 0) for stage in roots]
    while frontier:
        stage, depth = frontier.pop()
        if not stage or stage in seen_stages or depth > _MAX_DEPTH:
            continue
        seen_stages.add(stage)
        contract_rows, hollow, read_error = _contract_requirements(stage, ctx)
        if hollow:
            unknown.append(stage)
        if read_error:
            unreadable[stage] = read_error
        rows = list(contract_rows) + _graph_requirements(stage)
        for path, declared_producer in rows:
            producers = tuple(
                p for p in ((declared_producer,) + producers_for_path(path)) if p
            )
            deduped = tuple(dict.fromkeys(producers))
            prior = requirements.get(path)
            if prior is None:
                requirements[path] = Requirement(path, deduped, stage)
            elif set(deduped) - set(prior.producers):
                merged = tuple(dict.fromkeys(prior.producers + deduped))
                requirements[path] = Requirement(path, merged, prior.required_by)
            for producer in deduped:
                frontier.append((producer, depth + 1))
    return CriticalPath(
        requirements=tuple(requirements[p] for p in sorted(requirements)),
        root_producers=tuple(roots),
        unknown_stages=tuple(sorted(set(unknown))),
        unreadable_stages=tuple(
            UnreadableContract(stage, unreadable[stage]) for stage in sorted(unreadable)
        ),
    )


# ---------------------------------------------------------------------------
# satisfaction — existence is not satisfaction
# ---------------------------------------------------------------------------

def requirement_satisfied(ctx: RunContext, rel: str, consumer: str) -> bool:
    """True when ``rel`` really satisfies ``consumer`` — hollow does not count.

    Reuses the acceptance semantics rather than a file check, so a zero-length WAV
    or a schema-partial JSON reads as unsatisfied. Any error resolves to True: we
    only ever want to *fail* to prove severance.
    """
    try:
        if not ctx.artifact_exists(rel):
            return False
    except Exception as exc:
        _note_swallow("requirement_satisfied.exists", exc)
        return True
    try:
        from interview_mux.artifact_completeness import artifact_status_for_stage

        return str(artifact_status_for_stage(rel, ctx, consumer)) == "complete"
    except Exception as exc:
        _note_swallow("requirement_satisfied.completeness", exc)
        return True


def _revivable_by_operator(ctx: RunContext) -> str:
    try:
        from interview_mux.homunculus.gates import category_status

        cats = category_status(ctx)
    except Exception as exc:
        _note_swallow("revivable_by_operator", exc)
        return ""
    for name in _REVIVING_GATES:
        row = cats.get(name)
        if isinstance(row, dict) and row.get("open"):
            return name
    return ""


def _repair_pinned(ctx: RunContext, stage: str) -> bool:
    """A heal / repair plan that names this stage may still revive its artifact."""
    try:
        from interview_mux.execution_contract import read_active_vo_repair_plan
        from interview_mux.remediation_framework import read_active_remediation_plan

        plans = [read_active_remediation_plan(ctx), read_active_vo_repair_plan(ctx)]
    except Exception as exc:
        _note_swallow("repair_pinned", exc)
        return False
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        named = set(plan.get("allowed_rerun_stages") or [])
        named.update(plan.get("invalidate_set") or [])
        for key in ("resume_stage", "consumer_stage", "producer_stage"):
            value = plan.get(key)
            if value:
                named.add(str(value))
        if stage in named:
            return True
    return False


def producer_runnable(ctx: RunContext, stage: str) -> bool:
    """Could ``stage`` still write its outputs in this run?

    This is the guard that keeps absence from becoming severance. Contract
    population is live, so a stage gaining a declared hard input immediately adds a
    requirement whose artifact is simply *not written yet* — that is work not yet
    done, not a dead path. Only a producer the dispatch door will refuse for a spent
    cap counts as not runnable, and the check is made against live budget state so a
    stale defect row cannot halt a run on its own.
    """
    sid = str(stage or "").strip()
    if not sid:
        return True
    try:
        from interview_mux.homunculus.budget import attempt_cap, count_attempts, exemption_for

        cap, reason = attempt_cap(sid)
        used = count_attempts(ctx, sid)
        if used < cap:
            return True
        if str(reason) not in TERMINAL_BLOCKERS:
            return True
        # Mirrors ``dispatch_cap_refusal`` minus its exemption log write: asking
        # whether a producer could run must not look like an exemption being taken.
        exemption = exemption_for(ctx, sid, "stage")
        return exemption is not None and used < cap + exemption.grace
    except Exception as exc:
        _note_swallow("producer_runnable", exc)
        return True  # cannot tell ⇒ assume the producer can still run


def _terminal_defect_stages(ctx: RunContext) -> dict[str, dict[str, Any]]:
    try:
        from interview_mux.defect_ledger import open_defects

        rows = open_defects(ctx)
    except Exception as exc:
        _note_swallow("terminal_defect_stages", exc)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("blocker") or "") not in TERMINAL_BLOCKERS:
            continue
        stage = str(row.get("stage") or "")
        if stage:
            out.setdefault(stage, row)
    return out


def severed_requirements(ctx: RunContext) -> list[dict[str, Any]]:
    """Requirements with no surviving producer. Empty unless severance is proven."""
    dead = _terminal_defect_stages(ctx)
    if not dead:
        return []
    gate = _revivable_by_operator(ctx)
    if gate:
        return []
    path = critical_path(ctx)
    severed: list[dict[str, Any]] = []
    for req in path.requirements:
        if not req.producers:
            continue  # unknown producer — cannot prove severance
        survivors = [p for p in req.producers if p not in dead]
        if survivors:
            continue
        # Absence is never authoritative: the artifact being missing only matters if
        # nobody can still write it. Live budget state decides, not the ledger row.
        if any(producer_runnable(ctx, p) for p in req.producers):
            continue
        if any(_repair_pinned(ctx, p) for p in req.producers):
            continue
        if requirement_satisfied(ctx, req.path, req.required_by):
            continue
        blocker = dead.get(req.producers[0]) or next(iter(dead.values()))
        severed.append(
            {
                "artifact": req.path,
                "required_by": req.required_by,
                "producers": list(req.producers),
                "blocker": str(blocker.get("blocker") or ""),
                "defect_id": str(blocker.get("defect_id") or ""),
                "resume": req.producers[0],
            }
        )
    return severed


def ship_reachable(ctx: RunContext) -> Reachability:
    """Can this run still land ``master/master.wav``?

    Signature is stable for the solver: ``ship_reachable(ctx) -> Reachability``.
    """
    if master_committed(ctx):
        return Reachability(True, True, "master_committed")
    try:
        severed = severed_requirements(ctx)
    except Exception as exc:
        _note_swallow("ship_reachable.severed_requirements", exc)
        severed = []
    if severed:
        return Reachability(
            False,
            True,
            "severed_required_artifact",
            blockers=tuple(str(s["artifact"]) for s in severed),
            detail={"severed": severed},
        )
    return Reachability(True, False, "no_proven_severance")


def proven_unreachable(ctx: RunContext) -> bool:
    """True only when the ship path is *proven* dead."""
    reach = ship_reachable(ctx)
    return reach.certain and not reach.reachable


def halt_payload(ctx: RunContext) -> dict[str, Any] | None:
    """§10.2: the halt message is the product — unmet dep, producer, resume pin."""
    reach = ship_reachable(ctx)
    if reach.reachable or not reach.certain:
        return None
    severed = list((reach.detail or {}).get("severed") or [])
    first = severed[0] if severed else {}
    return {
        "reason": reach.reason,
        "blockers": list(reach.blockers),
        "unmet": severed,
        "resume": str(first.get("resume") or ""),
        "halt_enabled": halt_enabled(),
        # Advisory: how much of the analysis behind this verdict was blind.
        "analysis": analysis_health(),
    }


def _record_degraded_analysis(ctx: RunContext) -> None:
    """Surface a failed contract read even when nothing is severed.

    Otherwise the only writer of ``operator/ship_reachability.json`` is a proven
    severance, so the finding-6 fail-open would stay invisible in precisely the case
    where it fires: the analysis goes blind, finds nothing, and reports a clean
    ``no_proven_severance``. Writes only when a read actually failed, so a healthy
    run is byte-for-byte unchanged. Report-only — no halt, no verdict.

    Reports what the analysis *already observed* in this process and deliberately
    does not recompute the path: ``severed_requirements`` returns early before
    ``critical_path`` when no producer is dead, so on a run with nothing to prove
    the contracts are never read and there is correspondingly nothing to report.
    The moment severance is actually evaluated — the only moment the guard matters —
    a failed read becomes visible here.
    """
    try:
        health = analysis_health()
        if not health.get("unresolved"):
            return
        record_reachability(
            ctx,
            {
                "reason": "analysis_degraded",
                "blockers": [],
                "unmet": [],
                "resume": "",
                "halt_enabled": halt_enabled(),
                "analysis": health,
            },
        )
        ctx.log(
            "ship reachability analysis is degraded — "
            f"{health.get('operator_reason')}",
            level="warning",
        )
    except Exception as exc:
        _note_swallow("record_degraded_analysis", exc)


def unreachable_halt(ctx: RunContext) -> dict[str, Any] | None:
    """Payload when the walk must stop, else None. Never raises."""
    try:
        payload = halt_payload(ctx)
    except Exception as exc:
        _note_swallow("unreachable_halt.halt_payload", exc)
        return None
    if payload is None:
        _record_degraded_analysis(ctx)
        return None
    try:
        record_reachability(ctx, payload)
    except Exception as exc:
        _note_swallow("unreachable_halt.record_reachability", exc)
    if not halt_enabled():
        try:
            ctx.log(
                "ship path provably severed but halt is disabled "
                f"({_ENV_HALT} unset) — advancing: {payload.get('blockers')}",
                level="warning",
            )
        except Exception as exc:
            _note_swallow("unreachable_halt.log", exc)
        return None
    return payload


REACHABILITY_REL = "operator/ship_reachability.json"


def record_reachability(ctx: RunContext, payload: dict[str, Any]) -> None:
    """Persist the verdict so a halt (or a suppressed halt) is auditable."""
    from datetime import datetime, timezone
    from pathlib import Path

    from interview_mux.file_store import write_json as fs_write_json

    doc = dict(payload)
    doc["recorded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dest = Path(ctx.run_dir) / REACHABILITY_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(dest, doc)
