"""Targeted LLM patch calls for specific artifact paths."""

from __future__ import annotations

import copy
from typing import Any

from interview_mux.adaptation_loop_guard import AdaptationLoopGuard
from interview_mux.artifact_completeness import merge_artifact
from interview_mux.coverage_limits import gap_fill_cap
from interview_mux.openai_structured_output import compose_envelope_schema, strictify_schema
from interview_mux.openai_schema_semantic_lint import assert_openai_semantic_schema
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.sufficiency_engine import SufficiencyFinding, findings_to_gap_paths


def compose_patch_schema(stage_key: str, paths: list[str]) -> dict[str, Any]:
    """Minimal envelope schema containing only listed artifact paths."""
    full = compose_envelope_schema(stage_key, strict=True)
    art = copy.deepcopy(full["properties"]["artifacts"])
    props = art.get("properties") or {}
    patch_props = {k: props[k] for k in paths if k in props}
    if not patch_props and paths:
        patch_props = {p.split("[")[0].split(".")[0]: props.get(p.split("[")[0], {"type": "string"}) for p in paths}
    art["properties"] = patch_props
    art["required"] = list(patch_props.keys())
    envelope = copy.deepcopy(full)
    envelope["properties"]["artifacts"] = strictify_schema(art)
    assert_openai_semantic_schema(envelope)
    return envelope


def run_micro_gap_fill(
    ctx: Any,
    stage_key: str,
    paths: list[str],
    *,
    existing: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Run a bounded micro-fill via gap_fill_context patch mode (no extra API surface in tests)."""
    guard = AdaptationLoopGuard.load(ctx, stage_key)
    if not guard.can_micro_gap_fill():
        return existing or {}, ["micro_gap_fill budget exhausted"]
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        return existing or {}, [f"no artifact for {stage_key}"]
    from interview_mux.artifact_completeness import build_gap_fill_context

    gfc = build_gap_fill_context(ctx, stage_key)
    if not gfc:
        gfc = {
            "gaps": paths,
            "existing": existing,
            "skip_fields": [],
            "instructions": "Patch only listed paths.",
        }
    else:
        gap_cap = gap_fill_cap(len(paths) + len(gfc.get("gaps") or []))
        merged_gaps = list({*list(gfc.get("gaps") or []), *paths})
        gfc = {**gfc, "gaps": merged_gaps[:gap_cap]}
    # Delegate to gap-fill path in routing — return plan for orchestrator
    guard.mark_micro_gap_fill()
    guard.save(ctx)
    patch_plan = {
        "stage_key": stage_key,
        "artifact_path": rel,
        "paths": paths,
        "gap_fill_context": gfc,
    }
    meta = {"micro_gap_fill_plan": patch_plan}
    out = copy.deepcopy(existing or {})
    out.setdefault("_meta", {})
    hist = list((out["_meta"].get("remediation_history") or []))
    hist.append({"action": "micro_gap_fill", "paths": paths})
    out["_meta"]["remediation_history"] = hist[-12:]
    out["_meta"].update(meta)
    return out, []


def merge_micro_fill_result(
    stage_key: str,
    existing: dict[str, Any] | None,
    patch: dict[str, Any],
) -> dict[str, Any]:
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        return patch
    return merge_artifact(rel, existing, patch, stage_key=stage_key)


def paths_from_findings(findings: list[SufficiencyFinding]) -> list[str]:
    return findings_to_gap_paths(findings)[:8]


__all__ = [
    "compose_patch_schema",
    "merge_micro_fill_result",
    "paths_from_findings",
    "run_micro_gap_fill",
]
