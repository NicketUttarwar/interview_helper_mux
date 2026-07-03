"""Explicit JSON null semantics for LLM artifacts — critical vs nullable field policy."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.field_path_match import path_matches_pattern
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

# Irreplaceable paths per stage — JSON null triggers hard stop.
CRITICAL_FIELDS: dict[str, frozenset[str]] = {
    "speaker_roles": frozenset({"speakers", "speakers[].role", "speakers[].speaker_id"}),
    "content_context": frozenset({"thesis", "topics", "topics[].name", "topics[].summary"}),
    "content_brief_reanchor": frozenset(
        {"thesis", "topics", "topics[].name", "topics[].summary", "topics[].segment_ids"}
    ),
    "boundary_detection": frozenset({"boundaries"}),
    "segment_classification": frozenset({"segments", "segments[].segment_id", "segments[].type"}),
    "missing_framing": frozenset({"evaluations"}),
    "optimal_questions": frozenset({"gaps"}),
    "topic_coverage_audit": frozenset({"coverage_score"}),
    "narrative_arc_plan": frozenset({"chapters"}),
    "full_master_ranking": frozenset({"ordered_segment_ids"}),
    "highlight_selection": frozenset({"highlights"}),
    "transitions": frozenset({"transitions"}),
    "podcast_show_description": frozenset({"description"}),
}

# Optional paths where JSON null means "unavailable" — acknowledged and excluded from volleys.
NULLABLE_FIELDS: dict[str, frozenset[str]] = {
    "speaker_roles": frozenset({"speakers[].label", "speakers[].confidence", "notes"}),
    "content_context": frozenset(
        {
            "audience",
            "jargon_glossary",
            "emotional_beats",
            "key_claims",
            "topics[].segment_ids",
            "topics[].approx_time_range",
            "key_claims[].approx_time_range",
            "key_claims[].segment_ids",
            "key_claims[].evidence_segment_ids",
            "emotional_beats[].segment_ids",
            "emotional_beats[].description",
            "jargon_glossary[].first_segment_id",
        }
    ),
    "content_brief_reanchor": frozenset(
        {
            "audience",
            "jargon_glossary",
            "emotional_beats",
            "key_claims",
            "topic_relationships",
            "key_claims[].approx_time_range",
            "emotional_beats[].segment_ids",
            "emotional_beats[].description",
            "jargon_glossary[].first_segment_id",
        }
    ),
    "boundary_detection": frozenset({"warnings", "notes"}),
    "segment_classification": frozenset({"segments[].topic_tags", "segments[].notes"}),
    "missing_framing": frozenset({"evaluations[].notes"}),
    "optimal_questions": frozenset({"gaps[].notes"}),
    "topic_coverage_audit": frozenset({"gaps", "notes"}),
    "narrative_arc_plan": frozenset({"ordering_constraints", "notes"}),
    "full_master_ranking": frozenset({"excluded_segment_ids", "notes"}),
    "highlight_selection": frozenset({"notes"}),
    "transitions": frozenset({"transitions[].notes"}),
    "podcast_show_description": frozenset({"subtitle", "keywords"}),
}


def null_policy_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    base = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "enabled": True,
        "allow_unavailable_reason": True,
        "hard_stop_on_critical_null": True,
        "exclude_from_volleys": True,
        "fabricate_enabled": True,
        "prefer_omit_over_fabricate": True,
        "permissive_mode": True,
        "auto_fabricate_unknown_optional": True,
        "block_only_evidentiary_critical": True,
    }
    raw = base.get("llm_null_policy") or {}
    return {**defaults, **raw}


def null_policy_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(null_policy_cfg(cfg).get("enabled", True))


def critical_fields_for_stage(stage_key: str) -> frozenset[str]:
    return CRITICAL_FIELDS.get(stage_key, frozenset())


def nullable_fields_for_stage(stage_key: str) -> frozenset[str]:
    return NULLABLE_FIELDS.get(stage_key, frozenset())


def _walk_null_paths(
    obj: Any,
    *,
    prefix: str = "",
    paths: list[str] | None = None,
) -> list[str]:
    out = paths if paths is not None else []
    if obj is None:
        if prefix:
            out.append(prefix)
        return out
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key.startswith("_"):
                continue
            child = f"{prefix}.{key}" if prefix else key
            if val is None:
                out.append(child)
            elif isinstance(val, (dict, list)):
                _walk_null_paths(val, prefix=child, paths=out)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            child = f"{prefix}[{i}]"
            if item is None:
                out.append(child)
            elif isinstance(item, (dict, list)):
                _walk_null_paths(item, prefix=child, paths=out)
            elif isinstance(item, dict):
                for k, v in item.items():
                    if k.startswith("_"):
                        continue
                    leaf = f"{prefix}[].{k}"
                    if v is None:
                        out.append(leaf.replace(f"[{i}]", "[]"))
    return out


def find_null_fields(stage_key: str, artifacts: dict[str, Any] | None) -> list[str]:
    if not artifacts or not isinstance(artifacts, dict):
        return []
    raw = _walk_null_paths(artifacts)
    # Normalize list indices to [] pattern for policy matching
    normalized: list[str] = []
    for p in raw:
        import re

        norm = re.sub(r"\[\d+\]", "[]", p)
        if norm not in normalized:
            normalized.append(norm)
    return normalized


def _is_critical_null(stage_key: str, path: str) -> bool:
    critical = critical_fields_for_stage(stage_key)
    for pat in critical:
        if path_matches_pattern(path, pat):
            return True
    return False


def _is_nullable_path(stage_key: str, path: str) -> bool:
    nullable = nullable_fields_for_stage(stage_key)
    for pat in nullable:
        if path_matches_pattern(path, pat):
            return True
    return False


def partition_nulls(
    stage_key: str,
    paths: list[str],
) -> tuple[list[str], list[str]]:
    critical: list[str] = []
    acknowledged: list[str] = []
    for path in paths:
        if _is_critical_null(stage_key, path):
            critical.append(path)
        elif _is_nullable_path(stage_key, path):
            acknowledged.append(path)
        else:
            # Unknown null — permissive default: acknowledge (omit) rather than hard stop.
            acknowledged.append(path)
    return critical, acknowledged


def null_acknowledged_paths(artifacts: dict[str, Any] | None) -> list[str]:
    if not isinstance(artifacts, dict):
        return []
    meta = artifacts.get("_meta") or {}
    ack = meta.get("null_acknowledged") or {}
    paths = ack.get("paths") or []
    return [str(p) for p in paths if p]


def acknowledge_null_fields(
    ctx: Any,
    stage_key: str,
    artifacts: dict[str, Any],
    *,
    envelope_meta: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Annotate _meta.null_acknowledged; return (artifacts, critical_nulls, acknowledged_nulls)."""
    if not null_policy_enabled():
        return artifacts, [], []

    out = copy.deepcopy(artifacts)
    paths = find_null_fields(stage_key, out)
    if not paths:
        return out, [], []

    critical, acknowledged = partition_nulls(stage_key, paths)
    if acknowledged:
        meta = out.setdefault("_meta", {})
        ack = meta.setdefault("null_acknowledged", {})
        existing = set(ack.get("paths") or [])
        merged = sorted(existing | set(acknowledged))
        ack["paths"] = merged
        ack["updated_at"] = datetime.now(timezone.utc).isoformat()

    if acknowledged and ctx is not None:
        rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key, "")
        llm_meta = envelope_meta or {}
        ctx.log(
            f"LLM null acknowledged ({stage_key}): {len(acknowledged)} nullable field(s) unavailable",
            level="info",
            stage=stage_key,
            action_id="llm.null.acknowledged",
            detail={
                "stage_key": stage_key,
                "paths": acknowledged[:12],
                "artifact_path": rel,
                "model_id": llm_meta.get("model_id"),
                "task_kind": llm_meta.get("task_kind"),
                "llm_call_path": llm_meta.get("llm_call_path"),
            },
            origin="pipeline",
        )

    return out, critical, acknowledged


