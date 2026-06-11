"""Optional sequential specialist LLM passes (BUILD-084)."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.analysis_memory import enqueue_investigations
from interview_mux.config import merged_config
from interview_mux.local_volley_framer import prepare_volley_for_llm
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import run_prompt_envelope

SPECIALIST_PROMPTS: dict[str, str] = {
    "comprehension_risk_blind": "_shared/specialists/comprehension-risk-blind.system.txt",
    "theme_coverage_pass": "_shared/specialists/theme-coverage-pass.system.txt",
    "emphasis_coverage_pass": "_shared/specialists/emphasis-coverage-pass.system.txt",
}

PRE_STAGE_SPECIALISTS: dict[str, tuple[str, ...]] = {
    "missing_framing": ("comprehension_risk_blind",),
}

POST_STAGE_SPECIALISTS: dict[str, tuple[str, ...]] = {
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
            applied = apply_segment_topic_patches(ctx, patches)
            if applied:
                ctx.log(
                    f"theme_coverage_pass: applied topic patches to {applied} segment(s)",
                    level="info",
                    stage=parent_stage,
                )
            else:
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


def apply_segment_topic_patches(ctx: RunContext, patches: list[Any]) -> int:
    """Merge specialist topic patches into segments/manifest.json."""
    from interview_mux.artifact_cross_validate import invalidate_stage_summaries
    from interview_mux.llm_flow_hardening import flow_hardening_enabled
    from interview_mux.pipeline import ANALYSIS_ORDER

    if not patches or not ctx.artifact_exists("segments/manifest.json"):
        return 0
    manifest = ctx.read_json("segments/manifest.json")
    segments = manifest.get("segments") or []
    if not isinstance(segments, list):
        return 0
    by_id = {
        str(seg.get("segment_id")): seg for seg in segments if isinstance(seg, dict) and seg.get("segment_id")
    }
    applied = 0
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        seg_id = str(patch.get("segment_id") or "")
        tags = patch.get("topic_tags")
        if not seg_id or seg_id not in by_id or not isinstance(tags, list) or not tags:
            continue
        by_id[seg_id]["topic_tags"] = [str(t) for t in tags if t]
        applied += 1
    if applied:
        manifest["segments"] = list(by_id.values())
        if flow_hardening_enabled():
            from interview_mux.artifact_writes import write_validated_artifact

            write_validated_artifact(
                ctx,
                "segments/manifest.json",
                manifest,
                merge_from_disk=False,
                stage_key="segment_classification",
            )
            downstream = tuple(ANALYSIS_ORDER[ANALYSIS_ORDER.index("missing_framing") : ANALYSIS_ORDER.index("optimal_questions") + 1])
            ctx.clear_from("missing_framing", ANALYSIS_ORDER)
            invalidate_stage_summaries(ctx, downstream)
        else:
            ctx.write_json("segments/manifest.json", manifest)
    return applied


def load_comprehension_risks(ctx: RunContext, parent_stage: str = "missing_framing") -> list[dict[str, Any]]:
    """Read comprehension risks from the latest specialist pass for a parent stage."""
    spec_path = ctx.path(
        "understanding", "stage_runs", parent_stage, "specialist_comprehension_risk_blind.json"
    )
    if not spec_path.is_file():
        return []
    try:
        env = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    risks = (env.get("artifacts") or {}).get("comprehension_risks")
    return risks if isinstance(risks, list) else []


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
    return stage_key in PRE_STAGE_SPECIALISTS or stage_key in POST_STAGE_SPECIALISTS


def run_specialist(
    ctx: RunContext,
    specialist_key: str,
    parent_stage: str,
    stage_input: dict[str, Any],
) -> dict[str, Any]:
    prompt_rel = SPECIALIST_PROMPTS.get(specialist_key)
    if not prompt_rel:
        raise ValueError(f"Unknown specialist: {specialist_key}")
    volley, _ = prepare_volley_for_llm(
        ctx, parent_stage, stage_input, profile="shard", task_kind="specialist"
    )
    return run_prompt_envelope(
        f"{parent_stage}__{specialist_key}",
        prompt_rel,
        messages=volley,
        ctx=ctx,
        task_kind="specialist",
    )


def _persist_specialist_output(
    ctx: RunContext,
    *,
    stage_key: str,
    spec_key: str,
    env: dict[str, Any],
) -> None:
    base = ctx.path("understanding", "stage_runs", stage_key)
    base.mkdir(parents=True, exist_ok=True)
    out_path = base / f"specialist_{spec_key}.json"
    out_path.write_text(json.dumps(env, indent=2), encoding="utf-8")


def maybe_run_pre_stage_specialists(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run configured specialists before the parent primary LLM call."""
    if not specialists_enabled(cfg, stage_key=stage_key):
        return []
    outputs: list[dict[str, Any]] = []
    for spec_key in PRE_STAGE_SPECIALISTS.get(stage_key, ()):
        try:
            env = run_specialist(ctx, spec_key, stage_key, stage_input)
            outputs.append({"specialist": spec_key, "envelope": env})
            _persist_specialist_output(ctx, stage_key=stage_key, spec_key=spec_key, env=env)
        except Exception as exc:
            from interview_mux.llm_flow_hardening import flow_hardening_enabled

            level = "action" if flow_hardening_enabled() and spec_key == "comprehension_risk_blind" else "warning"
            ctx.log(
                f"Pre-stage specialist {spec_key} failed: {exc}",
                level=level,
                stage=stage_key,
            )
            if flow_hardening_enabled() and spec_key == "comprehension_risk_blind":
                enqueue_specialist_investigation(
                    ctx,
                    parent_stage=stage_key,
                    specialist_key=spec_key,
                    question=f"Pre-stage specialist failed: {exc}",
                )
    return outputs


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
            _persist_specialist_output(ctx, stage_key=stage_key, spec_key=spec_key, env=env)
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
