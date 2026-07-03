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
from interview_mux.normalization_decision import (
    DownstreamAction,
    NormalizationDecision,
    resolve_normalization_decision,
    summarize_decisions,
)
from interview_mux.null_field_policy import find_null_fields, null_policy_cfg
from interview_mux.openai_structured_output import resolve_parent_stage_key

NormalizationActionKind = Literal["omit", "fabricate", "block"]


@dataclass
class NormalizationAction:
    kind: NormalizationActionKind
    path: str
    detail: str | None = None
    downstream: str | None = None


@dataclass
class NormalizationResult:
    normalized: dict[str, Any]
    ok: bool
    actions: list[NormalizationAction] = field(default_factory=list)
    decisions: list[NormalizationDecision] = field(default_factory=list)
    fabricate_calls: int = 0
    blocked_paths: list[str] = field(default_factory=list)
    suggested_downstream: list[str] = field(default_factory=list)
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
        if _delete_path(out, path):
            continue
        norm = re.sub(r"\[\d+\]", "", path).replace("..", ".")
        _delete_path(out, norm)
    return out


# Optional array-typed leaves — JSON null must become [] before schema verify.
_OPTIONAL_ARRAY_LEAVES: frozenset[str] = frozenset(
    {
        "segment_ids",
        "evidence_segment_ids",
        "depends_on_claim_ids",
        "topic_tags",
        "excluded_segment_ids",
        "keywords",
        "ordering_constraints",
    }
)


