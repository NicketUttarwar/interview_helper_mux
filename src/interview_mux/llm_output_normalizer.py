"""Global LLM output normalization — omit | fabricate | block before schema verification."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.field_necessity_registry import (
    FieldAction,
    classify_field_path,
    parse_verification_error_path,
)
from interview_mux.llm_fabricate import fabricate_field_values, merge_fabrication_meta
from interview_mux.llm_response_verify import verify_llm_response
from interview_mux.null_field_policy import find_null_fields, null_policy_cfg
from interview_mux.openai_structured_output import resolve_parent_stage_key

NormalizationActionKind = Literal["omit", "fabricate", "block"]


@dataclass
class NormalizationAction:
    kind: NormalizationActionKind
    path: str
    detail: str | None = None


@dataclass
class NormalizationResult:
    normalized: dict[str, Any]
    ok: bool
    actions: list[NormalizationAction] = field(default_factory=list)
    fabricate_calls: int = 0
    blocked_paths: list[str] = field(default_factory=list)
    verification_errors: list[str] = field(default_factory=list)


def _delete_path(obj: Any, path: str) -> bool:
    """Remove key at path; supports speakers[0].notes and notes."""
    if not isinstance(obj, dict):
        return False
    parts = re.split(r"\.(?![^\[]*\])", path)
    if len(parts) == 1 and "[" not in parts[0]:
        return obj.pop(parts[0], None) is not None

    cur: Any = obj
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        m = re.match(r"^(.+)\[(\d+)\]$", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if not isinstance(cur, dict) or key not in cur:
                return False
            arr = cur[key]
            if not isinstance(arr, list) or idx >= len(arr):
                return False
            if is_last:
                if isinstance(arr[idx], dict):
                    # delete leaf inside object at index — part was wrong split
                    return False
                arr.pop(idx)
                return True
            cur = arr[idx]
        else:
            if is_last:
                if isinstance(cur, dict):
                    return cur.pop(part, None) is not None
                return False
            if not isinstance(cur, dict) or part not in cur:
                return False
            cur = cur[part]
    return False


def _delete_null_leaves(artifacts: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    out = copy.deepcopy(artifacts)
    for path in paths:
        # Try exact path first
        if _delete_path(out, path):
            continue
        norm = re.sub(r"\[\d+\]", "", path).replace("..", ".")
        _delete_path(out, norm)
    return out


def _collect_null_paths(stage_key: str, envelope: dict[str, Any]) -> list[str]:
    artifacts = envelope.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    return find_null_fields(stage_key, artifacts)


def _apply_omit_to_envelope(
    envelope: dict[str, Any],
    stage_key: str,
    paths: list[str],
) -> tuple[dict[str, Any], list[NormalizationAction]]:
    actions: list[NormalizationAction] = []
    out = copy.deepcopy(envelope)
    artifacts = out.get("artifacts")
    if not isinstance(artifacts, dict):
        return out, actions
    updated = _delete_null_leaves(artifacts, paths)
    meta = updated.setdefault("_meta", {})
    ack = meta.setdefault("null_acknowledged", {})
    existing = set(ack.get("paths") or [])
    merged = sorted(existing | set(paths))
    ack["paths"] = merged
    ack["updated_at"] = datetime.now(timezone.utc).isoformat()
    out["artifacts"] = updated
    for p in paths:
        actions.append(NormalizationAction(kind="omit", path=p))
    summary = meta.setdefault("normalization_summary", {})
    summary["omit_count"] = int(summary.get("omit_count") or 0) + len(paths)
    summary["updated_at"] = datetime.now(timezone.utc).isoformat()
    return out, actions


def _verify_target(envelope: dict[str, Any], task_kind: str | None) -> dict[str, Any]:
    if task_kind == "arbiter":
        target = envelope.get("artifacts") or envelope
        return target if isinstance(target, dict) else envelope
    return envelope


def normalize_llm_response(
    ctx: Any,
    *,
    interaction_id: str,
    parsed: dict[str, Any],
    stage_key: str | None = None,
    task_kind: str | None = None,
    volley: list[dict[str, str]] | None = None,
    max_passes: int = 3,
) -> NormalizationResult:
    """
    Normalize null/type issues before verify_llm_response.
    Returns post-normalized envelope and whether verification passes.
    """
    cfg = null_policy_cfg()
    if task_kind == "arbiter":
        verification = verify_llm_response(
            interaction_id,
            _verify_target(parsed, task_kind),
            stage_key=stage_key,
            task_kind=task_kind,
        )
        return NormalizationResult(
            normalized=parsed,
            ok=verification.ok,
            verification_errors=verification.errors,
        )
    if not cfg.get("enabled", True):
        verification = verify_llm_response(
            interaction_id,
            _verify_target(parsed, task_kind),
            stage_key=stage_key,
            task_kind=task_kind,
        )
        return NormalizationResult(
            normalized=parsed,
            ok=verification.ok,
            verification_errors=verification.errors,
        )

    parent = resolve_parent_stage_key(stage_key or "") or stage_key or ""
    prefer_omit = bool(cfg.get("prefer_omit_over_fabricate", True))
    current = copy.deepcopy(parsed)
    all_actions: list[NormalizationAction] = []
    fabricate_calls = 0
    blocked: list[str] = []

    # Proactive omit of nullable null fields before verification
    if parent:
        proactive_omit = [
            p
            for p in _collect_null_paths(parent, current)
            if classify_field_path(parent, p, prefer_omit=prefer_omit) == FieldAction.OMIT
        ]
        if proactive_omit:
            current, proactive_actions = _apply_omit_to_envelope(current, parent, proactive_omit)
            all_actions.extend(proactive_actions)

    for _pass in range(max_passes):
        target = _verify_target(current, task_kind)
        verification = verify_llm_response(
            interaction_id,
            target,
            stage_key=stage_key,
            task_kind=task_kind,
        )
        if verification.ok:
            return NormalizationResult(
                normalized=current,
                ok=True,
                actions=all_actions,
                fabricate_calls=fabricate_calls,
                blocked_paths=blocked,
            )

        omit_paths: list[str] = []
        fabricate_paths: list[str] = []

        # Null fields in artifacts
        if parent:
            for path in _collect_null_paths(parent, current):
                action = classify_field_path(parent, path, prefer_omit=prefer_omit)
                if action == FieldAction.OMIT:
                    omit_paths.append(path)
                elif action == FieldAction.FABRICATE:
                    fabricate_paths.append(path)
                else:
                    blocked.append(path)
                    all_actions.append(NormalizationAction(kind="block", path=path))

        # Paths from verification errors (e.g. type mismatch)
        for err in verification.errors:
            path = parse_verification_error_path(err)
            if not path:
                continue
            action = classify_field_path(parent or "", path, prefer_omit=prefer_omit)
            if action == FieldAction.OMIT and path not in omit_paths:
                omit_paths.append(path)
            elif action == FieldAction.FABRICATE and path not in fabricate_paths:
                fabricate_paths.append(path)
            elif action == FieldAction.BLOCK:
                blocked.append(path)

        if not omit_paths and not fabricate_paths:
            break

        if omit_paths:
            current, omit_actions = _apply_omit_to_envelope(current, parent, omit_paths)
            all_actions.extend(omit_actions)
            if ctx is not None:
                ctx.log(
                    f"LLM null omitted ({parent}): {', '.join(omit_paths[:4])}",
                    level="info",
                    stage=parent or stage_key,
                    action_id="llm.null.omitted",
                    detail={"paths": omit_paths[:12], "stage_key": parent},
                    origin="pipeline",
                )

        if fabricate_paths and cfg.get("fabricate_enabled", True):
            max_calls = int(cfg.get("fabricate_max_calls_per_stage_attempt", 2))
            if fabricate_calls < max_calls:
                artifacts = current.get("artifacts") or {}
                if isinstance(artifacts, dict):
                    updated, prov = fabricate_field_values(
                        ctx,
                        parent,
                        artifacts,
                        fabricate_paths,
                        volley=volley,
                    )
                    merge_fabrication_meta(updated, prov)
                    current["artifacts"] = updated
                    fabricate_calls += 1
                    for p in fabricate_paths:
                        all_actions.append(NormalizationAction(kind="fabricate", path=p))

    target = _verify_target(current, task_kind)
    final = verify_llm_response(
        interaction_id,
        target,
        stage_key=stage_key,
        task_kind=task_kind,
    )
    if ctx is not None and not final.ok and blocked:
        ctx.log(
            f"LLM normalizer blocked ({parent}): {', '.join(blocked[:4])}",
            level="error",
            stage=parent or stage_key,
            action_id="llm.null.blocked",
            detail={"blocked_paths": blocked[:12]},
            origin="pipeline",
        )
    return NormalizationResult(
        normalized=current,
        ok=final.ok,
        actions=all_actions,
        fabricate_calls=fabricate_calls,
        blocked_paths=blocked,
        verification_errors=final.errors,
    )


def normalize_envelope_for_stage(
    ctx: Any,
    envelope: dict[str, Any],
    *,
    stage_key: str,
    interaction_id: str | None = None,
    task_kind: str = "primary",
    volley: list[dict[str, str]] | None = None,
) -> NormalizationResult:
    """Convenience wrapper for stage routing / resilience paths."""
    from interview_mux.llm_interaction_registry import resolve_interaction_id

    iid = interaction_id or resolve_interaction_id(
        stage_key=stage_key,
        task_kind=task_kind,
        provider="openai",
    )
    return normalize_llm_response(
        ctx,
        interaction_id=iid,
        parsed=envelope,
        stage_key=stage_key,
        task_kind=task_kind,
        volley=volley,
    )
