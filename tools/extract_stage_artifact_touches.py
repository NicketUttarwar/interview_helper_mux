#!/usr/bin/env python3
"""Static evidence for contract population: which artifacts does a stage touch?

Plan `.cursor/plans/solver_brain_020.plan.md` §4.3 ranks sources of dependency
truth as: the runtime conformance recorder (`contract_conformance`), then
`_PROPAGATION_SEEDS`, then the heal-pin tables. This tool is the *static* rung
below all of those — it AST-walks a stage entrypoint module plus the local
modules it imports and reports every literal artifact path passed to a `ctx`
read/write helper.

It is an evidence generator for a human populating `docs/cross-cutting/
stage-contracts/*.yaml`, not an authority: it cannot see paths built at runtime
and it over-reports (a helper module is shared by several stages). Supersedes
the crude `docs/cross-cutting/stage-contracts/_extracted_deps.json`.

    python tools/extract_stage_artifact_touches.py ingest transcribe
    python tools/extract_stage_artifact_touches.py --group prepare
    python tools/extract_stage_artifact_touches.py --group build --call-depth 3

Three things it does beyond matching string literals, because without them the
delivery groups report nothing useful:

* **Module constants are resolved.** `mastering_shape_runtime` reads
  `ctx.read_json(AGENDA_REL)`, never the literal, so a literal-only walk saw
  zero reads for all three Shape stages.
* **f-strings collapse to a glob.** `f"{RESEARCH_DIR}/{field_id}.json"` becomes
  `mastering/research/*.json`, which is the shape a contract output family
  declares anyway.
* **Calls follow into other `interview_mux` modules** (`--call-depth`, default
  2). Most delivery stage bodies are thin wrappers whose reads live one or two
  modules away — `run_mastering_plan_synthesize` reaches `master/selection.json`
  only via `shape_order_emit.attach_shape_order`.

Still a lead, not proof: cross-module following cannot see which branch runs, so
it over-reports, and a path assembled from runtime values is invisible to it.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

READ_HELPERS = frozenset(
    {"read_json", "read_path", "read_text", "artifact_path", "artifact_exists",
     "artifact_exists_required", "resolve_read_path"}
)
WRITE_HELPERS = frozenset(
    {"path", "write_json", "write_text", "write_bytes", "final_path",
     "resolve_write_path", "write_committed_json", "write_mirrored_json",
     "write_mirrored_text"}
)

# A path-shaped literal: has a directory or a known artifact suffix.
_SUFFIXES = (".json", ".wav", ".mp3", ".vtt", ".txt", ".jsonl", ".md", ".png")


def _looks_like_artifact(value: str) -> bool:
    return bool(value) and value.endswith(_SUFFIXES)


def _module_path(dotted: str) -> Path | None:
    candidate = SRC.joinpath(*dotted.split(".")).with_suffix(".py")
    if candidate.is_file():
        return candidate
    pkg = SRC.joinpath(*dotted.split(".")) / "__init__.py"
    return pkg if pkg.is_file() else None


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` and ``NAME = f"{CONST}/x.json"``.

    Delivery stage bodies name their artifacts through constants almost
    exclusively (`AGENDA_REL`, `PLAN_REL`, `DOSSIER_REL`), so a literal-only
    walk reports an empty read set for them.
    """
    consts: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = _string_of(node.value, consts)
        if value:
            consts[target.id] = value
    return consts


