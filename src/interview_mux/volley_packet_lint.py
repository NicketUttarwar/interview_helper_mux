"""Strip pipeline metadata from LLM user packets; require tape-derived slices."""

from __future__ import annotations

from typing import Any

_FORBIDDEN_KEY_SUBSTR = (
    "stage_done",
    "path_ok",
    "file_exists",
    "exists_on_disk",
    "artifact_exists",
    "e2e_soft",
    "e2e_heal",
    "fingerprint_hash",
    "run_meta",
)

_TAPE_KEYS = (
    "transcript",
    "segments",
    "manifest",
    "spine",
    "segment_text",
    "excerpts",
    "words",
    "turns",
    "talking_points",
    "claims",
    "gap_evaluations",
    "interviewer_lines",
    "ordered_segment_ids",
    "must_keep_segment_ids",
    "stt_island_excerpts",
    "topic_excerpts",
    "content_brief",
    "narrative_plan",
    "pairs",
    "combined_seam_text",
)


def _forbidden_key(key: str) -> bool:
    k = str(key or "").strip().lower()
    if k in {"exists", "path_ok", "stage_done", "artifact_exists"}:
        return True
    return any(s in k for s in _FORBIDDEN_KEY_SUBSTR)


def strip_forbidden_metadata(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: strip_forbidden_metadata(v)
            for k, v in obj.items()
            if not _forbidden_key(str(k))
        }
    if isinstance(obj, list):
        return [strip_forbidden_metadata(x) for x in obj]
    return obj


def has_tape_derived_slice(obj: Any, *, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if any(t in lk for t in _TAPE_KEYS) and v not in (None, "", [], {}):
                return True
            if has_tape_derived_slice(v, depth=depth + 1):
                return True
    elif isinstance(obj, list):
        return any(has_tape_derived_slice(x, depth=depth + 1) for x in obj[:12])
    elif isinstance(obj, str) and len(obj.strip()) >= 40:
        return True
    return False


def lint_llm_user_payload(payload: Any, *, require_tape: bool = True) -> Any:
    cleaned = strip_forbidden_metadata(payload)
    if require_tape and not has_tape_derived_slice(cleaned):
        raise ValueError("LLM user packet has no tape-derived slice")
    return cleaned
