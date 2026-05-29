"""Optional sequential specialist LLM passes (BUILD-084)."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.analysis_memory import enqueue_investigations
from interview_mux.config import merged_config
from interview_mux.context_volley import build_message_volley
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import run_prompt_envelope

SPECIALIST_PROMPTS: dict[str, str] = {
    "comprehension_risk_blind": "_shared/specialists/comprehension-risk-blind.system.txt",
    "theme_coverage_pass": "_shared/specialists/theme-coverage-pass.system.txt",
    "emphasis_coverage_pass": "_shared/specialists/emphasis-coverage-pass.system.txt",
}

POST_STAGE_SPECIALISTS: dict[str, tuple[str, ...]] = {
    "missing_framing": ("comprehension_risk_blind",),
    "segment_classification": ("theme_coverage_pass",),
    "topic_coverage_audit": ("emphasis_coverage_pass",),
    "full_master_ranking": ("comprehension_risk_blind",),
}

COMPREHENSION_RISK_THRESHOLD = 0.7


def _process_specialist_investigations(
    ctx: RunContext,
    *,
    parent_stage: str,
    specialist_key: str,
    envelope: dict[str, Any],
) -> int:
    """Enqueue investigations from specialist artifacts when thresholds are met."""
    artifacts = envelope.get("artifacts") or {}
    items: list[dict[str, Any]] = []

    if specialist_key == "comprehension_risk_blind":
        for row in artifacts.get("comprehension_risks") or []:
            if not isinstance(row, dict):
                continue
            score = float(row.get("risk_score") or 0)
            if score < COMPREHENSION_RISK_THRESHOLD:
                continue
            seg = row.get("segment_id", "")
            items.append(
                {
                    "kind": "gap_unresolved",
                    "question": row.get("rationale") or f"High comprehension risk on {seg}",
                    "priority": "high",
                    "blocking": False,
                    "suggested_action": {"type": "rerun_stage", "stage": "missing_framing"},
                    "target": {"segment_id": seg},
                }
            )

    elif specialist_key == "theme_coverage_pass":
        patches = artifacts.get("segment_topic_patches") or []
        if patches:
            items.append(
                {
                    "kind": "theme_unmapped",
                    "question": f"Specialist found {len(patches)} segment topic patch(es) — re-check classification",
                    "priority": "medium",
                    "blocking": False,
                    "suggested_action": {"type": "rerun_stage", "stage": "segment_classification"},
                }
            )

    elif specialist_key == "emphasis_coverage_pass":
        coverage = artifacts.get("emphasis_coverage") if isinstance(artifacts.get("emphasis_coverage"), dict) else {}
        gaps = coverage.get("gaps") or []
        if gaps:
            items.append(
                {
                    "kind": "theme_unmapped",
                    "question": f"Emphasis coverage gaps ({len(gaps)}) — re-audit topic coverage",
                    "priority": "medium",
                    "blocking": False,
                    "suggested_action": {"type": "rerun_stage", "stage": "topic_coverage_audit"},
                }
            )

    if items:
        enqueue_investigations(ctx, items, created_by_stage=parent_stage)
    return len(items)


def _specialists_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = cfg if cfg is not None else merged_config()
    return (resolved.get("analysis") or {}).get("specialists") or {}


def specialists_enabled(
    cfg: dict[str, Any] | None = None,
    *,
    stage_key: str | None = None,
) -> bool:
    spec_cfg = _specialists_cfg(cfg)
    if not spec_cfg.get("enabled", False):
        return False
    pilot_stages = spec_cfg.get("pilot_stages")
    if pilot_stages is not None:
        if stage_key is None:
            return bool(pilot_stages)
        return stage_key in pilot_stages
    if stage_key is None:
        return True
    return stage_key in POST_STAGE_SPECIALISTS


def run_specialist(
    ctx: RunContext,
    specialist_key: str,
    parent_stage: str,
    stage_input: dict[str, Any],
) -> dict[str, Any]:
    prompt_rel = SPECIALIST_PROMPTS.get(specialist_key)
    if not prompt_rel:
        raise ValueError(f"Unknown specialist: {specialist_key}")
    volley = build_message_volley(ctx, parent_stage, stage_input, profile="shard")
    return run_prompt_envelope(
        f"{parent_stage}__{specialist_key}",
        prompt_rel,
        messages=volley,
        ctx=ctx,
        task_kind="specialist",
    )


def maybe_run_post_stage_specialists(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run configured specialists after a parent stage completes."""
    if not specialists_enabled(cfg, stage_key=stage_key):
        return []
    outputs: list[dict[str, Any]] = []
    for spec_key in POST_STAGE_SPECIALISTS.get(stage_key, ()):
        try:
            env = run_specialist(ctx, spec_key, stage_key, stage_input)
            outputs.append({"specialist": spec_key, "envelope": env})
            base = ctx.path("understanding", "stage_runs", stage_key)
            base.mkdir(parents=True, exist_ok=True)
            out_path = base / f"specialist_{spec_key}.json"
            out_path.write_text(json.dumps(env, indent=2), encoding="utf-8")
            _process_specialist_investigations(
                ctx,
                parent_stage=stage_key,
                specialist_key=spec_key,
                envelope=env,
            )
        except Exception as exc:
            ctx.log(
                f"Specialist {spec_key} failed: {exc}",
                level="warning",
                stage=stage_key,
            )
    return outputs


def enqueue_specialist_investigation(
    ctx: RunContext,
    *,
    parent_stage: str,
    specialist_key: str,
    question: str,
) -> None:
    enqueue_investigations(
        ctx,
        [
            {
                "kind": "run_specialist",
                "question": question,
                "priority": "medium",
                "blocking": False,
                "suggested_action": {
                    "type": "run_specialist",
                    "stage": parent_stage,
                    "specialist": specialist_key,
                },
            }
        ],
        created_by_stage=parent_stage,
    )
