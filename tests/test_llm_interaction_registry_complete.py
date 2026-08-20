"""CI: every run_prompt_envelope / generate_local_chat site maps to the interaction registry."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from interview_mux.config import repo_root
from interview_mux.llm_interaction_registry import (
    LLM_INTERACTION_REGISTRY,
    expected_gateway_sites,
    registry_ids,
    resolve_interaction_id,
)

_SRC = repo_root() / "src" / "interview_mux"


def _grep_call_sites(symbol: str) -> list[tuple[str, int, str]]:
    pattern = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    hits: list[tuple[str, int, str]] = []
    for path in _SRC.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line) and not line.strip().startswith("#"):
                rel = str(path.relative_to(repo_root()))
                hits.append((rel, i, line.strip()))
    return hits


def test_registry_has_all_catalog_ids():
    expected = {
        "OA-01", "OA-02", "OA-03", "OA-04", "OA-05", "OA-06", "OA-07", "OA-08",
        "OF-01", "OF-02", "OF-03", "OF-04", "OF-05", "OF-06", "OF-07",
        "OF-L1", "OF-L3",
        "OM-01", "OM-F01", "OM-SAFE",
        "OS-01", "OS-02", "OS-03", "OS-04", "OS-05",
        "LX-01", "LX-01a", "LX-01b", "LX-01c", "LX-01d",
        "OH-02", "OH-03", "OH-A1", "OH-J1", "OH-J2",
        "OH-C1", "OH-C2", "OH-C3", "OH-C4", "OH-C5", "OH-C6",
    }
    assert expected.issubset(registry_ids())


def test_registry_has_no_ids_for_dropped_v2_subsystems():
    """Arbiter/shard/collate, the capability router, ITR clarification and micro-gap-fill are gone."""
    dropped = {"OM-02", "OM-03", "OM-04", "OM-05", "LX-02", "LX-02a", "LX-03", "LX-04", "LX-05", "OM-LX-P", "OH-01", "OH-P1"}
    assert not (dropped & registry_ids())
    assert not [iid for iid in registry_ids() if iid.startswith("OM-MG-")]


def test_registry_entries_have_required_fields():
    required = {
        "id", "provider", "interaction", "stage_key", "task_kind",
        "trigger", "entrypoint", "prompt_rel", "response_schema", "goal",
    }
    for iid, row in LLM_INTERACTION_REGISTRY.items():
        assert iid == row["id"]
        missing = required - set(row.keys())
        assert not missing, f"{iid} missing {missing}"


def test_registry_entrypoints_resolve_to_live_modules():
    for iid, row in LLM_INTERACTION_REGISTRY.items():
        module, _, func = str(row["entrypoint"]).partition(".")
        path = _SRC / f"{module}.py"
        if not path.is_file():
            path = _SRC / "stages" / f"{module}.py"
        assert path.is_file(), f"{iid} entrypoint module {module!r} does not exist"
        if not func:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        }
        assert func in names, f"{iid} entrypoint {row['entrypoint']!r} not defined in {path.name}"


def test_resolve_interaction_id_only_returns_registered_ids():
    ids = registry_ids()
    cases = [
        {"stage_key": "speaker_roles", "task_kind": "primary"},
        {"stage_key": "unknown_stage", "task_kind": "primary"},
        {"stage_key": "missing_framing__comprehension_risk_blind", "task_kind": "specialist"},
        {"stage_key": "content_context", "task_kind": "arbiter"},
        {"stage_key": "content_context", "task_kind": "collate", "volley_retry_index": 1},
        {"stage_key": "content_context", "task_kind": "local_primary", "provider": "local_mlx"},
        {"stage_key": "content_context__itr", "task_kind": "itr", "provider": "local_mlx"},
        {"stage_key": "junction_feel_audit", "task_kind": "primary"},
        {"stage_key": "junction_thought_complete", "task_kind": "primary"},
    ]
    for case in cases:
        assert resolve_interaction_id(**case) in ids, case
    assert resolve_interaction_id(stage_key="junction_feel_audit", task_kind="primary") == "OH-J1"
    assert resolve_interaction_id(stage_key="junction_thought_complete", task_kind="primary") == "OH-J2"


def test_run_prompt_envelope_sites_in_expected_modules():
    sites = expected_gateway_sites()["run_prompt_envelope"]
    hits = _grep_call_sites("run_prompt_envelope")
    assert hits, "no run_prompt_envelope call sites found"
    for rel, line_no, _ in hits:
        module = Path(rel).stem
        assert any(s in rel for s in sites), (
            f"unexpected run_prompt_envelope at {rel}:{line_no} — add to registry or expected_gateway_sites"
        )


def test_generate_local_chat_sites_in_expected_modules():
    sites = expected_gateway_sites()["generate_local_chat"]
    hits = _grep_call_sites("generate_local_chat")
    assert hits, "no generate_local_chat call sites found"
    for rel, line_no, _ in hits:
        assert any(s in rel for s in sites), (
            f"unexpected generate_local_chat at {rel}:{line_no}"
        )
