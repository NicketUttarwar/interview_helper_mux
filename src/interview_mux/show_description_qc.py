"""Deterministic validators for Flow 3 show description (H-F3-01 evidence anchors)."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext

_WORD_TOLERANCE = 15


def _norm(value: str) -> str:
    return (value or "").strip().casefold()


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))


def _segment_ids_from_manifest(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return set()
    manifest = ctx.read_json("segments/manifest.json")
    ids: set[str] = set()
    for seg in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
        if isinstance(seg, dict):
            sid = seg.get("segment_id") or seg.get("id")
            if sid:
                ids.add(str(sid))
    return ids


def validate_show_description(
    ctx: RunContext,
    doc: dict[str, Any],
    *,
    brief: dict[str, Any] | None = None,
) -> list[str]:
    """Return actionable show-description QC errors (empty list = pass)."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["Show description artifact is not an object"]

    evidence = doc.get("evidence_segment_ids") or []
    if not evidence:
        errors.append("evidence_segment_ids must be non-empty")
    else:
        valid_ids = _segment_ids_from_manifest(ctx)
        if valid_ids:
            for sid in evidence:
                if str(sid) not in valid_ids:
                    errors.append(f'evidence_segment_ids contains unknown segment_id "{sid}"')

    body = str(doc.get("description_markdown") or "").replace("\\n", "\n")
    declared = doc.get("word_count")
    if declared is not None:
        actual = _word_count(body)
        if abs(int(declared) - actual) > _WORD_TOLERANCE:
            errors.append(
                f"word_count {declared} does not match description_markdown ({actual} words, "
                f"tolerance ±{_WORD_TOLERANCE})"
            )

    hook = str(doc.get("hook_sentence") or "").strip()
    if hook and body and not body.strip().startswith(hook[: min(len(hook), 80)]):
        errors.append("hook_sentence must appear at the start of description_markdown")

    if brief is None and ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
    if isinstance(brief, dict):
        themes_highlighted = {_norm(t) for t in (doc.get("themes_highlighted") or []) if isinstance(t, str)}
        for claim in brief.get("key_claims") or []:
            if not isinstance(claim, dict):
                continue
            name = claim.get("claim") or claim.get("name") or claim.get("text")
            if not isinstance(name, str) or not name.strip():
                continue
            norm = _norm(name)
            if norm not in themes_highlighted and norm not in _norm(body):
                errors.append(
                    f'key_claim "{name}" from content_brief not reflected in themes_highlighted or description'
                )

    return errors
