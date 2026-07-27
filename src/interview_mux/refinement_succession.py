"""Succession unlocks and mutual exclusions for refinement passes."""

from __future__ import annotations

from typing import Any

from interview_mux.refinement_catalog import refinement_cfg
from interview_mux.run_context import RunContext


def _succ() -> dict[str, Any]:
    return dict(refinement_cfg().get("succession") or {})


def priority_order() -> list[str]:
    return list(_succ().get("priority") or [])


def gap_path_resolved(ctx: RunContext) -> bool:
    """True when gap recompose done OR skip-copied OR framing disabled."""
    if ctx.is_done("gap_framing_recompose"):
        return True
    if ctx.artifact_exists("understanding/gap_fill_skip.json"):
        return True
    # skip-copy marker
    if ctx.artifact_exists("understanding/refinement_skip_copy.json"):
        return True
    if ctx.artifact_exists("understanding/gap_report.json"):
        # draft promoted without recompose stage
        plan = {}
        if ctx.artifact_exists("understanding/refinement_plan.json"):
            plan = ctx.read_json("understanding/refinement_plan.json") or {}
        for p in plan.get("passes") or []:
            if p.get("pass_id") == "gap_framing_recompose" and p.get("status") == "skip":
                return True
    return False


def is_unlocked(ctx: RunContext, pass_id: str) -> bool:
    unlocks = _succ().get("unlocks") or []
    # Passes with no unlock rule are open (subject to other gates)
    relevant = [u for u in unlocks if u.get("unlock") == pass_id]
    if not relevant:
        return True
    for rule in relevant:
        if rule.get("after_accept") == "gap_framing_recompose":
            if ctx.is_done("gap_framing_recompose"):
                return True
        if rule.get("after_accept_or_skip_copy") == "gap_framing_recompose":
            if gap_path_resolved(ctx):
                return True
        if rule.get("after_signal") == "post_gap_topic_holes":
            if ctx.artifact_exists("master/coverage_audit.json"):
                cov = ctx.read_json("master/coverage_audit.json")
                holes = (cov or {}).get("uncovered_topics") or (cov or {}).get("gaps") if isinstance(cov, dict) else None
                if holes:
                    return True
    return False


def mutex_blocked(ctx: RunContext, pass_id: str) -> bool:
    for rule in _succ().get("mutex") or []:
        passes = list(rule.get("passes") or [])
        if pass_id not in passes:
            continue
        others = [p for p in passes if p != pass_id]
        for other in others:
            if ctx.is_done(other):
                return True
            # activated in plan this run
            if ctx.artifact_exists("understanding/refinement_plan.json"):
                plan = ctx.read_json("understanding/refinement_plan.json") or {}
                for p in plan.get("passes") or []:
                    if p.get("pass_id") == other and p.get("status") == "activate":
                        return True
    return False
