#!/usr/bin/env python3
"""Predict — and then verify — the test blast radius of a guardrail-subtraction wave.

Campaign: `p3-subtract` in `.cursor/plans/solver_brain_020.plan.md` §7 step 4.
Worklist:  `docs/cross-cutting/subtraction-holes.md`.

Why this exists
---------------
Mass guardrail deletion deliberately breaks the repo's "zero net-new failures"
invariant. The replacement invariant is stricter:

    every new test failure must be ATTRIBUTABLE to a specific intentional
    deletion. An unexplained new failure is a bug, not a hole.

Attribution has to be *predictive*, not forensic — you cannot reconstruct why a
test broke after deleting 3,000 lines. So before a wave runs, this tool computes
PREDICTED (every test that could plausibly fail), the wave runs, and the gate is

    ACTUAL_NEW ⊆ PREDICTED

Containment, not equality: PREDICTED is deliberately over-broad, so a predicted
test that keeps passing is fine. A failure *outside* PREDICTED stops the wave.

Three subcommands
-----------------
  orphans   find symbols with no reference anywhere — the wave-0 candidate set
  predict   given a wave's symbols, emit the predicted failing test files
  compare   baseline/after node-id sets -> NEW, FIXED, FLAKE, and the gate verdict

The orphan check is the load-bearing one, and it is deliberately paranoid. An
earlier hand-rolled version of this analysis only looked for references *outside*
the defining module, which reported `stage_acceptance.AcceptanceResult` as dead
code — it is the return type of `stage_acceptance_ok`, the runtime acceptance
contract. Deleting it would have taken out the sufficiency engine on the first
"provably zero blast radius" wave. Hence `--strict`: intra-module references,
string literals, `__all__`, and getattr-style dynamic lookups all count as live.

Four rules this tool encodes, each bought with a wasted wave
-----------------------------------------------------------
1. **A symbol is deletable only if every caller is also being deleted.** Checking
   a symbol in isolation classified half a module as "self-contained" and left
   `NameError`s behind every surviving caller. `_closure_evict` iterates to a
   fixpoint over *all* of `src/`, not just the defining module, because
   references between candidate modules are not free either — only the deleted
   symbols go away, and surviving symbols in those files keep their call sites.

2. **Apply every carve-out BEFORE the closure.** Carving a symbol back to
   "surviving" re-pins everything it calls, so a carve applied afterwards
   silently invalidates the closure. This is why `CARVED_OUT_NAME_RE` and
   `AMBIGUOUS_KEEP_SYMBOLS` live here rather than in a post-processing filter.

3. **Bisect restores cumulatively, against a shim-free base.** Guard chains run
   several links deep and fork, so single-symbol probes all report "still fails"
   and invite the wrong conclusion that no symbol explains the break. Restore
   1, then 1+2, then 1+2+3; the first green gives you the chain depth.

4. **After appending a raising shim, assert the name is absent from the rest of
   the file.** Python's last definition wins, so a shim appended at EOF shadows
   the real symbol and any bisect through it measures the shim, not the restore.
   `_is_subtraction_shim` exists so these tombstones are never recounted as new
   deletable mass — a self-referential error that inflates every later estimate.

Why the campaign closed
-----------------------
Successive corrections to rules 1 and 2 walked the no-rewrite deletable set from
~8,900 lines to 3. That convergence is the finding: the imperative guardrail mass
is **superseded-and-still-wired**, not superseded-and-orphaned. What remains sits
in the EXTERNAL bucket — obsolete by policy, but with live call sites. Removing it
is a caller-rewrite refactor, not a deletion. See `subtraction-holes.md` §12.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
TESTS = REPO / "tests"

# Reference sources beyond `src/`. `tools/full_auto_driver.py` is the full-auto
# forensics campaign driver and calls into the guardrail modules directly; a scan
# that skipped it reported four live driver helpers as dead code. Any directory
# that can import `interview_mux` has to be scanned.
EXTRA_SCAN_ROOTS: tuple[str, ...] = ("tools", "scripts")

# Modules the subtraction campaign is allowed to cut into. Anything outside this
# set is either the replacement (see KEEP_MODULES) or unrelated.
CANDIDATE_MODULES: tuple[str, ...] = (
    "delivery_guardrails",
    "thrash_hardening",
    "heal_routing",
    "artifact_repairs",
    "recovery_controller",
    "stage_acceptance",
    "delivery_invariants",
    "artifact_completeness",
    "stage_input_checks",
    "identical_failures",
    "forensics_stall",
    "remediation_framework",
    "stage_resilience",
    "seed_policy",
    "execution_invalidation_profiles",
    "stage_completion",
    "artifact_lifecycle",
)

# The replacement. A candidate symbol referenced from here is load-bearing: the
# new system calling into the thing it supposedly replaces. Never deletable.
KEEP_MODULES: frozenset[str] = frozenset(
    {
        "solver.py",
        "dispatch_door.py",
        "ship_reachability.py",
        "dispatch_delta.py",
        "defect_ledger.py",
        "contract_conformance.py",
        "master_epoch.py",
        "artifact_ownership.py",
        "stage_contract.py",
        "artifact_dependency_graph.py",
        "write_staging.py",
    }
)

# Class B per subtraction-holes.md §9.2: guards that stop a stage SUCCEEDING ON BAD
# DATA. Their absence yields a well-formed wrong artifact that no detector sees, so
# they are carved out of the campaign. Class A guards — which stop a stage FAILING
# TO RUN — surface as a dispatch refusal, a defect row and a PMQ block, and are
# deletable. The whole `artifact_sanitize` package is content sanitation, hence B.
CARVED_OUT_MODULES: frozenset[str] = frozenset(
    {
        "stage_input_checks",
        "artifact_repairs",
        "artifact_sanitize",
    }
)

# Individual Class B symbols inside otherwise-deletable Class A modules.
CARVED_OUT_SYMBOLS: frozenset[str] = frozenset(
    {
        # waives the authoritative listen-delight ship gate (NORTH_STAR)
        "delivery_guardrails.listen_delight_waived_unattended",
        "delivery_guardrails.ensure_listen_delight_waiver_unattended",
        "delivery_guardrails.listen_delight_quality_waived",
        # VO line ownership drift -> wrong voice on a line, audible, undetected
        "delivery_invariants.sync_vo_line_owners",
    }
)

# Modules that are content/completeness judgement end to end: everything in them
# decides whether data is GOOD, never whether a stage can RUN. Class B wholesale.
CARVED_OUT_HEURISTIC_MODULES: frozenset[str] = frozenset(
    {
        "artifact_completeness",
        "stage_acceptance",
        "artifact_lifecycle",
    }
)

# A symbol whose name says it judges data quality is Class B wherever it lives.
# This ran as a post-hoc filter until it caused the ordering bug described in
# `_closure_evict`; it belongs here, BEFORE the closure, so that carving a symbol
# back to "surviving" re-pins whatever it calls.
CARVED_OUT_NAME_RE = re.compile(
    r"(incompleteness|usable|trivially_empty|acceptable|hollow|unsanitary|drift"
    r"|validator|sanitiz|_gaps?_|gap_rule|compute_gaps|gap_fill|thin|honest"
    r"|complete|coverage|zero_pickup|empty|stale|fingerprint|schema|residual"
    r"|corrupt|boundaries_doc)",
    re.I,
)

# Ambiguous between A and B. Per the campaign rule, ambiguity resolves to KEEP.
AMBIGUOUS_KEEP_SYMBOLS: frozenset[str] = frozenset(
    {
        # discards staged writes: if it is wrong the stage still succeeds, and the
        # loss is silent. Reads as A (unblocks a stage) but fails B's test.
        "thrash_hardening.discard_pending_shadows_for_stage",
        # done-stamping with deferred VO pairs outstanding (exec_5570 family)
        "thrash_hardening.vo_done_with_deferred_pairs_ok",
    }
)

# Raising tombstones left by earlier waves. The symbol is already deleted; the stub
# exists so pinned tests fail on their assertion instead of at collection. It is not
# new deletable mass and must never be counted as such.
SUBTRACTION_SHIM_RE = re.compile(r"removed by p3-subtract", re.I)


def _is_subtraction_shim(sym: "Symbol") -> bool:
    path = SRC / "interview_mux" / f"{sym.module}.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    for node in tree.body:
        if getattr(node, "name", None) != sym.name:
            continue
        return bool(SUBTRACTION_SHIM_RE.search(ast.unparse(node)))
    return False

# Files another agent is writing in this session. Deleting a symbol means deleting
# its call sites, so a symbol referenced from one of these cannot be cut without
# corrupting that worker. Re-check before every wave: the set shrinks as workers
# finish, and deferred symbols become available again.
def worker_owned() -> frozenset[str]:
    raw = os.environ.get("MUX_SUBTRACT_WORKER_OWNED", "")
    if raw.strip():
        return frozenset(p.strip() for p in raw.split(",") if p.strip())
    return frozenset(
        {
            "post_master_quality.py",
            "defect_ledger.py",
            "ship_reachability.py",
            "write_staging.py",
            "artifact_lifecycle.py",
            "pipeline.py",
            "sufficiency_engine.py",
            "artifact_dependency_graph.py",
            "solver.py",
            "agenda.py",
            "artifact_ownership.py",
            "contract_dependency_data.py",
            "bootstrap_stage_contracts.py",
        }
    )


# Pinned-lesson corpus per docs/cross-cutting/contract-migration-test-policy.md.
# Never deleted; left failing on purpose, as the hole map.
PINNED_NAME_RE = re.compile(r"test_(i\d|f\d|h[a-z0-9]*\d|end[a-f])")
PINNED_MARKER = "MUX_FORENSICS"


def _is_pinned(path: Path) -> bool:
    if PINNED_NAME_RE.search(path.name):
        return True
    try:
        return PINNED_MARKER in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


@dataclass
class Symbol:
    module: str
    name: str
    lineno: int
    end_lineno: int
    kind: str

    @property
    def lines(self) -> int:
        return self.end_lineno - self.lineno + 1

    @property
    def qual(self) -> str:
        return f"{self.module}.{self.name}"


def top_level_symbols(module: str) -> list[Symbol]:
    path = SRC / "interview_mux" / f"{module}.py"
    if not path.is_file():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[Symbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(
                Symbol(module, node.name, node.lineno, node.end_lineno or node.lineno, type(node).__name__)
            )
    return out


@dataclass
class Reference:
    """Where a symbol name appears, and whether that reference keeps it alive."""

    same_module_code: int = 0
    other_src_files: set[str] = field(default_factory=set)
    keep_module_files: set[str] = field(default_factory=set)
    test_files: set[str] = field(default_factory=set)
    string_literals: set[str] = field(default_factory=set)
    non_python: set[str] = field(default_factory=set)

    @property
    def live(self) -> bool:
        return bool(
            self.same_module_code
            or self.other_src_files
            or self.test_files
            or self.string_literals
            or self.non_python
        )


def _referenced_names(node: ast.AST) -> set[str]:
    """Every bare name, attribute tail and imported name mentioned under ``node``."""
    used: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            used.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            used.add(sub.attr)
        elif isinstance(sub, ast.ImportFrom):
            used.update(a.name for a in sub.names)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            used.update(re.findall(r"\w+", sub.value))
    return used


def src_symbol_refs() -> list[tuple[str, set[str]]]:
    """(owner, names-it-references) for every top-level symbol across src/.

    Owner is ``module.symbol``, or ``module.<module-level>`` for code outside any
    def/class — registries and constants pin a symbol just as hard as a call does.
    """
    out: list[tuple[str, set[str]]] = []
    for path in sorted((SRC / "interview_mux").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                owner = f"{path.stem}.{node.name}"
            else:
                owner = f"{path.stem}.<module-level>"
            out.append((owner, _referenced_names(node)))
    return out


def _closure_evict(buckets: dict[str, list]) -> list[tuple["Symbol", str]]:
    """Shrink DELETABLE until every member's callers are also being deleted.

    Checking a symbol in isolation is not enough, and neither is checking only its
    own module. Two ways a "self-contained" symbol is actually pinned:

      - a sibling in the same module calls it;
      - a *surviving* symbol in another candidate module calls it, often through a
        function-local import that a file-level reference scan attributes to the
        candidate set and then discounts.

    Both leave live call sites behind. The second is the more dangerous of the two:
    these call sites are usually wrapped in ``except Exception: pass``, so the
    missing symbol does not crash — the guard just silently stops guarding.

    **Every carve-out must be applied before this runs.** A symbol carved back to
    "surviving" re-pins everything it calls, so a carve applied afterwards silently
    invalidates the closure. That is how `stage_resilience.all_pipeline_stage_ids`
    came up DELETABLE while its only caller, `registry_coverage`, was being carved to
    Class B one layer up.
    """
    refs = src_symbol_refs()
    evicted: list[tuple[Symbol, str]] = []
    while True:
        doomed = {f"{s.module}.{s.name}" for s, _ in buckets["DELETABLE"]}
        names = {s.name for s, _ in buckets["DELETABLE"]}
        pinned_by: dict[str, set[str]] = {}
        for owner, used in refs:
            if owner in doomed:
                continue  # caller is being deleted too, so its calls vanish with it
            for name in used & names:
                pinned_by.setdefault(name, set()).add(owner)
        keep = [(s, w) for s, w in buckets["DELETABLE"] if s.name in pinned_by]
        if not keep:
            return evicted
        for s, _ in keep:
            evicted.append(
                (s, "caller kept: " + ", ".join(sorted(pinned_by[s.name])[:3]))
            )
        buckets["DELETABLE"] = [
            (s, w) for s, w in buckets["DELETABLE"] if s.name not in pinned_by
        ]
        buckets["EXTERNAL"].extend(keep)


def intra_module_callers(module: str) -> dict[str, set[str]]:
    """symbol -> set of sibling top-level symbols that reference it.

    A symbol with a sibling caller is only deletable if that caller is being
    deleted too. Checking each symbol in isolation — which an earlier version of
    `plan` did — classifies half a module as "self-contained" and then leaves
    `NameError`s behind every surviving caller.
    """
    path = SRC / "interview_mux" / f"{module}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tops = {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    callers: dict[str, set[str]] = {name: set() for name in tops}
    for owner, node in tops.items():
        used: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                used.add(sub.id)
            elif isinstance(sub, ast.Attribute):
                used.add(sub.attr)
            elif isinstance(sub, ast.arg) and sub.annotation is not None:
                used.update(re.findall(r"\w+", ast.unparse(sub.annotation)))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            used.update(re.findall(r"\w+", ast.unparse(node.returns)))
        for target in used & tops.keys():
            if target != owner:
                callers[target].add(owner)
    # module-level code (constants, registries) referencing a symbol pins it too
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in callers:
                callers[sub.id].add("<module-level>")
            elif isinstance(sub, ast.Attribute) and sub.attr in callers:
                callers[sub.attr].add("<module-level>")
    return callers


def _same_module_code_refs(module: str, name: str) -> int:
    """Count references to `name` inside its own module, excluding its own definition.

    This is the check whose absence nearly deleted `AcceptanceResult`. A symbol
    used only as a type annotation or a return value inside its defining module
    has zero external importers and is still completely alive.
    """
    path = SRC / "interview_mux" / f"{module}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    count = 0
    for node in ast.walk(tree):
        # Skip the symbol's own definition so it does not count as its own user.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            continue
        if isinstance(node, ast.Name) and node.id == name:
            count += 1
        elif isinstance(node, ast.Attribute) and node.attr == name:
            count += 1
        elif isinstance(node, ast.arg) and node.annotation is not None:
            count += len(re.findall(rf"\b{re.escape(name)}\b", ast.unparse(node.annotation)))
    # Annotations on the defining nodes themselves (return types of *other* defs).
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != name:
            if node.returns is not None and re.search(rf"\b{re.escape(name)}\b", ast.unparse(node.returns)):
                count += 1
    return count


def _string_literal_refs(name: str, texts: dict[str, str]) -> set[str]:
    """Symbol names appearing inside string literals — dynamic dispatch, registries."""
    pat = re.compile(rf"['\"]{re.escape(name)}['\"]")
    return {fname for fname, text in texts.items() if pat.search(text)}


def scan_references(symbols: list[Symbol], *, strict: bool = True) -> dict[str, Reference]:
    src_files = _py_files(SRC)
    for extra in EXTRA_SCAN_ROOTS:
        root = REPO / extra
        if root.is_dir():
            src_files.extend(p for p in _py_files(root) if p.name != Path(__file__).name)
    test_files = _py_files(TESTS) if TESTS.is_dir() else []
    cache: dict[Path, str] = {}
    for f in src_files + test_files:
        try:
            cache[f] = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            cache[f] = ""

    # Config/registry files can name a symbol dynamically. Read them once: the
    # naive per-symbol rglob is O(symbols x files) and the repo carries thousands
    # of forensics result JSONs.
    non_python_cache: dict[str, str] = {}
    if strict:
        skip = {"ASSETS", ".git", "node_modules", ".venv", "results"}
        for pattern in ("*.yaml", "*.yml", "*.json", "*.toml", "*.cfg", "*.sh"):
            for p in REPO.rglob(pattern):
                if skip & set(p.parts):
                    continue
                try:
                    non_python_cache[str(p.relative_to(REPO))] = p.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                except OSError:
                    continue

    out: dict[str, Reference] = {}
    for sym in symbols:
        ref = Reference()
        word = re.compile(rf"\b{re.escape(sym.name)}\b")
        own = f"{sym.module}.py"

        if strict:
            ref.same_module_code = _same_module_code_refs(sym.module, sym.name)

        for f in src_files:
            if f.name == own:
                continue
            if word.search(cache[f]):
                ref.other_src_files.add(f.name)
                if f.name in KEEP_MODULES:
                    ref.keep_module_files.add(f.name)

        for f in test_files:
            if word.search(cache[f]):
                ref.test_files.add(str(f.relative_to(REPO)))

        if strict:
            ref.string_literals = _string_literal_refs(
                sym.name, {f.name: cache[f] for f in src_files if f.name != own}
            )
            for rel, text in non_python_cache.items():
                if word.search(text):
                    ref.non_python.add(rel)

        out[sym.qual] = ref
    return out


def cmd_orphans(args: argparse.Namespace) -> int:
    modules = args.modules or list(CANDIDATE_MODULES)
    symbols = [s for m in modules for s in top_level_symbols(m)]
    refs = scan_references(symbols, strict=not args.loose)

    orphans = [s for s in symbols if not refs[s.qual].live]
    load_bearing = [s for s in symbols if refs[s.qual].keep_module_files]

    print(f"scanned {len(symbols)} top-level symbols across {len(modules)} modules")
    print(f"strict mode: {not args.loose} (intra-module + string + non-python references count as live)")
    print()
    print(f"LOAD-BEARING (referenced by the replacement) — {len(load_bearing)} symbols, NEVER delete")
    for s in sorted(load_bearing, key=lambda s: s.qual):
        print(f"  {s.qual:<62}{s.lines:>5}L  <- {','.join(sorted(refs[s.qual].keep_module_files))}")
    print()
    total = sum(s.lines for s in orphans)
    print(f"ORPHANS (no reference anywhere) — {len(orphans)} symbols, {total} lines")
    for s in sorted(orphans, key=lambda s: (s.module, -s.lines)):
        print(f"  {s.qual:<62}{s.lines:>5}L  {s.kind}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "orphans": [
                        {"module": s.module, "name": s.name, "lines": s.lines,
                         "lineno": s.lineno, "end_lineno": s.end_lineno, "kind": s.kind}
                        for s in orphans
                    ],
                    "load_bearing": [
                        {"module": s.module, "name": s.name, "lines": s.lines,
                         "used_by": sorted(refs[s.qual].keep_module_files)}
                        for s in load_bearing
                    ],
                    "total_orphan_lines": total,
                },
                indent=2,
            )
        )
        print(f"\nwrote {args.json}")
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    """PREDICTED = every test file that imports or names a deleted symbol.

    The unit is the *file*, not the test function: deleting a module makes every
    test in an importing file fail at collection, not just the relevant one.
    """
    wave = json.loads(Path(args.wave).read_text())
    names = {e["name"] for e in wave.get("orphans", wave.get("symbols", []))}
    modules = {e["module"] for e in wave.get("orphans", wave.get("symbols", []))}

    predicted: dict[str, list[str]] = {}
    for f in _py_files(TESTS):
        text = f.read_text(encoding="utf-8", errors="ignore")
        hits = [n for n in names if re.search(rf"\b{re.escape(n)}\b", text)]
        imports = [m for m in modules if re.search(rf"interview_mux\.{re.escape(m)}\b", text)]
        if hits or (imports and args.include_module_importers):
            predicted[str(f.relative_to(REPO))] = sorted(set(hits + [f"import:{m}" for m in imports]))

    pinned = {p for p in predicted if _is_pinned(REPO / p)}
    print(f"PREDICTED failing test files: {len(predicted)}  (pinned: {len(pinned)}, scaffolding: {len(predicted) - len(pinned)})")
    for p in sorted(predicted):
        tag = "PINNED     " if p in pinned else "SCAFFOLDING"
        print(f"  {tag} {p}  <- {', '.join(predicted[p])}")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"predicted_files": sorted(predicted), "pinned": sorted(pinned),
                        "reasons": predicted}, indent=2)
        )
        print(f"\nwrote {args.json}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Classify every candidate symbol for a wave on a concurrently-edited tree.

    Five buckets, checked in this order — the first match wins, because each is a
    stronger veto than the one after it:

      LOAD_BEARING  the replacement imports it (§3). Never deletable.
      CARVED        Class B, silent wrong master (§9.2). Never deletable.
      BLOCKED       a worker-owned file calls it. Deleting means editing their
                    file. Defer; re-check next wave.
      EXTERNAL      called from ordinary code outside the candidate set. Deletable
                    only by also editing that caller — out of scope for a pass that
                    must not widen blast radius.
      DELETABLE     every reference is inside the candidate modules themselves.
                    Self-contained; safe to cut as a unit.
    """
    modules = args.modules or list(CANDIDATE_MODULES)
    owned = worker_owned()
    symbols = [s for m in modules for s in top_level_symbols(m)]
    refs = scan_references(symbols, strict=not args.loose)
    candidate_files = {f"{m}.py" for m in CANDIDATE_MODULES}

    buckets: dict[str, list[tuple[Symbol, str]]] = {
        k: [] for k in ("LOAD_BEARING", "CARVED", "BLOCKED", "EXTERNAL", "DELETABLE")
    }
    for s in symbols:
        r = refs[s.qual]
        blockers = sorted(r.other_src_files & owned)
        external = sorted(r.other_src_files - owned - candidate_files)
        if r.keep_module_files:
            buckets["LOAD_BEARING"].append((s, ",".join(sorted(r.keep_module_files))))
        elif s.module in CARVED_OUT_MODULES or s.qual in CARVED_OUT_SYMBOLS:
            buckets["CARVED"].append((s, "Class B — silent wrong master"))
        elif s.module in CARVED_OUT_HEURISTIC_MODULES:
            buckets["CARVED"].append((s, "Class B — data-judgement module"))
        elif CARVED_OUT_NAME_RE.search(s.name):
            buckets["CARVED"].append((s, "Class B — data-judgement name"))
        elif s.qual in AMBIGUOUS_KEEP_SYMBOLS:
            buckets["CARVED"].append((s, "ambiguous A/B — resolves to KEEP"))
        elif _is_subtraction_shim(s):
            buckets["CARVED"].append((s, "subtraction shim — already-deleted tombstone"))
        elif blockers:
            buckets["BLOCKED"].append((s, ",".join(blockers)))
        elif external:
            buckets["EXTERNAL"].append((s, ",".join(external[:4])))
        else:
            buckets["DELETABLE"].append((s, "self-contained"))

    evicted = _closure_evict(buckets)
    if evicted:
        print(
            f"closure pass evicted {len(evicted)} symbols "
            f"({sum(s.lines for s, _ in evicted)} lines) with surviving callers"
        )

    for name in ("LOAD_BEARING", "CARVED", "BLOCKED", "EXTERNAL", "DELETABLE"):
        rows = buckets[name]
        total = sum(s.lines for s, _ in rows)
        print(f"\n{name}: {len(rows)} symbols, {total} lines")
        if name in ("DELETABLE", "BLOCKED") or args.verbose:
            for s, why in sorted(rows, key=lambda r: (r[0].module, -r[0].lines)):
                print(f"  {s.qual:<62}{s.lines:>5}L  {why}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "orphans": [
                        {"module": s.module, "name": s.name, "lines": s.lines,
                         "lineno": s.lineno, "end_lineno": s.end_lineno, "kind": s.kind}
                        for s, _ in buckets["DELETABLE"]
                    ],
                    "deferred": [
                        {"module": s.module, "name": s.name, "lines": s.lines, "blocked_by": why}
                        for s, why in buckets["BLOCKED"]
                    ],
                    "carved": [
                        {"module": s.module, "name": s.name, "lines": s.lines}
                        for s, _ in buckets["CARVED"]
                    ],
                    # The successor work item: obsolete by policy, but with live
                    # call sites. `callers` is what a rewrite has to touch.
                    "external": [
                        {"module": s.module, "name": s.name, "lines": s.lines,
                         "callers": why}
                        for s, why in buckets["EXTERNAL"]
                    ],
                    "load_bearing": [
                        {"module": s.module, "name": s.name, "lines": s.lines,
                         "needed_by": why}
                        for s, why in buckets["LOAD_BEARING"]
                    ],
                },
                indent=2,
            )
        )
        print(f"\nwrote {args.json}")
    return 0


