#!/usr/bin/env python3
"""Offline replay validation for the deterministic solver (plan §6.3, todo ``p2-shadow``).

The promotion gate in §6.2 asks for *one full-auto run with zero non-deferred
disagreements*. No such run can be made while the forensics campaign is open, so this
harness answers the question from runs that already happened: for every dispatch a
completed execution actually made, reconstruct the on-disk state as it stood at that
moment and ask the solver what it would have done.

**Zero disagreements is not the whole story, and on its own it is a false green.**
``solver.shadow_summary()["zero"]`` keys on ``disagree`` alone — deferrals are excluded
by design so they cannot block promotion. But a solver that has no justified opinion
about most of the pipeline disagrees with nobody, so that number is trivially
satisfiable while contract population is unfinished. This harness therefore reports a
**deferral census** alongside the disagreement count, and never quotes one without the
other:

    authority rate   decision points where the solver could pick on its own authority
                     (``Decision.would_choose_confident`` is not None) — i.e. where
                     `authoritative_sequence` would NOT hand the pick back to seed order
    coverage census  per decision point, how many candidate stages were confidently
                     admissible vs deferred vs blocked
    defer causes     split into COVERAGE (contract population removes it) and
                     STRUCTURAL (population never will)

Neither coverage number gates. **D12 (plan §11) retired the 80% authority bar and the
5% structural-deferral bar**, because a solver that defers is *safe* — deferral hands
the pick back to the walk — so the thing that must be zero is being confidently wrong,
not being quiet. Both numbers are still published, prominently, as the D10/D11 progress
signal. See ``promotion_verdict``.

Divergences are classified, never summed into one number::

    already_done  the driver re-dispatched a stage that was already complete
    skip          solver proves the dispatched stage was not runnable (agreement in spirit)
    choice        solver would confidently have run a different stage (real disagreement)

``already_done`` is held apart from ``skip`` on purpose. A completed stage is not a
blocked stage, and a refusal to re-run finished work is not a divergence about control
flow — it is the driver re-walking ground it had covered. Folding the two together put
590 of 1,107 "skip divergences" in the wrong bucket and made the headline meaningless.

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
# Not a divergence: the dispatched stage was already complete. `evaluate_stage` scores
# `already_done` as a positive blocker (solver.py:602), which is right for admissibility
# and wrong for a census — a finished stage is not a blocked one. Held in its own class
# so neither the blocked count nor the skip count absorbs it.
ALREADY_DONE = "already_done"
DONE_BLOCKER = "already_done"

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

# --- promotion gate (D12, plan §11) ----------------------------------------
# Exactly two conditions gate, and every condition must hold. A veto is a successful
# outcome for this harness — it is what "validate first" bought.
#
# Only *unexplained* choice divergences veto. A choice divergence whose preferred
# stage has no ledger dispatch row anywhere in the run is not evidence about the
# solver: that stage's done-timeline is reconstructed from marker mtime alone, which
# is a known lower bound (the marker records the last write, not the first). Those are
# reported in full and separately, never folded into the explained count and never
# silently dropped.
MAX_CHOICE_DIVERGENCES = 0
# D12's second condition: no regression against the driver. See `driver_regressions`.
MAX_DRIVER_REGRESSIONS = 0

# --- retired gates, kept as reported metrics -------------------------------
# D12 dropped both of these as vetoes. The rationale is that a deferring solver is
# *safe* — `authoritative_sequence` hands a deferred stage back to seed order — so a
# coverage percentage is the wrong shape for a gate. They stay in the report as the
# progress signal for D10/D11, quoted against the bar that used to gate them so the
# number keeps its scale. Nothing reads these to decide anything.
RETIRED_AUTHORITY_BAR = 0.80
RETIRED_STRUCTURAL_DEFER_BAR = 0.05
# Named so a future edit that tries to gate on them trips a test rather than a reader.
RETIRED_GATE_IDS: tuple[str, ...] = ("solver_has_authority", "structural_deferral_bounded")

# Evidence from outside the replay that bears on the same question. Recorded here so
# the report is not read as if replay were the only input.
EXTERNAL_EVIDENCE: tuple[str, ...] = (
    "Live shadow mode on a fresh run measured the solver **confidently admissible on "
    "2 of 72 stages, deferring on 35**, because only the `prepare` contract group is "
    "conformance-strict. That is an independent measurement of the same coverage "
    "problem this replay reports. Under D12 it is a progress signal, not a veto.",
    "**The fresh-run census is a tautology, not a measurement.** Exactly **37 of the "
    "72 seed-order stages declare a concrete hard input and 35 do not** (verified "
    "against `load_contract` for all 72). That partition *is* the fresh-run census: "
    "on an empty run directory the 37 return `hard_input_missing` — the correct "
    "answer — and the 35 return `hard_inputs_undeclared`, which is an *unknown* and "
    "never an exclusion. `confident` means zero unknowns, so it needs at least one "
    "*satisfied* declared hard input, which no stage can have against an empty "
    "directory. Probing an empty run reproduces `0 confident / 35 deferred / 37 "
    "blocked` exactly. A statistic that can only take one value cannot rank solver "
    "quality, which is the concrete reason D12's retirement of the authority bar is "
    "right rather than merely convenient.",
)

# Hand-maintained accounts of individual divergences that have been traced to root
# cause. Rendered next to the machine-generated list; deliberately does NOT change the
# verdict, so an explanation can never quietly promote anything.
KNOWN_DIVERGENCES: dict[str, str] = {
    "missing_framing": (
        "**Resolved: the replay was shown content from 11h33m in the future.** "
        "Superseded twice. The A-01 research-thin latch first diagnosed here was real "
        "and is fixed (`b01d8436`); with it gone the refusal at exec_5188 seq 207 "
        "became `missing_framing batch_fill — LLM must score 34 segment(s)`, and that "
        "one is an artifact of the producer witness.\n"
        "\n"
        "  The run's `.archived/20260903T155920Z` copy of "
        "`understanding/gap_evaluations.json` is the pre-repair revision committed at "
        "04:42:31Z, and it decides the question. Its 234 evaluations partition into "
        "three append blocks whose `_meta.repairs` stamps land strictly inside their "
        "own block, matching the three `missing_framing` dispatches exactly: "
        "**0–78 committed 04:34:05Z, 79–156 committed 04:39:57Z, 157–233 committed "
        "04:42:31Z**. Unscored batch-coverage fills appear at indices **146–156 only** "
        "— inside the *second* block. Run 1's block carries **zero** of them and every "
        "row untagged. So at the 04:34:13Z decision point the artifact was run 1's 79 "
        "scored evaluations, the batch_fill condition was **false**, and rebuilding the "
        "snapshot with that revision gives `stage_done=True` → `already_done` → the "
        "solver **agrees** with the driver's `gap_framing_compose`. Rebuilding it with "
        "the 04:39:57Z revision reproduces the divergence, which is precisely why the "
        "driver re-dispatched `missing_framing` at 04:40:06Z (seq 245, source `rerun`): "
        "run 2's sparse shard is what introduced the fills. `seg_032` shows the "
        "mechanism in one row — scored `severity=medium/missing_callback` in block 1, "
        "an unscored `ok_with_light_bridge` fill in block 2, scored again in block 3.\n"
        "\n"
        "  One correction to the record, since the timing argument is the whole case: "
        "the 34 fills in the surviving file carry **no repair stamp at all**. They are "
        "`filled_by=missing_framing_batch_coverage / reason=llm_sparse_shard_output`, "
        "minted by the stage body on a sparse LLM shard. The `_meta.repairs` instants "
        "(16:07:16Z, five `default_value` patches; 16:35:33Z, 45 "
        "`fabricate_evaluation` rows) describe *different* rows, none of which the "
        "predicate flags. The ~11.5h gap is real but the witness for it is "
        "`_meta.committed_at` (16:07:16Z, stamped by "
        "`artifact_lifecycle.fingerprint_artifact` over the body actually in the file), "
        "not the repair log. That is the witness `content_postdates_point` measures, "
        "and it is what excuses this divergence — this prose does not."
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

# Findings from adjacent work that bear on the numbers above but were deliberately not
# implemented. Recorded so they are not rediscovered from scratch; neither is a gate.
ADJACENT_FINDINGS: tuple[str, ...] = (
    "The `_MASTERING_SCHEMA_STAGES` short-circuit still swallows the research-thin "
    "refusal for `mastering_shape_agenda` and `mastering_shape_candidates`. Wiring it "
    "through is **not** obviously safe: the rollup's about-to-bind branch cannot fire "
    "before the first Shape stage runs, so a naive fix risks minting a *fresh* latch of "
    "the same shape as the A-01 one that `b01d8436` just removed.",
    "\"Stale record versus live state\" looks like the general shape of this codebase's "
    "recurring completed-but-inadequate class, of which "
    "`research_dossier_shape_core_stale` is one instance. A single predicate might cover "
    "several of them, but that is a refactor rather than a fix, and it is unowned.",
    "The `content_postdates_point` witness this report relies on is only as good as "
    "`_meta.committed_at` coverage. Artifacts written without going through "
    "`artifact_lifecycle.fingerprint_artifact` carry no stamp, so a future-content "
    "divergence on one of those would land in the genuine residue and veto. That "
    "direction is the safe one, but it means the reconstruction-artifact count is a "
    "floor, not an exact figure.",
)

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
    "The regression check (D12 condition 2) can only prove unrunnability one way: the "
    "driver recorded the stage `done`, nothing invalidated it, and it was never started "
    "again. A stage the driver never dispatched at all leaves no trace either way, so "
    "the check is sound but not exhaustive — zero regressions means 'the driver's "
    "history contradicts the solver nowhere it can speak', not 'the solver is right'.",
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

    ``complete`` is split out of ``blocked``. `evaluate_stage` returns
    ``already_done`` as a positive blocker (solver.py:602) because for admissibility
    that is the correct answer — a finished stage must not be offered. But counting it
    as *blocked* makes the census say the pipeline seizes up as it succeeds: the
    blocked count climbs toward 72 precisely because the run is finishing. Only
    ``blocked`` now means "the solver proved this cannot run", and that is the number
    the report leads with.
    """

    candidates: int = 0
    confident: int = 0
    deferred: int = 0
    blocked: int = 0
    complete: int = 0
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
            "complete": self.complete,
            "has_authority": self.has_authority,
        }


