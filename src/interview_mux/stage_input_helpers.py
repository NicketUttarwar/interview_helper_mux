"""Small helpers for stage input shaping (v2 — no volley/disfluency)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from interview_mux.run_context import RunContext


@dataclass
class StagePlan:
    task_line: str = ""
    prior_stages: tuple[str, ...] = ()
    profile_keys: tuple[str, ...] = ()
    investigation_kinds: frozenset[str] = field(default_factory=frozenset)
    max_investigations: int = 0


STAGE_PLANS: dict[str, StagePlan] = {}


def plan_for_stage(stage_key: str) -> StagePlan:
    return STAGE_PLANS.get(stage_key, StagePlan())


def _format_profile_slice(state: dict[str, Any], profile_keys: tuple[str, ...]) -> str:
    if not profile_keys:
        return ""
    parts: list[str] = []
    for key in profile_keys:
        val = state.get(key)
        if val:
            parts.append(f"{key}: {val}")
    return "\n".join(parts)[:2000]


def transcript_quality_for_ctx(ctx: RunContext) -> dict[str, Any]:
    """Optional transcript quality summary for LLM stage inputs."""
    out: dict[str, Any] = {}
    if ctx.artifact_exists("transcript/review_queue.json"):
        try:
            q = ctx.read_json("transcript/review_queue.json")
            if isinstance(q, dict):
                out["review_queue_size"] = len(q.get("items") or [])
        except Exception:
            pass
    return out


def attach_disfluency_context(payload: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    _ = ctx
    return payload


def interviewer_sample_lines(ctx: RunContext, *, limit: int = 8) -> list[str]:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    try:
        report = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return []
    lines: list[str] = []
    for row in report.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or row.get("line") or "").strip()
        if text:
            lines.append(text[:240])
        if len(lines) >= limit:
            break
    return lines


def truncation_flags_for_volley(volley: list[dict[str, str]] | None) -> list[str]:
    _ = volley
    return []


def volley_char_estimate(volley: list[dict[str, str]] | None) -> int:
    total = 0
    for msg in volley or []:
        if isinstance(msg, dict):
            total += len(str(msg.get("content") or ""))
    return total
