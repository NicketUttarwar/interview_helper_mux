"""Narrative validators for the final Flow 1 EDL."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
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


def _edl_narrative_qc_cfg() -> dict[str, Any]:
    raw = merged_config().get("edl_narrative_qc") or {}
    defaults = {
        "strict": True,
        "require_synthesized_vo": False,
        "require_framing_before_impact": True,
    }
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def _vo_pickup_index(edl: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for clip in clips:
        if clip.get("type") != "vo_pickup":
            continue
        key = (
            _as_id(clip.get("line_id")),
            _as_id(clip.get("targets_segment_id")),
            _as_id(clip.get("placement") or "before"),
        )
        out[key] = clip
    return out


def _clip_timeline_index(edl: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    return sorted(
        ((int(c.get("timeline_start_ms") or 0), c) for c in clips),
        key=lambda row: row[0],
    )


def _validate_framing_before_impact(
    ctx: RunContext,
    edl: dict[str, Any],
    speech: list[str],
    errors: list[str],
) -> None:
    cfg = _edl_narrative_qc_cfg()
    if not cfg.get("require_framing_before_impact", True):
        return
    from interview_mux.gap_framing import load_gap_framing_plan

    plan = load_gap_framing_plan(ctx)
    if not plan:
        return
    timeline = _clip_timeline_index(edl)
    speech_positions = {sid: idx for idx, sid in enumerate(speech)}
    vo_by_line = {
        _as_id(c.get("line_id")): int(c.get("timeline_start_ms") or 0)
        for _, c in timeline
        if c.get("type") == "vo_pickup" and _as_id(c.get("line_id"))
    }
    # Only enforce framing ids that still exist in the committed gap_report.
    live_line_ids: set[str] = set()
    if ctx.artifact_exists("understanding/gap_report.json"):
        try:
            gr = ctx.read_json("understanding/gap_report.json")
            if isinstance(gr, dict):
                live_line_ids = {
                    _as_id(ln.get("line_id"))
                    for ln in (gr.get("interviewer_lines") or [])
                    if isinstance(ln, dict) and ln.get("line_id") and not ln.get("skipped_optional")
                }
        except Exception:
            live_line_ids = set()

    for act in plan.get("acts") or []:
        if not isinstance(act, dict):
            continue
        for block in act.get("impact_blocks") or []:
            if not isinstance(block, dict):
                continue
            primaries = [str(s) for s in (block.get("source_segment_ids") or []) if s]
            if not primaries:
                continue
            primary = primaries[0]
            if primary not in speech_positions:
                continue
            framing_ids = [
                _as_id(lid)
                for lid in (block.get("framing_line_ids") or [])
                if lid and (not live_line_ids or _as_id(lid) in live_line_ids)
            ]
            if not framing_ids:
                continue
            speech_ms = next(
                (int(c.get("timeline_start_ms") or 0) for _, c in timeline if c.get("type") == "speech" and _as_id(c.get("segment_id")) == primary),
                None,
            )
            if speech_ms is None:
                continue
            preceding = [vo_by_line[lid] for lid in framing_ids if lid in vo_by_line and vo_by_line[lid] < speech_ms]
            if not preceding:
                errors.append(
                    f'master/edl.json: impact segment "{primary}" lacks preceding framing VO '
                    f"({', '.join(framing_ids[:3])}). Re-run edl or gap_framing_compose."
                )


def _validate_framing_succinct_exclusions(
    ctx: RunContext,
    selection: dict[str, Any],
    speech: list[str],
    errors: list[str],
) -> None:
    from interview_mux.gap_framing import ranking_exclude_segment_ids

    covered = ranking_exclude_segment_ids(ctx)
    if not covered:
        return
    speech_set = set(speech)
    notes = str(selection.get("notes") or "").lower()
    for sid in covered:
        if sid not in speech_set:
            continue
        excluded_ok = False
        for row in selection.get("excluded_segment_ids") or []:
            if isinstance(row, dict) and str(row.get("segment_id")) == sid:
                reason = str(row.get("reason") or "")
                if reason == "covered_by_framing_vo" or "duplicate" in reason:
                    excluded_ok = True
                break
        if not excluded_ok and "duplicate" not in notes:
            errors.append(
                f'master/edl.json: framing-covered segment "{sid}" appears as speech without '
                "covered_by_framing_vo exclusion. Re-run full_master_ranking."
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
    vo_clips = _vo_pickup_index(edl)
    placement_keys = {
        (_as_id(p.get("line_id")), _as_id(p.get("targets_segment_id")), _as_id(p.get("placement")))
        for p in edl.get("gap_placements") or []
        if isinstance(p, dict)
    }
    missing_vo = set((edl.get("warnings") or {}).get("missing_vo_files") or [])

    from interview_mux.gates import vo_gap_line_effectively_optional

    qc_cfg = _edl_narrative_qc_cfg()
    require_synth = bool(qc_cfg.get("require_synthesized_vo", False))

    seen_line_ids: dict[str, int] = {}
    seen_text_targets: dict[tuple[str, str, str], int] = {}
    for line in report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        delivery = str(line.get("delivery") or "").lower()
        if delivery not in ("record", "synthesize"):
            continue
        if vo_gap_line_effectively_optional(ctx, line):
            continue
        line_id = _as_id(line.get("line_id"))
        target = _as_id(line.get("targets_segment_id"))
        placement = _as_id(line.get("placement") or "before")
        if line_id:
            seen_line_ids[line_id] = seen_line_ids.get(line_id, 0) + 1
        text_norm = " ".join(str(line.get("text") or "").strip().lower().split())
        if text_norm and target:
            tkey = (text_norm, target, placement)
            seen_text_targets[tkey] = seen_text_targets.get(tkey, 0) + 1
        if target not in speech_set:
            continue
        key = (line_id, target, placement)
        if key not in vo_keys:
            warning_ok = line_id in missing_vo or target in missing_vo
            if delivery == "synthesize" and not require_synth:
                warning_ok = True
            if not warning_ok:
                errors.append(
                    f'master/edl.json: gap line "{line_id}" targeting "{target}" '
                    "has no vo_pickup clip and no missing_vo_files warning. Re-run vo_ingest "
                    "or edl."
                )
        elif delivery == "synthesize" and require_synth:
            clip = vo_clips.get(key) or {}
            src = _as_id(clip.get("source_path"))
            dur = int(clip.get("duration_ms") or 0)
            if not src or dur <= 0:
                errors.append(
                    f'master/edl.json: synthesized gap line "{line_id}" missing WAV on clip. '
                    "Synthesize at G1 or re-run edl."
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

    # Orphan VO: pickup targeting a segment that is not on the air speech order.
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict) or clip.get("type") != "vo_pickup":
            continue
        target = _as_id(clip.get("targets_segment_id"))
        if not target:
            continue
        if target not in speech_set:
            lid = _as_id(clip.get("line_id")) or "?"
            errors.append(
                f'master/edl.json: orphan vo_pickup "{lid}" targets "{target}" '
                "which is not in ordered speech. Strip VO or retarget after junction exclude."
            )

    for lid, count in seen_line_ids.items():
        if count > 1:
            errors.append(
                f'understanding/gap_report.json: line_id "{lid}" appears {count}x. '
                "Dedupe interviewer_lines before vo_ingest / edl."
            )
    for (text_norm, target, placement), count in seen_text_targets.items():
        if count > 1:
            snippet = text_norm[:80]
            errors.append(
                f'understanding/gap_report.json: identical VO text targeting "{target}" '
                f'({placement}) appears {count}x ("{snippet}"). Dedupe before edl.'
            )

    # Global spoken-sentence uniqueness across all non-skipped interviewer lines.
    from interview_mux.spoken_copy_guard import sentence_keys

    seen_sentence_owners: dict[str, str] = {}
    for line in report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or line.get("skipped_optional"):
            continue
        lid = _as_id(line.get("line_id")) or _as_id(line.get("targets_segment_id")) or "?"
        for key in sentence_keys(str(line.get("text") or "")):
            prior = seen_sentence_owners.get(key)
            if prior and prior != lid:
                errors.append(
                    f'understanding/gap_report.json: spoken sentence key collision '
                    f'between "{prior}" and "{lid}" ({key!r}). '
                    "Regenerate unique synthetic copy before edl."
                )
            else:
                seen_sentence_owners[key] = lid

    vo_clip_ids: dict[str, int] = {}
    for clip in clips:
        if clip.get("type") != "vo_pickup":
            continue
        lid = _as_id(clip.get("line_id"))
        if not lid:
            continue
        vo_clip_ids[lid] = vo_clip_ids.get(lid, 0) + 1
    for lid, count in vo_clip_ids.items():
        if count > 1:
            errors.append(
                f'master/edl.json: vo_pickup line_id "{lid}" appears {count}x. '
                "Dedupe gap lines before building the EDL."
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
    _validate_framing_before_impact(ctx, edl, speech, errors)
    _validate_framing_succinct_exclusions(ctx, selection, speech, errors)
    _validate_speaker_volley_integrity(ctx, speech, errors)
    _validate_audit_artifact(ctx, errors)
    return errors


def _validate_speaker_volley_integrity(ctx: Any, speech: list[str], errors: list[str]) -> None:
    """Ensure locked speaker volleys are not split in the EDL speech order."""
    try:
        from interview_mux.episode_structure import load_episode_structure
        from interview_mux.speaker_volley import check_speaker_volley_integrity

        doc = load_episode_structure(ctx)
        if not isinstance(doc, dict):
            return
        volleys = doc.get("speaker_volleys")
        if not isinstance(volleys, list) or not volleys:
            return
        ok, flags = check_speaker_volley_integrity(list(speech), volleys)
        if not ok:
            for f in flags[:8]:
                errors.append(f"speaker_volley_integrity:{f}")
    except Exception:
        return
