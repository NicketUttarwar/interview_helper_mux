#!/usr/bin/env python3
"""Offline replay validation for the deterministic solver (plan §6.3, todo ``p2-shadow``).

The promotion gate in §6.2 asks for *one full-auto run with zero non-deferred
disagreements*. No such run can be made while the forensics campaign is open, so this
harness answers the question from runs that already happened: for every dispatch a
completed execution actually made, reconstruct the on-disk state as it stood at that
moment and ask the solver what it would have done.

**Zero disagreements is not the gate, and on its own it is a false green.**
``solver.shadow_summary()["zero"]`` keys on ``disagree`` alone — deferrals are excluded
by design so they cannot block promotion. But a solver that has no justified opinion
about most of the pipeline disagrees with nobody, so that number is trivially
satisfiable while contract population is unfinished. This harness therefore reports a
**deferral census** alongside the disagreement count and treats a low coverage number
as a veto in its own right:

    authority rate   decision points where the solver could pick on its own authority
                     (``Decision.would_choose_confident`` is not None) — i.e. where
                     `authoritative_sequence` would NOT hand the pick back to seed order
    coverage census  per decision point, how many candidate stages were confidently
                     admissible vs deferred vs blocked
    defer causes     split into COVERAGE (contract population removes it) and
                     STRUCTURAL (population never will)

Divergences are classified, never summed into one number::

    skip      solver proves the dispatched stage was not runnable   (agreement in spirit)
    choice    solver would confidently have run a different stage   (real disagreement)

The classifier is ``solver.compare_walk_choice`` — reused, not reimplemented, so the
numbers stay comparable with live shadow logging. Comparison scope is the candidate
list the walk was actually working from (its ``walk_seed_agenda`` ledger row), so a
stage the walk's own filters removed is never counted as a solver preference.

Replay fidelity is limited and the limits are printed with every report; see
``FIDELITY``. Reconstructed state is not live state.

Usage::

    python tools/solver_replay.py                     # full corpus, write the report
    python tools/solver_replay.py --runs exec_11871
    python tools/solver_replay.py --limit 20 --max-points 50 --json /tmp/replay.json

The harness only ever reads the execution folders. Every solver evaluation runs
against a throwaway snapshot tree in a temp directory: data files are copied, media is
recreated as same-size sparse placeholders, and nothing is hardlinked or symlinked back
into ``ASSETS/executions``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

LEDGER_REL = "mastering/homunculus/ledger.json"
INVALIDATION_REL = "operator/invalidation_log.jsonl"
RUN_META_REL = "run_meta.json"

# The harness synthesises a point-in-time version of these, so the final-state copy
# must never be materialised.
SYNTHESISED: frozenset[str] = frozenset({LEDGER_REL, RUN_META_REL})

SNAPSHOT_SKIP_PREFIXES: tuple[str, ...] = (
    ".run.lock",
    ".locks/",
    "__pycache__/",
    "operator/solver_decision.jsonl",
)
SNAPSHOT_SKIP_SUFFIXES: tuple[str, ...] = (".lock", ".pyc")

# Media is recreated as a same-size sparse placeholder instead of copied — the solver
# only ever asks audio and images for existence and size, and this is what keeps a
# 6GB run directory replayable. Everything else is copied byte-for-byte no matter how
# large: `transcript/full.json` is 1.2MB in the reference run, and a placeholder for it
# reads as a corrupt artifact and fabricates `hard_input_missing` blockers.
MEDIA_SUFFIXES: frozenset[str] = frozenset(
    {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4", ".mov",
     ".png", ".jpg", ".jpeg", ".webp", ".npy", ".pt", ".bin"}
)
SPARSE_BYTES_LIMIT = 256_000

# Divergence classes. `SKIP` and `CHOICE` are reported separately, always.
AGREE = "agree"
DEFER = "defer"
SKIP = "skip"
CHOICE = "choice"

# --- deferral cause split (amendment item 3) -------------------------------
# COVERAGE: the contract does not yet say enough. Populating it removes the unknown,
# so these shrink to zero as the §4.3 group ratchet advances.
COVERAGE_UNKNOWNS: tuple[str, ...] = (
    "hard_inputs_undeclared",
    "outputs_undeclared",
    "producer_undeclared",
    "contract_absent",
)
# STRUCTURAL: no amount of contract population removes these. Gate state that is not
# on disk, glob inputs the rule refuses to resolve, config-optional gates, predicates
# that cannot be evaluated. This is the class that decides whether the solver can ever
# be authoritative, and it matters far more than the coverage class.
STRUCTURAL_UNKNOWNS: tuple[str, ...] = (
    "gate_indeterminate",
    "gate_may_pause",
    "gate_auto_accept_pending",
    "gate_optional_by_config",
    "input_is_path_spec",
    "when_indeterminate",
    "ownership_indeterminate",
    "door_indeterminate",
)

# --- promotion gate --------------------------------------------------------
# Every condition must hold. Any one of them failing is a veto, and a veto is a
# successful outcome for this harness — it is what "validate first" bought.
# Only *unexplained* choice divergences veto. A choice divergence whose preferred
# stage has no ledger dispatch row anywhere in the run is not evidence about the
# solver: that stage's done-timeline is reconstructed from marker mtime alone, which
# is a known lower bound (the marker records the last write, not the first). Those are
# reported in full and separately, never folded into the explained count and never
# silently dropped.
MAX_CHOICE_DIVERGENCES = 0
# Fraction of decision points where the solver could pick on its own authority.
# Below this, promotion buys an indirection layer and nothing else: the walk still
# decides, and the operator believes otherwise.
MIN_AUTHORITY_RATE = 0.80
# Fraction of stage verdicts deferring for a reason contract population cannot fix.
MAX_STRUCTURAL_DEFER_RATE = 0.05

# Evidence from outside the replay that bears on the same question. Recorded here so
# the report is not read as if replay were the only input.
EXTERNAL_EVIDENCE: tuple[str, ...] = (
    "Live shadow mode on a fresh run measured the solver **confidently admissible on "
    "2 of 72 stages, deferring on 35**, because only the `prepare` contract group is "
    "conformance-strict. That is an independent measurement of the same coverage "
    "problem this replay reports, and on its own it vetoes promotion.",
)

# Hand-maintained accounts of individual divergences that have been traced to root
# cause. Rendered next to the machine-generated list; deliberately does NOT change the
# verdict, so an explanation can never quietly promote anything.
KNOWN_DIVERGENCES: dict[str, str] = {
    "missing_framing": (
        "`stage_outputs_present('missing_framing')` routes through "
        "`stage_artifact_incompleteness`, which reads the CONTENT of "
        "`understanding/gap_evaluations.json`. The replay can restore that file's "
        "existence from the producer's ledger `done` row but only ever has its "
        "end-of-run bytes, so a content-sensitive completeness check is being asked "
        "about the wrong revision. Note the driver re-dispatched `missing_framing` "
        "twice within four minutes of the divergence (exec_5188 seq 235 and 245), so "
        "the solver's preference was not obviously wrong — but the replay cannot "
        "settle it, and it is left in the unexplained count rather than argued away."
    ),
    "content_brief_reanchor": (
        "`content_brief_reanchor` executes as a substep and never emits a "
        "`kind=stage` ledger row, so the replay has no event evidence for it at all "
        "and falls back to its `.stage_done` marker mtime. In exec_11871 the session "
        "log shows the stage completing at 01:08:45Z while the surviving marker is "
        "stamped 02:02:56Z — written early, invalidated, rewritten late. Every "
        "decision point in between therefore sees a stage the walk had already "
        "retired, and the solver correctly calls it runnable from state that is wrong."
    ),
}

FIDELITY: tuple[str, ...] = (
    "Artifact presence at time T is reconstructed from two witnesses: file mtime (the "
    "last write only) and the producing stage's ledger `done` row. The mtime witness "
    "misses artifacts overwritten later in the run; the producer witness covers most "
    "of that gap but reinstates the artifact's FINAL content, not the content it had "
    "at T. Content-sensitive sufficiency checks therefore see end-of-run bytes.",
    "run_meta.json is pinned to its final content from the first decision point, "
    "because posture, brain id and automation mode are run-level constants that "
    "cannot be recovered per-instant. Gate state that lives in run_meta (only the "
    "pre-clean enable does) is therefore seen as of end-of-run.",
    "The ownership matrix version seal is stripped from the replayed run_meta. Every "
    "run in the corpus was sealed against an older matrix, so leaving it in makes "
    "write_permitted refuse every output with `matrix_version_mismatch` — an artifact "
    "of replaying old runs against today's code, not a solver opinion.",
    "The dispatch door's attempt memo and no-delta guard read "
    "operator/dispatch_memo.json, which post-dates every run in the corpus. In replay "
    "they never fire, so door refusals are limited to ledger-counted caps and the "
    "skip class is an undercount on that axis.",
    "Lease and audio-serialisation state are wall-clock predicates. Replayed against "
    "a finished run they always read 'free', so the replay cannot exercise "
    "lease_held_by_gui or audio_serialize_inflight.",
    "Stage-done state comes from ledger done rows plus marker mtimes, reconciled "
    "against the invalidation log. A marker created, removed and recreated inside one "
    "decision interval is not recoverable.",
    "Stages that never produce a `kind=stage` ledger row — ones that run as a substep "
    "of another dispatch, through an API route, or are marked by a heal — have no "
    "event evidence at all, so their done-timeline is the marker mtime alone. Choice "
    "divergences naming such a stage are reported separately as "
    "reconstruction-limited rather than counted as disagreements, and the replay "
    "genuinely cannot settle them either way.",
    "Replay proves what the solver would have DECIDED given reconstructed state. It "
    "cannot prove what the run would have DONE: a refused dispatch changes every "
    "subsequent state, and the replay always follows the driver's actual path. No "
    "counterfactual trajectory is explored.",
    "Deferral causes are read off StageVerdict.unknowns, which is the solver's own "
    "account of what it could not answer. A check the solver never attempts cannot "
    "appear as an unknown, so the census measures declared ignorance, not total "
    "ignorance.",
)


# ---------------------------------------------------------------------------
# corpus selection
# ---------------------------------------------------------------------------

# A ledger this size is a real run rather than a pytest fixture. 22 folders clear it;
# the next band down is 3KB and holds synthetic trees with one or two dispatches.
SUBSTANTIVE_LEDGER_BYTES = 100_000


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    path: Path
    ledger_bytes: int
    has_master: bool
    mtime: float
    pinned: bool = False

    @property
    def substantive(self) -> bool:
        return self.ledger_bytes >= SUBSTANTIVE_LEDGER_BYTES

    @property
    def rank(self) -> tuple[int, int, int, int, float]:
        # Substantive outranks reached-master on purpose: the two richest runs in the
        # tree never shipped a master, and ranking on master alone spends the whole
        # 100-folder budget on 759-byte fixtures that happen to have one.
        return (
            int(self.pinned),
            int(self.substantive),
            int(self.has_master),
            self.ledger_bytes,
            self.mtime,
        )


def executions_root() -> Path:
    return REPO / "ASSETS" / "executions"


def select_corpus(
    *,
    limit: int = 100,
    pinned: Iterable[str] = ("exec_11871",),
    root: Path | None = None,
) -> list[RunSpec]:
    """At most ``limit`` execution folders, richest first. Hard cap, stat-only ranking.

    The ceiling is on folders *scanned*, so ranking parses nothing: it uses directory
    mtime, ``master/master.wav`` existence and ledger file size. The executions tree
    holds ~18k directories, and the ~300 most recent are all pytest fixtures with a
    sub-2KB ledger — recency alone selects an empty corpus. Hence the reached-master
    and ledger-size preference, with ``exec_11871`` pinned to the front.
    """
    base = root or executions_root()
    prefixes = tuple(str(p) for p in pinned if str(p).strip())
    specs: list[RunSpec] = []
    if not base.is_dir():
        return specs
    for entry in base.iterdir():
        if not entry.name.startswith("exec_") or not entry.is_dir():
            continue
        try:
            ledger_bytes = (entry / LEDGER_REL).stat().st_size
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        specs.append(
            RunSpec(
                run_id=entry.name,
                path=entry,
                ledger_bytes=ledger_bytes,
                has_master=(entry / "master" / "master.wav").is_file(),
                mtime=mtime,
                pinned=bool(prefixes) and entry.name.startswith(prefixes),
            )
        )
    specs.sort(key=lambda s: s.rank, reverse=True)
    return specs[: max(1, int(limit))]


# ---------------------------------------------------------------------------
# ledger timeline
# ---------------------------------------------------------------------------

def _epoch(raw: Any) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


@dataclass(frozen=True)
class DecisionPoint:
    """One dispatch the driver actually made, with the candidate set it saw."""

    seq: int
    at: str
    epoch: float
    stage: str
    source: str
    candidates: tuple[str, ...]
    candidate_origin: str
    from_walk: bool


def read_ledger_entries(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / LEDGER_REL
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = doc.get("entries") if isinstance(doc, dict) else doc
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def decision_points(entries: list[dict[str, Any]]) -> list[DecisionPoint]:
    """Every ``stage/started`` row, paired with the candidate list in force.

    The walk logs its own candidate set as a ``fallback/walk_seed_agenda`` row
    (``stages``) immediately before walking it; the conductor logs ``agenda`` rows
    (``remaining``). Using the driver's own candidate set is what keeps the comparison
    fair and comparable with live shadow numbers: the solver must not be allowed to
    prefer a stage the walk's filters had already removed.

    When the dispatched stage is *not* in that list the dispatch did not come off the
    walk at all (an explicit re-run, a heal pin, a conductor tool call). Scope then
    narrows to the dispatched stage alone, so the comparison asks only "was this
    runnable" and never manufactures a preference from a list the driver was not
    choosing from.
    """
    points: list[DecisionPoint] = []
    walk_candidates: tuple[str, ...] = ()
    walk_seq = -1
    agenda_candidates: tuple[str, ...] = ()
    agenda_seq = -1
    for row in sorted(entries, key=lambda r: int(r.get("seq") or 0)):
        kind = str(row.get("kind") or "")
        seq = int(row.get("seq") or 0)
        if kind == "fallback" and row.get("identity") == "walk_seed_agenda":
            stages = row.get("stages")
            if isinstance(stages, list):
                walk_candidates = tuple(str(s) for s in stages if str(s))
                walk_seq = seq
            continue
        if kind == "agenda":
            remaining = row.get("remaining")
            if isinstance(remaining, list):
                agenda_candidates = tuple(str(s) for s in remaining if str(s))
                agenda_seq = seq
            continue
        if kind != "stage" or str(row.get("status") or "") != "started":
            continue
        stage = str(row.get("identity") or "")
        epoch = _epoch(row.get("at"))
        if not stage or epoch is None:
            continue
        from_walk = walk_seq > agenda_seq and bool(walk_candidates)
        if from_walk:
            candidates, origin = walk_candidates, "walk_seed_agenda"
        elif agenda_candidates:
            candidates, origin = agenda_candidates, "agenda_remaining"
        else:
            candidates, origin = (stage,), "dispatch_only"
        if stage not in candidates:
            candidates, origin = (stage,), "scope_narrowed"
        points.append(
            DecisionPoint(
                seq=seq,
                at=str(row.get("at") or ""),
                epoch=epoch,
                stage=stage,
                source=str(row.get("source") or "unknown"),
                candidates=candidates,
                candidate_origin=origin,
                from_walk=from_walk,
            )
        )
    return points


def done_timeline(entries: list[dict[str, Any]]) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for row in entries:
        if str(row.get("kind") or "") != "stage":
            continue
        if str(row.get("status") or "") != "done":
            continue
        epoch = _epoch(row.get("at"))
        stage = str(row.get("identity") or "")
        if epoch is not None and stage:
            out.append((epoch, stage))
    out.sort()
    return out


def invalidation_timeline(run_dir: Path) -> list[tuple[float, frozenset[str]]]:
    path = run_dir / INVALIDATION_REL
    if not path.is_file():
        return []
    out: list[tuple[float, frozenset[str]]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        epoch = _epoch(row.get("ts") or row.get("at"))
        if epoch is None:
            continue
        stages: set[str] = set()
        for key in ("invalidated_artifacts", "invalidated", "stages"):
            value = row.get(key)
            if isinstance(value, list):
                stages.update(str(s) for s in value if str(s))
        if stages:
            out.append((epoch, frozenset(stages)))
    out.sort()
    return out


def stage_output_paths() -> dict[str, tuple[str, ...]]:
    """``stage -> declared output rel paths``, for the producer-done presence witness."""
    out: dict[str, list[str]] = {}
    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        for sid, rel in STAGE_ARTIFACT_DISK_PATHS.items():
            if rel:
                out.setdefault(str(sid), []).append(str(rel))
    except Exception:
        pass
    try:
        from interview_mux.stage_contract import all_contract_stage_ids, load_contract

        for sid in all_contract_stage_ids():
            contract = load_contract(sid)
            if contract is None:
                continue
            for dep in contract.outputs:
                rel = str(getattr(dep, "path", "") or "")
                if rel and "*" not in rel:
                    out.setdefault(str(sid), []).append(rel)
    except Exception:
        pass
    return {sid: tuple(dict.fromkeys(paths)) for sid, paths in out.items()}


# ---------------------------------------------------------------------------
# point-in-time snapshot
# ---------------------------------------------------------------------------

@dataclass
class Snapshot:
    """An incrementally-grown reconstruction of a run directory at time ``T``.

    Files are added in mtime order as ``T`` advances, so replaying every decision
    point of a run costs one pass over the tree rather than one copy per point.
    Nothing is linked back to the source: data files are copied, media becomes
    same-size sparse placeholders, so a hypothetical write through the snapshot
    cannot reach the forensics corpus.
    """

    source: Path
    dest: Path
    files: list[tuple[float, Path]] = field(default_factory=list)
    cursor: int = 0
    marked: set[str] = field(default_factory=set)
    present: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, source: Path, dest: Path) -> "Snapshot":
        dest.mkdir(parents=True, exist_ok=True)
        (dest / ".stage_done").mkdir(exist_ok=True)
        (dest / "vo_pickup").mkdir(exist_ok=True)
        files: list[tuple[float, Path]] = []
        for path in source.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(source).as_posix()
            if rel in SYNTHESISED or rel.startswith(SNAPSHOT_SKIP_PREFIXES):
                continue
            if rel.endswith(SNAPSHOT_SKIP_SUFFIXES) or rel.startswith(".stage_done/"):
                continue
            try:
                files.append((path.stat().st_mtime, path))
            except OSError:
                continue
        files.sort(key=lambda row: row[0])
        snap = cls(source=source, dest=dest, files=files)
        snap.write_run_meta()
        return snap

    def write_run_meta(self) -> None:
        """Pin run_meta from the start, minus the ownership-matrix seal.

        Posture, brain id and automation mode are run-level constants the replay
        cannot recover per-instant, so the final document is the only available
        witness. The matrix-version seal is dropped because every corpus run was
        sealed against an older matrix: leaving it in makes ``write_permitted`` refuse
        every declared output as ``matrix_version_mismatch``, which is a fact about
        replaying old runs under new code, not a solver opinion.
        """
        src = self.source / RUN_META_REL
        dest = self.dest / RUN_META_REL
        try:
            meta = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(meta, dict):
            from interview_mux.artifact_ownership import MATRIX_VERSION_META_KEY

            meta.pop(MATRIX_VERSION_META_KEY, None)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(meta, default=str), encoding="utf-8")

    def _materialise(self, path: Path) -> None:
        try:
            rel = path.relative_to(self.source)
        except ValueError:
            return
        key = rel.as_posix()
        if key in self.present:
            return
        target = self.dest / rel
        try:
            size = path.stat().st_size
        except OSError:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        sparse = path.suffix.lower() in MEDIA_SUFFIXES and size > SPARSE_BYTES_LIMIT
        try:
            if sparse:
                with target.open("wb") as fh:
                    fh.truncate(size)
            else:
                shutil.copyfile(path, target)
        except OSError:
            return
        self.present.add(key)

    def advance_to(self, epoch: float) -> None:
        while self.cursor < len(self.files) and self.files[self.cursor][0] <= epoch:
            self._materialise(self.files[self.cursor][1])
            self.cursor += 1

    def materialise_outputs(self, rels: Iterable[str]) -> None:
        """Second presence witness: this stage is done, so its outputs existed."""
        for rel in rels:
            if rel in self.present:
                continue
            src = self.source / rel
            if src.is_file():
                self._materialise(src)

    def set_done(self, stages: Iterable[str]) -> None:
        wanted = {str(s) for s in stages if str(s)}
        root = self.dest / ".stage_done"
        root.mkdir(parents=True, exist_ok=True)
        for stage in wanted - self.marked:
            try:
                (root / stage).touch()
            except OSError:
                continue
        for stage in self.marked - wanted:
            try:
                (root / stage).unlink()
            except OSError:
                continue
        self.marked = wanted

    def write_ledger(self, entries: list[dict[str, Any]]) -> None:
        dest = self.dest / LEDGER_REL
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps({"schema_version": 1, "entries": entries}, default=str),
            encoding="utf-8",
        )


def done_at(
    epoch: float,
    dones: list[tuple[float, str]],
    invalidations: list[tuple[float, frozenset[str]]],
    markers: dict[str, float],
) -> set[str]:
    """Stages whose ``.stage_done`` marker was present at ``epoch``.

    Two independent witnesses, unioned. The ledger says a stage completed and was not
    invalidated since; the marker mtime says the surviving marker was written at or
    before ``epoch``. The union is needed because the ledger misses hollow markers (8
    of them in the reference run) and the mtime misses markers later removed and
    rewritten.
    """
    last_done: dict[str, float] = {}
    for at, stage in dones:
        if at > epoch:
            break
        last_done[stage] = at
    for at, stages in invalidations:
        if at > epoch:
            break
        for stage in stages:
            if last_done.get(stage, float("inf")) <= at:
                last_done.pop(stage, None)
    out = set(last_done)
    out.update(stage for stage, mt in markers.items() if mt <= epoch)
    return out


def marker_mtimes(run_dir: Path) -> dict[str, float]:
    root = run_dir / ".stage_done"
    if not root.is_dir():
        return {}
    out: dict[str, float] = {}
    for path in root.iterdir():
        if not path.is_file():
            continue
        try:
            out[path.name] = path.stat().st_mtime
        except OSError:
            continue
    return out


# ---------------------------------------------------------------------------
# census
# ---------------------------------------------------------------------------

def unknown_bucket(unknown: str) -> str:
    family = str(unknown or "").split(":", 1)[0]
    if family in COVERAGE_UNKNOWNS:
        return "coverage"
    if family in STRUCTURAL_UNKNOWNS:
        return "structural"
    return "other"


@dataclass
class Census:
    """Solver coverage at one decision point — the number the amendment demands.

    ``confident`` stages are ones the solver can act on. ``deferred`` stages are
    admissible but unprovable, and ``authoritative_sequence`` hands each of them back
    to seed order — so a run made mostly of deferrals is a run the walk still decides.
    """

    candidates: int = 0
    confident: int = 0
    deferred: int = 0
    blocked: int = 0
    has_authority: bool = False
    defer_families: dict[str, int] = field(default_factory=dict)
    defer_buckets: dict[str, int] = field(default_factory=dict)
    defer_non_strict_group: int = 0

    def as_row(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "confident_admissible": self.confident,
            "deferred": self.deferred,
            "blocked": self.blocked,
            "has_authority": self.has_authority,
        }


def census_for(decision: Any) -> Census:
    """Read a ``solver.Decision`` into a coverage census. No solver logic duplicated."""
    from interview_mux.contract_conformance import group_is_strict

    out = Census(candidates=len(decision.verdicts))
    out.has_authority = decision.would_choose_confident is not None
    for verdict in decision.verdicts:
        if not verdict.admissible:
            out.blocked += 1
            continue
        if verdict.confident:
            out.confident += 1
            continue
        out.deferred += 1
        try:
            strict = group_is_strict(verdict.stage)
        except Exception:
            strict = False
        if not strict:
            out.defer_non_strict_group += 1
        for unknown in verdict.unknowns:
            family = str(unknown).split(":", 1)[0]
            out.defer_families[family] = out.defer_families.get(family, 0) + 1
            bucket = unknown_bucket(unknown)
            out.defer_buckets[bucket] = out.defer_buckets.get(bucket, 0) + 1
    return out


def merge_census(target: Census, other: Census) -> None:
    target.candidates += other.candidates
    target.confident += other.confident
    target.deferred += other.deferred
    target.blocked += other.blocked
    target.defer_non_strict_group += other.defer_non_strict_group
    for key, n in other.defer_families.items():
        target.defer_families[key] = target.defer_families.get(key, 0) + n
    for key, n in other.defer_buckets.items():
        target.defer_buckets[key] = target.defer_buckets.get(key, 0) + n


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    run_id: str
    seq: int
    at: str
    stage: str
    source: str
    verdict: str
    klass: str
    solver_choice: str | None
    reason: str
    reasons: tuple[str, ...]
    candidates: int
    candidate_origin: str
    choice_ever_dispatched: bool | None = None
    choice_evidence: str = ""

    @property
    def family(self) -> str:
        return self.reason.split(":", 1)[0] if self.reason else "unknown"

    @property
    def unexplained(self) -> bool:
        """A choice divergence the replay's own evidence cannot account for."""
        return self.klass == CHOICE and self.choice_evidence == "ledger"

    def as_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "run_id": self.run_id,
            "seq": self.seq,
            "at": self.at,
            "stage": self.stage,
            "source": self.source,
            "verdict": self.verdict,
            "class": self.klass,
            "solver_choice": self.solver_choice,
            "reason": self.reason,
            "family": self.family,
            "candidates": self.candidates,
            "candidate_origin": self.candidate_origin,
        }
        if self.reasons:
            row["reasons"] = list(self.reasons)
        if self.choice_ever_dispatched is not None:
            row["choice_ever_dispatched"] = self.choice_ever_dispatched
        if self.choice_evidence:
            row["choice_evidence"] = self.choice_evidence
            row["unexplained"] = self.unexplained
        return row


