"""Mid-tier / deterministic fabrication for normalizable LLM artifact fields."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.field_necessity_registry import NEVER_FABRICATE_PATHS
from interview_mux.field_path_match import path_matches_pattern
from interview_mux.null_field_policy import null_policy_cfg


def _leaf_name(path: str) -> str:
    part = path.split(".")[-1]
    if part.endswith("]"):
        part = part.split("[")[-1].rstrip("]")
    return part


# Top-level / nested array fields — never fabricate as empty string.
_ARRAY_FIELD_LEAVES: frozenset[str] = frozenset(
    {
        "era_tags",
        "narrative_beats",
        "topic_relationships",
        "hypotheses",
        "themes",
        "themes_append",
        "topics",
        "key_claims",
        "jargon_glossary",
        "emotional_beats",
        "warnings",
        "gaps",
        "highlights",
        "transitions",
        "chapters",
        "segments",
        "boundaries",
        "evaluations",
        "speakers",
        "topic_tags",
        "excluded_segment_ids",
        "segment_ids",
        "evidence_segment_ids",
        "depends_on_claim_ids",
        "ordering_constraints",
        "keywords",
        "shard_plan",
    }
)


def deterministic_fabricated_value(path: str, *, stage_key: str | None = None) -> Any:
    """Benign default when LLM fabricate is disabled or in tests."""
    leaf = _leaf_name(path)
    if leaf == "notes":
        return "No additional notes."
    if leaf == "warnings":
        return []
    if leaf in {"subtitle", "keywords"}:
        return "" if leaf == "subtitle" else []
    if leaf == "audience":
        return "General audience"
    if leaf in {"tone", "tone_class"}:
        return "conversational"
    if leaf == "format_class":
        return "one_on_one"
    if leaf == "format_notes":
        return "Standard interview format."
    if leaf in {"pacing", "interviewer_style", "interviewee_style"}:
        return "moderate"
    if leaf == "confidence":
        return 0.75
    if leaf == "label":
        return "sample"
    if leaf == "description":
        return "See transcript for details."
    if leaf == "title":
        return "Episode"
    if leaf == "one_line_summary":
        return "Interview summary pending review."
    if leaf == "reason":
        return "Automated placeholder — review if surfaced to operator."
    if leaf == "emotional_beats":
        return []
    if leaf == "jargon_glossary":
        return []
    if leaf == "key_claims":
        return []
    if leaf == "topic_tags":
        return []
    if leaf == "excluded_segment_ids":
        return []
    if leaf == "gaps":
        return []
    if leaf in _ARRAY_FIELD_LEAVES:
        return []
    return ""


def fabricate_field_values(
    ctx: Any,
    stage_key: str,
    artifacts: dict[str, Any],
    paths: list[str],
    *,
    volley: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Apply fabricated values at paths. Returns (updated_artifacts, provenance_rows).
    Uses deterministic benign defaults; optional LLM batch when fabricate_enabled.
    """
    cfg = null_policy_cfg()
    if not cfg.get("fabricate_enabled", True):
        provenance: list[dict[str, Any]] = []
        out = dict(artifacts)
        for path in paths:
            if any(path_matches_pattern(path, pat) for pat in NEVER_FABRICATE_PATHS):
                continue
            val = deterministic_fabricated_value(path, stage_key=stage_key)
            _set_path(out, path, val)
            provenance.append(
                {
                    "path": path,
                    "action": "fabricate",
                    "source": "deterministic",
                    "model_id": None,
                }
            )
        return out, provenance

    max_paths = int(cfg.get("fabricate_max_paths_per_call", 8))
    batch = paths[:max_paths]
    provenance = []
    out = dict(artifacts)

    # Deterministic benign defaults (mid-tier LLM hook point for future OM-F* calls)
    for path in batch:
        if any(path_matches_pattern(path, pat) for pat in NEVER_FABRICATE_PATHS):
            continue
        val = deterministic_fabricated_value(path, stage_key=stage_key)
        _set_path(out, path, val)
        prompt_seed = f"{stage_key}:{path}"
        provenance.append(
            {
                "path": path,
                "action": "fabricate",
                "source": "deterministic_benign",
                "model_id": cfg.get("fabricate_model_tier", "mid"),
                "prompt_hash": hashlib.sha256(prompt_seed.encode()).hexdigest()[:12],
            }
        )
        if ctx is not None:
            ctx.log(
                f"Fabricated benign value for {path} ({stage_key})",
                level="info",
                stage=stage_key,
                action_id="llm.null.fabricated",
                detail={"path": path, "stage_key": stage_key},
                origin="pipeline",
            )
    return out, provenance


def _set_path(obj: dict[str, Any], path: str, value: Any) -> None:
    """Set value at dotted path with [] array wildcard."""
    import re

    parts = re.split(r"\.(?![^\[]*\])", path)
    cur: Any = obj
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        m = re.match(r"^(.+)\[(\d+|\])\]$", part)
        if m:
            key, idx = m.group(1), m.group(2)
            arr = cur.setdefault(key, [])
            if not isinstance(arr, list):
                return
            if idx == "]":
                if is_last:
                    if arr and isinstance(arr[-1], dict):
                        # leaf on last array element — unsupported pattern
                        pass
                    return
                if not arr:
                    arr.append({})
                cur = arr[-1]
            else:
                j = int(idx)
                while len(arr) <= j:
                    arr.append({})
                if is_last:
                    arr[j] = value
                    return
                cur = arr[j]
        else:
            if is_last:
                cur[part] = value
                return
            if part not in cur or not isinstance(cur[part], dict):
                cur[part] = {}
            cur = cur[part]


def merge_fabrication_meta(artifacts: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return artifacts
    meta = artifacts.setdefault("_meta", {})
    fab = meta.setdefault("fabricated_fields", [])
    fab.extend(rows)
    meta["fabrication_updated_at"] = datetime.now(timezone.utc).isoformat()
    return artifacts
