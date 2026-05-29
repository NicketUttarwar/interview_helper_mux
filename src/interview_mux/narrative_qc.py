from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _norm_name(value: str) -> str:
    return (value or "").strip().casefold()


def _topic_mapping_index(mappings: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        topic = mapping.get("topic")
        if isinstance(topic, str) and topic.strip():
            out[_norm_name(topic)] = mapping
    return out


def _documented_excludes(missing_coverage: list[Any]) -> set[str]:
    documented: set[str] = set()
    for item in missing_coverage:
        if not isinstance(item, dict):
            continue
        name = item.get("item")
        suggestion = (item.get("suggestion") or "").strip()
        if isinstance(name, str) and name.strip() and suggestion:
            documented.add(_norm_name(name))
    return documented


def _validate_topic_coverage(
    brief_topics: list[Any],
    audit: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    mappings = audit.get("topic_mappings") or []
    missing_coverage = audit.get("missing_coverage") or []
    by_topic = _topic_mapping_index(mappings)
    documented = _documented_excludes(missing_coverage)

    for topic_obj in brief_topics:
        if not isinstance(topic_obj, dict):
            continue
        name = topic_obj.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        norm = _norm_name(name)
        mapping = by_topic.get(norm)
        if mapping:
            covered = mapping.get("covered")
            segment_ids = mapping.get("segment_ids") or []
            if covered and segment_ids:
                continue
            if covered and not segment_ids:
                errors.append(
                    f'Topic "{name}": topic_mappings marks covered=true but segment_ids is empty'
                )
                continue
        if norm in documented:
            continue
        errors.append(
            f'Topic "{name}" from content_brief is not covered in coverage_audit '
            "(no topic_mappings with segment_ids and no documented exclude in missing_coverage)"
        )

    return errors


def _validate_chapters(selection: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    chapters = selection.get("chapters")
    if not isinstance(chapters, list):
        return errors

    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        label = chapter.get("title") or chapter.get("chapter_id") or f"chapter[{index}]"
        segment_ids = chapter.get("segment_ids")
        if not segment_ids:
            errors.append(f'Chapter "{label}" has zero segments in selection.json')
    return errors


def _validate_claim_mappings(brief: dict[str, Any], audit: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    claims = brief.get("key_claims") or []
    mappings = audit.get("claim_mappings") or []
    if not claims or not mappings:
        return errors
    by_claim = {
        _norm_name(str(m.get("claim", ""))): m for m in mappings if isinstance(m, dict) and m.get("claim")
    }
    for claim_obj in claims:
        if not isinstance(claim_obj, dict):
            continue
        name = claim_obj.get("claim") or claim_obj.get("name") or claim_obj.get("text")
        if not isinstance(name, str) or not name.strip():
            continue
        mapping = by_claim.get(_norm_name(name))
        if not mapping:
            errors.append(f'Claim "{name}" has no claim_mappings entry in coverage_audit')
            continue
        if mapping.get("covered") and not (mapping.get("segment_ids") or []):
            errors.append(f'Claim "{name}": covered=true but segment_ids is empty')
    return errors


def validate_flow1_narrative(
    ctx: RunContext,
    *,
    require_selection: bool = False,
) -> list[str]:
    """Return actionable Flow 1 narrative QC errors (empty list = pass)."""
    errors: list[str] = []

    if not ctx.artifact_exists("understanding/content_brief.json"):
        errors.append("Missing understanding/content_brief.json")
        return errors

    brief = ctx.read_json("understanding/content_brief.json")
    brief_topics = brief.get("topics") or []

    if not ctx.artifact_exists("flow_1_master/coverage_audit.json"):
        errors.append("Missing flow_1_master/coverage_audit.json")
    else:
        audit = ctx.read_json("flow_1_master/coverage_audit.json")
        errors.extend(_validate_topic_coverage(brief_topics, audit))
        errors.extend(_validate_claim_mappings(brief, audit))

    has_selection = ctx.artifact_exists("flow_1_master/selection.json")
    if require_selection and not has_selection:
        errors.append("Missing flow_1_master/selection.json")
    elif has_selection:
        selection = ctx.read_json("flow_1_master/selection.json")
        if isinstance(selection, dict):
            errors.extend(_validate_chapters(selection))

    return errors
