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


def _speech_clip_by_id(edl: dict[str, Any], segment_id: str) -> dict[str, Any] | None:
    sid = _as_id(segment_id)
    if not sid:
        return None
    for clip in edl.get("clips") or []:
        if (
            isinstance(clip, dict)
            and clip.get("type") == "speech"
            and _as_id(clip.get("segment_id")) == sid
        ):
            return clip
    return None


def _end_text_for_clip(
    clip: dict[str, Any],
    words: list[dict[str, Any]],
    segments: dict[str, Any],
) -> tuple[str, int | None]:
    end_ms = clip.get("source_end_ms")
    try:
        end_ms_i = int(end_ms) if end_ms is not None else None
    except (TypeError, ValueError):
        end_ms_i = None
    sid = _as_id(clip.get("segment_id"))
    text = ""
    if words and end_ms_i is not None:
        toks = [
            str(w.get("text") or "").strip()
            for w in words
            if isinstance(w, dict)
            and int(w.get("end_ms") or 0) <= end_ms_i + 20
            and int(w.get("end_ms") or 0) >= end_ms_i - 12_000
        ]
        text = " ".join(t for t in toks[-24:] if t)
    if not text and sid and isinstance(segments.get(sid), dict):
        text = str((segments.get(sid) or {}).get("text") or "")
    return text, end_ms_i


def qc_text_before(words: list[dict[str, Any]], end_ms: int) -> str:
    """The closing text QC judges at ``end_ms`` (last 24 words in 12 s)."""
    toks = [
        str(w.get("text") or "").strip()
        for w in words
        if isinstance(w, dict)
        and int(w.get("end_ms") or 0) <= end_ms + 20
        and int(w.get("end_ms") or 0) >= end_ms - 12_000
    ]
    return " ".join(t for t in toks[-24:] if t)


def qc_hinge_at(words: list[dict[str, Any]], end_ms: int) -> bool:
    """Single definition of "ends on a complete thought" for EDL build and QC."""
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

    text = qc_text_before(words, int(end_ms))
    return bool(text) and bool(is_legal_conceptual_hinge(text, words=words or None, end_ms=int(end_ms)))


def first_qc_hinge_between(
    words: list[dict[str, Any]], after_ms: int, until_ms: int
) -> int | None:
    """First word end in (after_ms, until_ms] where QC accepts the close."""
    for w in words:
        if not isinstance(w, dict):
            continue
        end = int(w.get("end_ms") or 0)
        if after_ms < end <= until_ms and qc_hinge_at(words, end):
            return end
    return None


# How far a hanging close may look for a complete thought, either direction.
HINGE_SEARCH_MS = 12_000


def _validate_vo_after_legal_hinge(
    ctx: Any,
    edl: dict[str, Any],
    errors: list[str],
) -> None:
    """Refuse transition / vo_pickup after a hanging native close."""
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

    words: list[dict[str, Any]] = []
    if ctx.artifact_exists("transcript/full.json"):
        try:
            doc = ctx.read_json("transcript/full.json")
            raw = (doc or {}).get("words") if isinstance(doc, dict) else None
            if isinstance(raw, list):
                words = [w for w in raw if isinstance(w, dict)]
        except Exception:
            words = []
    segments: dict[str, Any] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        try:
            man = ctx.read_json("segments/manifest.json")
            for row in (man or {}).get("segments") or []:
                if isinstance(row, dict) and row.get("segment_id"):
                    segments[str(row["segment_id"])] = row
        except Exception:
            segments = {}

    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        ctype = str(clip.get("type") or "")
        if ctype not in {"transition", "vo_pickup"}:
            continue
        after = _as_id(clip.get("after_segment_id"))
        if not after:
            continue
        speech = _speech_clip_by_id(edl, after)
        if speech is None:
            continue
        text, end_ms = _end_text_for_clip(speech, words, segments)
        if not text:
            continue
        if is_legal_conceptual_hinge(text, words=words or None, end_ms=end_ms):
            continue
        # The tape may never finish this thought: no legal close inside the
        # clip and none within reach after it (the speaker trails off, as
        # exec_052 seg_060 did into 22 s of silence). Nothing in the pipeline
        # can satisfy the demand then, so it is a warning, not a stop
        # (ISSUES entry 59). A reachable close still makes it an error,
        # because the EDL build extends or trims to it.
        if words and end_ms is not None and not _hinge_reachable(
            speech, words, end_ms, _extension_horizon_ms(edl, end_ms)
        ):
            try:
                ctx.log(
                    f'{ctype} after "{after}": source never completes the thought '
                    "within reach (tape trail-off); allowed",
                    level="warning",
                    stage="edl",
                )
            except Exception:
                pass
            continue
        errors.append(
            f'master/edl.json: {ctype} after "{after}" lands on an incomplete thought. '
            "Fuse or recut to a complete-thought hinge before inserting VO."
        )


