#!/usr/bin/env python3
"""Static ownership checklist for new stages and shared remap writers."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "interview_mux"
REMAP_CALLS = {"apply_full_segment_id_remap", "rewrite_artifact_segment_refs"}


def _string_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if len(node.targets) == 1 else None
        )
        value = node.value
        if (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            constants[target.id] = value.value
    return constants


def _literal_string(node: ast.AST, constants: dict[str, str]) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id, "")
    return ""


def _returned_string_literals(tree: ast.Module) -> dict[str, set[str]]:
    returned: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        values = {
            str(ret.value.value)
            for ret in ast.walk(node)
            if isinstance(ret, ast.Return)
            and isinstance(ret.value, ast.Constant)
            and isinstance(ret.value.value, str)
        }
        if values:
            returned[node.name] = values
    return returned


def remap_call_site_findings(src_root: Path = SRC) -> list[str]:
    """Every production remap persist must name a registered literal stage."""
    from interview_mux.artifact_ownership import SEGMENT_ID_REMAP_STAGES

    registered = set(SEGMENT_ID_REMAP_STAGES)
    findings: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        if path.name == "segment_id_remap.py":
            continue  # helper-to-helper forwarding; callers supply the writer
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        constants = _string_constants(tree)
        returned = _returned_string_literals(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            if name not in REMAP_CALLS:
                continue
            keyword = next((k for k in node.keywords if k.arg == "stage_key"), None)
            stage = _literal_string(keyword.value, constants) if keyword else ""
            rel = path.relative_to(ROOT)
            if (
                not stage
                and keyword
                and isinstance(keyword.value, ast.Call)
                and isinstance(keyword.value.func, ast.Name)
            ):
                possible = returned.get(keyword.value.func.id, set())
                if possible and possible <= registered:
                    continue
            if not stage:
                findings.append(f"{rel}:{node.lineno}: remap call lacks literal stage_key")
            elif stage not in registered:
                findings.append(
                    f"{rel}:{node.lineno}: remap stage {stage!r} is not registered"
                )
    return findings


def shared_co_writer_findings() -> list[str]:
    """AST-declared shared-path co-writers must all be catalog producers."""
    from interview_mux.artifact_ownership import owners_of
    from interview_mux.post_decision_sanitize import SHARED_PATH_CO_PRODUCERS

    findings: list[str] = []
    for rel, producers in sorted(SHARED_PATH_CO_PRODUCERS.items()):
        owners = set(owners_of(rel))
        for producer in producers:
            if producer not in owners:
                findings.append(
                    f"{rel}: co-writer {producer!r} is not a catalog producer "
                    f"(owners={sorted(owners)})"
                )
    return findings


def main() -> int:
    findings = remap_call_site_findings() + shared_co_writer_findings()
    if findings:
        print("ownership_new_stage_checklist: FAIL", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("ownership_new_stage_checklist: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