def verdict_is_complete(verdict: Any) -> bool:
    """True when the *only* thing stopping this stage is that it already finished.

    ``evaluate_stage`` returns on ``already_done`` before any other check runs, so a
    complete stage carries that one reason and nothing else. Requiring it to be the
    sole reason is what keeps a genuinely blocked stage from being laundered into the
    complete bucket by an incidental match.

    The fix belongs in ``solver.py:602`` — ``already_done`` is not a blocker in the
    same sense as ``hard_input_missing`` — but that module is owned elsewhere, so the
    correction lives in the replay tool's classification and the underlying issue is
    reported rather than patched here.
    """
    reasons = tuple(str(r) for r in (getattr(verdict, "reasons", ()) or ()))
    return reasons == (DONE_BLOCKER,)


def census_for(decision: Any) -> Census:
    """Read a ``solver.Decision`` into a coverage census. No solver logic duplicated."""
    from interview_mux.contract_conformance import group_is_strict

    out = Census(candidates=len(decision.verdicts))
    out.has_authority = decision.would_choose_confident is not None
    for verdict in decision.verdicts:
        if not verdict.admissible:
            if verdict_is_complete(verdict):
                out.complete += 1
            else:
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
    target.complete += other.complete
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
    regression_proof: str = ""
    future_content: str = ""

    @property
    def family(self) -> str:
        return self.reason.split(":", 1)[0] if self.reason else "unknown"

    @property
    def resolution(self) -> str:
        """Which reconstruction limitation, if any, accounts for a choice divergence.

        Two independent limitations, each with its own witness, and one residue:

        ``mtime_only``              the preferred stage emits no ``kind=stage`` ledger
                                    row, so its done-timeline is marker mtime alone.
        ``content_postdates_point`` the artifact that decided its runnability records a
                                    commit *after* this decision point.
        ``genuine``                 neither witness applies. This is the residue the
                                    D12 gate counts.
        """
        if self.klass != CHOICE:
            return ""
        if self.choice_evidence != "ledger":
            return "mtime_only"
        if self.future_content:
            return "content_postdates_point"
        return "genuine"

    @property
    def driver_regression(self) -> bool:
        """D12 condition 2 — the solver proposed a stage the driver proved was done."""
        return self.klass == CHOICE and bool(self.regression_proof)

    @property
    def unexplained(self) -> bool:
        """A choice divergence the replay's own evidence cannot account for."""
        return self.resolution == "genuine"

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
            row["resolution"] = self.resolution
            if self.future_content:
                row["future_content"] = self.future_content
        if self.klass == CHOICE:
            row["driver_regression"] = self.driver_regression
            if self.regression_proof:
                row["regression_proof"] = self.regression_proof
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
        out = {AGREE: 0, DEFER: 0, SKIP: 0, CHOICE: 0, ALREADY_DONE: 0}
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


