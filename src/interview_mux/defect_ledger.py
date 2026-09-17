"""Advance-past defect ledger — the audit trail that replaces thrash (plan §5.5, D1).

D1: when a stage cannot progress, the run advances past it while ``master.wav`` is
still provably reachable and records a defect here. Halting is the exception and
must be justified by unreachability, not by a failed attempt.

The ledger is a **publishability input**: PMQ refuses ``publish_allowed`` while any
ship-bar-degrading defect is open, which is what keeps advance-past from quietly
shipping a hollow master (see docs/cross-cutting/publishability-contract.md).
"""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

DEFECT_LEDGER_REL = "operator/defect_ledger.json"

# Skipping one of these leaves a master that is missing or unfaithful to the air
# order, so an open defect on them degrades the ship bar. Bed/SFX stages are
# deliberately absent: production already allows an omitted bed.
SHIP_BAR_CRITICAL_STAGES: frozenset[str] = frozenset(
    {
        "full_master_ranking",
        "selection_framing_apply",
        "selection_order_sanitize",
        "air_script_compose",
        "air_script_seams",
        "air_contract_sanitize",
        "transitions",
        "edl",
        "edl_narrative_audit",
        "assembly_preview",
        "vo_synthesize",
        "vo_line_adjudicate",
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "master_transcript_build",
    }
)

STATE_OPEN = "open"
STATE_RESOLVED = "resolved"

# Blockers that degrade the ship bar wherever they are recorded. Severity is a
# property of *what went wrong*; `SHIP_BAR_CRITICAL_STAGES` above is only the
# floor. Budget blockers (`max_*`, `attempt_memo`) are deliberately absent: a
# spent cap says nothing about the artifact, so it stays stage-keyed.
SHIP_BAR_CRITICAL_BLOCKERS: frozenset[str] = frozenset(
    {
        "missing_hard_input",
    }
)

# Substring probes for composed blocker strings, so a blocker minted by a future
# caller is classified by its nature rather than needing a table entry.
SHIP_BAR_BLOCKER_MARKERS: tuple[str, ...] = (
    "missing_hard_input",
    "semantically_incomplete",
    "output_missing",
    "schema_invalid",
    "contract_violation",
    "artifact_corrupt",
    "unrecoverable",
)

# `detail["severity"]` values a caller may use to declare a defect serious
# without the stage being on the critical list.
SEVERE_DETAIL_SEVERITIES: frozenset[str] = frozenset({"critical", "fatal", "blocking"})

# Tag written onto the empty doc that a corrupt ledger reads back as. Never a
# real ledger key — `_write` strips it.
_UNREADABLE_KEY = "_unreadable"


class DefectLedgerUnreadable(RuntimeError):
    """The ledger exists but cannot be counted.

    Raised by `defect_summary` so a decision path cannot read a corrupt or
    unparseable ledger as "no defects". PMQ refuses on this; it is never softened
    into ``open_ship_bar: 0``.
    """


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _empty_doc() -> dict[str, Any]:
    return {"version": 1, "updated_at": _now(), "defects": {}, "order": []}


def defect_id(stage: str, blocker: str, artifact: str = "") -> str:
    key = "|".join([str(stage or ""), str(blocker or ""), str(artifact or "")])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class DefectSeverity:
    """Why this defect does (or does not) degrade the ship bar."""

    degrades_ship_bar: bool
    reason: str


def defect_severity(
    stage: str,
    blocker: str = "",
    artifact: str = "",
    detail: dict[str, Any] | None = None,
) -> DefectSeverity:
    """Classify a defect by *what went wrong*, with the stage list as a floor.

    Blocking used to depend only on which stage happened to record the defect, so
    a serious problem observed by a stage outside `SHIP_BAR_CRITICAL_STAGES` did
    not block publication. The stage list is kept as the first rule, so anything
    that blocked before still blocks; every rule after it can only add.
    """
    sid = str(stage or "").strip()
    if sid in SHIP_BAR_CRITICAL_STAGES:
        return DefectSeverity(True, f"critical_stage:{sid}")
    kind = str(blocker or "").strip()
    if kind in SHIP_BAR_CRITICAL_BLOCKERS:
        return DefectSeverity(True, f"critical_blocker:{kind}")
    lowered = kind.lower()
    for marker in SHIP_BAR_BLOCKER_MARKERS:
        if marker in lowered:
            return DefectSeverity(True, f"critical_blocker_marker:{marker}")
    if isinstance(detail, dict):
        declared = str(detail.get("severity") or "").strip().lower()
        if declared in SEVERE_DETAIL_SEVERITIES:
            return DefectSeverity(True, f"detail_severity:{declared}")
        if detail.get("ship_bar") is True:
            return DefectSeverity(True, "detail_ship_bar")
    return DefectSeverity(False, "not_severe")