def _string_of(node: ast.AST, consts: dict[str, str]) -> str | None:
    """Best-effort constant folding: literal, known name, or f-string -> glob."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                parts.append(piece.value)
            elif isinstance(piece, ast.FormattedValue):
                resolved = _string_of(piece.value, consts)
                # An unresolvable interpolation is a runtime value: widen to a
                # glob rather than dropping the whole path.
                parts.append(resolved if resolved is not None else "*")
            else:
                parts.append("*")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_of(node.left, consts)
        right = _string_of(node.right, consts)
        if left is not None and right is not None:
            return left + right
    return None


class _Visitor(ast.NodeVisitor):
    def __init__(self, consts: dict[str, str] | None = None) -> None:
        self.reads: set[str] = set()
        self.writes: set[str] = set()
        self.local_imports: set[str] = set()
        self.consts = consts or {}

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module and node.module.startswith("interview_mux"):
            self.local_imports.add(node.module)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name.startswith("interview_mux"):
                self.local_imports.add(alias.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
            resolved = [_string_of(a, self.consts) for a in node.args]
            literals = [v for v in resolved if v]
            joined = "/".join(literals)
            # `ctx.read_path("preclean", "isolated.wav")` means one artifact, not
            # two. Only fall back to the individual components when the joined
            # form is not itself path-shaped.
            if _looks_like_artifact(joined):
                candidates = {joined}
            else:
                candidates = {c for c in literals if _looks_like_artifact(c)}
            for candidate in candidates:
                if name in READ_HELPERS:
                    self.reads.add(candidate)
                elif name in WRITE_HELPERS:
                    self.writes.add(candidate)
        self.generic_visit(node)


def _function_index(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    out: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node  # type: ignore[assignment]
    return out


class _Module:
    """Parsed module plus the two name tables a cross-module walk needs."""

    def __init__(self, dotted: str, tree: ast.Module) -> None:
        self.dotted = dotted
        self.functions = _function_index(tree)
        self.constants = _module_constants(tree)
        # `from interview_mux.x import foo` -> foo lives in interview_mux.x.
        # Function-local imports count: this codebase defers most of them to
        # dodge cycles, so a module-body-only scan misses nearly every edge.
        self.name_origin: dict[str, str] = {}
        self.module_alias: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if not (node.module or "").startswith("interview_mux"):
                    continue
                for alias in node.names:
                    target = f"{node.module}.{alias.name}"
                    if _module_path(target) is not None:
                        self.module_alias[alias.asname or alias.name] = target
                    else:
                        self.name_origin[alias.asname or alias.name] = str(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("interview_mux"):
                        key = alias.asname or alias.name.rsplit(".", 1)[-1]
                        self.module_alias[key] = alias.name


# Guardrail / completion infrastructure. Every stage calls into these, and they
# probe the whole run tree, so following them turns any stage's report into the
# union of all artifacts. They are the code the contracts are meant to replace —
# their reads belong to the guardrail, not to the stage.
OPAQUE_MODULES: frozenset[str] = frozenset(
    {
        "interview_mux.stage_completion",
        "interview_mux.thrash_hardening",
        "interview_mux.delivery_guardrails",
        "interview_mux.delivery_invariants",
        "interview_mux.artifact_lifecycle",
        "interview_mux.recovery_controller",
        "interview_mux.heal_routing",
        "interview_mux.stage_acceptance",
        "interview_mux.artifact_dependency_graph",
        "interview_mux.dispatch_door",
        "interview_mux.dispatch_delta",
        "interview_mux.operator_trace",
        "interview_mux.pipeline",
        "interview_mux.defect_ledger",
        "interview_mux.ship_reachability",
        "interview_mux.post_master_quality",
        "interview_mux.publishability_boundary",
    }
)


def _is_opaque(dotted: str) -> bool:
    return dotted in OPAQUE_MODULES or dotted.startswith("interview_mux.homunculus")


_MODULE_CACHE: dict[str, _Module | None] = {}


def _load_module(dotted: str) -> _Module | None:
    if dotted not in _MODULE_CACHE:
        path = _module_path(dotted)
        if path is None:
            _MODULE_CACHE[dotted] = None
        else:
            try:
                _MODULE_CACHE[dotted] = _Module(
                    dotted, ast.parse(path.read_text(encoding="utf-8"))
                )
            except (OSError, SyntaxError):
                _MODULE_CACHE[dotted] = None
    return _MODULE_CACHE[dotted]


def scan_entrypoint(module: str, entry: str, *, call_depth: int = 2) -> dict[str, set[str]]:
    """Scope the walk to one function, its same-module helpers, and their callees.

    Several stages share a module — `stages/understanding.py` holds five — so a
    whole-module scan reports their union and is useless for populating a single
    contract. `call_depth` bounds how many module hops a callee may be: the
    delivery groups need at least 2, because their stage bodies are wrappers.
    """
    reads: set[str] = set()
    writes: set[str] = set()
    seen: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()

    def walk(dotted: str, name: str, hops: int, bound: dict[str, str] | None = None) -> None:
        if hops > call_depth:
            return
        if hops and _is_opaque(dotted):
            return
        mod = _load_module(dotted)
        if mod is None or name not in mod.functions:
            return
        bound = bound or {}
        key = (dotted, name, tuple(sorted(bound.items())))
        if key in seen:
            return
        seen.add(key)
        fn = mod.functions[name]
        scope = {**mod.constants, **bound}
        visitor = _Visitor(scope)
        visitor.visit(fn)
        reads.update(visitor.reads)
        writes.update(visitor.writes)
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in mod.functions:
                    walk(dotted, func.id, hops, _bind(mod, func.id, node, scope))
                elif func.id in mod.name_origin:
                    target = mod.name_origin[func.id]
                    other = _load_module(target)
                    walk(target, func.id, hops + 1, _bind(other, func.id, node, scope))
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                target = mod.module_alias.get(func.value.id)
                if target:
                    other = _load_module(target)
                    walk(target, func.attr, hops + 1, _bind(other, func.attr, node, scope))

    walk(module, entry, 0)
    return {"reads": reads, "writes": writes}


def _bind(
    mod: "_Module | None", func_name: str, call: ast.Call, scope: dict[str, str]
) -> dict[str, str]:
    """Bind a callee's parameters to the string literals passed at this call site.

    `sonic_context` reads everything through `_read_if_dict(ctx, rel)`, so the
    artifact names live in the *caller's* argument list and a callee-local walk
    sees only the opaque parameter. Without this the whole module reports zero
    reads, which is how `sonic_context_build` looked hollow.
    """
    if mod is None or func_name not in mod.functions:
        return {}
    fn = mod.functions[func_name]
    params = [a.arg for a in fn.args.args]
    out: dict[str, str] = {}
    for param, arg in zip(params, call.args):
        value = _string_of(arg, scope)
        if value:
            out[param] = value
    for kw in call.keywords:
        if kw.arg and kw.arg in params:
            value = _string_of(kw.value, scope)
            if value:
                out[kw.arg] = value
    return out


def scan(module: str, *, depth: int) -> dict[str, set[str]]:
    seen: set[str] = set()
    reads: set[str] = set()
    writes: set[str] = set()

    def walk(dotted: str, level: int) -> None:
        if dotted in seen or level > depth:
            return
        seen.add(dotted)
        path = _module_path(dotted)
        if path is None:
            return
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            return
        visitor = _Visitor()
        visitor.visit(tree)
        reads.update(visitor.reads)
        writes.update(visitor.writes)
        for child in sorted(visitor.local_imports):
            walk(child, level + 1)

    walk(module, 0)
    return {"reads": reads, "writes": writes}


def dispatch_table() -> dict[str, tuple[str, str]]:
    """stage_id -> (module, function), read out of `pipeline.py`'s own tables.

    `_analysis_stage_fns` / `_delivery_stage_fns` are the authority on which
    function a dispatch runs; guessing from file names is not.
    """
    text = (SRC / "interview_mux" / "pipeline.py").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    out: dict[str, tuple[str, str]] = {}
    # "stage": lambda: module_alias.run_x(ctx)
    for stage, alias, fn in re.findall(
        r'"([a-z0-9_]+)": lambda: ([a-z0-9_]+)\.([a-z0-9_]+)\(ctx\)', flat
    ):
        out[stage] = (f"interview_mux.stages.{alias}", fn)
    # "stage": lambda: __import__("dotted.module", fromlist=["run_x"]).run_x(ctx)
    for stage, module, fn in re.findall(
        r'"([a-z0-9_]+)": lambda: __import__\( "([a-z0-9_.]+)", fromlist=\["[a-z0-9_]+"\], \)\.([a-z0-9_]+)\(ctx\)',
        flat,
    ):
        out[stage] = (module, fn)
    for stage, module, fn in re.findall(
        r'"([a-z0-9_]+)": lambda: __import__\( "([a-z0-9_.]+)", fromlist=\["[a-z0-9_]+"\] \)\.([a-z0-9_]+)\(ctx\)',
        flat,
    ):
        out[stage] = (module, fn)
    return out


def stage_modules(stage_id: str) -> list[str]:
    """Modules defining `run_<stage_id>` / `run_<stage_id>_stage`.

    Name-match on the stage id alone is useless: half of `stages/` mentions
    `"ingest"` somewhere, which drags the whole delivery tail into the report.
    """
    entry = dispatch_table().get(stage_id)
    if entry:
        module = entry[0]
        if _module_path(module) is not None:
            return [module]
        bare = module.rsplit(".", 1)[-1]
        for candidate in (f"interview_mux.{bare}", f"interview_mux.stages.{bare}"):
            if _module_path(candidate) is not None:
                return [candidate]
    wanted = (f"def run_{stage_id}(", f"def run_{stage_id}_stage(", f"def {stage_id}(")
    hits: list[str] = []
    roots = [SRC / "interview_mux" / "stages", SRC / "interview_mux"]
    for root in roots:
        for path in sorted(root.glob("*.py")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if any(w in text for w in wanted):
                rel = path.relative_to(SRC).with_suffix("")
                hits.append(".".join(rel.parts))
    return hits


def _split_by_write_authority(
    stage_id: str, writes: set[str]
) -> tuple[set[str], dict[str, str]]:
    from interview_mux.artifact_ownership import write_permitted
    from interview_mux.stage_contract import is_path_spec

    permitted: set[str] = set()
    denied: dict[str, str] = {}
    for rel in writes:
        if is_path_spec(rel):
            permitted.add(rel)
            continue
        ok, reason = write_permitted(None, rel, stage_id)
        if ok or reason == "unknown_path":
            permitted.add(rel)
        else:
            denied[rel] = reason
    return permitted, denied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stages", nargs="*")
    ap.add_argument("--group", help="operator phase id from v2.phases")
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--modules", action="store_true", help="print the modules scanned")
    ap.add_argument(
        "--entrypoint-only",
        action="store_true",
        help="scope to run_<stage> and same-module helpers (shared stage modules)",
    )
    ap.add_argument(
        "--call-depth",
        type=int,
        default=2,
        help="module hops a callee may be from the entrypoint (--entrypoint-only)",
    )
    args = ap.parse_args()

    stages = list(args.stages)
    if args.group:
        from interview_mux.v2.phases import phase_stage_ids

        stages.extend(phase_stage_ids(args.group))

    from interview_mux.stage_contract import load_contract

    out: dict[str, dict[str, list[str]]] = {}
    for stage_id in stages:
        modules = stage_modules(stage_id)
        reads: set[str] = set()
        writes: set[str] = set()
        for module in modules:
            if args.entrypoint_only:
                fn = dispatch_table().get(stage_id)
                entries = [fn[1]] if fn else []
                entries += [f"run_{stage_id}", f"run_{stage_id}_stage", stage_id]
                for entry in entries:
                    found = scan_entrypoint(module, entry, call_depth=args.call_depth)
                    reads |= found["reads"]
                    writes |= found["writes"]
            else:
                found = scan(module, depth=args.depth)
                reads |= found["reads"]
                writes |= found["writes"]
        contract = load_contract(stage_id)
        declared_in = {d.path for d in contract.inputs} if contract else set()
        declared_out = {d.path for d in contract.outputs} if contract else set()
        permitted, denied = _split_by_write_authority(stage_id, writes)
        row = {
            "observed_reads": sorted(reads),
            "observed_writes": sorted(permitted),
            # The single best filter on this tool's over-reporting: a write the
            # ownership constitution refuses this stage cannot be one the stage
            # really makes (it would be a runtime `authority_denied`), so it came
            # from following a shared helper. `unknown_path` is different — that
            # is a real write with no catalog row, i.e. an ownership gap.
            "writes_denied_by_ownership": [
                f"{rel} ({reason})" for rel, reason in sorted(denied.items())
            ],
            "declared_inputs": sorted(declared_in),
            "declared_outputs": sorted(declared_out),
            "undeclared_reads": sorted(reads - declared_in - declared_out),
            "undeclared_writes": sorted(permitted - declared_out),
        }
        if args.modules:
            row["modules"] = modules
        out[stage_id] = row
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
