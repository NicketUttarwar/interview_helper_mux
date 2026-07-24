"""Prompt-edit promotion gate.

Spec: docs/cross-cutting/mastering-quality-hardening.md (Workstream 12)
Artifacts: mastering/prompt_edit_log.json, mastering/prompt_promotions.json

Autonomous prompt evolution helps the run that made the edit and can quietly
degrade every other source type. Edits therefore stay run-local until corpus
evidence plus an operator approval say otherwise.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_hardening_config import prompt_edit_cfg
from interview_mux.run_context import RunContext

PROMOTIONS_ARTIFACT = "mastering/prompt_promotions.json"
RUN_LOCAL_PROMPT_DIR = "mastering/prompts_minted"

# A promoted prompt must beat these on the eval corpus before it becomes a seed.
CORPUS_THRESHOLDS: dict[str, float] = {
    "integrity_recall": 1.0,
    "integrity_false_positive_rate": 0.0,
    "diversity_floor_met": 1.0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_local_prompt_rel(step_id: str, version: int) -> str:
    return f"{RUN_LOCAL_PROMPT_DIR}/{step_id}.v{version}.system.txt"


def promotion_blockers(
    *,
    corpus_results: dict[str, Any] | None,
    operator_approval: dict[str, Any] | None,
    cfg: dict[str, Any] | None = None,
) -> list[str]:
    """Reasons this edit may not become a global seed. Empty list means promotable."""
    conf = prompt_edit_cfg(cfg)
    blockers: list[str] = []

    if not conf.get("allow_global_promotion", False):
        blockers.append("mastering.prompt_edit.allow_global_promotion is false")

    if not corpus_results:
        blockers.append("no eval-corpus results attached")
    else:
        for metric, floor in CORPUS_THRESHOLDS.items():
            value = corpus_results.get(metric)
            if value is None:
                blockers.append(f"corpus metric missing: {metric}")
            elif metric.endswith("_rate"):
                if float(value) > floor:
                    blockers.append(f"{metric} {value} exceeds ceiling {floor}")
            elif float(value) < floor:
                blockers.append(f"{metric} {value} below floor {floor}")

    if conf.get("require_operator_approval", True):
        if not (operator_approval or {}).get("approved"):
            blockers.append("operator approval not recorded")

    return blockers


def can_promote(
    *,
    corpus_results: dict[str, Any] | None,
    operator_approval: dict[str, Any] | None,
    cfg: dict[str, Any] | None = None,
) -> bool:
    return not promotion_blockers(
        corpus_results=corpus_results, operator_approval=operator_approval, cfg=cfg
    )


def record_promotion_request(
    ctx: RunContext,
    *,
    step_id: str,
    version: int,
    corpus_results: dict[str, Any] | None = None,
    operator_approval: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a promotion decision to the run's promotion ledger."""
    blockers = promotion_blockers(
        corpus_results=corpus_results, operator_approval=operator_approval, cfg=cfg
    )
    entry = {
        "step_id": step_id,
        "version": version,
        "prompt_ref": run_local_prompt_rel(step_id, version),
        "scope": "global" if not blockers else "run_local",
        "promoted": not blockers,
        "blockers": blockers,
        "corpus_results": corpus_results or {},
        "operator_approval": operator_approval or {},
        "recorded_at": _now(),
    }

    existing = ctx.read_json(PROMOTIONS_ARTIFACT) if ctx.artifact_exists(PROMOTIONS_ARTIFACT) else None
    doc = existing if isinstance(existing, dict) else {"version": 1, "promotions": []}
    doc.setdefault("promotions", []).append(entry)
    doc["updated_at"] = entry["recorded_at"]
    ctx.write_json(PROMOTIONS_ARTIFACT, doc)
    return entry
