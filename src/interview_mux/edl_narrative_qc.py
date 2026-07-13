"""Narrative validators for the final Flow 1 EDL."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _as_id(value: Any) -> str:
    return str(value or "").strip()


def _id_list(values: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(values, list):
        return out
    for item in values:
        if isinstance(item, dict):
            sid = _as_id(item.get("segment_id") or item.get("id"))
        else:
            sid = _as_id(item)
        if sid:
            out.append(sid)
    return out


def _speech_order(edl: dict[str, Any]) -> list[str]:
    clips = edl.get("clips") or []
    if not isinstance(clips, list):
        return []
    return [
        _as_id(c.get("segment_id"))
        for c in clips
        if isinstance(c, dict) and c.get("type") == "speech" and _as_id(c.get("segment_id"))
    ]


def _clip_pairs(edl: dict[str, Any], clip_type: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    clips = edl.get("clips") or []
    if not isinstance(clips, list):
        return pairs
    for clip in clips:
        if not isinstance(clip, dict) or clip.get("type") != clip_type:
            continue
        after = _as_id(clip.get("after_segment_id"))
        before = _as_id(clip.get("before_segment_id"))
        if after and before:
            pairs.add((after, before))
    return pairs


def _transition_items(transitions: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(transitions, dict):
        return []
    items = transitions.get("transitions") or []
    return [item for item in items if isinstance(item, dict)]


def _topic_name(item: dict[str, Any]) -> str:
    return _as_id(item.get("topic") or item.get("name") or item.get("item"))


def _documented_missing(missing_coverage: Any) -> set[str]:
    documented: set[str] = set()
    if not isinstance(missing_coverage, list):
        return documented
    for item in missing_coverage:
        if not isinstance(item, dict):
            continue
        name = _topic_name(item)
        if name and _as_id(item.get("suggestion") or item.get("reason")):
            documented.add(name.casefold())
    return documented


def _validate_selection_parity(
    selection: dict[str, Any],
    speech: list[str],
    errors: list[str],
) -> None:
    selected = _id_list(selection.get("ordered_segment_ids"))
    if selected and speech != selected:
        errors.append(
            "master/edl.json: speech clips do not match final selection "
            f"ordered_segment_ids; expected {selected}, got {speech}. "
            "Re-run edl after saving timeline edits."
        )

    speech_set = set(speech)
    for sid in _id_list(selection.get("excluded_segment_ids")):
        if sid in speech_set:
            errors.append(
                f'master/edl.json: excluded segment "{sid}" appears as speech. '
                "Fix selection.json or re-run full_master_ranking / edl."
            )


def _validate_coverage_survives_edl(
    coverage: dict[str, Any],
    speech: list[str],
    errors: list[str],
) -> None:
    speech_set = set(speech)
    documented = _documented_missing(coverage.get("missing_coverage"))
    for mapping in coverage.get("topic_mappings") or []:
        if not isinstance(mapping, dict) or not mapping.get("covered"):
            continue
        name = _topic_name(mapping) or "(unnamed topic)"
        mapped = set(_id_list(mapping.get("segment_ids")))
        if mapped and not mapped.intersection(speech_set) and name.casefold() not in documented:
            errors.append(
                f'master/edl.json: covered topic "{name}" lost all mapped '
                "segments in the final EDL. Re-run full_master_ranking after NLE edits "
                "or document the exclusion in coverage_audit.missing_coverage."
            )

    for mapping in coverage.get("claim_mappings") or []:
        if not isinstance(mapping, dict) or not mapping.get("covered"):
            continue
        claim = _as_id(mapping.get("claim") or mapping.get("name") or mapping.get("text"))
        mapped = set(_id_list(mapping.get("segment_ids")))
        if mapped and not mapped.intersection(speech_set):
            errors.append(
                f'master/edl.json: covered claim "{claim or "(unnamed claim)"}" '
                "lost all mapped segments in the final EDL. Re-run full_master_ranking "
                "or revise the coverage audit."
            )


def _validate_chapter_continuity(
    selection: dict[str, Any],
    speech: list[str],
    errors: list[str],
) -> None:
    positions = {sid: idx for idx, sid in enumerate(speech)}
    chapter_ranges: list[tuple[int, int, str]] = []
    for index, chapter in enumerate(selection.get("chapters") or []):
        if not isinstance(chapter, dict):
            continue
        label = _as_id(chapter.get("title") or chapter.get("chapter_id")) or f"chapter[{index}]"
        ids = _id_list(chapter.get("segment_ids"))
        if not ids:
            continue
        missing = [sid for sid in ids if sid not in positions]
        if missing:
            errors.append(
                f'master/selection.json: chapter "{label}" references segments '
                f"missing from EDL speech clips: {missing}. Re-run full_master_ranking."
            )
            continue
        idxs = sorted(positions[sid] for sid in ids)
        if idxs and idxs[-1] - idxs[0] + 1 != len(idxs):
            errors.append(
                f'master/edl.json: chapter "{label}" is split by unrelated '
                "speech clips in the final timeline. Re-run full_master_ranking."
            )
        chapter_ranges.append((idxs[0], idxs[-1], label))

    for i in range(len(chapter_ranges) - 1):
        _, end_a, label_a = chapter_ranges[i]
        start_b, _, label_b = chapter_ranges[i + 1]
        if start_b <= end_a:
            errors.append(
                f'master/selection.json: chapters "{label_a}" and "{label_b}" '
                "overlap in final EDL order. Re-run full_master_ranking."
            )


def _validate_ordering_constraints(
    narrative_plan: dict[str, Any],
    speech: list[str],
    errors: list[str],
) -> None:
    positions = {sid: idx for idx, sid in enumerate(speech)}
    for index, constraint in enumerate(narrative_plan.get("ordering_constraints") or []):
        if not isinstance(constraint, dict):
            continue
        before = _as_id(
            constraint.get("before_segment_id")
            or constraint.get("before")
            or constraint.get("setup_segment_id")
        )
        after = _as_id(
            constraint.get("after_segment_id")
            or constraint.get("after")
            or constraint.get("payoff_segment_id")
        )
        if not before or not after:
            continue
        if before not in positions or after not in positions:
            missing = [sid for sid in (before, after) if sid not in positions]
            errors.append(
                f"master/narrative_plan.json: ordering_constraints[{index}] "
                f"references segment(s) missing from final EDL: {missing}. "
                "Re-run narrative_arc_plan or full_master_ranking."
            )
            continue
        if positions[before] >= positions[after]:
            reason = _as_id(constraint.get("reason"))
            suffix = f" ({reason})" if reason else ""
            errors.append(
                f'master/edl.json: ordering constraint violated: "{before}" '
                f'must appear before "{after}"{suffix}. Re-run full_master_ranking.'
            )


def _validate_transitions(
    transitions: dict[str, Any] | None,
    edl: dict[str, Any],
    speech: list[str],
    errors: list[str],
) -> None:
    adjacency = {(speech[i], speech[i + 1]) for i in range(len(speech) - 1)}
    edl_transition_pairs = _clip_pairs(edl, "transition")
    for item in _transition_items(transitions):
        after = _as_id(item.get("after_segment_id"))
        before = _as_id(item.get("before_segment_id"))
        if not after or not before:
            continue
        pair = (after, before)
        if pair in adjacency and pair not in edl_transition_pairs:
            errors.append(
                f'master/edl.json: missing transition clip between "{after}" '
                f'and "{before}" from transitions.json. Re-run edl.'
            )
        elif pair not in adjacency and after in speech and before in speech:
            errors.append(
                f'master/transitions.json: transition "{after}" -> "{before}" '
                "does not match adjacent final EDL speech order. Re-run transitions "
                "after full_master_ranking/NLE edits."
            )

    for pair in edl_transition_pairs:
        if pair not in adjacency:
            errors.append(
                f'master/edl.json: transition clip "{pair[0]}" -> "{pair[1]}" '
                "does not sit between adjacent speech clips. Re-run edl."
            )


def _validate_gap_placements(
    ctx: RunContext,
    edl: dict[str, Any],
    speech: list[str],
    errors: list[str],
) -> None:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return
    report = ctx.read_json("understanding/gap_report.json")
    speech_set = set(speech)
    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    vo_keys = {
        (_as_id(c.get("line_id")), _as_id(c.get("targets_segment_id")), _as_id(c.get("placement")))
        for c in clips
        if c.get("type") == "vo_pickup"
    }
    placement_keys = {
        (_as_id(p.get("line_id")), _as_id(p.get("targets_segment_id")), _as_id(p.get("placement")))
        for p in edl.get("gap_placements") or []
        if isinstance(p, dict)
    }
    missing_vo = set((edl.get("warnings") or {}).get("missing_vo_files") or [])

    for line in report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or line.get("delivery") != "record":
            continue
        line_id = _as_id(line.get("line_id"))
        target = _as_id(line.get("targets_segment_id"))
        placement = _as_id(line.get("placement") or "before")
        if target not in speech_set:
            continue
        key = (line_id, target, placement)
        if key not in vo_keys:
            warning_ok = line_id in missing_vo or target in missing_vo
            if not warning_ok:
                errors.append(
                    f'master/edl.json: gap line "{line_id}" targeting "{target}" '
                    "has no vo_pickup clip and no missing_vo_files warning. Re-run vo_ingest "
                    "or edl."
                )
        if key not in placement_keys:
            errors.append(
                f'master/edl.json: gap line "{line_id}" targeting "{target}" '
                "has no matching gap_placements entry. Re-run edl."
            )

    for key in placement_keys:
        if key not in vo_keys:
            errors.append(
                f'master/edl.json: gap_placements entry {key} has no matching '
                "vo_pickup clip. Re-run edl."
            )


def _validate_audit_artifact(ctx: RunContext, errors: list[str]) -> None:
    if not ctx.artifact_exists("master/edl_narrative_audit.json"):
        return
    audit = ctx.read_json("master/edl_narrative_audit.json")
    verdict = _as_id(audit.get("verdict")).casefold()
    blocking = audit.get("blocking_issues") or []
    if verdict == "fail" or blocking:
        labels: list[str] = []
        for item in blocking[:4] if isinstance(blocking, list) else []:
            if isinstance(item, dict):
                labels.append(_as_id(item.get("issue") or item.get("summary") or item.get("reason")))
            else:
                labels.append(_as_id(item))
        detail = "; ".join(label for label in labels if label)
        errors.append(
            "master/edl_narrative_audit.json: flagship audit found blocking "
            f"narrative issue(s){': ' + detail if detail else ''}. "
            "Resolve the audit recommendations before edl."
        )


def validate_flow1_edl_narrative(
    ctx: RunContext,
    edl: dict[str, Any] | None = None,
) -> list[str]:
    """Return actionable final-EDL narrative errors (empty list = pass)."""
    if edl is None:
        if not ctx.artifact_exists("master/edl.json"):
            return ["Missing master/edl.json"]
        edl = ctx.read_json("master/edl.json")
    if not isinstance(edl, dict):
        return ["master/edl.json root must be an object"]

    required = [
        "master/selection.json",
        "master/coverage_audit.json",
        "master/narrative_plan.json",
    ]
    errors = [f"Missing {path}" for path in required if not ctx.artifact_exists(path)]
    if errors:
        return errors

    selection = ctx.read_json("master/selection.json")
    coverage = ctx.read_json("master/coverage_audit.json")
    narrative_plan = ctx.read_json("master/narrative_plan.json")
    transitions = (
        ctx.read_json("master/transitions.json")
        if ctx.artifact_exists("master/transitions.json")
        else None
    )
    speech = _speech_order(edl)
    if not speech:
        return ["master/edl.json: no speech clips available for narrative validation"]

    _validate_selection_parity(selection, speech, errors)
    _validate_coverage_survives_edl(coverage, speech, errors)
    _validate_chapter_continuity(selection, speech, errors)
    _validate_ordering_constraints(narrative_plan, speech, errors)
    _validate_transitions(transitions, edl, speech, errors)
    _validate_gap_placements(ctx, edl, speech, errors)
    _validate_audit_artifact(ctx, errors)
    return errors
