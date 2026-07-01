from __future__ import annotations

import json
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import run_prompt_envelope

ARBITER_PROMPT = "_shared/arbiter.system.txt"


def run_llm_arbiter(
    *,
    ctx: RunContext | None = None,
    stage_key: str,
    attempt_number: int,
    envelope: dict[str, Any],
    schema_errors: list[str],
    context_chars: int,
    truncation_flags: list[str],
    stage_expectations: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "stage_key": stage_key,
        "attempt_number": attempt_number,
        "envelope_summary": _summarize_envelope(envelope),
        "schema_errors": schema_errors,
        "context_chars": context_chars,
        "truncation_flags": truncation_flags,
        "stage_expectations": stage_expectations,
    }
    try:
        verdict_env = run_prompt_envelope(
            "_arbiter",
            ARBITER_PROMPT,
            user_content=_compact_json(payload),
            ctx=ctx,
            include_preamble=False,
            task_kind="arbiter",
            call_attempt=attempt_number,
            record_stage_key=stage_key,
        )
    except (ValueError, json.JSONDecodeError):
        return {
            "verdict": "enqueue_investigation",
            "confidence": 0.0,
            "gaps": ["Arbiter response was not valid JSON."],
            "shard_plan": [],
            "suggested_investigation": {
                "kind": "arbiter_parse_failure",
                "question": f"Re-run {stage_key} after arbiter parse failure.",
                "blocking": True,
            },
            "reasoning_summary": "Arbiter call failed JSON parse; enqueueing investigation.",
        }
    return _normalize_arbiter_result(verdict_env.get("artifacts") or verdict_env)


def _summarize_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    artifacts = envelope.get("artifacts") or {}
    counts: dict[str, int] = {}
    for key, value in artifacts.items():
        if isinstance(value, list):
            counts[key] = len(value)
        elif isinstance(value, dict):
            counts[key] = len(value)
        else:
            counts[key] = 1
    return {
        "status": envelope.get("status"),
        "confidence": envelope.get("confidence"),
        "reasoning_summary": envelope.get("reasoning_summary"),
        "artifact_keys": list(artifacts.keys()),
        "artifact_counts": counts,
    }


def _normalize_arbiter_result(raw: dict[str, Any]) -> dict[str, Any]:
    verdict = str(raw.get("verdict", "")).strip() or "enqueue_investigation"
    out = {
        "verdict": verdict,
        "confidence": float(raw.get("confidence", 0.0) or 0.0),
        "gaps": raw.get("gaps") or [],
        "shard_plan": raw.get("shard_plan") or [],
        "suggested_investigation": raw.get("suggested_investigation"),
        "reasoning_summary": str(raw.get("reasoning_summary", "") or ""),
    }
    if out["verdict"] == "decompose" and not out["shard_plan"]:
        out["verdict"] = "enqueue_investigation"
        out["gaps"] = [*out["gaps"], "Arbiter requested decompose without shard plan."]
    return out


def _compact_json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