@dataclass
class RunReplay:
    run_id: str
    points: int = 0
    evaluated: int = 0
    has_master: bool = False
    observations: list[Observation] = field(default_factory=list)
    census: Census = field(default_factory=Census)
    census_points: int = 0
    authority_points: int = 0
    pipeline_census: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    seconds: float = 0.0

    def counts(self) -> dict[str, int]:
        out = {AGREE: 0, DEFER: 0, SKIP: 0, CHOICE: 0}
        for obs in self.observations:
            out[obs.klass] = out.get(obs.klass, 0) + 1
        return out


def choice_evidence(stage: str, ledger_stages: set[str]) -> str:
    """How well the replay can account for a preferred stage's done-timeline.

    ``ledger`` — the run dispatched this stage through the ledger, so its completions
    are timestamped events and the reconstruction rests on them.

    ``mtime_only`` — the stage never produced a ``kind=stage`` ledger row at all (it
    ran as a substep, through an API route, or was marked by a heal). Its done-state
    then comes from the surviving ``.stage_done`` marker's mtime, which records the
    *last* write. A marker created early, invalidated and rewritten late reads as
    absent for the whole middle of the run, and the solver correctly concludes the
    stage is runnable when the walk had already retired it. That is a property of the
    evidence, not of the solver, so it cannot be scored as a disagreement — but it is
    counted and printed, never dropped.
    """
    return "ledger" if stage in ledger_stages else "mtime_only"


