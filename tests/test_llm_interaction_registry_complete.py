"""CI: every run_prompt_envelope / generate_local_chat site maps to the interaction registry."""

from __future__ import annotations

import re
from pathlib import Path

from interview_mux.config import repo_root
from interview_mux.llm_interaction_registry import (
    LLM_INTERACTION_REGISTRY,
    expected_gateway_sites,
    registry_ids,
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
        "OF-01", "OF-02", "OF-03", "OF-04", "OF-05", "OF-06", "OF-07", "OF-08",
        "OF-09", "OF-10", "OF-L1", "OF-L2", "OF-L3",
        "OM-01", "OM-02", "OM-03", "OM-04", "OM-05",
        "OS-01", "OS-02", "OS-03",
        "LX-01", "LX-01a", "LX-01b", "LX-01c", "LX-01d",
        "LX-02", "LX-02a",
    }
    assert expected.issubset(registry_ids())


def test_registry_entries_have_required_fields():
    required = {
        "id", "provider", "interaction", "stage_key", "task_kind",
        "trigger", "entrypoint", "prompt_rel", "response_schema", "goal",
    }
    for iid, row in LLM_INTERACTION_REGISTRY.items():
        assert iid == row["id"]
        missing = required - set(row.keys())
        assert not missing, f"{iid} missing {missing}"


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
