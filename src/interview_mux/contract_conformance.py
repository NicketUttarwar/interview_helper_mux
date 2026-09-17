"""Runtime contract conformance — record what a stage really reads and writes.

Plan `.cursor/plans/solver_brain_020.plan.md` §4.1. A later deterministic solver
may only trust `docs/cross-cutting/stage-contracts/*.yaml` if the declared
`inputs` / `outputs` match what the stage bodies actually touch. This module is
the measuring instrument for that claim; it decides nothing.

**Report-only at runtime, always.** A mismatch logs a warning and never raises,
never fails a dispatch, and never gates a stage. Enforcement lives in
`tests/test_contract_conformance.py`, which fails for the groups listed in
`STRICT_GROUPS` and warns for every other group. That is the ratchet of plan
§3: scaffolding is global and immediate, enforcement is local and incremental.
`STRICT_GROUPS` only ever grows.

**Off by default.** Recording costs a dict insert per resolved path, but the
seams (`write_staging.resolve_write_path` / `resolve_read_path`) are hot, so it
is gated on `MUX_CONTRACT_RECORD=1` and the flag read is cached per process.

Groups are the operator phases of `interview_mux.v2.phases` (`prepare`,
`understand-a/b/c`, `fill_gaps`, `plan_rank`, `sound`, `build`, `ship`).
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

CONTRACT_OBSERVED_REL = "operator/contract_observed.json"

_ENV_RECORD = "MUX_CONTRACT_RECORD"
_ENV_STRICT_GROUPS = "MUX_CONTRACT_STRICT_GROUPS"

# Groups whose conformance findings FAIL the suite instead of warning (plan
# §3.5 DoD item 2). A group is added only once every stage in it declares its
# real reads and writes. Per plan §8.10 `MUX_CONTRACT_STRICT_GROUPS` overrides
# this list so one bad group can be reverted without reverting the campaign.
#
# `prepare` is flipped: its five stages are `process` bodies whose artifact
# reads and writes are all direct `ctx` calls in one entrypoint each, verified
# against `web/stages.py::STAGE_BY_ID` and each stage's own raise sites.
#
# `understand-c` and `sound` join it on two pieces of evidence, both required.
# First, every stage in them is clean under
# `tools/extract_stage_artifact_touches.py --entrypoint-only --call-depth 0`
# (the stage body plus its same-module helpers) fed through `evaluate()` — the
# same matcher this module uses. Second, and the binding one: flipping a group
# also makes its stages `precision_droppable` in
# `artifact_dependency_graph.precision_eligible`, so a flip is a live claim that
# those stages may be *left out* of an upstream redo's invalidation set. For
# these two groups the claim costs nothing — `transitive_invalidate` still equals
# `_blanket_invalidate` for all 72 stages with them strict, so precision stays
# inert and the flip cannot under-invalidate anything.
#
# That second condition is why the other six groups are still report-only, and
# why this reverses D11's payoff-first order rather than leading with `build`.
# The reasons are per-group and are recorded in
# `tests/test_contract_conformance.py::test_the_report_only_groups_are_pinned`;
# none of them is fixable by editing a contract.
#
# NOTE on what a flip does and does not assert today: nothing in the tree has a
# recorded `operator/contract_observed.json`, so
# `test_recorded_run_conformance_for_flipped_groups` skips and the ratchet has no
# runtime evidence to bite on yet. `MUX_CONTRACT_RECORD=1` on the next full-auto
# is what turns these flips into a real assertion.
STRICT_GROUPS: tuple[str, ...] = ("prepare", "understand-c", "sound")

# Infrastructure paths that no contract declares and none should: operator
# telemetry, done markers, the run manifest, GUI plumbing, and the homunculus
# ledger. Recording them would make every stage look non-conformant.
IGNORED_PREFIXES: tuple[str, ...] = (
    ".stage_done/",
    ".pending_writes/",
    "operator/",
    "logs/",
    "mastering/homunculus/",
    "analysis/forensics/",
    # LLM call telemetry, written by the shared volley runner for every
    # `llm_full` stage rather than by the stage body.
    "understanding/llm_calls/",
    # Per-stage volley bookkeeping, same shape as `understanding/llm_calls/`.
    "understanding/stage_runs/",
)

IGNORED_PATHS: frozenset[str] = frozenset(
    {
        "run_meta.json",
        "gui_job.json",
        "gui_log.jsonl",
        "llm_audit.jsonl",
        # `_probe` in `mastering_research` checks the marker directory itself,
        # which the `.stage_done/` prefix does not cover.
        ".stage_done",
        ".pending_writes",
        "understanding/analysis_state.json",
        "understanding/analysis_orchestration.json",
        "understanding/context_index.json",
        "understanding/investigation_queue.json",
        "understanding/refinement_ledger.json",
        # Federated air-order lifecycle bus (docs/cross-cutting/air-order-boundary.md).
        # `artifact_writes.write_validated_artifact` consults it on *every*
        # commit, so it is attributed to whichever stage is writing rather than
        # being that stage's dependency. `ops`-owned, like `operator/`.
        "master/air_order_integrity.json",
    }
)

# Finding kinds. Only the `undeclared_*` kinds can fail a strict group: a
# declared artifact that was never touched is usually a conditional dependency
# (`when` predicate false on this tape), not a contract lie.
UNDECLARED_READ = "undeclared_read"
UNDECLARED_WRITE = "undeclared_write"
UNUSED_INPUT = "declared_input_never_read"
UNUSED_OUTPUT = "declared_output_never_written"
PROBE_WRITE = "path_probe_not_a_write"

BLOCKING_KINDS: frozenset[str] = frozenset({UNDECLARED_READ, UNDECLARED_WRITE})

_record_flag: bool | None = None
_observed: dict[str, dict[str, dict[str, set[str]]]] = {}


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def recording_enabled() -> bool:
    """``MUX_CONTRACT_RECORD=1``. Cached — the seams are hot paths."""
    global _record_flag
    if _record_flag is None:
        _record_flag = _truthy(os.environ.get(_ENV_RECORD))
    return _record_flag


def reset_flag_cache() -> None:
    """Tests flip the env var after import."""
    global _record_flag
    _record_flag = None


def strict_groups() -> frozenset[str]:
    raw = os.environ.get(_ENV_STRICT_GROUPS)
    if raw is not None:
        return frozenset(g.strip() for g in raw.split(",") if g.strip())
    return frozenset(STRICT_GROUPS)


def group_for_stage(stage_id: str) -> str | None:
    from interview_mux.v2.phases import phase_for_stage

    phase = phase_for_stage(str(stage_id or ""))
    return str(phase.get("id")) if phase else None


def group_is_strict(stage_id: str) -> bool:
    group = group_for_stage(stage_id)
    return bool(group) and group in strict_groups()


def is_ignored(rel: str) -> bool:
    path = str(rel or "").strip().removeprefix("./")
    if not path or path in IGNORED_PATHS:
        return True
    if path.startswith(IGNORED_PREFIXES):
        return True
    # A bare directory (`transcripts/vo`, `transcript/review_clips`) is a
    # `ctx.path()` resolution ahead of an mkdir, not an artifact touch. Every
    # artifact is a file; the only suffixless paths any contract declares are
    # directory *families*, and those always carry a trailing slash.
    return not PurePosixPath(path).suffix and not path.endswith("/")


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def _bucket(run_dir: Any, stage_id: str) -> dict[str, set[str]]:
    key = str(run_dir)
    stages = _observed.setdefault(key, {})
    return stages.setdefault(str(stage_id), {"reads": set(), "writes": set()})


def note_read(ctx: Any, rel: str, stage_id: str | None = None) -> None:
    """Called from ``write_staging.resolve_read_path``. Never raises."""
    if not recording_enabled():
        return
    try:
        sid = stage_id or _active_stage_id()
        if not sid or is_ignored(rel):
            return
        _bucket(ctx.run_dir, sid)["reads"].add(str(rel))
    except Exception:
        return


def note_write(ctx: Any, rel: str, stage_id: str | None = None) -> None:
    """Called from ``write_staging.resolve_write_path``. Never raises."""
    if not recording_enabled():
        return
    try:
        sid = stage_id or _active_stage_id()
        if not sid or is_ignored(rel):
            return
        _bucket(ctx.run_dir, sid)["writes"].add(str(rel))
    except Exception:
        return


def _active_stage_id() -> str | None:
    from interview_mux.write_staging import active_stage_id

    return active_stage_id()


def observed_in_process(ctx: Any) -> dict[str, dict[str, list[str]]]:
    stages = _observed.get(str(ctx.run_dir)) or {}
    return {
        sid: {"reads": sorted(v["reads"]), "writes": sorted(v["writes"])}
        for sid, v in sorted(stages.items())
    }


def clear_in_process(ctx: Any | None = None) -> None:
    if ctx is None:
        _observed.clear()
        return
    _observed.pop(str(ctx.run_dir), None)


# ---------------------------------------------------------------------------
# Persistence — operator/contract_observed.json
# ---------------------------------------------------------------------------

def read_observed(ctx: Any) -> dict[str, dict[str, list[str]]]:
    """Merge the on-disk record with anything recorded in this process."""
    from interview_mux.file_store import read_json as fs_read_json

    disk: dict[str, dict[str, list[str]]] = {}
    path = Path(ctx.run_dir) / CONTRACT_OBSERVED_REL
    if path.is_file():
        try:
            doc = fs_read_json(path)
        except Exception:
            doc = None
        if isinstance(doc, dict) and isinstance(doc.get("stages"), dict):
            disk = {
                str(sid): {
                    "reads": [str(p) for p in (row.get("reads") or [])],
                    "writes": [str(p) for p in (row.get("writes") or [])],
                }
                for sid, row in doc["stages"].items()
                if isinstance(row, dict)
            }
    merged: dict[str, dict[str, set[str]]] = {}
    for source in (disk, observed_in_process(ctx)):
        for sid, row in source.items():
            slot = merged.setdefault(sid, {"reads": set(), "writes": set()})
            slot["reads"].update(row.get("reads") or [])
            slot["writes"].update(row.get("writes") or [])
    return {
        sid: {"reads": sorted(v["reads"]), "writes": sorted(v["writes"])}
        for sid, v in sorted(merged.items())
    }


def flush_observed(ctx: Any) -> Path | None:
    """Persist the merged record. Refuses without an ownership ALLOW row.

    The recorder is an observer; it must not be the reason a run gains a write
    it has no authority for. `operator/` resolves as `operational_unregistered`
    in the catalog today, but the check is explicit so a future DENY row stops
    the recorder rather than the recorder punching through it.
    """
    if not recording_enabled():
        return None
    try:
        from interview_mux.artifact_ownership import write_permitted

        ok, reason = write_permitted(
            ctx, CONTRACT_OBSERVED_REL, None, role="ops", verb="persist"
        )
    except Exception:
        ok, reason = False, "ownership_unavailable"
    if not ok:
        _log(ctx, f"contract recorder refused: {CONTRACT_OBSERVED_REL} ({reason})")
        return None
    from interview_mux.file_store import write_json as fs_write_json

    doc = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stages": read_observed(ctx),
    }
    dest = Path(ctx.run_dir) / CONTRACT_OBSERVED_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(dest, doc)
    return dest


def _log(ctx: Any, message: str, *, stage: str | None = None) -> None:
    try:
        ctx.log(message, level="warning", stage=stage)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    stage_id: str
    kind: str
    path: str
    group: str | None = None

    @property
    def blocking(self) -> bool:
        return self.kind in BLOCKING_KINDS

    def __str__(self) -> str:
        return f"{self.stage_id} [{self.group or 'no-group'}] {self.kind}: {self.path}"


@dataclass
class ConformanceReport:
    findings: list[Finding] = field(default_factory=list)

    def for_stage(self, stage_id: str) -> list[Finding]:
        return [f for f in self.findings if f.stage_id == stage_id]

    def blocking(self, groups: Iterable[str] | None = None) -> list[Finding]:
        allowed = frozenset(groups) if groups is not None else strict_groups()
        return [f for f in self.findings if f.blocking and f.group in allowed]

    def warnings(self, groups: Iterable[str] | None = None) -> list[Finding]:
        allowed = frozenset(groups) if groups is not None else strict_groups()
        return [f for f in self.findings if not (f.blocking and f.group in allowed)]


def _matches(rel: str, spec: str) -> bool:
    """Declared paths may be `glob:` specs (see `write_staging._stage_output_spec_matches`)."""
    pattern = spec[len("glob:") :] if spec.startswith("glob:") else spec
    if pattern == rel:
        return True
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatch(rel, pattern)
    # A declared directory covers the files beneath it.
    return pattern.endswith("/") and rel.startswith(pattern)


def declared_paths(stage_id: str) -> tuple[list[str], list[str]]:
    """(declared input paths, declared output paths) from the contract."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract(stage_id)
    if not contract:
        return [], []
    return (
        [i.path for i in contract.inputs if i.path],
        [o.path for o in contract.outputs if o.path],
    )