def classify(comparison: Any, dispatched_ever: set[str]) -> tuple[str, bool | None]:
    """Map a ``solver.ShadowComparison`` onto the two divergence classes.

    ``compare_walk_choice`` returns one ``disagree`` verdict for two very different
    events, and collapsing them is exactly the number that would overstate the
    evidence:

    * the dispatched stage is provably not runnable → the solver would have **skipped**
      the dispatch. That is the refusal-of-thrash this campaign exists to produce, and
      it counts as agreement in spirit.
    * the solver confidently prefers a **different** stage → a real disagreement about
      control flow, which has to be explained one by one.
    """
    from interview_mux import solver

    if comparison.verdict == solver.AGREE:
        return AGREE, None
    if comparison.verdict == solver.DEFER:
        return DEFER, None
    if comparison.solver_choice and comparison.solver_choice != comparison.chosen:
        return CHOICE, comparison.solver_choice in dispatched_ever
    return SKIP, None


def replay_run(
    spec: RunSpec,
    *,
    workdir: Path,
    max_points: int = 0,
    census_stride: int = 1,
    pipeline_census_samples: int = 4,
) -> RunReplay:
    from interview_mux import solver
    from interview_mux.run_context import RunContext

    started = time.time()
    entries = read_ledger_entries(spec.path)
    points = decision_points(entries)
    if max_points and len(points) > max_points:
        # Keep both ends: the early run is where contracts are sparse, the late run is
        # where the thrash lives. Sampling the middle out preserves both.
        head = max_points // 2
        points = points[:head] + points[-(max_points - head):]
    replay = RunReplay(run_id=spec.run_id, points=len(points), has_master=spec.has_master)
    if not points:
        replay.seconds = time.time() - started
        return replay

    dispatched_ever = {p.stage for p in points}
    ledger_stages = {
        str(r.get("identity") or "")
        for r in entries
        if str(r.get("kind") or "") == "stage" and r.get("identity")
    }
    dones = done_timeline(entries)
    invalidations = invalidation_timeline(spec.path)
    markers = marker_mtimes(spec.path)
    outputs = stage_output_paths()
    by_seq = sorted(entries, key=lambda r: int(r.get("seq") or 0))

    dest = workdir / spec.run_id
    try:
        snapshot = Snapshot.build(spec.path, dest)
    except OSError as exc:
        replay.error = f"snapshot_failed:{exc}"
        replay.seconds = time.time() - started
        return replay

    ctx = RunContext(spec.run_id, create=False)
    ctx.run_dir = dest

    sample_at = set()
    if pipeline_census_samples > 0 and points:
        step = max(1, len(points) // pipeline_census_samples)
        sample_at = {i for i in range(0, len(points), step)}

    cursor = 0
    for index, point in enumerate(points):
        snapshot.advance_to(point.epoch)
        done_now = done_at(point.epoch, dones, invalidations, markers)
        for stage in done_now:
            snapshot.materialise_outputs(outputs.get(stage, ()))
        snapshot.set_done(done_now)
        while cursor < len(by_seq) and int(by_seq[cursor].get("seq") or 0) < point.seq:
            cursor += 1
        snapshot.write_ledger(by_seq[:cursor])
        # walk_seed_agenda sets this before it walks; mirror it so the dispatch door
        # applies on exactly the dispatches it applies to in production.
        setattr(ctx, "_homunculus_seed_walk", point.from_walk)
        try:
            comparison = solver.compare_walk_choice(
                ctx, point.stage, point.candidates, source=point.source
            )
        except Exception as exc:  # noqa: BLE001
            replay.observations.append(
                Observation(
                    run_id=spec.run_id,
                    seq=point.seq,
                    at=point.at,
                    stage=point.stage,
                    source=point.source,
                    verdict="error",
                    klass=DEFER,
                    solver_choice=None,
                    reason=f"replay_error:{type(exc).__name__}",
                    reasons=(str(exc)[:200],),
                    candidates=len(point.candidates),
                    candidate_origin=point.candidate_origin,
                )
            )
            continue
        klass, ever = classify(comparison, dispatched_ever)
        replay.evaluated += 1
        replay.observations.append(
            Observation(
                run_id=spec.run_id,
                seq=point.seq,
                at=point.at,
                stage=point.stage,
                source=point.source,
                verdict=comparison.verdict,
                klass=klass,
                solver_choice=comparison.solver_choice,
                reason=comparison.reason,
                reasons=tuple(
                    str(r) for r in (comparison.detail or {}).get("reasons") or ()
                ),
                candidates=len(point.candidates),
                candidate_origin=point.candidate_origin,
                choice_ever_dispatched=ever,
                choice_evidence=(
                    choice_evidence(comparison.solver_choice or "", ledger_stages)
                    if klass == CHOICE
                    else ""
                ),
            )
        )
        if census_stride > 0 and index % census_stride == 0:
            try:
                decision = solver.admissible_set(ctx, stages=point.candidates)
            except Exception:
                decision = None
            if decision is not None:
                cen = census_for(decision)
                merge_census(replay.census, cen)
                replay.census_points += 1
                replay.authority_points += int(cen.has_authority)
        if index in sample_at:
            try:
                whole = solver.admissible_set(ctx)
            except Exception:
                whole = None
            if whole is not None:
                cen = census_for(whole)
                replay.pipeline_census.append(
                    {"seq": point.seq, "at": point.at, **cen.as_row()}
                )
    shutil.rmtree(dest, ignore_errors=True)
    replay.seconds = time.time() - started
    return replay


# ---------------------------------------------------------------------------
# aggregation + verdict
# ---------------------------------------------------------------------------

def promotion_verdict(summary: dict[str, Any]) -> dict[str, Any]:
    """Every condition must hold. A veto is a successful outcome for this harness."""
    checks: list[dict[str, Any]] = []
    unexplained = summary["choice_unexplained"]
    checks.append(
        {
            "id": "no_unexplained_disagreements",
            "pass": unexplained <= MAX_CHOICE_DIVERGENCES,
            "detail": (
                f"{unexplained} unexplained choice divergence(s) of "
                f"{summary['choice_divergences']} total "
                f"({summary['choice_reconstruction_limited']} attributed to "
                f"mtime-only reconstruction); gate allows {MAX_CHOICE_DIVERGENCES}"
            ),
        }
    )
    rate = summary["authority_rate"]
    checks.append(
        {
            "id": "solver_has_authority",
            "pass": rate is not None and rate >= MIN_AUTHORITY_RATE,
            "detail": (
                f"solver could decide on its own authority at "
                f"{_pct(rate)} of decision points; gate needs "
                f"{_pct(MIN_AUTHORITY_RATE)}"
            ),
        }
    )
    structural = summary["structural_defer_rate"]
    checks.append(
        {
            "id": "structural_deferral_bounded",
            "pass": structural is not None and structural <= MAX_STRUCTURAL_DEFER_RATE,
            "detail": (
                f"{_pct(structural)} of stage verdicts defer for a reason contract "
                f"population cannot fix; gate allows {_pct(MAX_STRUCTURAL_DEFER_RATE)}"
            ),
        }
    )
    failed = [c for c in checks if not c["pass"]]
    return {
        "promote": not failed,
        "checks": checks,
        "vetoes": [c["id"] for c in failed],
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def summarise(replays: list[RunReplay]) -> dict[str, Any]:
    observations = [o for r in replays for o in r.observations]
    counts: dict[str, int] = {AGREE: 0, DEFER: 0, SKIP: 0, CHOICE: 0}
    for obs in observations:
        counts[obs.klass] = counts.get(obs.klass, 0) + 1
    skip_families: dict[str, int] = {}
    choice_pairs: dict[str, int] = {}
    for obs in observations:
        if obs.klass == SKIP:
            skip_families[obs.family] = skip_families.get(obs.family, 0) + 1
        elif obs.klass == CHOICE:
            key = f"{obs.stage} -> {obs.solver_choice}"
            choice_pairs[key] = choice_pairs.get(key, 0) + 1

    census = Census()
    for replay in replays:
        merge_census(census, replay.census)
    census_points = sum(r.census_points for r in replays)
    authority_points = sum(r.authority_points for r in replays)
    verdicts = census.confident + census.deferred + census.blocked
    decided = counts[AGREE] + counts[SKIP] + counts[CHOICE]

    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs_scanned": len(replays),
        "runs_with_dispatches": sum(1 for r in replays if r.points),
        "runs_reaching_master": sum(1 for r in replays if r.has_master),
        "decision_points": sum(r.points for r in replays),
        "evaluated": sum(r.evaluated for r in replays),
        "counts": counts,
        "agreement_rate": (counts[AGREE] / decided) if decided else None,
        "skip_divergences": counts[SKIP],
        "choice_divergences": counts[CHOICE],
        "choice_unexplained": sum(1 for o in observations if o.unexplained),
        "choice_reconstruction_limited": sum(
            1 for o in observations if o.klass == CHOICE and not o.unexplained
        ),
        "skip_families": dict(sorted(skip_families.items(), key=lambda kv: -kv[1])),
        "choice_pairs": dict(sorted(choice_pairs.items(), key=lambda kv: -kv[1])),
        "choice_examples": [o.as_row() for o in observations if o.klass == CHOICE][:60],
        "choice_unexplained_examples": [o.as_row() for o in observations if o.unexplained][:40],
        "skip_examples": [o.as_row() for o in observations if o.klass == SKIP][:40],
        # --- the deferral census, first class ---
        "census_points": census_points,
        "authority_points": authority_points,
        "authority_rate": (authority_points / census_points) if census_points else None,
        "stage_verdicts": verdicts,
        "confident_admissible": census.confident,
        "deferred_stages": census.deferred,
        "blocked_stages": census.blocked,
        "confident_rate": (census.confident / verdicts) if verdicts else None,
        "defer_rate": (census.deferred / verdicts) if verdicts else None,
        "defer_buckets": dict(sorted(census.defer_buckets.items(), key=lambda kv: -kv[1])),
        "defer_families": dict(sorted(census.defer_families.items(), key=lambda kv: -kv[1])),
        "defer_in_non_strict_group": census.defer_non_strict_group,
        "structural_defer_rate": (
            (census.defer_buckets.get("structural", 0) / verdicts) if verdicts else None
        ),
        "pipeline_census": [
            {"run_id": r.run_id, **row} for r in replays for row in r.pipeline_census
        ][:40],
        "errors": [{"run_id": r.run_id, "error": r.error} for r in replays if r.error],
        "runs": [
            {
                "run_id": r.run_id,
                "reached_master": r.has_master,
                "decision_points": r.points,
                "evaluated": r.evaluated,
                "authority_points": r.authority_points,
                "census_points": r.census_points,
                "confident_admissible": r.census.confident,
                "deferred": r.census.deferred,
                "blocked": r.census.blocked,
                "seconds": round(r.seconds, 1),
                **r.counts(),
            }
            for r in replays
            if r.points
        ],
        "gate": {
            "max_choice_divergences": MAX_CHOICE_DIVERGENCES,
            "min_authority_rate": MIN_AUTHORITY_RATE,
            "max_structural_defer_rate": MAX_STRUCTURAL_DEFER_RATE,
        },
        "fidelity": list(FIDELITY),
    }
    summary["verdict"] = promotion_verdict(summary)
    return summary


def run_replay(
    *,
    limit: int = 100,
    max_points: int = 0,
    only: tuple[str, ...] = (),
    census_stride: int = 1,
) -> dict[str, Any]:
    specs = select_corpus(limit=limit)
    if only:
        specs = [s for s in specs if any(s.run_id.startswith(p) for p in only)]
    replays: list[RunReplay] = []
    with tempfile.TemporaryDirectory(prefix="solver_replay_") as tmp:
        workdir = Path(tmp)
        for spec in specs:
            replays.append(
                replay_run(
                    spec,
                    workdir=workdir,
                    max_points=max_points,
                    census_stride=census_stride,
                )
            )
    return summarise(replays)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def render_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    verdict = summary["verdict"]
    lines: list[str] = []
    add = lines.append

    add("# Solver replay validation")
    add("")
    add(
        "Offline replay of the deterministic solver (`src/interview_mux/solver.py`) "
        "against completed execution folders, standing in for the live full-auto run "
        "the forensics campaign forbids. Regenerate with `python tools/solver_replay.py`."
    )
    add("")
    add(f"Generated: {summary['generated_at']}")
    add("")

    add("## Verdict")
    add("")
    add(f"**Promotion: {'APPROVED' if verdict['promote'] else 'VETOED'}**")
    add("")
    add("| Gate condition | Result | Detail |")
    add("|---|---|---|")
    for check in verdict["checks"]:
        add(f"| `{check['id']}` | {'pass' if check['pass'] else '**VETO**'} | {check['detail']} |")
    add("")
    if not verdict["promote"]:
        add(
            "A veto here is the intended outcome of validating first. The headline "
            "below is deliberately two numbers, not one: agreement is only meaningful "
            "next to coverage."
        )
        add("")
    add("### Corroborating evidence from outside the replay")
    add("")
    for note in EXTERNAL_EVIDENCE:
        add(f"- {note}")
    add("")

    add("## Headline — coverage AND agreement, together")
    add("")
    add(
        f"The solver could decide on its own authority at **{_pct(summary['authority_rate'])}** "
        f"of {summary['census_points']} decision points "
        f"({summary['authority_points']} of {summary['census_points']}). "
        f"Across {summary['stage_verdicts']} stage verdicts it was confidently "
        f"admissible on **{summary['confident_admissible']}** "
        f"({_pct(summary['confident_rate'])}), deferred on "
        f"**{summary['deferred_stages']}** ({_pct(summary['defer_rate'])}) and blocked "
        f"**{summary['blocked_stages']}**."
    )
    add("")
    add(
        f"Real disagreements: **{summary['choice_unexplained']} unexplained** "
        f"(of {summary['choice_divergences']} choice divergences; "
        f"{summary['choice_reconstruction_limited']} are attributable to mtime-only "
        "state reconstruction, see below). That number is worthless on its own — a "
        "solver with no justified opinion disagrees with nobody — which is why it is "
        "never quoted apart from the coverage figure above."
    )
    add("")

    add("## Corpus")
    add("")
    add(
        f"- Execution folders scanned: **{summary['runs_scanned']}** (hard cap 100; "
        "ranked pinned → reached `master/master.wav` → ledger size → recency)"
    )
    add(f"- Folders contributing at least one dispatch: **{summary['runs_with_dispatches']}**")
    add(f"- Folders that reached `master/master.wav`: **{summary['runs_reaching_master']}**")
    add(
        f"- Decision points replayed: **{summary['evaluated']}** of "
        f"{summary['decision_points']} recorded"
    )
    add("")
    add(
        "Recency alone selects nothing usable: the ~300 most recently written "
        "`exec_*` folders are all pytest fixtures whose ledger is under 2KB. The "
        "ranking therefore prefers runs that reached a master and runs with the most "
        "recorded history, with `exec_11871` pinned to the front."
    )
    add("")
    add("| Run | Master | Points | Agree | Defer | Skip | Choice | Authority |")
    add("|---|---|---|---|---|---|---|---|")
    for row in summary["runs"]:
        authority = (
            f"{row['authority_points']}/{row['census_points']}"
            if row["census_points"]
            else "n/a"
        )
        add(
            f"| `{row['run_id']}` | {'yes' if row['reached_master'] else 'no'} | "
            f"{row['evaluated']} | {row[AGREE]} | {row[DEFER]} | {row[SKIP]} | "
            f"{row[CHOICE]} | {authority} |"
        )
    add("")

    add("## Deferral census")
    add("")
    add("| Stage verdict | Count | Share |")
    add("|---|---|---|")
    add(
        f"| confidently admissible | {summary['confident_admissible']} | "
        f"{_pct(summary['confident_rate'])} |"
    )
    add(f"| deferred | {summary['deferred_stages']} | {_pct(summary['defer_rate'])} |")
    add(f"| blocked | {summary['blocked_stages']} | |")
    add("")
    add("### Deferral causes, split by whether contract population can fix them")
    add("")
    add("| Bucket | Unknowns | Meaning |")
    add("|---|---|---|")
    buckets = summary["defer_buckets"]
    add(
        f"| `coverage` | {buckets.get('coverage', 0)} | the contract does not yet "
        "declare enough; §4.3 population removes these |"
    )
    add(
        f"| `structural` | {buckets.get('structural', 0)} | gate state that is not on "
        "disk, glob inputs, config-optional gates — population never removes these |"
    )
    if buckets.get("other"):
        add(f"| `other` | {buckets['other']} | unrecognised unknown family |")
    add("")
    add(
        f"Structural share of all stage verdicts: **{_pct(summary['structural_defer_rate'])}**. "
        f"{summary['defer_in_non_strict_group']} deferred verdicts belong to a contract "
        "group that is not yet conformance-strict."
    )
    add("")
    if summary["defer_families"]:
        add("| Unknown family | Bucket | Count |")
        add("|---|---|---|")
        for family, n in summary["defer_families"].items():
            add(f"| `{family}` | `{unknown_bucket(family)}` | {n} |")
        add("")
    if summary["pipeline_census"]:
        add("### Whole-pipeline census (all dispatchable stages, sampled)")
        add("")
        add("| Run | At | Confident | Deferred | Blocked |")
        add("|---|---|---|---|---|")
        for row in summary["pipeline_census"][:20]:
            add(
                f"| `{row['run_id'][:28]}` | {row['at']} | {row['confident_admissible']} | "
                f"{row['deferred']} | {row['blocked']} |"
            )
        add("")

    add("## Divergences — the two classes, never merged")
    add("")
    add("| Class | Meaning | Count |")
    add("|---|---|---|")
    add(f"| `agree` | solver would have dispatched the same stage | {counts[AGREE]} |")
    add(
        f"| `defer` | solver declines to have an opinion (hollow contract, "
        f"indeterminate gate) | {counts[DEFER]} |"
    )
    add(
        f"| **`skip`** | solver proves the dispatched stage was not runnable — it would "
        f"have refused the dispatch. Agreement in spirit. | **{counts[SKIP]}** |"
    )
    add(
        f"| **`choice`** | solver would confidently have run a *different* stage — a "
        f"real disagreement | **{counts[CHOICE]}** |"
    )
    add("")
    add(
        f"Of those {counts[CHOICE]} choice divergences, **{summary['choice_unexplained']}** "
        f"{'is' if summary['choice_unexplained'] == 1 else 'are'} unexplained and "
        f"**{summary['choice_reconstruction_limited']}** name a "
        "preferred stage that produced no `kind=stage` ledger row anywhere in its run. "
        "For that second group the stage's done-timeline rests on the surviving "
        "`.stage_done` marker's mtime, which records the last write rather than the "
        "first, so the replay cannot distinguish a solver preference from a marker "
        "that was written early, invalidated and rewritten late. Both groups are listed."
    )
    add("")
    if summary["skip_families"]:
        add("### Skip divergences by blocker family")
        add("")
        add("| Blocker | Count |")
        add("|---|---|")
        for family, n in summary["skip_families"].items():
            add(f"| `{family}` | {n} |")
        add("")
        add("Examples:")
        add("")
        for row in summary["skip_examples"][:8]:
            add(f"- `{row['stage']}` @ seq {row['seq']} — `{row['reason']}`")
        add("")
    if summary["choice_pairs"]:
        add("### Choice divergences (real disagreements)")
        add("")
        add("| Driver ran | Solver would have run | Count | Evidence |")
        add("|---|---|---|---|")
        evidence: dict[str, str] = {}
        for row in summary["choice_examples"]:
            evidence.setdefault(
                f"{row['stage']} -> {row['solver_choice']}",
                str(row.get("choice_evidence") or ""),
            )
        for pair, n in summary["choice_pairs"].items():
            ran, would = pair.split(" -> ", 1)
            kind = evidence.get(pair, "")
            label = "**unexplained**" if kind == "ledger" else "mtime-only reconstruction"
            add(f"| `{ran}` | `{would}` | {n} | {label} |")
        add("")
        if summary["choice_unexplained_examples"]:
            add("Unexplained, each needing its own account:")
            add("")
            for row in summary["choice_unexplained_examples"]:
                add(
                    f"- `{row['run_id']}` seq {row['seq']} ({row['at']}): driver ran "
                    f"`{row['stage']}`, solver would have run `{row['solver_choice']}`"
                )
            add("")
        traced = {
            stage: note
            for stage, note in KNOWN_DIVERGENCES.items()
            if any(stage in pair for pair in summary["choice_pairs"])
        }
        if traced:
            add("#### Traced to root cause")
            add("")
            add(
                "These accounts are hand-maintained and deliberately do not change the "
                "verdict — an explanation must never be able to promote anything."
            )
            add("")
            for stage, note in sorted(traced.items()):
                add(f"- **`{stage}`** — {note}")
            add("")
    else:
        add("### Choice divergences (real disagreements)")
        add("")
        add(
            "**None.** No decision point produced a confident solver preference for a "
            "stage other than the one the driver dispatched. Read this together with "
            "the coverage figure above, not instead of it."
        )
        add("")

    add("## What this replay cannot prove")
    add("")
    for note in summary["fidelity"]:
        add(f"- {note}")
    add("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline solver replay validation")
    parser.add_argument("--limit", type=int, default=100, help="max folders scanned (cap 100)")
    parser.add_argument("--max-points", type=int, default=0, help="cap decision points per run")
    parser.add_argument("--census-stride", type=int, default=1, help="census every Nth point")
    parser.add_argument("--runs", nargs="*", default=[], help="restrict to run-id prefixes")
    parser.add_argument("--json", default="", help="write the raw summary here")
    parser.add_argument(
        "--markdown",
        default="",
        help="report path (default docs/cross-cutting/solver-replay-validation.md)",
    )
    parser.add_argument("--no-write", action="store_true", help="print only")
    args = parser.parse_args(argv)

    os.environ.setdefault("MUX_SOLVER_SHADOW", "0")
    summary = run_replay(
        limit=min(100, max(1, args.limit)),
        max_points=max(0, args.max_points),
        only=tuple(args.runs),
        census_stride=max(1, args.census_stride),
    )
    counts = summary["counts"]
    print(
        f"runs={summary['runs_with_dispatches']} points={summary['evaluated']} "
        f"agree={counts[AGREE]} defer={counts[DEFER]} skip={counts[SKIP]} "
        f"choice={counts[CHOICE]}"
    )
    print(
        f"authority_rate={_pct(summary['authority_rate'])} "
        f"confident={summary['confident_admissible']} "
        f"deferred={summary['deferred_stages']} blocked={summary['blocked_stages']} "
        f"structural_defer={_pct(summary['structural_defer_rate'])}"
    )
    print(
        f"verdict={'PROMOTE' if summary['verdict']['promote'] else 'VETO'} "
        f"{summary['verdict']['vetoes']}"
    )
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    if not args.no_write:
        dest = Path(args.markdown or (REPO / "docs/cross-cutting/solver-replay-validation.md"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render_markdown(summary), encoding="utf-8")
        print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
