"""Local LLM option generation for ITR clarifications."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from interview_mux.config import repo_root
from interview_mux.issue_severity_rules import ClassifiedIssue

_PROMPT_REL = "docs/prompts/_shared/specialists/artifact-clarification.system.txt"


def _load_system_prompt() -> str:
    path = repo_root() / _PROMPT_REL
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return (
        "You help operators resolve artifact validation issues. "
        "Respond with JSON only: "
        '{"recommended":"...", "options":[{"value":"...","label":"...","confidence":0.0,"reason":"..."}]}'
    )


def _rule_based_options(issue: ClassifiedIssue, artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    strategy = issue.repair_strategy or ""
    opts: list[dict[str, Any]] = []

    if issue.kind == "overlap" or strategy == "merge_overlap":
        opts = [
            {
                "value": "delete_segment",
                "label": f"Delete segment {issue.segment_id or 'duplicate'}",
                "confidence": 0.7,
                "reason": "Remove duplicate overlapping row",
            },
            {
                "value": "interviewer_question",
                "label": "Re-type as interviewer question",
                "confidence": 0.55,
                "reason": "Question marks or interviewer speaker",
            },
            {
                "value": "interviewee_answer",
                "label": "Re-type as interviewee answer",
                "confidence": 0.5,
                "reason": "Keep as guest response",
            },
        ]
    elif strategy == "infer_segment_types" or "all segments typed" in issue.message.lower():
        opts = [
            {"value": "interviewer_question", "label": "Interviewer question", "confidence": 0.6, "reason": "Taxonomy"},
            {"value": "interviewer_reaction", "label": "Interviewer reaction", "confidence": 0.5, "reason": "Taxonomy"},
            {"value": "interviewee_answer", "label": "Interviewee answer", "confidence": 0.5, "reason": "Taxonomy"},
        ]
    elif strategy == "fabricate_missing_segments":
        opts = [
            {
                "value": "fabricate_all",
                "label": "Auto-add missing segments from boundaries",
                "confidence": 0.85,
                "reason": "Fill coverage from boundary contract",
            },
        ]
    else:
        opts = [
            {"value": "accept_auto_repair", "label": "Apply suggested auto-repair", "confidence": 0.5, "reason": "Default"},
            {"value": "dismiss", "label": "Dismiss (non-blocking)", "confidence": 0.3, "reason": "Proceed without fix"},
        ]
    upstream = getattr(issue, "upstream_stage", None) or (issue.evidence or {}).get("upstream_stage")
    if upstream:
        label = str(upstream).replace("_", " ").title()
        opts.insert(
            0,
            {
                "value": f"rerun_upstream:{upstream}",
                "label": f"Re-run {label} (upstream)",
                "confidence": 0.75,
                "reason": "Root cause may be in upstream stage",
            },
        )
    return opts


def _parse_llm_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def infer_options_local_llm(
    ctx: Any,
    issue: ClassifiedIssue,
    artifacts: dict[str, Any],
    *,
    stage_key: str,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from interview_mux.artifact_issue_triage import triage_cfg

    tc = triage_cfg(cfg)
    if not tc.get("local_llm_for_important", True):
        return _rule_based_options(issue, artifacts)

    from interview_mux.local_llm_config import stage_on_quality_allowlist

    if not stage_on_quality_allowlist(stage_key, cfg):
        return _rule_based_options(issue, artifacts)

    context_snippet = ""
    if issue.segment_id and isinstance(artifacts.get("segments"), list):
        for row in artifacts["segments"]:
            if isinstance(row, dict) and str(row.get("segment_id")) == issue.segment_id:
                context_snippet = str(row.get("text") or "")[:400]
                break

    user_payload = {
        "stage_key": stage_key,
        "issue": {
            "message": issue.message,
            "kind": issue.kind,
            "segment_id": issue.segment_id,
            "repair_strategy": issue.repair_strategy,
        },
        "segment_excerpt": context_snippet,
    }

    try:
        from interview_mux.local_llm_runner import LocalLlmUnavailable, generate_local_chat

        raw, _meta = generate_local_chat(
            system=_load_system_prompt(),
            user=json.dumps(user_payload, indent=2),
            ctx=ctx,
            stage_key=f"{stage_key}__itr",
            max_tokens_override=512,
            cfg=cfg,
        )
        parsed = _parse_llm_json(raw)
        if parsed and isinstance(parsed.get("options"), list) and parsed["options"]:
            return parsed["options"][:6]
    except Exception:
        pass

    return _rule_based_options(issue, artifacts)