def log_critical_null_blocked(
    ctx: Any,
    stage_key: str,
    critical_paths: list[str],
    *,
    artifacts: dict[str, Any] | None = None,
    envelope: dict[str, Any] | None = None,
    arbiter_result: dict[str, Any] | None = None,
    volley: list[dict[str, str]] | None = None,
    llm_call_path: str | None = None,
) -> None:
    llm_meta = (envelope or {}).get("_llm_meta") or {}
    path = llm_call_path or llm_meta.get("llm_call_path")
    volley_chars = sum(len(m.get("content", "")) for m in (volley or []))
    excerpt = {}
    if artifacts:
        excerpt = {k: artifacts.get(k) for k in list(artifacts.keys())[:6]}
    ctx.log(
        f"CRITICAL: {stage_key} — irreplaceable field(s) null: {', '.join(critical_paths[:4])}. "
        f"API call saved at {path or 'n/a'}. Stage blocked; operator action required.",
        level="error",
        stage=stage_key,
        action_id="llm.null.critical_blocked",
        detail={
            "stage_key": stage_key,
            "critical_paths": critical_paths,
            "artifact_excerpt": json.dumps(excerpt, default=str)[:1500],
            "envelope_status": (envelope or {}).get("status"),
            "arbiter_verdict": (arbiter_result or {}).get("verdict"),
            "model_id": llm_meta.get("model_id"),
            "task_kind": llm_meta.get("task_kind"),
            "request_turns": len(volley or []),
            "llm_call_path": path,
            "volley_char_estimate": volley_chars,
        },
        origin="pipeline",
    )


def strip_null_leaves_for_volley(obj: Any, *, acknowledged_paths: frozenset[str] | None = None) -> Any:
    """Replace null leaves with compact unavailable markers for downstream volley shaping."""
    if obj is None:
        return {"_unavailable": True}
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            if key == "_meta":
                out[key] = val
                continue
            if val is None:
                out[key] = {"_unavailable": True}
            else:
                out[key] = strip_null_leaves_for_volley(val, acknowledged_paths=acknowledged_paths)
        return out
    if isinstance(obj, list):
        return [strip_null_leaves_for_volley(item, acknowledged_paths=acknowledged_paths) for item in obj]
    return obj