def _is_probe_not_a_write(stage_id: str, rel: str) -> bool:
    """A recorded 'write' the ownership constitution refuses this stage.

    `ctx.path()` resolves through `resolve_write_path`, and stage bodies use it
    for existence probes as often as for writes — `transcribe` calling
    `ctx.path("ingest/normalized.wav")` to check the source is recorded as a
    write of another stage's artifact. A real write there would raise
    `authority_denied` at commit, so the touch cannot be a write; it is a path
    resolution. Reclassified rather than dropped so the noise stays visible.

    Only an *explicit* denial counts. `unknown_path` — the catalog has no row for
    this path at all — stays an undeclared write, because that is exactly the
    shape of a stage minting a brand-new artifact nobody has modelled yet, which
    is the thing this recorder exists to catch.
    """
    try:
        from interview_mux.artifact_ownership import write_permitted

        ok, reason = write_permitted(None, rel, stage_id)
    except Exception:
        return False
    return not ok and str(reason or "").startswith(("not_allow", "deny"))


def evaluate(observed: dict[str, dict[str, list[str]]]) -> ConformanceReport:
    """Compare a recorded read/write map against the declared contracts."""
    report = ConformanceReport()
    for stage_id, row in sorted(observed.items()):
        group = group_for_stage(stage_id)
        inputs, outputs = declared_paths(stage_id)
        reads = [p for p in (row.get("reads") or []) if not is_ignored(p)]
        writes = [p for p in (row.get("writes") or []) if not is_ignored(p)]
        # A stage reading back its own output is conformant by construction.
        readable = list(inputs) + list(outputs)
        for rel in reads:
            if not any(_matches(rel, spec) for spec in readable):
                report.findings.append(
                    Finding(stage_id, UNDECLARED_READ, rel, group)
                )
        for rel in writes:
            if any(_matches(rel, spec) for spec in outputs):
                continue
            if _is_probe_not_a_write(stage_id, rel):
                report.findings.append(Finding(stage_id, PROBE_WRITE, rel, group))
                continue
            report.findings.append(Finding(stage_id, UNDECLARED_WRITE, rel, group))
        for spec in inputs:
            if not any(_matches(rel, spec) for rel in reads):
                report.findings.append(Finding(stage_id, UNUSED_INPUT, spec, group))
        for spec in outputs:
            if not any(_matches(rel, spec) for rel in writes):
                report.findings.append(Finding(stage_id, UNUSED_OUTPUT, spec, group))
    return report