def degrades_ship_bar(
    stage: str,
    blocker: str = "",
    artifact: str = "",
    detail: dict[str, Any] | None = None,
) -> bool:
    return defect_severity(stage, blocker, artifact, detail).degrades_ship_bar


def read_defect_ledger(ctx: RunContext) -> dict[str, Any]:
    """Lenient read — a corrupt ledger comes back empty but TAGGED `_unreadable`.

    Leniency exists for the write path: `record_defect` must keep working while
    the walk advances. Decision paths must not treat the tagged empty doc as an
    absence of defects — `defect_summary` raises `DefectLedgerUnreadable`.
    """
    path = Path(ctx.run_dir) / DEFECT_LEDGER_REL
    if not path.is_file():
        return _empty_doc()
    try:
        doc = ctx.read_json(DEFECT_LEDGER_REL)
    except Exception as exc:
        return _unreadable_doc(f"unparseable: {type(exc).__name__}: {exc}")
    if not isinstance(doc, dict):
        return _unreadable_doc(f"expected an object, found {type(doc).__name__}")
    if "defects" in doc and not isinstance(doc.get("defects"), dict):
        return _unreadable_doc(
            f"defects is a {type(doc.get('defects')).__name__}, expected object"
        )
    if "order" in doc and not isinstance(doc.get("order"), list):
        return _unreadable_doc(
            f"order is a {type(doc.get('order')).__name__}, expected array"
        )
    doc.setdefault("version", 1)
    doc.setdefault("defects", {})
    doc.setdefault("order", [])
    return doc


def _unreadable_doc(reason: str) -> dict[str, Any]:
    doc = _empty_doc()
    doc[_UNREADABLE_KEY] = f"{DEFECT_LEDGER_REL}: {reason}"[:240]
    return doc


def _write(ctx: RunContext, doc: dict[str, Any]) -> None:
    from interview_mux.file_store import write_json as fs_write_json

    doc.pop(_UNREADABLE_KEY, None)
    dest = Path(ctx.run_dir) / DEFECT_LEDGER_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(dest, doc)


