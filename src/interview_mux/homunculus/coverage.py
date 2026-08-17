"""Coverage completeness: every stage, prompt, and operator action is catalogued."""

from __future__ import annotations

from typing import Any

from interview_mux.config import repo_root
from interview_mux.homunculus.registry import all_specs
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

OUT_OF_SCOPE_PREFIXES = (
    "scripts/tf-",
    "scripts/bootstrap_venv",
    "scripts/build_gui",
    "terraform/",
)


def coverage_report() -> dict[str, Any]:
    specs = all_specs()
    identities = {s.identity for s in specs}
    names = {s.name for s in specs}
    missing_stages = [
        s for s in (*ANALYSIS_ORDER, *DELIVERY_ORDER) if s not in identities
    ]
    prompts_root = repo_root() / "docs" / "prompts"
    prompt_files = (
        sorted(p.relative_to(repo_root()).as_posix() for p in prompts_root.rglob("*.system.txt"))
        if prompts_root.is_dir()
        else []
    )
    missing_prompts = [p for p in prompt_files if p not in identities]
    actions_path = repo_root() / "docs" / "cross-cutting" / "operator_action_catalog.json"
    missing_actions: list[str] = []
    if actions_path.is_file():
        import json

        rows = json.loads(actions_path.read_text(encoding="utf-8"))
        for row in rows:
            if not isinstance(row, dict):
                continue
            if "[REMOVED]" in str(row.get("description") or ""):
                continue
            aid = str(row.get("action_id") or "")
            if aid and aid not in identities:
                missing_actions.append(aid)
    return {
        "spec_count": len(specs),
        "names": len(names),
        "missing_stages": missing_stages,
        "missing_prompts": missing_prompts,
        "missing_actions": missing_actions,
        "ok": not missing_stages and not missing_prompts and not missing_actions,
    }


def assert_coverage_complete() -> None:
    report = coverage_report()
    if not report["ok"]:
        raise AssertionError(
            "homunculus coverage gaps: "
            f"stages={report['missing_stages'][:8]} "
            f"prompts={report['missing_prompts'][:8]} "
            f"actions={report['missing_actions'][:8]}"
        )