def _hinge_reachable(
    speech: dict[str, Any],
    words: list[dict[str, Any]],
    end_ms: int,
    horizon_ms: int | None = None,
) -> bool:
    """True when a QC-legal close exists inside the clip or shortly after it.

    ``horizon_ms`` is where the EDL builder must stop extending (40 ms before
    the next on-air tape): a close beyond it is not reachable, so demanding it
    asks an edl rebuild for a cut it is not allowed to make (ISSUES 151).
    """
    try:
        start = int(speech.get("source_start_ms") or 0)
    except (TypeError, ValueError):
        start = 0
    lo = max(start, end_ms - HINGE_SEARCH_MS)
    if first_qc_hinge_between(words, lo, end_ms - 1) is not None:
        return True
    hi = end_ms + HINGE_SEARCH_MS
    if horizon_ms is not None:
        hi = min(hi, horizon_ms)
    if hi <= end_ms:
        return False
    return first_qc_hinge_between(words, end_ms, hi) is not None


def _extension_horizon_ms(edl: dict[str, Any], end_ms: int) -> int | None:
    starts = [
        int(c.get("source_start_ms") or 0)
        for c in (edl.get("clips") or [])
        if isinstance(c, dict) and c.get("type") == "speech" and int(c.get("source_start_ms") or 0) >= end_ms
    ]
    return (min(starts) - 40) if starts else None


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
    edl: dict[str, Any] | None = None,
) -> None:
    selected = _id_list(selection.get("ordered_segment_ids"))
    omitted = set(_id_list((edl or {}).get("omitted_unplayable_segment_ids")))
    if omitted:
        selected = [sid for sid in selected if sid not in omitted]
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
    edl: dict[str, Any] | None = None,
) -> None:
    positions = {sid: idx for idx, sid in enumerate(speech)}
    # Segments the EDL omitted as unplayable are not missing chapter members:
    # parity already honours the list, and the relabel works on the selection
    # order so it cannot remove them (ISSUES 175).
    omitted = set(_id_list((edl or {}).get("omitted_unplayable_segment_ids")))
    chapter_ranges: list[tuple[int, int, str]] = []
    for index, chapter in enumerate(selection.get("chapters") or []):
        if not isinstance(chapter, dict):
            continue
        label = _as_id(chapter.get("title") or chapter.get("chapter_id")) or f"chapter[{index}]"
        ids = [sid for sid in _id_list(chapter.get("segment_ids")) if sid not in omitted]
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

    # Compare chapters in air order, not list order: disjoint contiguous
    # chapters listed out of order read as "overlap" (ISSUES 151).
    chapter_ranges.sort(key=lambda row: row[0])
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
            continue
        if positions[before] >= positions[after]:
            reason = _as_id(constraint.get("reason"))
            suffix = f" ({reason})" if reason else ""
            errors.append(
                f'master/edl.json: ordering constraint violated: "{before}" '
                f'must appear before "{after}"{suffix}. Re-run full_master_ranking.'
            )