def record_defect(
    ctx: RunContext,
    *,
    stage: str,
    blocker: str,
    artifact: str = "",
    ship_bar: bool | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record an advance-past. Repeats increment ``count`` rather than adding rows."""
    did = defect_id(stage, blocker, artifact)
    doc = read_defect_ledger(ctx)
    defects = dict(doc.get("defects") or {})
    prev = dict(defects.get(did) or {})
    severity = defect_severity(stage, blocker, artifact, detail)
    if ship_bar is None:
        ship_bar_flag, ship_bar_reason = severity.degrades_ship_bar, severity.reason
    else:
        # An explicit flag stays authoritative: `refuse_dispatch` passes False for
        # `no_delta` because that guard only fires while the stage's own outputs are
        # already on disk. The classifier's verdict is kept alongside it.
        ship_bar_flag = bool(ship_bar)
        ship_bar_reason = f"caller:{ship_bar_flag} (classifier:{severity.reason})"
    row: dict[str, Any] = {
        "defect_id": did,
        "stage": str(stage or ""),
        "blocker": str(blocker or ""),
        "artifact": str(artifact or ""),
        "degrades_ship_bar": ship_bar_flag,
        "ship_bar_reason": ship_bar_reason,
        "state": STATE_OPEN,
        "count": int(prev.get("count") or 0) + 1,
        "first_seen_at": str(prev.get("first_seen_at") or _now()),
        "updated_at": _now(),
    }
    if detail:
        row["detail"] = detail
    reach = _reachability_row(ctx)
    if reach:
        row["reachability"] = reach
    defects[did] = row
    order = [d for d in (doc.get("order") or []) if d != did]
    order.append(did)
    doc["defects"] = defects
    doc["order"] = order[-400:]
    doc["updated_at"] = _now()
    _write(ctx, doc)
    try:
        ctx.log(
            f"defect recorded {stage}: {blocker}"
            + (" (ship bar)" if row["degrades_ship_bar"] else ""),
            level="warning" if row["degrades_ship_bar"] else "info",
            stage=str(stage or None),
            detail={"defect_id": did, "artifact": artifact, "count": row["count"]},
        )
    except Exception:
        pass
    return row


def _reachability_row(ctx: RunContext) -> dict[str, Any]:
    try:
        from interview_mux.ship_reachability import ship_reachable

        reach = ship_reachable(ctx)
        return {
            "reachable": reach.reachable,
            "certain": reach.certain,
            "reason": reach.reason,
        }
    except Exception:
        return {}


def defects(ctx: RunContext, doc: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    doc = read_defect_ledger(ctx) if doc is None else doc
    rows = doc.get("defects") or {}
    out: list[dict[str, Any]] = []
    for did in doc.get("order") or []:
        row = rows.get(did)
        if isinstance(row, dict):
            out.append(row)
    return out


def open_defects(ctx: RunContext) -> list[dict[str, Any]]:
    return [r for r in defects(ctx) if str(r.get("state") or STATE_OPEN) == STATE_OPEN]


def open_ship_bar_defects(ctx: RunContext) -> list[dict[str, Any]]:
    """Open defects that degrade the ship bar — PMQ refuses publish while any exist."""
    return [r for r in open_defects(ctx) if r.get("degrades_ship_bar")]


def resolve_stage_defects(
    ctx: RunContext,
    stage: str,
    *,
    reason: str = "stage_progressed",
) -> int:
    """Close this stage's defects once it actually produced work."""
    sid = str(stage or "").strip()
    if not sid:
        return 0
    doc = read_defect_ledger(ctx)
    rows = dict(doc.get("defects") or {})
    closed = 0
    for did, row in list(rows.items()):
        if not isinstance(row, dict) or str(row.get("stage") or "") != sid:
            continue
        if str(row.get("state") or STATE_OPEN) != STATE_OPEN:
            continue
        updated = dict(row)
        updated["state"] = STATE_RESOLVED
        updated["resolved_at"] = _now()
        updated["resolved_reason"] = str(reason or "")
        rows[did] = updated
        closed += 1
    if not closed:
        return 0
    doc["defects"] = rows
    doc["updated_at"] = _now()
    _write(ctx, doc)
    return closed


def defect_summary(ctx: RunContext) -> dict[str, Any]:
    """Compact view for PMQ / GUI: counts plus the open ship-bar blockers.

    Raises `DefectLedgerUnreadable` when the count cannot be trusted. Callers are
    decision paths, so "we could not count" must reach them as an error rather
    than as a zero they will read as permission to publish.
    """
    doc = read_defect_ledger(ctx)
    unreadable = doc.get(_UNREADABLE_KEY)
    if unreadable:
        raise DefectLedgerUnreadable(str(unreadable))
    all_rows = defects(ctx, doc)
    open_rows = [r for r in all_rows if str(r.get("state") or STATE_OPEN) == STATE_OPEN]
    ship_rows = [r for r in open_rows if r.get("degrades_ship_bar")]
    return {
        "total": len(all_rows),
        "open": len(open_rows),
        "open_ship_bar": len(ship_rows),
        "blockers": [
            {
                "stage": str(r.get("stage") or ""),
                "blocker": str(r.get("blocker") or ""),
                "artifact": str(r.get("artifact") or ""),
                "count": int(r.get("count") or 0),
                "ship_bar_reason": str(r.get("ship_bar_reason") or ""),
            }
            for r in ship_rows[:12]
        ],
    }


# ---------------------------------------------------------------------------
# Stages that SUCCEED and still commit a wrong artifact
# ---------------------------------------------------------------------------
#
# Everything above records a defect when a stage cannot be *dispatched*. A stage
# that dispatches successfully, stamps `.stage_done`, and commits a semantically
# wrong artifact recorded nothing at all — the asymmetry that leaves the guard
# layer irreplaceable, because the guards are what catch stages succeeding on bad
# data. The sweep below closes it by pushing every done stage's declared output
# through `artifact_completeness.artifact_status_for_stage`, which runs the whole
# `_gaps_*` rule table plus json-schema validation.
#
# Rollout mirrors `contract_conformance`: report-only by default, enforcement is a
# ratchet that only grows. A report-only finding is still recorded in the ledger
# (so the rate is observable) but carries `degrades_ship_bar: False`.

SEMANTIC_OUTPUT_BLOCKER = "output_semantically_incomplete"
SEMANTIC_OUTPUT_MISSING_BLOCKER = "output_missing_after_success"
SEMANTIC_SWEEP_SOURCE = "semantic_output_sweep"

_ENV_SEMANTIC_BLOCKING = "MUX_DEFECT_SEMANTIC_BLOCKING"
_ENV_SEMANTIC_BLOCKING_STAGES = "MUX_DEFECT_SEMANTIC_BLOCKING_STAGES"

# Stages whose semantic-output findings BLOCK instead of reporting. Empty means
# report-only everywhere. Like `contract_conformance.STRICT_GROUPS` this only ever
# grows, and `MUX_DEFECT_SEMANTIC_BLOCKING_STAGES` overrides it so one bad stage
# can be reverted without reverting the campaign.
SEMANTIC_BLOCKING_STAGES: tuple[str, ...] = ()

# What `artifact_status_for_stage` will actually apply to an artifact. Recorded on
# every finding so a weak verdict is never presented as a semantic one: a
# `schema_only` or `bytes_only` finding does not license deleting a guard.
COVERAGE_GAP_RULE = "gap_rule"
COVERAGE_SCHEMA_ONLY = "schema_only"
COVERAGE_BYTES_ONLY = "bytes_only"


def _bytes_only_suffixes() -> tuple[str, ...]:
    from interview_mux.artifact_completeness import BINARY_ARTIFACT_SUFFIXES

    return (".txt",) + tuple(BINARY_ARTIFACT_SUFFIXES)


def semantic_sweep_blocking_stages() -> frozenset[str]:
    """Stages under enforcement. ``{"*"}`` means all of them."""
    raw = os.environ.get(_ENV_SEMANTIC_BLOCKING_STAGES)
    if raw is not None:
        return frozenset(s.strip() for s in raw.split(",") if s.strip())
    if _truthy(os.environ.get(_ENV_SEMANTIC_BLOCKING)):
        return frozenset({"*"})
    return frozenset(SEMANTIC_BLOCKING_STAGES)


def semantic_sweep_enforced() -> bool:
    return bool(semantic_sweep_blocking_stages())


def semantic_sweep_blocks(stage: str) -> bool:
    allowed = semantic_sweep_blocking_stages()
    return "*" in allowed or str(stage or "").strip() in allowed


def semantic_rule_coverage(rel_path: str, stage: str) -> str:
    """Which authority governs ``rel_path`` inside `artifact_status_for_stage`.

    Mirrors `artifact_completeness._gap_rule_for`. `gap_rule` means one of the
    `_gaps_*` rules runs — the real content. `schema_only` means json-schema and
    nothing else. `bytes_only` means a size check. Reported verbatim so the sweep
    can never be mistaken for a semantic check where it is not one.
    """
    from interview_mux.artifact_completeness import (
        ARTIFACT_COMPLETENESS_RULES,
        STAGE_GAP_RULES,
    )
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    rel = str(rel_path or "")
    if rel.endswith(_bytes_only_suffixes()):
        return COVERAGE_BYTES_ONLY
    sid = str(stage or "").strip()
    if sid in STAGE_GAP_RULES and STAGE_ARTIFACT_DISK_PATHS.get(sid) == rel:
        return COVERAGE_GAP_RULE
    if rel in ARTIFACT_COMPLETENESS_RULES:
        return COVERAGE_GAP_RULE
    return COVERAGE_SCHEMA_ONLY


# Stage attributed to rule-covered artifacts that no stage declares as its primary
# output (`understanding/analysis_state.json` and friends). Four of the rule
# table's entries are only reachable this way; without the pass their rules never
# run, which drifts the sweep toward the degraded "file exists" check it must not
# become.
ORPHAN_ARTIFACT_STAGE = "artifact_completeness_sweep"


def orphan_rule_artifacts() -> tuple[str, ...]:
    """Rule-covered artifacts absent from `STAGE_ARTIFACT_DISK_PATHS`."""
    from interview_mux.artifact_completeness import ARTIFACT_COMPLETENESS_RULES
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    declared = set(STAGE_ARTIFACT_DISK_PATHS.values())
    return tuple(sorted(r for r in ARTIFACT_COMPLETENESS_RULES if r not in declared))


@dataclass(frozen=True)
class SemanticOutputFinding:
    """A done stage whose declared output is not `complete`."""

    stage: str
    artifact: str
    status: str
    coverage: str
    gaps: tuple[str, ...]
    schema_errors: tuple[str, ...]
    blocking: bool

    def as_row(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "artifact": self.artifact,
            "status": self.status,
            "completeness_coverage": self.coverage,
            "gaps": list(self.gaps),
            "schema_errors": list(self.schema_errors),
            "blocking": self.blocking,
        }


def _semantic_gap_detail(
    ctx: RunContext, rel_path: str, stage: str
) -> tuple[list[str], list[str]]:
    """(semantic gap paths, schema errors) behind a non-complete status."""
    from interview_mux.artifact_completeness import compute_gaps
    from interview_mux.prompt_validation import validate_artifact_write

    if not ctx.artifact_exists(rel_path):
        return ["(absent)"], []
    if rel_path.endswith(_bytes_only_suffixes()):
        return ["(empty_or_truncated)"], []
    try:
        raw = ctx.read_json(rel_path)
    except Exception as exc:
        return [f"(unreadable: {type(exc).__name__})"], []
    data = raw if isinstance(raw, dict) else None
    gaps = [g.path for g in compute_gaps(rel_path, data, stage_key=stage, ctx=ctx)]
    schema = list(validate_artifact_write(rel_path, data)) if data else ["missing"]
    return gaps, [str(e) for e in schema]


def semantic_output_findings(
    ctx: RunContext,
) -> tuple[list[SemanticOutputFinding], dict[str, Any]]:
    """Read-only sweep of every done stage's declared output. Records nothing.

    Separate from `record_semantic_output_defects` so the firing rate can be
    measured against a finished run without writing to it.
    """
    from interview_mux.artifact_completeness import artifact_status_for_stage
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    findings: list[SemanticOutputFinding] = []
    coverage = Counter[str]()
    errors: list[str] = []
    examined = 0
    for stage, rel in sorted(STAGE_ARTIFACT_DISK_PATHS.items()):
        if not rel:
            continue
        try:
            if not ctx.is_done(stage):
                continue
            examined += 1
            kind = semantic_rule_coverage(rel, stage)
            coverage[kind] += 1
            status = artifact_status_for_stage(rel, ctx, stage)
            if status == "complete":
                continue
            gaps, schema_errors = _semantic_gap_detail(ctx, rel, stage)
            findings.append(
                SemanticOutputFinding(
                    stage=stage,
                    artifact=rel,
                    status=status,
                    coverage=kind,
                    gaps=tuple(gaps[:12]),
                    schema_errors=tuple(schema_errors[:8]),
                    blocking=semantic_sweep_blocks(stage),
                )
            )
        except Exception as exc:
            errors.append(f"{stage}: {type(exc).__name__}: {exc}"[:200])

    # Pass 2: rule-covered artifacts no stage owns as a primary output. Checked
    # only once present on disk — an artifact nobody produced yet is not a defect.
    # Skipped entirely on a run where nothing has completed: "succeeded on bad
    # data" presupposes something succeeded, and a half-written analysis_state on
    # an abandoned run is not a defect.
    orphans = 0
    for rel in orphan_rule_artifacts() if examined else ():
        try:
            if not ctx.artifact_exists(rel):
                continue
            orphans += 1
            kind = semantic_rule_coverage(rel, "")
            coverage[kind] += 1
            status = artifact_status_for_stage(rel, ctx, "")
            if status == "complete":
                continue
            gaps, schema_errors = _semantic_gap_detail(ctx, rel, "")
            findings.append(
                SemanticOutputFinding(
                    stage=ORPHAN_ARTIFACT_STAGE,
                    artifact=rel,
                    status=status,
                    coverage=kind,
                    gaps=tuple(gaps[:12]),
                    schema_errors=tuple(schema_errors[:8]),
                    blocking=semantic_sweep_blocks(ORPHAN_ARTIFACT_STAGE),
                )
            )
        except Exception as exc:
            errors.append(f"{rel}: {type(exc).__name__}: {exc}"[:200])

    report: dict[str, Any] = {
        "examined_stages": examined,
        "examined_orphan_artifacts": orphans,
        "findings": len(findings),
        "blocking_findings": sum(1 for f in findings if f.blocking),
        "enforced": semantic_sweep_enforced(),
        "blocking_stages": sorted(semantic_sweep_blocking_stages()),
        "coverage": dict(sorted(coverage.items())),
        "finding_coverage": dict(
            sorted(Counter(f.coverage for f in findings).items())
        ),
        "by_status": dict(sorted(Counter(f.status for f in findings).items())),
        "sweep_errors": errors[:8],
        "detail": [f.as_row() for f in findings[:24]],
    }
    return findings, report


def record_semantic_output_defects(ctx: RunContext) -> dict[str, Any]:
    """Sweep, then record a defect per finding. Report-only unless enforced.

    Report-only rows are still written to the ledger — that is how the rate stays
    observable — but with `degrades_ship_bar: False`, so they cannot refuse a
    publish until a stage is added to `SEMANTIC_BLOCKING_STAGES` or the env
    override is set.
    """
    findings, report = semantic_output_findings(ctx)
    recorded: list[str] = []
    for finding in findings:
        blocker = (
            SEMANTIC_OUTPUT_MISSING_BLOCKER
            if finding.status == "pending"
            else SEMANTIC_OUTPUT_BLOCKER
        )
        row = record_defect(
            ctx,
            stage=finding.stage,
            blocker=blocker,
            artifact=finding.artifact,
            ship_bar=None if finding.blocking else False,
            detail={
                "source": SEMANTIC_SWEEP_SOURCE,
                "report_only": not finding.blocking,
                **finding.as_row(),
            },
        )
        recorded.append(str(row.get("defect_id") or ""))
    report["recorded_defect_ids"] = recorded
    report["resolved_defect_ids"] = _resolve_stale_sweep_defects(ctx, set(recorded))
    return report


def _resolve_stale_sweep_defects(ctx: RunContext, live: set[str]) -> list[str]:
    """Close sweep rows that no longer fire, so a repaired artifact stops blocking.

    `resolve_stage_defects` only runs when a stage re-dispatches to `done`, and the
    orphan pass has no stage to re-dispatch at all. Without this, one bad artifact
    would refuse publication forever once enforcement is on.
    """
    doc = read_defect_ledger(ctx)
    if doc.get(_UNREADABLE_KEY):
        return []
    rows = dict(doc.get("defects") or {})
    closed: list[str] = []
    for did, row in list(rows.items()):
        if not isinstance(row, dict) or did in live:
            continue
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        if str(detail.get("source") or "") != SEMANTIC_SWEEP_SOURCE:
            continue
        if str(row.get("state") or STATE_OPEN) != STATE_OPEN:
            continue
        rows[did] = {
            **row,
            "state": STATE_RESOLVED,
            "resolved_at": _now(),
            "resolved_reason": "semantic_output_complete",
        }
        closed.append(did)
    if not closed:
        return []
    doc["defects"] = rows
    doc["updated_at"] = _now()
    _write(ctx, doc)
    return closed