_NODEID = re.compile(r"^(FAILED|ERROR)\s+(\S+)")


def parse_failures(path: Path) -> set[str]:
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = _NODEID.match(line.strip())
        if m:
            out.add(m.group(2).split(" ")[0])
    return out


def cmd_compare(args: argparse.Namespace) -> int:
    """The gate. ACTUAL_NEW must be a subset of PREDICTED."""
    b1 = parse_failures(Path(args.baseline))
    b2 = parse_failures(Path(args.baseline2)) if args.baseline2 else b1
    after = parse_failures(Path(args.after))

    # Anything that disagrees between two identical baseline runs is flaky and is
    # excluded from both sides. The repo's suite is mildly flaky by design note.
    flake = b1 ^ b2
    baseline = (b1 | b2) - flake
    after_stable = after - flake

    new = after_stable - baseline
    fixed = baseline - after_stable

    predicted_files: set[str] = set()
    if args.predicted:
        predicted_files = set(json.loads(Path(args.predicted).read_text())["predicted_files"])

    unexplained = {n for n in new if n.split("::")[0] not in predicted_files} if args.predicted else new

    print(f"baseline failures (stable) : {len(baseline)}")
    print(f"flaky node ids (excluded)  : {len(flake)}")
    print(f"after failures (stable)    : {len(after_stable)}")
    print(f"NEW failures               : {len(new)}")
    print(f"FIXED (no longer failing)  : {len(fixed)}")
    if args.predicted:
        print(f"PREDICTED test files       : {len(predicted_files)}")
        print(f"UNEXPLAINED (NEW - PRED)   : {len(unexplained)}")
    print()
    if new:
        print("NEW failures:")
        for n in sorted(new):
            mark = "  " if n.split("::")[0] in predicted_files else "!!"
            print(f"  {mark} {n}")
    if unexplained:
        print()
        print("GATE FAILED — unexplained new failures are BUGS, not holes.")
        print("Roll the wave back from the snapshot tag and diagnose each one.")
        return 1
    print()
    print("GATE PASSED — ACTUAL_NEW is a subset of PREDICTED.")
    print("Record every NEW failure in docs/cross-cutting/subtraction-holes.md §6.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("orphans", help="find symbols with no reference anywhere (wave-0 candidates)")
    o.add_argument("--modules", nargs="*", help="limit to these modules")
    o.add_argument("--loose", action="store_true",
                   help="DANGEROUS: ignore intra-module/string/non-python refs (reproduces the AcceptanceResult bug)")
    o.add_argument("--json", help="write machine-readable output here")
    o.set_defaults(func=cmd_orphans)

    pl = sub.add_parser("plan", help="classify symbols for a wave on a live tree")
    pl.add_argument("--modules", nargs="*", help="limit to these modules")
    pl.add_argument("--loose", action="store_true", help="DANGEROUS: see `orphans --loose`")
    pl.add_argument("--verbose", action="store_true", help="list every bucket, not just the actionable ones")
    pl.add_argument("--json", help="write machine-readable output here")
    pl.set_defaults(func=cmd_plan)

    p = sub.add_parser("predict", help="predict the failing test set for a wave")
    p.add_argument("wave", help="JSON from `orphans --json`, or {symbols:[{module,name}]}")
    p.add_argument("--include-module-importers", action="store_true",
                   help="also predict files importing an affected module (use for whole-module deletions)")
    p.add_argument("--json", help="write machine-readable output here")
    p.set_defaults(func=cmd_predict)

    c = sub.add_parser("compare", help="gate: ACTUAL_NEW must be a subset of PREDICTED")
    c.add_argument("--baseline", required=True, help="pytest output, run 1")
    c.add_argument("--baseline2", help="pytest output, run 2 (flake detection)")
    c.add_argument("--after", required=True, help="pytest output after the wave")
    c.add_argument("--predicted", help="JSON from `predict --json`")
    c.set_defaults(func=cmd_compare)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
