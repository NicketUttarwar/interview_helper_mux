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
            segment_ids = [str(s) for s in (mapping.get("segment_ids") or []) if s]
            if covered and segment_ids:
                continue
            if covered and not segment_ids:
                errors.append(
                    f'Topic "{name}": topic_mappings marks covered=true but segment_ids is empty'
                )
                continue
            # covered=false with remaining segment_ids still counts as covered when
            # those ids remain in the final air order — callers often flip the flag
            # after pruning without clearing segment_ids.
            if segment_ids and covered is False:
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

    ordered = [
        str(sid)
        for sid in (selection.get("ordered_segment_ids") or [])
        if sid
    ]
    order_index = {sid: idx for idx, sid in enumerate(ordered)}

    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        label = chapter.get("title") or chapter.get("chapter_id") or f"chapter[{index}]"
        segment_ids = chapter.get("segment_ids")
        if not segment_ids:
            errors.append(f'Chapter "{label}" has zero segments in selection.json')
            continue
        ids = [str(sid) for sid in segment_ids if sid]
        idxs = [order_index[sid] for sid in ids if sid in order_index]
        if len(idxs) != len(ids):
            missing = [sid for sid in ids if sid not in order_index]
            errors.append(
                f'Chapter "{label}" references segments not in ordered_segment_ids: '
                f"{missing[:4]}"
            )
            continue
        # Membership span in air order — not the stored list order. After
        # guest-first / opening repair, chapter.segment_ids may still be
        # source-sorted while the span is contiguous (exec_002 002/007/005/004).
        uniq = sorted(set(idxs))
        if uniq and uniq[-1] - uniq[0] + 1 != len(uniq):
            errors.append(
                f'Chapter "{label}" segments are not contiguous in ordered_segment_ids'
            )
    return errors


def _validate_reverse_tape_budget(ctx: RunContext, selection: dict[str, Any]) -> list[str]:
    from interview_mux.config import merged_config

    mastering = merged_config().get("mastering") or {}
    air = mastering.get("air_order") if isinstance(mastering.get("air_order"), dict) else {}
    max_rev = int(air.get("max_reverse_gap_ms", 0) or 0)
    if max_rev <= 0 or not ctx.artifact_exists("segments/manifest.json"):
        return []
    manifest = ctx.read_json("segments/manifest.json")
    by_id = {
        str(row.get("segment_id")): row
        for row in (manifest.get("segments") or [])
        if isinstance(row, dict) and row.get("segment_id")
    }
    ordered = [
        str(sid)
        for sid in (selection.get("ordered_segment_ids") or [])
        if sid
    ]
    errors: list[str] = []
    prev_end: int | None = None
    for sid in ordered:
        row = by_id.get(sid)
        if not isinstance(row, dict):
            continue
        start = int(row.get("start_ms") or 0)
        end = int(row.get("end_ms") or start)
        if prev_end is not None and start < prev_end - max_rev:
            errors.append(
                f"Reverse tape jump exceeds {max_rev}ms before {sid} "
                f"(gap_ms={start - prev_end})"
            )
        prev_end = end
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


def _cross_check_coherence_missing_callback(
    ctx: RunContext,
    brief_topics: list[Any],
    audit: dict[str, Any],
) -> list[str]:
    """Flag when coherence missing_callback risks lack matching coverage_audit excludes."""
    from interview_mux.coherence.paths import COHERENCE_REPORT_PATH

    if not ctx.artifact_exists(COHERENCE_REPORT_PATH):
        return []
    report = ctx.read_json(COHERENCE_REPORT_PATH)
    if not (report.get("gate") or {}).get("activated"):
        return []
    missing_coverage = audit.get("missing_coverage") or []
    documented = _documented_excludes(missing_coverage)
    errors: list[str] = []
    for risk in report.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        if risk.get("kind") != "missing_callback" or risk.get("status") == "resolved":
            continue
        topic = str((risk.get("evidence") or {}).get("topic") or risk.get("theme_id") or "")
        if not topic:
            continue
        norm = _norm_name(topic)
        if norm not in documented:
            by_topic = _topic_mapping_index(audit.get("topic_mappings") or [])
            mapping = by_topic.get(norm)
            if not mapping or not (mapping.get("segment_ids") or []):
                errors.append(
                    f'Coherence missing_callback for "{topic}" not reflected in coverage_audit'
                )
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

    if not ctx.artifact_exists("master/coverage_audit.json"):
        errors.append("Missing master/coverage_audit.json")
    else:
        audit = ctx.read_json("master/coverage_audit.json")
        errors.extend(_validate_topic_coverage(brief_topics, audit))
        errors.extend(_validate_claim_mappings(brief, audit))
        errors.extend(_cross_check_coherence_missing_callback(ctx, brief_topics, audit))

    has_selection = ctx.artifact_exists("master/selection.json")
    if require_selection and not has_selection:
        errors.append("Missing master/selection.json")
    elif has_selection:
        selection = ctx.read_json("master/selection.json")
        if isinstance(selection, dict):
            errors.extend(_validate_chapters(selection))
            errors.extend(_validate_reverse_tape_budget(ctx, selection))

    return errors