def _coerce_empty_strings_to_null(obj: Any) -> Any:
    """LLMs often emit '' for unavailable array/null fields — treat as JSON null."""
    if obj == "":
        return None
    if isinstance(obj, dict):
        return {k: _coerce_empty_strings_to_null(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_empty_strings_to_null(item) for item in obj]
    return obj


def _coerce_null_array_leaves(obj: Any) -> Any:
    """Coerce null optional array leaves to [] (e.g. emotional_beats[].segment_ids)."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            if val is None and key in _OPTIONAL_ARRAY_LEAVES:
                out[key] = []
            elif isinstance(val, (dict, list)):
                out[key] = _coerce_null_array_leaves(val)
            else:
                out[key] = val
        return out
    if isinstance(obj, list):
        return [_coerce_null_array_leaves(item) for item in obj]
    return obj


def _coerce_artifact_empty_strings(envelope: dict[str, Any]) -> dict[str, Any]:
    artifacts = envelope.get("artifacts")
    if not isinstance(artifacts, dict):
        return envelope
    out = copy.deepcopy(envelope)
    coerced = _coerce_empty_strings_to_null(artifacts)
    out["artifacts"] = _coerce_null_array_leaves(coerced)
    return out


def _collect_null_paths(stage_key: str, envelope: dict[str, Any]) -> list[str]:
    artifacts = envelope.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    return find_null_fields(stage_key, artifacts)


def _record_decision_meta(envelope: dict[str, Any], decisions: list[NormalizationDecision]) -> None:
    artifacts = envelope.get("artifacts")
    if not isinstance(artifacts, dict):
        return
    meta = artifacts.setdefault("_meta", {})
    summary = meta.setdefault("normalization_summary", {})
    agg = summarize_decisions(decisions)
    summary.update(agg)
    summary["updated_at"] = datetime.now(timezone.utc).isoformat()
    downstreams = sorted({d.downstream.value for d in decisions})
    if downstreams:
        summary["suggested_downstream"] = downstreams


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
        actions.append(
            NormalizationAction(
                kind="omit",
                path=p,
                downstream=DownstreamAction.OMIT_AND_ACKNOWLEDGE.value,
            )
        )
    summary = meta.setdefault("normalization_summary", {})
    summary["omit_count"] = int(summary.get("omit_count") or 0) + len(paths)
    summary["updated_at"] = datetime.now(timezone.utc).isoformat()
    return out, actions


def _verify_target(envelope: dict[str, Any], task_kind: str | None) -> dict[str, Any]:
    if task_kind == "arbiter":
        target = envelope.get("artifacts") or envelope
        return target if isinstance(target, dict) else envelope
    return envelope


def _decide_for_path(
    stage_key: str,
    path: str,
    *,
    prefer_omit: bool,
    cfg: dict[str, Any],
    error_kind: str | None = None,
) -> NormalizationDecision:
    return resolve_normalization_decision(
        stage_key,
        path,
        prefer_omit=prefer_omit,
        error_kind=error_kind,
        cfg=cfg,
    )


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

    Permissive decision tree (automation-first):
    1. OMIT nullable / commentary nulls → acknowledge, continue
    2. FABRICATE low-risk optional fields → benign defaults, continue
    3. BLOCK only evidentiary/critical → record downstream (volley_retry / micro_gap_fill)
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
    current = _coerce_artifact_empty_strings(parsed)
    all_actions: list[NormalizationAction] = []
    all_decisions: list[NormalizationDecision] = []
    fabricate_calls = 0
    blocked: list[str] = []
    suggested: list[str] = []

    if parent:
        proactive_decisions: list[tuple[str, NormalizationDecision]] = []
        for path in _collect_null_paths(parent, current):
            decision = _decide_for_path(parent, path, prefer_omit=prefer_omit, cfg=cfg, error_kind="null")
            proactive_decisions.append((path, decision))
            all_decisions.append(decision)
        proactive_omit = [p for p, d in proactive_decisions if d.action == FieldAction.OMIT]
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
            _record_decision_meta(current, all_decisions)
            return NormalizationResult(
                normalized=current,
                ok=True,
                actions=all_actions,
                decisions=all_decisions,
                fabricate_calls=fabricate_calls,
                blocked_paths=blocked,
                suggested_downstream=sorted(set(suggested)),
            )

        omit_paths: list[str] = []
        fabricate_paths: list[str] = []

        if parent:
            for path in _collect_null_paths(parent, current):
                decision = _decide_for_path(parent, path, prefer_omit=prefer_omit, cfg=cfg, error_kind="null")
                all_decisions.append(decision)
                suggested.append(decision.downstream.value)
                if decision.action == FieldAction.OMIT:
                    omit_paths.append(path)
                elif decision.action == FieldAction.FABRICATE:
                    fabricate_paths.append(path)
                else:
                    blocked.append(path)
                    all_actions.append(
                        NormalizationAction(
                            kind="block",
                            path=path,
                            detail=decision.reason,
                            downstream=decision.downstream.value,
                        )
                    )

        for err in verification.errors:
            path = parse_verification_error_path(err)
            if not path:
                continue
            decision = _decide_for_path(
                parent or "",
                path,
                prefer_omit=prefer_omit,
                cfg=cfg,
                error_kind="schema",
            )
            all_decisions.append(decision)
            suggested.append(decision.downstream.value)
            if decision.action == FieldAction.OMIT and path not in omit_paths:
                omit_paths.append(path)
            elif decision.action == FieldAction.FABRICATE and path not in fabricate_paths:
                fabricate_paths.append(path)
            elif decision.action == FieldAction.BLOCK:
                blocked.append(path)
                all_actions.append(
                    NormalizationAction(
                        kind="block",
                        path=path,
                        detail=decision.reason,
                        downstream=decision.downstream.value,
                    )
                )

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
                        all_actions.append(
                            NormalizationAction(
                                kind="fabricate",
                                path=p,
                                downstream=DownstreamAction.FABRICATE_BENIGN.value,
                            )
                        )

    target = _verify_target(current, task_kind)
    final = verify_llm_response(
        interaction_id,
        target,
        stage_key=stage_key,
        task_kind=task_kind,
    )
    _record_decision_meta(current, all_decisions)
    if ctx is not None and not final.ok and blocked:
        ctx.log(
            f"LLM normalizer blocked ({parent}): {', '.join(blocked[:4])} "
            f"→ downstream {sorted(set(suggested))[:3]}",
            level="warning",
            stage=parent or stage_key,
            action_id="llm.null.blocked",
            detail={
                "blocked_paths": blocked[:12],
                "suggested_downstream": sorted(set(suggested)),
            },
            origin="pipeline",
        )
    return NormalizationResult(
        normalized=current,
        ok=final.ok,
        actions=all_actions,
        decisions=all_decisions,
        fabricate_calls=fabricate_calls,
        blocked_paths=blocked,
        suggested_downstream=sorted(set(suggested)),
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