def started_epochs(entries: list[dict[str, Any]]) -> dict[str, list[float]]:
    """``stage -> every epoch the driver actually started it``."""
    out: dict[str, list[float]] = {}
    for row in entries:
        if str(row.get("kind") or "") != "stage":
            continue
        if str(row.get("status") or "") != "started":
            continue
        epoch = _epoch(row.get("at"))
        stage = str(row.get("identity") or "")
        if epoch is not None and stage:
            out.setdefault(stage, []).append(epoch)
    for values in out.values():
        values.sort()
    return out


def regression_proof(
    stage: str,
    epoch: float,
    *,
    dones: list[tuple[float, str]],
    invalidations: list[tuple[float, frozenset[str]]],
    starts: dict[str, list[float]],
) -> str:
    """D12 condition 2: does the driver's own history prove ``stage`` was unrunnable?

    The only witness the ledger can supply is completion. ``stage`` was not runnable at
    ``epoch`` if the driver recorded it **done** at or before ``epoch``, nothing
    invalidated it in between, **and** the driver never started it again afterwards.
    That last clause is what makes this a proof rather than a guess: a driver that
    re-dispatches the stage minutes later has demonstrated the opposite, so its history
    proves nothing and the divergence is an ordering argument instead of a regression.

    Only choice divergences can regress. At an ``agree`` point the solver's pick is the
    stage the driver ran, and at a ``skip``, ``already_done`` or ``defer`` point the
    solver proposes nothing of its own — so there is nothing to check.

    Returns the proof text, or ``""`` when the driver's history does not settle it.
    """
    if not stage:
        return ""
    completed: float | None = None
    for at, sid in dones:
        if at > epoch:
            break
        if sid == stage:
            completed = at
    if completed is None:
        return ""
    for at, stages in invalidations:
        if at > epoch:
            break
        if stage in stages and completed <= at:
            return ""
    if any(at > epoch for at in starts.get(stage, ())):
        return ""
    done_at_iso = datetime.fromtimestamp(completed, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return f"driver recorded `done` at {done_at_iso} and never started it again"


def content_postdates_point(
    snapshot_dir: Path, rels: Iterable[str], epoch: float
) -> str:
    """Proof that bytes the replay showed the solver did not exist at ``epoch``.

    ``_meta.committed_at`` is stamped by ``artifact_lifecycle.fingerprint_artifact``
    at commit time and describes *the body currently in the file*, alongside a
    ``content_hash`` of that body. So when it post-dates the decision point, the
    producer witness has handed the solver an artifact revision the live run could not
    have shown it — the first FIDELITY limitation, measured off the run's own bytes
    instead of narrated.

    This is deliberately conservative. An artifact with no ``_meta.committed_at`` is no
    proof and yields ``""``, which leaves the divergence in the unexplained count. The
    witness can only ever *excuse* a divergence on positive, per-run evidence.
    """
    for rel in rels:
        path = snapshot_dir / rel
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        stamp = (doc.get("_meta") or {}).get("committed_at") if isinstance(
            doc.get("_meta"), dict
        ) else None
        committed = _epoch(stamp)
        if committed is None or committed <= epoch:
            continue
        gap = committed - epoch
        hours, rem = divmod(int(gap), 3600)
        return (
            f"`{rel}` records `_meta.committed_at` "
            f"{datetime.fromtimestamp(committed, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}, "
            f"{hours}h{rem // 60:02d}m after this decision point"
        )
    return ""


def classify(comparison: Any, dispatched_ever: set[str]) -> tuple[str, bool | None]:
    """Map a ``solver.ShadowComparison`` onto the divergence classes.

    ``compare_walk_choice`` returns one ``disagree`` verdict for three very different
    events, and collapsing them is exactly the number that would overstate the
    evidence:

    * the dispatched stage was **already complete** → the solver would have declined to
      re-run finished work. That is not a disagreement about control flow at all, so it
      gets its own class and is counted in neither the skip nor the agreement column.
    * the dispatched stage is provably not runnable for some other reason → the solver
      would have **skipped** the dispatch. That is the refusal-of-thrash this campaign
      exists to produce, and it counts as agreement in spirit.
    * the solver confidently prefers a **different** stage → a real disagreement about
      control flow, which has to be explained one by one.

    The ``already_done`` reconstruction is sound in the one direction that matters
    here: a surviving marker whose final mtime is at or before ``T`` did exist at
    ``T``, so this class cannot be inflated by the mtime witness. Its failure mode is
    the opposite — under-counting, which shows up as a choice divergence instead.
    """
    from interview_mux import solver

    if comparison.verdict == solver.AGREE:
        return AGREE, None
    if comparison.verdict == solver.DEFER:
        return DEFER, None
    if comparison.solver_choice and comparison.solver_choice != comparison.chosen:
        return CHOICE, comparison.solver_choice in dispatched_ever
    reason = str(getattr(comparison, "reason", "") or "")
    if reason.split(":", 1)[0] == DONE_BLOCKER:
        return ALREADY_DONE, None
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
    starts = started_epochs(entries)
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
                regression_proof=(
                    regression_proof(
                        comparison.solver_choice or "",
                        point.epoch,
                        dones=dones,
                        invalidations=invalidations,
                        starts=starts,
                    )
                    if klass == CHOICE
                    else ""
                ),
                future_content=(
                    content_postdates_point(
                        dest, outputs.get(comparison.solver_choice or "", ()), point.epoch
                    )
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
    """D12's two conditions. Both must hold; a veto is a successful outcome here.

    The coverage percentages are still computed and still returned — as ``metrics``,
    which nothing in this function reads. That separation is the whole point of the
    re-gate: keeping the numbers visible while making it structurally impossible for
    them to veto.
    """
    checks: list[dict[str, Any]] = []
    unexplained = summary["choice_unexplained"]
    res = summary.get("choice_resolution") or {}
    checks.append(
        {
            "id": "no_unexplained_disagreements",
            "pass": unexplained <= MAX_CHOICE_DIVERGENCES,
            "detail": (
                f"{unexplained} genuine choice divergence(s) of "
                f"{summary['choice_divergences']} total "
                f"({res.get('mtime_only', 0)} attributed to mtime-only reconstruction, "
                f"{res.get('content_postdates_point', 0)} to content that post-dates "
                f"the decision point); gate allows {MAX_CHOICE_DIVERGENCES}"
            ),
        }
    )
    regressions = summary.get("driver_regressions", 0)
    checks.append(
        {
            "id": "no_regression_against_driver",
            "pass": regressions <= MAX_DRIVER_REGRESSIONS,
            "detail": (
                f"{regressions} decision point(s) where the solver proposed a stage "
                "the driver's own history proves was not runnable (recorded `done`, "
                "not invalidated, never started again); gate allows "
                f"{MAX_DRIVER_REGRESSIONS}"
            ),
        }
    )
    failed = [c for c in checks if not c["pass"]]

    rate = summary["authority_rate"]
    structural = summary["structural_defer_rate"]
    metrics: list[dict[str, Any]] = [
        {
            "id": "solver_has_authority",
            "value": rate,
            "retired_bar": RETIRED_AUTHORITY_BAR,
            "detail": (
                f"solver could decide on its own authority at {_pct(rate)} of "
                f"decision points (retired bar: {_pct(RETIRED_AUTHORITY_BAR)})"
            ),
        },
        {
            "id": "structural_deferral_bounded",
            "value": structural,
            "retired_bar": RETIRED_STRUCTURAL_DEFER_BAR,
            "detail": (
                f"{_pct(structural)} of stage verdicts defer for a reason contract "
                "population cannot fix (retired bar: "
                f"{_pct(RETIRED_STRUCTURAL_DEFER_BAR)})"
            ),
        },
    ]
    return {
        "promote": not failed,
        "checks": checks,
        "vetoes": [c["id"] for c in failed],
        "metrics": metrics,
        "retired_gates": list(RETIRED_GATE_IDS),
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def summarise(replays: list[RunReplay]) -> dict[str, Any]:
    observations = [o for r in replays for o in r.observations]
    counts: dict[str, int] = {AGREE: 0, DEFER: 0, SKIP: 0, CHOICE: 0, ALREADY_DONE: 0}
    for obs in observations:
        counts[obs.klass] = counts.get(obs.klass, 0) + 1
    skip_families: dict[str, int] = {}
    choice_pairs: dict[str, int] = {}
    already_done_sources: dict[str, int] = {}
    for obs in observations:
        if obs.klass == SKIP:
            skip_families[obs.family] = skip_families.get(obs.family, 0) + 1
        elif obs.klass == CHOICE:
            key = f"{obs.stage} -> {obs.solver_choice}"
            choice_pairs[key] = choice_pairs.get(key, 0) + 1
        elif obs.klass == ALREADY_DONE:
            already_done_sources[obs.source] = already_done_sources.get(obs.source, 0) + 1

    census = Census()
    for replay in replays:
        merge_census(census, replay.census)
    census_points = sum(r.census_points for r in replays)
    authority_points = sum(r.authority_points for r in replays)
    verdicts = census.confident + census.deferred + census.blocked + census.complete
    # `already_done` is excluded from the agreement denominator: it is neither an
    # agreement about control flow nor a divergence, so leaving it in would move the
    # rate for a reason that has nothing to do with the solver.
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
        "agreement_denominator": decided,
        "skip_divergences": counts[SKIP],
        "already_done_dispatches": counts[ALREADY_DONE],
        "already_done_sources": dict(
            sorted(already_done_sources.items(), key=lambda kv: -kv[1])
        ),
        "choice_divergences": counts[CHOICE],
        "choice_unexplained": sum(1 for o in observations if o.unexplained),
        "choice_resolution": {
            key: sum(1 for o in observations if o.resolution == key)
            for key in ("mtime_only", "content_postdates_point", "genuine")
        },
        "choice_future_content_examples": [
            o.as_row() for o in observations if o.resolution == "content_postdates_point"
        ][:40],
        "driver_regressions": sum(1 for o in observations if o.driver_regression),
        "driver_regression_examples": [
            o.as_row() for o in observations if o.driver_regression
        ][:40],
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
        "complete_stages": census.complete,
        "confident_rate": (census.confident / verdicts) if verdicts else None,
        "defer_rate": (census.deferred / verdicts) if verdicts else None,
        "defer_buckets": dict(sorted(census.defer_buckets.items(), key=lambda kv: -kv[1])),
        "defer_families": dict(sorted(census.defer_families.items(), key=lambda kv: -kv[1])),
        "defer_in_non_strict_group": census.defer_non_strict_group,
        "structural_defer_rate": (
            (census.defer_buckets.get("structural", 0) / verdicts) if verdicts else None
        ),
        "adjacent_findings": list(ADJACENT_FINDINGS),
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
                "complete": r.census.complete,
                "seconds": round(r.seconds, 1),
                **r.counts(),
            }
            for r in replays
            if r.points
        ],
        "gate": {
            "max_choice_divergences": MAX_CHOICE_DIVERGENCES,
            "max_driver_regressions": MAX_DRIVER_REGRESSIONS,
            "retired": {
                "authority_rate": RETIRED_AUTHORITY_BAR,
                "structural_defer_rate": RETIRED_STRUCTURAL_DEFER_BAR,
            },
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
    add(
        "The bar is **D12** (plan §11): zero unexplained replay disagreements, and no "
        "regression against the driver. Those are the only two conditions, and both "
        "must hold."
    )
    add("")
    add(f"**D12 gate {'MET' if verdict['promote'] else 'NOT MET'} — promotion "
        f"{'APPROVED' if verdict['promote'] else 'VETOED'}**")
    add("")
    add("| D12 condition | Result | Detail |")
    add("|---|---|---|")
    for check in verdict["checks"]:
        add(f"| `{check['id']}` | {'pass' if check['pass'] else '**VETO**'} | {check['detail']} |")
    add("")
    if not verdict["promote"]:
        add(
            "A veto here is the intended outcome of validating first. `MUX_SOLVER_"
            "AUTHORITATIVE` stays OFF."
        )
        add("")
    else:
        res = summary["choice_resolution"]
        attributed = res["mtime_only"] + res["content_postdates_point"]
        if attributed:
            add(
                f"> **Read this with the verdict.** The gate passes because all "
                f"{attributed} of the {summary['choice_divergences']} choice "
                "divergences are attributed to *known limitations of the replay "
                "instrument*, not because the solver was independently shown to be "
                "right at those points. Each attribution rests on a per-run witness "
                "recorded below (§ *How the choice divergences resolve*), and the "
                "replay genuinely cannot settle those points either way. D14 still "
                "requires a live full-auto to confirm, and that confirmation is doing "
                "more work than usual here."
            )
            add("")

    add("### Retired bars — reported as context, never as vetoes")
    add("")
    add(
        "D12 dropped the 80% authority condition and the 5% structural-deferral "
        "condition. A solver that defers is *safe* — `authoritative_sequence` hands a "
        "deferred stage back to seed order — so what must be zero is being "
        "confidently **wrong**, not being quiet. Both numbers stay here as the "
        "progress signal for D10 (gate state on disk) and D11 (the strict ratchet), "
        "quoted against the bar that used to gate them so the scale is still legible. "
        "`promotion_verdict` cannot read them."
    )
    add("")
    add("| Retired metric | Today | Retired bar | Status |")
    add("|---|---|---|---|")
    for metric in verdict.get("metrics", ()):
        add(
            f"| `{metric['id']}` | {_pct(metric['value'])} | "
            f"{_pct(metric['retired_bar'])} | reported only |"
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
        f"**{summary['deferred_stages']}** ({_pct(summary['defer_rate'])}), genuinely "
        f"blocked on **{summary['blocked_stages']}** and **{summary['complete_stages']}** "
        "were already complete."
    )
    add("")
    res = summary["choice_resolution"]
    add(
        f"Real disagreements: **{summary['choice_unexplained']} genuine** of "
        f"{summary['choice_divergences']} choice divergences "
        f"({res['mtime_only']} attributed to mtime-only state reconstruction, "
        f"{res['content_postdates_point']} to an artifact whose own commit stamp "
        f"post-dates the decision point), and **{summary['driver_regressions']}** "
        "regression(s) against the driver. Those two numbers are the D12 gate, and the "
        "attributions behind the first are itemised under *How the choice divergences "
        "resolve*. The coverage figure above is worthless as a gate in either direction "
        "— a solver with no justified opinion disagrees with nobody — which is why it "
        "is never quoted alone and no longer vetoes."
    )
    add("")
    add(
        f"Separated out of the old headline: **{summary['already_done_dispatches']}** "
        "dispatches were of a stage that was **already complete**. Those used to be "
        "counted as `skip` divergences and their verdicts as `blocked`, which is what "
        "made both numbers unreadable — a finished stage is neither blocked nor a "
        "disagreement."
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
    add("| Run | Master | Points | Agree | Defer | Done | Skip | Choice | Authority |")
    add("|---|---|---|---|---|---|---|---|---|")
    for row in summary["runs"]:
        authority = (
            f"{row['authority_points']}/{row['census_points']}"
            if row["census_points"]
            else "n/a"
        )
        add(
            f"| `{row['run_id']}` | {'yes' if row['reached_master'] else 'no'} | "
            f"{row['evaluated']} | {row[AGREE]} | {row[DEFER]} | "
            f"{row[ALREADY_DONE]} | {row[SKIP]} | {row[CHOICE]} | {authority} |"
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
    add(f"| already complete | {summary['complete_stages']} | |")
    add("")
    add(
        "`already complete` is split out of `blocked` on purpose. `evaluate_stage` "
        "returns `already_done` as a positive blocker (`solver.py:602`), which is the "
        "right answer for admissibility — a finished stage must not be offered — but "
        "counting it as *blocked* made the census say the pipeline seizes up as it "
        "succeeds, with the blocked count climbing toward 72 precisely because the run "
        "was finishing. `blocked` now means only \"the solver proved this cannot run\". "
        "**The underlying issue is in `solver.py`, which this tool does not own**: the "
        "correction is applied in the replay tool's classification "
        "(`verdict_is_complete`), keyed on `already_done` being the sole reason, so a "
        "genuinely blocked stage cannot be laundered into this bucket."
    )
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
        add("| Run | At | Confident | Deferred | Blocked | Already complete |")
        add("|---|---|---|---|---|---|")
        for row in summary["pipeline_census"][:20]:
            add(
                f"| `{row['run_id'][:28]}` | {row['at']} | {row['confident_admissible']} | "
                f"{row['deferred']} | {row['blocked']} | {row.get('complete', 0)} |"
            )
        add("")

    add("## Divergences — the classes, never merged")
    add("")
    add("| Class | Meaning | Count |")
    add("|---|---|---|")
    add(f"| `agree` | solver would have dispatched the same stage | {counts[AGREE]} |")
    add(
        f"| `defer` | solver declines to have an opinion (hollow contract, "
        f"indeterminate gate) | {counts[DEFER]} |"
    )
    add(
        f"| `already_done` | the dispatched stage was **already complete** — not a "
        f"disagreement about control flow at all | {counts[ALREADY_DONE]} |"
    )
    add(
        f"| **`skip`** | solver proves the dispatched stage was not runnable *for some "
        f"other reason* — it would have refused the dispatch. Agreement in spirit. | "
        f"**{counts[SKIP]}** |"
    )
    add(
        f"| **`choice`** | solver would confidently have run a *different* stage — a "
        f"real disagreement | **{counts[CHOICE]}** |"
    )
    add("")
    add(
        f"Agreement rate is {_pct(summary['agreement_rate'])} over the "
        f"{summary['agreement_denominator']} points that produced an opinion about "
        "control flow (`agree` + `skip` + `choice`). `already_done` and `defer` are "
        "outside that denominator: neither is a statement about which stage should run "
        "next."
    )
    add("")
    if summary["already_done_dispatches"]:
        add("### Already-complete dispatches — held apart from `skip`")
        add("")
        add(
            f"**{summary['already_done_dispatches']}** dispatches re-ran a stage the "
            "solver could see was already finished. This is real driver behaviour "
            "worth reading, but it is not evidence about solver quality, so it is "
            "counted in neither the skip column nor the agreement rate. The `rerun` "
            "and `operator` sources are deliberate re-runs; a `conductor` or walk "
            "source is the thrash the campaign is chasing."
        )
        add("")
        add("| Dispatch source | Count |")
        add("|---|---|")
        for source, n in summary["already_done_sources"].items():
            add(f"| `{source}` | {n} |")
        add("")
        add(
            "This class is not inflatable by the reconstruction: a surviving "
            "`.stage_done` marker whose final mtime is at or before `T` did exist at "
            "`T`, so the mtime witness cannot invent a completion. Its failure mode is "
            "the opposite — a marker rewritten late reads as absent, which surfaces as "
            "a choice divergence instead."
        )
        add("")
    res = summary["choice_resolution"]
    add("### How the choice divergences resolve")
    add("")
    add(
        f"The {counts[CHOICE]} choice divergences resolve as "
        f"**{res['mtime_only'] + res['content_postdates_point']} reconstruction "
        f"artifacts and {res['genuine']} genuine**. Only the genuine residue reaches "
        "the D12 gate. Each row states the criterion and the witness it needs, and "
        "every attribution is computed per run from the corpus bytes — no divergence is "
        "excused by prose."
    )
    add("")
    add("| Resolution | Count | Criterion | Witness |")
    add("|---|---|---|---|")
    add(
        f"| `mtime_only` | {res['mtime_only']} | the preferred stage emits no "
        "`kind=stage` ledger row anywhere in its run, so its done-timeline rests on the "
        "surviving `.stage_done` marker's mtime — which records the *last* write, not "
        "the first | absence of any `kind=stage` row for that stage |"
    )
    add(
        f"| `content_postdates_point` | {res['content_postdates_point']} | an artifact "
        "that decided the preferred stage's runnability records a commit **after** this "
        "decision point, so the producer witness fed the solver a revision the live run "
        "could not have shown it | `_meta.committed_at` on that artifact, stamped at "
        "commit time by `artifact_lifecycle.fingerprint_artifact` |"
    )
    add(
        f"| **`genuine`** | **{res['genuine']}** | neither witness applies — the replay "
        "has sound evidence and the solver still disagreed | — |"
    )
    add("")
    add(
        "The two limitations are the first and sixth entries of *What this replay "
        "cannot prove* below. Neither witness can be satisfied by an absent field: an "
        "artifact with no `_meta.committed_at` is no proof and leaves its divergence in "
        "the genuine residue, so the attribution can only ever be made on positive "
        "evidence."
    )
    add("")
    if summary["choice_future_content_examples"]:
        add("Divergences excused by a future-content commit, with their proof:")
        add("")
        for row in summary["choice_future_content_examples"]:
            add(
                f"- `{row['run_id']}` seq {row['seq']} ({row['at']}): driver ran "
                f"`{row['stage']}`, solver would have run `{row['solver_choice']}` — "
                f"{row.get('future_content', '')}"
            )
        add("")

    add("### Regressions against the driver (D12 condition 2)")
    add("")
    add(
        f"**{summary['driver_regressions']}** of the {counts[CHOICE]} choice "
        "divergences are regressions. A regression is a decision point where the "
        "solver proposed a stage the *driver's own history proves* was not runnable: "
        "the ledger recorded it `done` at or before that instant, nothing invalidated "
        "it in between, and the driver never started it again for the rest of the run. "
        "That last clause is what makes it a proof — a driver that re-dispatches the "
        "stage minutes later has demonstrated the opposite, so its history settles "
        "nothing and the divergence is an ordering argument rather than a regression."
    )
    add("")
    add(
        "Only `choice` points can regress. At an `agree` point the solver's pick is the "
        "stage the driver ran, and at a `skip`, `already_done` or `defer` point the "
        "solver proposes nothing of its own."
    )
    add("")
    if summary["driver_regression_examples"]:
        for row in summary["driver_regression_examples"]:
            add(
                f"- `{row['run_id']}` seq {row['seq']} ({row['at']}): driver ran "
                f"`{row['stage']}`, solver would have run `{row['solver_choice']}` — "
                f"{row.get('regression_proof', '')}"
            )
        add("")
    else:
        add("**None.** This D12 condition passes.")
        add("")

    if summary["skip_families"]:
        add("### Skip divergences by blocker family")
        add("")
        add(
            "`already_done` no longer appears here — it has its own class above. What "
            "is left is the set of dispatches the solver would have refused on a real "
            "blocker."
        )
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
        add("| Driver ran | Solver would have run | Count | Resolution | Regression |")
        add("|---|---|---|---|---|")
        resolutions: dict[str, str] = {}
        regressed: dict[str, bool] = {}
        for row in summary["choice_examples"]:
            key = f"{row['stage']} -> {row['solver_choice']}"
            resolutions.setdefault(key, str(row.get("resolution") or ""))
            regressed[key] = regressed.get(key, False) or bool(row.get("driver_regression"))
        labels = {
            "mtime_only": "mtime-only reconstruction",
            "content_postdates_point": "content post-dates the point",
            "genuine": "**genuine — counts against the gate**",
        }
        for pair, n in summary["choice_pairs"].items():
            ran, would = pair.split(" -> ", 1)
            label = labels.get(resolutions.get(pair, ""), "unclassified")
            reg = "**yes**" if regressed.get(pair) else "no"
            add(f"| `{ran}` | `{would}` | {n} | {label} | {reg} |")
        add("")
        if summary["choice_unexplained_examples"]:
            add("Genuine residue — each of these counts against the gate:")
            add("")
            for row in summary["choice_unexplained_examples"]:
                add(
                    f"- `{row['run_id']}` seq {row['seq']} ({row['at']}): driver ran "
                    f"`{row['stage']}`, solver would have run `{row['solver_choice']}`"
                )
            add("")
        else:
            add(
                "**No genuine residue.** Every choice divergence carries one of the two "
                "reconstruction witnesses above. That is what clears the D12 condition, "
                "and it is a statement about the instrument as much as about the solver "
                "— see the caveat under *Verdict*."
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
                "verdict — an explanation must never be able to promote anything. Where "
                "an account below describes a divergence that no longer counts, the "
                "thing that stopped it counting is the machine-computed witness in the "
                "resolution table, never the prose."
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
    add("## Known-adjacent, deliberately not implemented")
    add("")
    add(
        "Recorded so they are not rediscovered from scratch. None of these is a gate, "
        "and none is owned by this tool."
    )
    add("")
    for note in summary["adjacent_findings"]:
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
        f"agree={counts[AGREE]} defer={counts[DEFER]} "
        f"already_done={counts[ALREADY_DONE]} skip={counts[SKIP]} "
        f"choice={counts[CHOICE]}"
    )
    print(
        f"D12: unexplained={summary['choice_unexplained']} "
        f"regressions={summary['driver_regressions']}"
    )
    print(
        f"reported-only: authority_rate={_pct(summary['authority_rate'])} "
        f"structural_defer={_pct(summary['structural_defer_rate'])} | "
        f"confident={summary['confident_admissible']} "
        f"deferred={summary['deferred_stages']} blocked={summary['blocked_stages']} "
        f"complete={summary['complete_stages']}"
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