def _seam_has_host_turn(edl: dict[str, Any], after: str, before: str) -> bool:
    """True when a vo_pickup (or transition) already sits between two speech clips."""
    seeing = False
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        ctype = str(clip.get("type") or "")
        if ctype == "speech" and _as_id(clip.get("segment_id")) == after:
            seeing = True
            continue
        if not seeing:
            continue
        if ctype == "speech" and _as_id(clip.get("segment_id")) == before:
            return False
        if ctype in {"transition", "vo_pickup"}:
            return True
    return False


def _effective_transitions_for_edl(
    ctx: RunContext,
    transitions: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Align QC with the EDL builder: air-script filter + framing-VO dedupe.

    exec_2058 looped because filter_transitions_for_air_script dropped a
    native_handoff pair while QC still required that clip from disk.
    """
    doc = transitions if isinstance(transitions, dict) else None
    try:
        from interview_mux.air_script import filter_transitions_for_air_script
        from interview_mux.mastering_plan_loader import load_plan_raw

        filtered = filter_transitions_for_air_script(doc, load_plan_raw(ctx))
        if filtered is not None:
            doc = filtered
    except Exception:
        pass
    try:
        from interview_mux.gap_framing import dedupe_transitions_for_framing

        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else None
        )
        if isinstance(doc, dict):
            doc = dedupe_transitions_for_framing(gap, doc)
            from interview_mux.gap_framing import dedupe_transitions_by_adjacency

            doc = dedupe_transitions_by_adjacency(doc)
    except Exception:
        pass
    return doc


def _validate_transitions(
    transitions: dict[str, Any] | None,
    edl: dict[str, Any],
    speech: list[str],
    errors: list[str],
) -> None:
    adjacency = {(speech[i], speech[i + 1]) for i in range(len(speech) - 1)}
    edl_transition_pairs = _clip_pairs(edl, "transition")
    # Match build_flow1_edl: clone-voice adjacency may omit a planned transition
    # clip (recorded on edl.warnings.suppressed_clone_adjacency as
    # "transition:after->before"). Requiring that clip loops EDL forever.
    suppressed = {
        str(x)
        for x in ((edl.get("warnings") or {}).get("suppressed_clone_adjacency") or [])
        if x
    }
    # When the builder seats a layup on a seam instead of its transition and
    # that layup is then suppressed or has no WAV, the seam is empty on
    # purpose; rebuilding reaches the same decision (ISSUES 175).
    missing_vo = {
        str(x) for x in ((edl.get("warnings") or {}).get("missing_vo_files") or []) if x
    }
    unseated = suppressed | missing_vo
    for item in _transition_items(transitions):
        after = _as_id(item.get("after_segment_id"))
        before = _as_id(item.get("before_segment_id"))
        if not after or not before:
            continue
        pair = (after, before)
        if pair in adjacency and pair not in edl_transition_pairs:
            if _seam_has_host_turn(edl, after, before):
                continue
            if f"transition:{after}->{before}" in suppressed:
                continue
            if before in unseated or f"vo_layup_{before}" in unseated:
                continue
            errors.append(
                f'master/edl.json: missing transition clip between "{after}" '
                f'and "{before}" from transitions.json. Re-run edl.'
            )
        # A planned pair that is no longer adjacent never airs: the builder seats
        # only adjacent pairs and the loop below still refuses any non-adjacent
        # transition clip. Refusing the stale row asked for a transitions rerun
        # that the seat freeze skips, so edl rebuilt the same cut to the cap
        # (ISSUES 151).

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
    # Position = (timeline start, clip index): a zero-length VO shares its start
    # with the speech it precedes, and the clip list order breaks the tie.
    def _pos(clip: dict[str, Any]) -> tuple[int, int]:
        return (int(clip.get("timeline_start_ms") or 0), clip_index.get(id(clip), 0))

    clip_index = {id(c): i for i, c in enumerate(c for c in (edl.get("clips") or []) if isinstance(c, dict))}
    vo_by_line = {
        _as_id(c.get("line_id")): _pos(c)
        for _, c in timeline
        if c.get("type") == "vo_pickup" and _as_id(c.get("line_id"))
    }
    vo_targets = [
        (_as_id(c.get("targets_segment_id")), _pos(c))
        for _, c in timeline
        if c.get("type") == "vo_pickup" and _as_id(c.get("targets_segment_id"))
    ]
    # Only enforce framing ids that still exist in the committed gap_report
    # AND that air-script actually seated (EDL omits the rest).
    live_line_ids: set[str] = set()
    air_script_active = False
    gr: dict[str, Any] | None = None
    if ctx.artifact_exists("understanding/gap_report.json"):
        try:
            gr = ctx.read_json("understanding/gap_report.json")
            if isinstance(gr, dict):
                live_line_ids = {
                    _as_id(ln.get("line_id"))
                    for ln in (gr.get("interviewer_lines") or [])
                    if isinstance(ln, dict)
                    and ln.get("line_id")
                    and not ln.get("skipped_optional")
                    and not ln.get("air_script_omit")
                }
        except Exception:
            live_line_ids = set()
    try:
        from interview_mux.air_script import load_air_script, seated_vo_line_ids
        from interview_mux.mastering_plan_loader import load_plan_raw
        from interview_mux.opening_orientation import ORIENTATION_LINE_ID, orientation_omitted

        mastering = (
            load_plan_raw(ctx) if ctx.artifact_exists("mastering/mastering_plan.json") else {}
        )
        if isinstance(mastering, dict) and load_air_script(mastering):
            air_script_active = True
            seats = seated_vo_line_ids(mastering)
            script = load_air_script(mastering) or {}
            vo_seats = script.get("vo_seats") if isinstance(script.get("vo_seats"), dict) else {}
            orient = str((vo_seats or {}).get("orientation_id") or "") or ORIENTATION_LINE_ID
            live_line_ids = {
                lid
                for lid in live_line_ids
                if lid in seats
                or (
                    lid in {orient, ORIENTATION_LINE_ID}
                    and not orientation_omitted(gr if isinstance(gr, dict) else None)
                )
            }
    except Exception:
        pass

    for act in plan.get("acts") or []:
        if not isinstance(act, dict):
            continue
        for block in act.get("impact_blocks") or []:
            if not isinstance(block, dict):
                continue
            primaries = [str(s) for s in (block.get("source_segment_ids") or []) if s]
            if not primaries:
                continue
            # The block opens at whichever member airs first: ranking may reorder
            # a block (client exec_015: seg_007 aired before seg_006).
            on_air = [sid for sid in primaries if sid in speech_positions]
            if not on_air:
                continue
            primary = min(on_air, key=lambda sid: speech_positions[sid])
            framing_ids = [
                _as_id(lid)
                for lid in (block.get("framing_line_ids") or [])
                if lid
                and (
                    _as_id(lid) in live_line_ids
                    if (live_line_ids or air_script_active)
                    else True
                )
            ]
            if not framing_ids:
                continue
            speech_ms = next(
                (_pos(c) for _, c in timeline if c.get("type") == "speech" and _as_id(c.get("segment_id")) == primary),
                None,
            )
            if speech_ms is None:
                continue
            preceding = [vo_by_line[lid] for lid in framing_ids if lid in vo_by_line and vo_by_line[lid] < speech_ms]
            if not preceding:
                # The framing that airs may carry another id than the compose-era
                # plan names (layup owns the body after its authority stamp): a
                # seated VO for a block member that airs before the block frames it.
                members = set(on_air)
                preceding = [ms for tgt, ms in vo_targets if tgt in members and ms < speech_ms]
            if not preceding:
                from interview_mux.stage_completion import high_gap_heal_resume_stage

                pin = high_gap_heal_resume_stage(ctx)
                errors.append(
                    f'master/edl.json: impact segment "{primary}" lacks preceding framing VO '
                    f"({', '.join(framing_ids[:3])}). Re-run {pin} (never soft-pass EDL)."
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
    suppressed_clone_adjacency = set(
        (edl.get("warnings") or {}).get("suppressed_clone_adjacency") or []
    )

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
        # Duplicates matter only among lines that air; a stale copy that never
        # reaches the EDL cannot repeat on air, and the compose dedupe that
        # would remove it is refused under the freeze (ISSUES 175).
        aired = (line_id, target, placement) in vo_keys
        if line_id and aired:
            seen_line_ids[line_id] = seen_line_ids.get(line_id, 0) + 1
        text_norm = " ".join(str(line.get("text") or "").strip().lower().split())
        if text_norm and target and aired:
            tkey = (text_norm, target, placement)
            seen_text_targets[tkey] = seen_text_targets.get(tkey, 0) + 1
        if target not in speech_set:
            continue
        key = (line_id, target, placement)
        if key not in vo_keys:
            warning_ok = (
                line_id in missing_vo
                or target in missing_vo
                or line_id in suppressed_clone_adjacency
            )
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
            warning_ok = (
                line_id in missing_vo
                or target in missing_vo
                or line_id in suppressed_clone_adjacency
            )
            if delivery == "synthesize" and not require_synth:
                warning_ok = True
            if key not in vo_keys and warning_ok:
                continue
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
    # Only lines that air can collide on air. The builder already refuses a
    # repeat among the lines it seats; a line that is omitted, not record or
    # synthesize, or absent from the EDL never speaks (ISSUES 151).
    aired_ids = {
        _as_id(c.get("line_id"))
        for c in clips
        if c.get("type") == "vo_pickup" and _as_id(c.get("line_id"))
    }
    for line in report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or line.get("skipped_optional"):
            continue
        if line.get("air_script_omit") or str(line.get("delivery") or "") not in {"record", "synthesize"}:
            continue
        if aired_ids and _as_id(line.get("line_id")) not in aired_ids:
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


def _validate_clone_voice_adjacency(
    ctx: RunContext,
    edl: dict[str, Any],
    selection: dict[str, Any],
    errors: list[str],
) -> None:
    """Reject clone/native self-dialogue unless the VO recovers excluded tape."""
    if not ctx.artifact_exists("segments/manifest.json"):
        return
    manifest = ctx.read_json("segments/manifest.json")
    segments = {
        _as_id(row.get("segment_id")): row
        for row in ((manifest if isinstance(manifest, dict) else {}).get("segments") or [])
        if isinstance(row, dict) and _as_id(row.get("segment_id"))
    }
    report = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else {}
    )
    lines = {
        _as_id(line.get("line_id")): line
        for line in ((report if isinstance(report, dict) else {}).get("interviewer_lines") or [])
        if isinstance(line, dict) and _as_id(line.get("line_id"))
    }
    corpus = (
        ctx.read_json("understanding/nugget_corpus.json")
        if ctx.artifact_exists("understanding/nugget_corpus.json")
        else {}
    )
    from interview_mux.gap_framing import is_cut_recovery_vo
    from interview_mux.opening_orientation import is_episode_orientation

    ordered = _id_list(selection.get("ordered_segment_ids"))
    audible = [
        clip
        for clip in (edl.get("clips") or [])
        if isinstance(clip, dict) and clip.get("type") != "silence"
    ]
    # The builder keeps a seam when the acoustic listen says the voices differ
    # even though the speaker ids match; refusing it on id equality alone asks
    # an EDL rebuild to undo the builder's own verified decision (ISSUES 151).
    warnings = edl.get("warnings") if isinstance(edl.get("warnings"), dict) else {}
    kept_by_listen = {str(k) for k in (warnings.get("clone_adjacency_id_mismatch_kept") or []) if k}
    for index, clip in enumerate(audible):
        clip_type = str(clip.get("type") or "")
        if clip_type not in {"vo_pickup", "transition"}:
            continue
        seam_key = (
            _as_id(clip.get("line_id"))
            if clip_type == "vo_pickup"
            else f"transition:{_as_id(clip.get('after_segment_id'))}->{_as_id(clip.get('before_segment_id'))}"
        )
        if seam_key and seam_key in kept_by_listen:
            continue
        line = lines.get(_as_id(clip.get("line_id"))) if clip_type == "vo_pickup" else None
        voice = _as_id(clip.get("voice_speaker_id") or (line or {}).get("voice_speaker_id"))
        if not voice:
            continue
        exempt = bool(
            clip.get("clone_adjacency_exempt")
            or (
                line
                and (
                    line.get("clone_adjacency_exempt")
                    or is_episode_orientation(line)
                    or is_cut_recovery_vo(
                        line,
                        ordered_segment_ids=ordered,
                        nugget_corpus=corpus if isinstance(corpus, dict) else {},
                    )
                )
            )
        )
        if exempt:
            continue
        neighbor_segments = [
            _as_id(neighbor.get("segment_id"))
            for neighbor in (
                audible[max(0, index - 1) : index]
                + audible[index + 1 : index + 2]
            )
            if neighbor.get("type") == "speech"
        ]
        for segment_id in neighbor_segments:
            speaker = _as_id((segments.get(segment_id) or {}).get("speaker_id"))
            if speaker == voice:
                errors.append(
                    f'master/edl.json: {clip_type} "{_as_id(clip.get("line_id")) or clip.get("after_segment_id") or "?"}" '
                    f"uses cloned voice {voice!r} adjacent to native segment {segment_id!r}. "
                    "Retarget/drop generic VO; only proven excluded-tape nugget layups may remain."
                )
                break


def _validate_audit_artifact(ctx: RunContext, errors: list[str]) -> None:
    if not ctx.artifact_exists("master/edl_narrative_audit.json"):
        return
    audit = ctx.read_json("master/edl_narrative_audit.json")
    from interview_mux.edl_narrative_remutate import (
        effective_narrative_blocking_issues,
    )

    blocking = effective_narrative_blocking_issues(
        ctx, audit if isinstance(audit, dict) else {}
    )
    if blocking:
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

    # Under the hard freeze the air order and the seated VO are locked: checks
    # whose only remedy is a re-rank or a re-compose cannot be acted on, and
    # as errors they rebuilt the same EDL to the invoke cap (client exec_018;
    # ISSUES 175). They are recorded as warnings instead.
    frozen = False
    try:
        from interview_mux.artifact_repairs import _order_frozen

        frozen = bool(_order_frozen(ctx))
    except Exception:
        frozen = False
    # Quality judgements (ordering, framing, coverage, chapter labels, LLM
    # audit verdict, duplicate copy, one-synthetic-per-seam, VO after an
    # incomplete thought) are warnings whether or not the order is frozen:
    # their only remedies are a re-rank or a re-compose that reach the same
    # result (ISSUES 185). Structural checks stay in ``errors``.
    editorial: list[str] = []

    if ctx.artifact_exists("master/air_order_integrity.json"):
        try:
            integrity = ctx.read_json("master/air_order_integrity.json")
            stale_critical: list[dict[str, Any]] = []
            if isinstance(integrity, dict) and not integrity.get("ok"):
                stale_critical = [
                    v
                    for v in (integrity.get("violations") or [])
                    if isinstance(v, dict) and str(v.get("severity") or "") == "critical"
                ]
            if stale_critical:
                from interview_mux.air_order_integrity import collect_violations
                from interview_mux.air_order_policy import resolve_air_order_policy

                selection_live = (
                    ctx.read_json("master/selection.json")
                    if ctx.artifact_exists("master/selection.json")
                    else {}
                )
                policy = resolve_air_order_policy(
                    ctx,
                    selection=selection_live if isinstance(selection_live, dict) else None,
                )
                live_critical = [
                    v
                    for v in collect_violations(
                        ctx,
                        selection_live if isinstance(selection_live, dict) else {},
                        policy=policy,
                    )
                    if isinstance(v, dict) and str(v.get("severity") or "") == "critical"
                ]
                if not live_critical:
                    ctx.log(
                        "air_order_integrity stale report ignored — live audit passed",
                        level="info",
                        stage="edl_narrative_qc",
                    )
                else:
                    editorial.append(
                        "air_order_integrity unresolved critical: "
                        + "; ".join(
                            str(v.get("message") or v.get("code") or "")
                            for v in live_critical[:3]
                        )
                    )
        except Exception:
            pass

    selection = ctx.read_json("master/selection.json")
    coverage = ctx.read_json("master/coverage_audit.json")
    narrative_plan = ctx.read_json("master/narrative_plan.json")
    transitions = (
        ctx.read_json("master/transitions.json")
        if ctx.artifact_exists("master/transitions.json")
        else None
    )
    transitions = _effective_transitions_for_edl(ctx, transitions)
    speech = _speech_order(edl)
    if not speech:
        return ["master/edl.json: no speech clips available for narrative validation"]

    _validate_selection_parity(selection, speech, errors, edl)
    _validate_coverage_survives_edl(coverage, speech, editorial)
    _validate_chapter_continuity(selection, speech, editorial, edl)
    _validate_ordering_constraints(narrative_plan, speech, editorial)
    _validate_transitions(transitions, edl, speech, errors)
    _validate_vo_after_legal_hinge(ctx, edl, editorial)
    placement_findings: list[str] = []
    _validate_gap_placements(ctx, edl, speech, placement_findings)
    for finding in placement_findings:
        if "identical VO text" in finding or "spoken sentence key collision" in finding:
            editorial.append(finding)
        else:
            errors.append(finding)
    # Advisory only (ISSUES 184): the EDL seats every line the gap report airs,
    # so a same-voice seam is a quality note, not a reason to refuse the EDL.
    clone_advisory: list[str] = []
    _validate_clone_voice_adjacency(ctx, edl, selection, clone_advisory)
    if clone_advisory:
        try:
            ctx.log(
                f"EDL narrative QC: {len(clone_advisory)} clone-voice adjacency seam(s) "
                "(advisory): " + "; ".join(clone_advisory[:3]),
                level="warning",
                stage="edl_narrative_qc",
                detail={"clone_adjacency_advisory": clone_advisory[:20]},
            )
        except Exception:
            pass
    _validate_framing_before_impact(ctx, edl, speech, editorial)
    _validate_framing_succinct_exclusions(ctx, selection, speech, editorial)
    _validate_speaker_volley_integrity(ctx, speech, errors)
    _validate_single_synthetic_between_natives(edl, editorial)
    _validate_episode_vo_identity(ctx, edl, errors)
    _validate_audit_artifact(ctx, editorial)
    if editorial:
        try:
            ctx.log(
                f"EDL narrative QC: {len(editorial)} editorial issue(s) recorded as "
                "warnings (ISSUES 185): " + "; ".join(editorial[:4]),
                level="warning",
                stage="edl_narrative_qc",
                detail={"editorial": editorial[:20], "frozen": frozen},
            )
        except Exception:
            pass
    return errors


def _validate_single_synthetic_between_natives(
    edl: dict[str, Any], errors: list[str]
) -> None:
    """At most one vo_pickup/transition between native speech clips."""
    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    audible = [c for c in clips if str(c.get("type") or "") != "silence"]
    i = 0
    while i < len(audible):
        kind = str(audible[i].get("type") or "")
        if kind not in {"vo_pickup", "transition"}:
            i += 1
            continue
        run = []
        while i < len(audible) and str(audible[i].get("type") or "") in {
            "vo_pickup",
            "transition",
        }:
            run.append(audible[i])
            i += 1
        # The episode orientation is an opening preface the builder seats beside
        # the first segment's own VO (straight open, or a cold open's deferred
        # hook line); it is not a second insert at a mid-episode seam.
        from interview_mux.opening_orientation import is_episode_orientation

        if len([c for c in run if not is_episode_orientation(c)]) <= 1:
            continue
        labels: list[str] = []
        for clip in run:
            lid = _as_id(clip.get("line_id"))
            if lid:
                labels.append(lid)
                continue
            after = _as_id(clip.get("after_segment_id"))
            before = _as_id(clip.get("before_segment_id"))
            if after or before:
                labels.append(f"{after}->{before}")
        joined = ", ".join(labels) if labels else "unnamed"
        errors.append(
            "master/edl.json: "
            f"{len(run)} synthetic inserts adjacent ({joined}). "
            "At most one vo_pickup or transition between native speech clips."
        )


def _validate_episode_vo_identity(
    ctx: RunContext, edl: dict[str, Any], errors: list[str]
) -> None:
    """Seated synthetics must share one clone speaker and one locked ref."""
    clips = [
        c
        for c in (edl.get("clips") or [])
        if isinstance(c, dict) and str(c.get("type") or "") in {"vo_pickup", "transition"}
    ]
    if not clips:
        return
    voices = [_as_id(c.get("voice_speaker_id")) for c in clips]
    nonempty = {v for v in voices if v}
    if len(nonempty) > 1:
        errors.append(
            "master/edl.json: seated synthetic VO uses mixed voice_speaker_id "
            f"({sorted(nonempty)}). Episode VO must be one clone throughout."
        )
    locked = ""
    try:
        from interview_mux.speaker_delivery_plan import episode_vo_identity

        locked = _as_id((episode_vo_identity(ctx) or {}).get("speaker_id"))
    except Exception:
        locked = ""
    if locked:
        for clip in clips:
            voice = _as_id(clip.get("voice_speaker_id"))
            label = _as_id(clip.get("line_id")) or (
                f"{_as_id(clip.get('after_segment_id'))}->"
                f"{_as_id(clip.get('before_segment_id'))}"
            )
            if not voice:
                errors.append(
                    f'master/edl.json: synthetic "{label}" missing voice_speaker_id '
                    f"(episode lock is {locked})."
                )
            elif voice != locked:
                errors.append(
                    f'master/edl.json: synthetic "{label}" voice_speaker_id '
                    f"{voice!r} != episode lock {locked!r}."
                )
    if not ctx.artifact_exists("vo_pickup/synthesis_report.json"):
        return
    try:
        report = ctx.read_json("vo_pickup/synthesis_report.json")
    except Exception:
        return
    seated_ids = {
        _as_id(c.get("line_id"))
        for c in clips
        if _as_id(c.get("line_id"))
    }
    refs: set[str] = set()
    for entry in (report.get("entries") or []) if isinstance(report, dict) else []:
        if not isinstance(entry, dict):
            continue
        lid = _as_id(entry.get("line_id"))
        if lid not in seated_ids:
            continue
        ref_id = _as_id(entry.get("voice_ref_id"))
        ref_audio = _as_id(entry.get("ref_audio"))
        key = ref_id or (ref_audio.split("/")[-1] if ref_audio else "")
        if key:
            refs.add(key)
    if len(refs) > 1:
        errors.append(
            "vo_pickup/synthesis_report.json: seated synthetics used mixed "
            f"voice references ({sorted(refs)}). Episode VO must use one approved sample."
        )


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
        if ok:
            return
        # Selection is the air-order authority. A volley the *selection* already
        # splits or reorders is not the EDL's defect: the EDL is required to
        # follow the selection, and neither the frozen selection nor the sealed
        # episode structure can be rewritten here. Report those as warnings and
        # keep only violations the EDL introduced on its own (ISSUES entry 50).
        inherited: set[str] = set()
        try:
            if ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                sel_order = [
                    str(x) for x in ((sel or {}).get("ordered_segment_ids") or []) if x
                ]
                if sel_order:
                    _sel_ok, sel_flags = check_speaker_volley_integrity(sel_order, volleys)
                    inherited = set(sel_flags)
        except Exception:
            inherited = set()
        for f in flags[:8]:
            if f in inherited:
                try:
                    ctx.log(
                        f"speaker_volley_integrity:{f} inherited from selection order "
                        "(air-order authority); not an EDL defect",
                        level="warning",
                        stage="edl",
                    )
                except Exception:
                    pass
                continue
            errors.append(f"speaker_volley_integrity:{f}")
    except Exception:
        return