def warn_on_mismatch(ctx: Any, stage_id: str) -> list[Finding]:
    """Report-only hook: log this stage's findings, never raise, never gate.

    Called after a stage commits when recording is on. Even for a strict group
    this only warns — enforcement is a test-time decision, so a wrong contract
    can never halt a live run mid-campaign.
    """
    if not recording_enabled():
        return []
    try:
        observed = observed_in_process(ctx)
        if stage_id not in observed:
            return []
        findings = evaluate({stage_id: observed[stage_id]}).for_stage(stage_id)
        blocking = [f for f in findings if f.blocking]
        if blocking:
            _log(
                ctx,
                "contract conformance (report-only): "
                + "; ".join(str(f) for f in blocking[:12]),
                stage=stage_id,
            )
        flush_observed(ctx)
        return findings
    except Exception:
        return []


__all__ = [
    "BLOCKING_KINDS",
    "CONTRACT_OBSERVED_REL",
    "ConformanceReport",
    "Finding",
    "IGNORED_PATHS",
    "IGNORED_PREFIXES",
    "PROBE_WRITE",
    "STRICT_GROUPS",
    "UNDECLARED_READ",
    "UNDECLARED_WRITE",
    "UNUSED_INPUT",
    "UNUSED_OUTPUT",
    "clear_in_process",
    "declared_paths",
    "evaluate",
    "flush_observed",
    "group_for_stage",
    "group_is_strict",
    "is_ignored",
    "note_read",
    "note_write",
    "observed_in_process",
    "read_observed",
    "recording_enabled",
    "reset_flag_cache",
    "strict_groups",
    "warn_on_mismatch",
]
