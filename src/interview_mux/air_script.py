"""Air-script: Shape realization on mastering_plan (paper-edit + sonic scenes).

Canon: docs/cross-cutting/air-script.md
Pass A (after ranking): membership / order / cold_open / story_spine.
Pass B (after layup): per-seam montage moves + VO seats.
Opportunity hunter: pause-tails and spine hinges → sonic_scenes for music compose.
Fail-open when mastering.air_script.enable is false or the plan is absent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.hard_keep import hard_keep_segment_ids
from interview_mux.mastering_plan_loader import forced_sparse_plan, load_plan_raw, write_plan
from interview_mux.run_context import RunContext

AIR_SCRIPT_MOVES: tuple[str, ...] = (
    "native_handoff",
    "vo_then_clip",
    "clip_then_react_vo",
    "music_face_out",
    "air_breathe",
    "cold_open_hook",
    "information_package",
    "episode_close",
)

VO_SEAT_MOVES = frozenset({"vo_then_clip", "clip_then_react_vo", "information_package"})
# Air a present orientation line unless native-open omit already decided otherwise.
ORIENTATION_ALWAYS = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def air_script_cfg() -> dict[str, Any]:
    raw = ((merged_config().get("mastering") or {}).get("air_script") or {})
    defaults = {
        "enable": True,
        # Default True for Manual; full-auto/homunculus override below.
        "fail_open": True,
        "bed_coverage_aim_lo": 0.40,
        "bed_coverage_aim_hi": 0.85,
    }
    if isinstance(raw, dict):
        out = {**defaults, **raw}
    else:
        out = dict(defaults)
    # DEEP-AIR-01: under automation/homunculus, fail closed unless config forces open.
    if "fail_open" not in (raw if isinstance(raw, dict) else {}):
        try:
            from interview_mux.automation_run import automation_driver_env_enabled

            if automation_driver_env_enabled():
                out["fail_open"] = False
        except Exception:
            pass
    return out


def air_script_enabled() -> bool:
    return bool(air_script_cfg().get("enable", True))


def empty_air_script(*, pass_name: str = "pass_a") -> dict[str, Any]:
    return {
        "version": 1,
        "pass": pass_name,
        "beats": [],
        "omits": [],
        "energy_curve": [],
        "cold_open": {"kind": "none", "segment_id": None},
        "vo_seats": {
            "seated_line_ids": [],
            "omitted_line_ids": [],
            "orientation_id": None,
        },
        "generated_at": _now(),
    }


def persist_air_script_disabled_skip(
    ctx: RunContext,
    *,
    stage: str,
    pass_name: str,
) -> dict[str, Any]:
    """CSP-01: enable=false writes an honest skip latch on mastering_plan.

    Seed walk must not stall pending when ``mastering.air_script.enable`` is off.
    Caller heals after this write.
    """
    sid = str(stage or "").strip() or "air_script_compose"
    plan = load_plan_raw(ctx)
    if not isinstance(plan, dict):
        plan = forced_sparse_plan(reason="mastering.air_script.enable=false")
    else:
        plan = dict(plan)
    script = empty_air_script(pass_name=pass_name)
    script["enabled"] = False
    script["skip_reason"] = "air_script_disabled"
    script["note"] = "mastering.air_script.enable=false"
    plan["air_script"] = script
    write_plan(ctx, plan)
    if sid == "air_script_compose":
        try:
            from interview_mux.omit_ledger import OMIT_LEDGER_REL, empty_omit_ledger

            if not ctx.artifact_exists(OMIT_LEDGER_REL):
                ledger = empty_omit_ledger()
                ledger["skip_reason"] = "air_script_disabled"
                ctx.write_json(
                    OMIT_LEDGER_REL, ledger, stage_key="air_script_compose"
                )
        except Exception:
            pass
    ctx.log(
        f"{sid} skipped (mastering.air_script.enable=false) — wrote skip latch",
        level="info",
        stage=sid,
        action_id="air_script.disabled_skip",
    )
    return plan


def load_air_script(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None
    raw = plan.get("air_script")
    return raw if isinstance(raw, dict) else None


def ordered_ids_from_air_script(plan: dict[str, Any] | None) -> list[str]:
    """Air order for Pass B / lint — prefer plan.ordered_segment_ids.

    ``air_script.beats`` may be a thin hosted-framing reseat stub (3 VO seats).
    Using that as order shrinks Pass B to a three-clip show, trips ``vo_wall``,
    and delight-remutates forever (forensics exec_11130).
    """
    plan_dict = plan if isinstance(plan, dict) else {}
    plan_ordered = [str(s) for s in (plan_dict.get("ordered_segment_ids") or []) if s]
    script = load_air_script(plan_dict)
    if not script:
        return plan_ordered
    beat_ordered: list[str] = []
    seen: set[str] = set()
    for beat in script.get("beats") or []:
        if not isinstance(beat, dict):
            continue
        sid = str(beat.get("segment_id") or "")
        if sid and sid not in seen and str(beat.get("montage_move") or "") != "episode_close":
            beat_ordered.append(sid)
            seen.add(sid)
    if plan_ordered and (not beat_ordered or len(plan_ordered) >= len(beat_ordered)):
        return plan_ordered
    return beat_ordered


def requested_vo_line_ids(plan: dict[str, Any] | None) -> set[str]:
    """VO line ids claimed by beats — never revive seats listed as omitted.

    Pass B can stamp ``line_id`` onto ``vo_then_clip`` beats from gap rows that
    are already air_script_omit. Those beat refs must not expand the EDL seat
    set via ``filter_gap_lines_for_air_script`` (forensics exec_11130 pre_mix
    omit_collateral thrash on vo_layup_seg_019).
    """
    script = load_air_script(plan)
    if not script:
        return set()
    seats = script.get("vo_seats") if isinstance(script.get("vo_seats"), dict) else {}
    omitted = {
        str(x)
        for x in (seats.get("omitted_line_ids") or [])
        if x
    }
    out: set[str] = set()
    for beat in script.get("beats") or []:
        if not isinstance(beat, dict):
            continue
        if str(beat.get("montage_move") or "") not in VO_SEAT_MOVES:
            continue
        lid = str(beat.get("line_id") or "")
        if lid and lid not in omitted:
            out.add(lid)
    return out


def _orientation_line_id() -> str:
    try:
        from interview_mux.opening_orientation import ORIENTATION_LINE_ID

        return str(ORIENTATION_LINE_ID)
    except Exception:
        return "vo_preface_episode_orientation"


def _orientation_line_waived(line: dict[str, Any], gap_report: dict[str, Any] | None) -> bool:
    """True when orientation must not be force-seated (omit meta or durable waive).

    Bare ``skipped_optional`` / ``air_script_omit_sync`` alone are not durable —
    ``ORIENTATION_ALWAYS`` / ``filter_gap_lines_for_air_script`` revive those when
    ``opening_orientation.required`` is still true (exec_11630 audible_count=0).
    """
    try:
        from interview_mux.opening_orientation import orientation_omitted

        if orientation_omitted(gap_report):
            return True
    except Exception:
        pass
    reason = str(line.get("skip_reason_code") or "").strip().lower()
    # Stale Pass-B sync stamps must not waive a still-required orientation.
    if reason in {"execution_contract_waive"}:
        return True
    compensating = str(line.get("compensating_path") or "").strip().lower()
    if compensating in {"tier_d_logged_waive"}:
        return True
    return False


def build_vo_seats(
    plan: dict[str, Any] | None,
    gap_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Published live-VO contract: who airs, who Pass B omitted, orientation id.

    Waived / omitted orientation stays out of seated_line_ids (tier-D and native-open).
    """
    default_orientation_id = _orientation_line_id()
    orientation_id: str | None = default_orientation_id
    seated = set(requested_vo_line_ids(plan))
    # Preserve published seats (may exist before beats are rewritten).
    prior = load_air_script(plan) if isinstance(plan, dict) else None
    if isinstance(prior, dict):
        prior_seats = prior.get("vo_seats") if isinstance(prior.get("vo_seats"), dict) else {}
        seated |= {str(x) for x in (prior_seats.get("seated_line_ids") or []) if x}
        prior_orient = str(prior_seats.get("orientation_id") or "").strip()
        if prior_orient:
            seated.add(prior_orient)
    omitted: set[str] = set()
    live_orientation: str | None = None
    if isinstance(gap_report, dict):
        try:
            from interview_mux.opening_orientation import orientation_omitted

            if orientation_omitted(gap_report):
                orientation_id = None
        except Exception:
            pass
        for line in gap_report.get("interviewer_lines") or []:
            if not isinstance(line, dict):
                continue
            lid = str(line.get("line_id") or "")
            if not lid:
                continue
            is_orient = _is_orientation_line(line) or lid == default_orientation_id
            if is_orient:
                if _orientation_line_waived(line, gap_report):
                    omitted.add(lid)
                    seated.discard(lid)
                    continue
                seated.add(lid)
                live_orientation = lid
                orientation_id = lid
                continue
            # Gap omit/skip is the later decision — never keep a stale seat.
            if not gap_line_air_eligible(line):
                seated.discard(lid)
                omitted.add(lid)
                continue
            if lid in seated:
                continue
            omitted.add(lid)
    if live_orientation is None and orientation_id and orientation_id not in seated:
        # No live orientation in gap — do not invent a seat via default id.
        orientation_id = None
    omitted -= seated
    seated.discard("")
    omitted.discard("")
    return {
        "seated_line_ids": sorted(seated),
        "omitted_line_ids": sorted(omitted),
        "orientation_id": orientation_id,
    }


def seated_vo_line_ids(plan: dict[str, Any] | None) -> set[str]:
    """Live VO line ids. Prefer published vo_seats; fall back to beats + orientation."""
    script = load_air_script(plan)
    if not script:
        return set()
    seats = script.get("vo_seats")
    if isinstance(seats, dict) and "seated_line_ids" in seats:
        out = {str(x) for x in (seats.get("seated_line_ids") or []) if x}
        omitted = {str(x) for x in (seats.get("omitted_line_ids") or []) if x}
        oid = str(seats.get("orientation_id") or "").strip()
        # orientation_id must not re-seat a line already removed from seated_line_ids
        # or listed only in omitted_line_ids (omit wins when not also seated).
        if oid and oid not in omitted and oid in out:
            pass
        elif oid and oid not in omitted and not out:
            # Legacy orientation-only seat documents.
            out.add(oid)
        # Intersection: seated wins — floor/protect reseat is the later decision.
        # omitted_vo_line_ids subtracts seated, so do not drop seated here.
        return out
    return requested_vo_line_ids(plan)


def omitted_vo_line_ids(plan: dict[str, Any] | None) -> set[str]:
    script = load_air_script(plan)
    if not script:
        return set()
    seats = script.get("vo_seats")
    if isinstance(seats, dict) and "omitted_line_ids" in seats:
        seated = seated_vo_line_ids(plan)
        return {str(x) for x in (seats.get("omitted_line_ids") or []) if x} - seated
    return set()


def native_handoff_waive_reasons(plan: dict[str, Any] | None) -> dict[str, str]:
    """Dest segment_id → glue_waived reason (`native_handoff` or `air_breathe`)."""
    script = load_air_script(plan)
    if not script:
        return {}
    out: dict[str, str] = {}
    for beat in script.get("beats") or []:
        if not isinstance(beat, dict):
            continue
        move = str(beat.get("montage_move") or "")
        if move not in {"native_handoff", "air_breathe"}:
            continue
        sid = str(beat.get("segment_id") or "")
        if sid:
            out[sid] = move
    return out


def native_handoff_segment_ids(plan: dict[str, Any] | None) -> set[str]:
    """Destinations air-script seated as native Q→A / breathe — no spoken glue."""
    return set(native_handoff_waive_reasons(plan))


def omitted_segment_ids(plan: dict[str, Any] | None) -> set[str]:
    script = load_air_script(plan)
    if not script:
        return set()
    out: set[str] = set()
    for row in script.get("omits") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind") or "") != "segment_exclude":
            continue
        sid = str(row.get("subject_id") or "")
        if sid:
            out.add(sid)
    return out


def beat_move_for_segment(plan: dict[str, Any] | None, segment_id: str) -> str | None:
    script = load_air_script(plan)
    if not script:
        return None
    for beat in script.get("beats") or []:
        if not isinstance(beat, dict):
            continue
        if str(beat.get("segment_id") or "") == str(segment_id):
            return str(beat.get("montage_move") or "") or None
    return None


def compile_circumstance_card(ctx: RunContext) -> dict[str, Any]:
    """Deterministic circumstance card — no LLM."""
    from interview_mux.refinement_policy import detect_tape_character, resolve_policy_pack

    characters = detect_tape_character(ctx)
    pack = resolve_policy_pack(ctx, characters)
    format_class = ""
    tone_class = ""
    if ctx.artifact_exists("understanding/analysis_state.json"):
        st = ctx.read_json("understanding/analysis_state.json")
        if isinstance(st, dict):
            style = st.get("style") if isinstance(st.get("style"), dict) else {}
            format_class = str(style.get("format_class") or "")
            tone_class = str(style.get("tone_class") or "")
    topology_class = ""
    speaker_count = 0
    if ctx.artifact_exists("understanding/source_topology.json"):
        topo = ctx.read_json("understanding/source_topology.json")
        if isinstance(topo, dict):
            topology_class = str(topo.get("topology_class") or topo.get("class") or "")
            speaker_count = int(topo.get("speaker_count") or 0 or 0)
    duration_sec = 0.0
    underscore_policy = "normal"
    source_music_risk = False
    source_music_risk_level = "low"
    if ctx.artifact_exists("understanding/source_acoustic_profile.json"):
        sap = ctx.read_json("understanding/source_acoustic_profile.json")
        if isinstance(sap, dict):
            duration_sec = float(sap.get("duration_sec") or sap.get("duration") or 0)
            mix = sap.get("mix_contract") if isinstance(sap.get("mix_contract"), dict) else {}
            underscore_policy = str(mix.get("underscore_policy") or sap.get("underscore_policy") or "normal")
            risk_raw = sap.get("source_music_risk")
            if isinstance(risk_raw, str):
                source_music_risk_level = risk_raw.lower() or "low"
                source_music_risk = source_music_risk_level in {"high", "medium"}
            else:
                source_music_risk = bool(risk_raw)
                source_music_risk_level = "high" if source_music_risk else "low"
            if underscore_policy in {"skip", "sparse_or_skip"}:
                source_music_risk = True
                if source_music_risk_level == "low":
                    source_music_risk_level = "high"
    g1_skip = False
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled, resolve_gap_vo_delivery
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

        g1_skip = gap_fill_was_skipped(ctx) or not gap_framing_enabled(ctx)
        if not g1_skip:
            _ = resolve_gap_vo_delivery(ctx)
    except Exception:
        g1_skip = False
    nle_locked = False
    try:
        from interview_mux.nle_state import load_nle, nle_has_operator_edits

        nle_locked = nle_has_operator_edits(load_nle(ctx))
    except Exception:
        nle_locked = False
    passion_ids: list[str] = []
    if ctx.artifact_exists("analysis/high_value_speech_islands.json"):
        hv = ctx.read_json("analysis/high_value_speech_islands.json")
        if isinstance(hv, dict):
            passion_ids = [str(x) for x in (hv.get("segment_ids_touched") or []) if x]
    panel_overlap = "panel" in (format_class or topology_class or "").lower() and (
        speaker_count or 0
    ) >= 4
    dry_beds = bool(
        source_music_risk_level == "high"
        or underscore_policy in {"skip", "sparse_or_skip"}
        or panel_overlap
    )
    return {
        "tape_character": list(characters),
        "policy_pack": str(pack.get("pack_id") or "default"),
        "format_class": format_class or None,
        "tone_class": tone_class or None,
        "topology_class": topology_class or None,
        "speaker_count": speaker_count or None,
        "duration_sec": duration_sec or None,
        "g1_skip": g1_skip,
        "nle_locked": nle_locked,
        "underscore_policy": underscore_policy,
        "source_music_risk": source_music_risk,
        "source_music_risk_level": source_music_risk_level,
        "panel_overlap": panel_overlap,
        "passion_segment_ids": passion_ids[:24],
        "dry_beds": dry_beds,
        "richer_musical_hinges": bool(g1_skip),
        "generated_at": _now(),
    }


def _selection_ordered(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return []
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return []
    return [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]


def _talking_point_ids(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("understanding/talking_points.json"):
        return []
    tps = ctx.read_json("understanding/talking_points.json")
    rows = tps.get("talking_points") if isinstance(tps, dict) else tps
    ids: list[str] = []
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for key in ("segment_id", "cut_id", "source_segment_id"):
            sid = str(row.get(key) or "")
            if sid and sid not in seen:
                ids.append(sid)
                seen.add(sid)
        for sid in row.get("segment_ids") or []:
            s = str(sid)
            if s and s not in seen:
                ids.append(s)
                seen.add(s)
    return ids


def _story_spine(ctx: RunContext, ordered: list[str]) -> dict[str, Any]:
    tp_ids = [s for s in _talking_point_ids(ctx) if s in set(ordered)]
    scenes: list[dict[str, Any]] = []
    if ctx.artifact_exists("master/narrative_plan.json"):
        np = ctx.read_json("master/narrative_plan.json")
        chapters = (np.get("chapters") or []) if isinstance(np, dict) else []
        for i, ch in enumerate(chapters):
            if not isinstance(ch, dict):
                continue
            segs = [str(s) for s in (ch.get("segment_ids") or ch.get("segments") or []) if s and s in set(ordered)]
            if not segs:
                continue
            scenes.append(
                {
                    "scene_id": str(ch.get("chapter_id") or ch.get("id") or f"scene_{i+1}"),
                    "title": str(ch.get("title") or ch.get("label") or f"Scene {i+1}"),
                    "segment_ids": segs,
                    "purpose": str(ch.get("summary") or ch.get("purpose") or "")[:240],
                }
            )
    if not scenes and tp_ids:
        scenes.append(
            {
                "scene_id": "spine_talking_points",
                "title": "Talking points",
                "segment_ids": tp_ids,
                "purpose": "retell checklist",
            }
        )
    if not scenes and ordered:
        scenes.append(
            {
                "scene_id": "spine_air_order",
                "title": "Air order",
                "segment_ids": list(ordered),
                "purpose": "selection order",
            }
        )
    return {"talking_point_ids": tp_ids, "scenes": scenes}


def _energy_curve(ordered: list[str]) -> list[dict[str, Any]]:
    if not ordered:
        return []
    n = len(ordered)
    points = [
        ("hook", ordered[0], 0.9),
        ("development", ordered[min(1, n - 1)], 0.55),
        ("mid", ordered[n // 2], 0.45),
        ("climax", ordered[max(0, n - 2)], 0.85),
        ("close", ordered[-1], 0.4),
    ]
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for label, sid, energy in points:
        key = f"{label}:{sid}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label, "segment_id": sid, "energy": energy})
    return out


def lint_story_clarity(
    *,
    beats: list[dict[str, Any]],
    ordered: list[str],
    spine: dict[str, Any] | None = None,
    cold_open: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Story-success contract. Failures are blocking for paper-edit followability."""
    errors: list[str] = []
    warnings: list[str] = []
    vo_run = 0
    orientation_count = 0
    moves = [str(b.get("montage_move") or "") for b in beats if isinstance(b, dict)]
    for beat in beats:
        if not isinstance(beat, dict):
            continue
        move = str(beat.get("montage_move") or "")
        role = str(beat.get("role") or "")
        # Hosted-framing reseat stubs are seat markers, not a listener VO wall.
        if move in VO_SEAT_MOVES and role != "hosted_framing_reseat":
            vo_run += 1
            if vo_run >= 3:
                warnings.append("vo_wall")
        else:
            vo_run = 0
        if beat.get("is_orientation"):
            orientation_count += 1
        entering = str(beat.get("know_entering") or "").strip()
        leaving = str(beat.get("know_leaving") or "").strip()
        if (
            role != "hosted_framing_reseat"
            and move not in {"episode_close", "air_breathe", "music_face_out"}
            and (not entering or not leaving)
        ):
            warnings.append(f"missing_know_{beat.get('id') or beat.get('segment_id')}")
    if orientation_count > 1:
        errors.append("multiple_orientation")
    cold = cold_open if isinstance(cold_open, dict) else {}
    kind = str(cold.get("kind") or "none")
    hook_sid = str(cold.get("segment_id") or "")
    if kind in {"segment_hook", "vo_plus_segment"} and hook_sid:
        aired = {str(b.get("segment_id") or "") for b in beats if isinstance(b, dict)}
        if hook_sid not in aired and hook_sid not in set(ordered):
            errors.append("unpaid_cold_open")
    spine_ids = []
    if isinstance(spine, dict):
        spine_ids = [str(s) for s in (spine.get("talking_point_ids") or []) if s]
    aired_ids = [str(b.get("segment_id") or "") for b in beats if isinstance(b, dict) and b.get("segment_id")]
    omitted_setup = [s for s in spine_ids if s not in set(aired_ids) and s in set(ordered)]
    # Spine ids still in ordered but not in beats would be a drop-without-omit.
    if omitted_setup and not any(str(b.get("montage_move")) == "native_handoff" for b in beats if isinstance(b, dict)):
        warnings.append("spine_not_on_beats")
    score = 1.0
    score -= 0.25 * len(errors)
    score -= 0.05 * min(len(warnings), 8)
    if "vo_wall" in warnings:
        score -= 0.15
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "story_followability": round(max(0.0, min(1.0, score)), 4),
        "orientation_count": orientation_count,
    }


def enforce_air_script_omits(ctx: RunContext, selection: dict[str, Any]) -> dict[str, Any]:
    """Drop Pass A omitted non-hard-keeps if a later pack tries to restuff them."""
    plan = load_plan_raw(ctx)
    omitted = omitted_segment_ids(plan)
    if not omitted:
        return selection
    keeps = hard_keep_segment_ids(ctx)
    out = dict(selection)
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    kept = [s for s in ordered if s not in omitted or s in keeps]
    if kept == ordered:
        return selection
    out["ordered_segment_ids"] = kept
    excl = list(out.get("excluded_segment_ids") or [])
    have = {
        (e if isinstance(e, str) else str((e or {}).get("segment_id") or ""))
        for e in excl
    }
    for sid in ordered:
        if sid not in kept and sid not in have:
            excl.append({"segment_id": sid, "reason": "air_script_omit"})
    out["excluded_segment_ids"] = excl
    return out


def _prev_is_frame_turn(prev: dict[str, Any] | None) -> bool:
    """True when the previous aired clip is already a host/interviewer turn.

    Do not substring-match ``interview`` — that also matches ``interviewee`` and
    ``interviewee_answer``, which wrongly native-handoffs recovery layups after
    a guest beat.
    """
    if not isinstance(prev, dict):
        return False
    role = str(prev.get("speaker_role") or "").strip().lower()
    try:
        from interview_mux.conversation_context import role_is_frame

        if role_is_frame(role):
            return True
    except Exception:
        if role in {"interviewer", "moderator", "co_host", "host", "frame"}:
            return True
    typ = str(prev.get("type") or "").strip().lower()
    if typ in {"interviewer_question", "host_question", "moderator_question"}:
        return True
    if typ.startswith("interviewer_") or typ.startswith("host_"):
        return True
    return False


def _same_speaker_contiguous(
    prev: dict[str, Any] | None, cur: dict[str, Any] | None
) -> bool:
    if not isinstance(prev, dict) or not isinstance(cur, dict):
        return False
    if str(prev.get("speaker_id") or "") != str(cur.get("speaker_id") or ""):
        return False
    try:
        gap = int(cur.get("start_ms") or 0) - int(prev.get("end_ms") or 0)
    except (TypeError, ValueError):
        return False
    return 0 <= gap <= 2500


def _gap_line_for(
    gap_report: dict[str, Any] | None, segment_id: str, placement: str = "before"
) -> dict[str, Any] | None:
    if not isinstance(gap_report, dict):
        return None
    matches: list[dict[str, Any]] = []
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        # Required recovery layups must remain visible so Pass B can revive a
        # bad omit (e.g. interviewee matched as host via substring).
        if line.get("skipped_optional") and not line.get("required"):
            continue
        if str(line.get("targets_segment_id") or "") != segment_id:
            continue
        if str(line.get("placement") or "before") != placement:
            continue
        delivery = str(line.get("delivery") or "").lower()
        if delivery not in {"record", "synthesize"}:
            continue
        matches.append(line)
    if not matches:
        return None
    for line in matches:
        if _is_orientation_line(line):
            return line
    return matches[0]


def _is_orientation_line(line: dict[str, Any] | None) -> bool:
    if not isinstance(line, dict):
        return False
    try:
        from interview_mux.opening_orientation import is_episode_orientation

        return is_episode_orientation(line)
    except Exception:
        return str(line.get("line_category") or "") in {"episode_preface", "episode_orientation"}


def compose_pass_a(ctx: RunContext) -> dict[str, Any]:
    """Membership, order, cold open, energy curve, story spine. Writes plan.air_script."""
    plan = load_plan_raw(ctx)
    if not isinstance(plan, dict):
        return {}
    card = compile_circumstance_card(ctx)
    ordered = _selection_ordered(ctx)
    keeps = hard_keep_segment_ids(ctx)
    if card.get("nle_locked"):
        try:
            from interview_mux.nle_state import load_nle

            nle = load_nle(ctx)
            keeps = set(keeps) | {
                str(s) for s in (nle.get("ordered_segment_ids") or []) if s
            }
        except Exception:
            pass
    spine = _story_spine(ctx, ordered)
    spine_set = set(spine.get("talking_point_ids") or [])
    omit_ids: list[str] = []
    long_meander = "long_meander" in (card.get("tape_character") or [])
    if long_meander and spine_set and len(ordered) > max(8, len(spine_set) + 4):
        for sid in ordered:
            if sid in keeps or sid in spine_set:
                continue
            if sid in (card.get("passion_segment_ids") or []):
                continue
            omit_ids.append(sid)
        # Keep duration floor: never drop below ~40% of ordered.
        floor_n = max(len(keeps | spine_set), int(0.4 * len(ordered)))
        keep_n = len(ordered) - len(omit_ids)
        if keep_n < floor_n:
            omit_ids = omit_ids[: max(0, len(ordered) - floor_n)]
    kept = [s for s in ordered if s not in set(omit_ids)]
    if not kept:
        kept = list(ordered)

    cold = plan.get("cold_open") if isinstance(plan.get("cold_open"), dict) else {}
    cold_kind = str(cold.get("kind") or "none")
    hook_sid = str(cold.get("segment_id") or "")
    if cold_kind == "none" and kept:
        # Honest none unless a hook is already declared.
        pass
    if hook_sid and hook_sid in kept and kept[0] != hook_sid:
        kept = [hook_sid] + [s for s in kept if s != hook_sid]

    omits = [
        {
            "kind": "segment_exclude",
            "subject_id": sid,
            "compensating_path": "talking_point_spine_or_later_package",
            "reason_code": "pass_a_padding",
        }
        for sid in omit_ids
        if sid not in keeps
    ]
    script = empty_air_script(pass_name="pass_a")
    script["cold_open"] = {"kind": cold_kind, "segment_id": hook_sid or None}
    script["omits"] = omits
    script["energy_curve"] = _energy_curve(kept)
    script["beats"] = [
        {
            "id": f"beat_{i+1:03d}",
            "segment_id": sid,
            "montage_move": "native_handoff",
            "know_entering": "prior context",
            "know_leaving": "native beat",
        }
        for i, sid in enumerate(kept)
    ]
    plan = dict(plan) if plan else {}
    plan["air_script"] = script
    plan["circumstance_card"] = card
    plan["story_spine"] = spine
    if kept:
        plan["ordered_segment_ids"] = kept
    write_plan(ctx, plan)

    if omits:
        try:
            from interview_mux.omit_ledger import (
                OMIT_LEDGER_REL,
                empty_omit_ledger,
                mint_entry,
                write_omit_ledger,
            )

            prior = (
                ctx.read_json(OMIT_LEDGER_REL)
                if ctx.artifact_exists(OMIT_LEDGER_REL)
                else empty_omit_ledger()
            )
            entries = [e for e in (prior.get("entries") or []) if isinstance(e, dict)]
            seq = len(entries) + 1
            for i, row in enumerate(omits):
                entries.append(
                    mint_entry(
                        kind="segment_exclude",
                        subject_id=row["subject_id"],
                        decision="omit",
                        reason_code=str(row.get("reason_code") or "pass_a_padding"),
                        owner_stage="air_script_compose",
                        compensating_path=str(row.get("compensating_path") or ""),
                        seq=seq + i,
                    )
                )
            prior = dict(prior) if isinstance(prior, dict) else empty_omit_ledger()
            prior["entries"] = entries
            write_omit_ledger(ctx, prior)
        except Exception:
            pass

    # ASC-B3: air omits stay on the plan / omit ledger only — never shrink
    # master/selection.json. Later packs may still call enforce_air_script_omits.
    return plan


def compose_pass_b(ctx: RunContext) -> dict[str, Any]:
    """Per-seam montage moves; VO seats only where the listener would be lost."""
    try:
        from interview_mux.seat_authority import seat_mutation_allowed, soft_freeze_active

        if soft_freeze_active(ctx):
            allowed, why = seat_mutation_allowed(
                ctx, reason="compose_pass_b", require_meta_gate=True
            )
            if not allowed:
                # No-op: return existing plan under freeze
                plan = load_plan_raw(ctx) or {}
                ctx.log(
                    f"compose_pass_b: frozen no-op ({why})",
                    level="info",
                    stage="air_script_seams",
                )
                return plan if isinstance(plan, dict) else {}
    except Exception:
        pass
    plan = load_plan_raw(ctx) or {}
    script = load_air_script(plan) or empty_air_script(pass_name="pass_b")
    ordered = ordered_ids_from_air_script(plan) or _selection_ordered(ctx)
    card = plan.get("circumstance_card") if isinstance(plan.get("circumstance_card"), dict) else compile_circumstance_card(ctx)
    g1_skip = bool(card.get("g1_skip"))
    gap_report = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else {}
    )
    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        by_id = {
            str(s.get("segment_id")): s
            for s in ((man or {}).get("segments") or [])
            if isinstance(s, dict) and s.get("segment_id")
        }
    packages: list[dict[str, Any]] = []
    if isinstance(plan.get("information_packages"), list):
        packages = [p for p in plan["information_packages"] if isinstance(p, dict)]
    package_after = {str(p.get("after_segment_id") or "") for p in packages if p.get("after_segment_id")}
    cold = script.get("cold_open") if isinstance(script.get("cold_open"), dict) else {}
    cold_kind = str(cold.get("kind") or (plan.get("cold_open") or {}).get("kind") or "none")
    hook_sid = str(cold.get("segment_id") or (plan.get("cold_open") or {}).get("segment_id") or "")
    has_orientation = False
    omitted_orientation = False
    if isinstance(gap_report, dict):
        has_orientation = any(
            _is_orientation_line(ln)
            for ln in (gap_report.get("interviewer_lines") or [])
            if isinstance(ln, dict) and not ln.get("skipped_optional")
        )
        try:
            from interview_mux.opening_orientation import orientation_omitted

            omitted_orientation = orientation_omitted(gap_report)
        except Exception:
            omitted_orientation = False
    opening_owned: set[str] = set()
    if (has_orientation or omitted_orientation) and ordered:
        opening_owned.add(str(ordered[0]))
        try:
            from interview_mux.opening_orientation import native_cold_open_segment_id

            hook = native_cold_open_segment_id(ctx, list(ordered))
            if hook:
                opening_owned.add(str(hook))
        except Exception:
            pass

    beats: list[dict[str, Any]] = []
    for i, sid in enumerate(ordered):
        prev = by_id.get(ordered[i - 1]) if i else None
        cur = by_id.get(sid)
        line = _gap_line_for(gap_report if isinstance(gap_report, dict) else None, sid, "before")
        if line and not gap_line_air_eligible(line):
            line = None
        orient = _is_orientation_line(line) and not omitted_orientation
        move = "native_handoff"
        line_id = None
        if i == 0 and cold_kind in {"segment_hook", "vo_plus_segment"} and (not hook_sid or hook_sid == sid):
            move = "cold_open_hook"
        elif orient and not g1_skip:
            move = "vo_then_clip"
            line_id = str(line.get("line_id") or "") if line else None
        elif sid in package_after:
            move = "information_package"
            if line and not g1_skip:
                line_id = str(line.get("line_id") or "")
        elif g1_skip:
            move = "music_face_out" if i > 0 and not _same_speaker_contiguous(prev, cur) else "native_handoff"
        elif _same_speaker_contiguous(prev, cur):
            move = "native_handoff"
        elif line and str(line.get("origin") or "") == "nugget_layup":
            # Prefer skip unless the line recovers excluded facts.
            nuggets = line.get("selected_nugget_ids") or line.get("nugget_ids") or []
            if nuggets:
                move = "vo_then_clip"
                line_id = str(line.get("line_id") or "")
            else:
                move = "native_handoff"
        elif i > 0 and not _same_speaker_contiguous(prev, cur):
            move = "music_face_out"
        if (
            _prev_is_frame_turn(prev)
            and move in VO_SEAT_MOVES
            and not orient
        ):
            move = "native_handoff"
            line_id = None
        # Native intro (or seated orientation) owns the opening slot — no extra VO.
        if (has_orientation or omitted_orientation) and sid in opening_owned and move in VO_SEAT_MOVES and not orient:
            move = "native_handoff"
            line_id = None
        know_e = "oriented" if i == 0 or orient else "prior native"
        know_l = "next native unlocked" if move in VO_SEAT_MOVES else "native continues"
        beats.append(
            {
                "id": f"beat_{i+1:03d}",
                "segment_id": sid,
                "montage_move": move,
                "line_id": line_id,
                "is_orientation": bool(orient),
                "know_entering": know_e,
                "know_leaving": know_l,
            }
        )
    if ordered:
        beats.append(
            {
                "id": "beat_close",
                "segment_id": ordered[-1],
                "montage_move": "episode_close",
                "know_entering": "final native",
                "know_leaving": "episode cadence",
            }
        )
    lint = lint_story_clarity(
        beats=beats,
        ordered=ordered,
        spine=plan.get("story_spine") if isinstance(plan.get("story_spine"), dict) else None,
        cold_open=cold,
    )
    script = dict(script)
    script["pass"] = "pass_b"
    script["beats"] = beats
    script["story_clarity"] = lint
    # Clear stale gap omit flags for lines Pass B just seated into beats so
    # build_vo_seats does not immediately unseat required recovery layups.
    gap_for_seats: dict[str, Any] | None = (
        gap_report if isinstance(gap_report, dict) else None
    )
    beat_line_ids = {
        str(b.get("line_id") or "")
        for b in beats
        if isinstance(b, dict) and b.get("line_id")
    }
    if gap_for_seats and beat_line_ids:
        gap_for_seats = dict(gap_for_seats)
        cleared_lines: list[Any] = []
        for ln in gap_for_seats.get("interviewer_lines") or []:
            if not isinstance(ln, dict):
                cleared_lines.append(ln)
                continue
            lid = str(ln.get("line_id") or "")
            if lid and lid in beat_line_ids:
                ln = dict(ln)
                ln.pop("air_script_omit", None)
                ln["skipped_optional"] = False
                if not ln.get("skip_reason_code"):
                    pass
                else:
                    # Drop omit-ish skip reasons revived by Pass B seating.
                    reason = str(ln.get("skip_reason_code") or "").lower()
                    if reason in {
                        "air_script_omit",
                        "air_script_omit_sync",
                        "not_on_air",
                        "rendered_floor_prefer_wav",
                    }:
                        ln.pop("skip_reason_code", None)
            cleared_lines.append(ln)
        gap_for_seats["interviewer_lines"] = cleared_lines
    script["vo_seats"] = build_vo_seats({"air_script": script}, gap_for_seats)
    script["generated_at"] = _now()
    plan = dict(plan)
    plan["air_script"] = script
    write_plan(ctx, plan)
    return plan


def _pause_tail_segment_ids(ctx: RunContext, ordered: list[str]) -> list[str]:
    """Claim-landing pause tails from transcript word gaps (not mid-volley)."""
    if not ordered or not ctx.artifact_exists("transcript/full.json"):
        return []
    try:
        doc = ctx.read_json("transcript/full.json")
    except Exception:
        return []
    words = [w for w in ((doc or {}).get("words") or []) if isinstance(w, dict)]
    if not words:
        return []
    man = (
        ctx.read_json("segments/manifest.json")
        if ctx.artifact_exists("segments/manifest.json")
        else {}
    )
    by_id = {
        str(s.get("segment_id")): s
        for s in ((man or {}).get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    tails: list[str] = []
    for sid in ordered:
        seg = by_id.get(sid)
        if not isinstance(seg, dict):
            continue
        try:
            end_ms = int(seg.get("end_ms") or 0)
        except (TypeError, ValueError):
            continue
        following = [
            int(w.get("start_ms") or 0)
            for w in words
            if int(w.get("start_ms") or 0) >= end_ms
        ]
        if not following:
            tails.append(sid)
            continue
        gap = min(following) - end_ms
        if gap >= 400:
            tails.append(sid)
    return tails


def hunt_sonic_opportunities(ctx: RunContext) -> list[dict[str, Any]]:
    """Deterministic insert points for motif / beds / punctuators / outro."""
    plan = load_plan_raw(ctx) or {}
    card = plan.get("circumstance_card") if isinstance(plan.get("circumstance_card"), dict) else {}
    dry = bool(card.get("dry_beds"))
    ordered = ordered_ids_from_air_script(plan) or _selection_ordered(ctx)
    script = load_air_script(plan) or {}
    beats = [b for b in (script.get("beats") or []) if isinstance(b, dict)]
    energy = {str(p.get("segment_id")): p for p in (script.get("energy_curve") or []) if isinstance(p, dict)}
    opportunities: list[dict[str, Any]] = []
    if not ordered:
        return opportunities
    first = ordered[0]
    last = ordered[-1]
    opportunities.append(
        {
            "kind": "open_motif",
            "segment_id": first,
            "suggested_role": "theme_cold_open",
            "why": "speech-free motif after orientation / before first native",
        }
    )
    scenes = []
    spine = plan.get("story_spine") if isinstance(plan.get("story_spine"), dict) else {}
    scenes = [s for s in (spine.get("scenes") or []) if isinstance(s, dict)]
    if not scenes:
        scenes = [{"scene_id": "all", "segment_ids": ordered}]
    passion = set(str(x) for x in (card.get("passion_segment_ids") or []))
    for si, scene in enumerate(scenes):
        segs = [str(s) for s in (scene.get("segment_ids") or []) if s in set(ordered)]
        if not segs:
            continue
        lift = any(s in passion for s in segs) or (energy.get(segs[-1]) or {}).get("label") == "climax"
        if not dry:
            opportunities.append(
                {
                    "kind": "scene_bed",
                    "segment_id": segs[0],
                    "span_segment_ids": segs,
                    "suggested_role": "theme_underscore" if not lift else "optional_loop",
                    "why": f"abundant constant-level underbed for scene {scene.get('scene_id')}",
                }
            )
        opportunities.append(
            {
                "kind": "scene_resolve",
                "segment_id": segs[-1],
                "suggested_role": "theme_chapter_resolve",
                "why": "chapter / talking-point cadence",
            }
        )
        if si > 0 or card.get("richer_musical_hinges"):
            opportunities.append(
                {
                    "kind": "hinge_stinger",
                    "segment_id": segs[-1],
                    "suggested_role": "theme_emphasis",
                    "why": "scene hinge punctuator",
                }
            )
    for beat in beats:
        move = str(beat.get("montage_move") or "")
        sid = str(beat.get("segment_id") or "")
        if move == "information_package" and sid:
            opportunities.append(
                {
                    "kind": "package_faceout",
                    "segment_id": sid,
                    "suggested_role": "theme_chapter_resolve",
                    "why": "information package face-out",
                }
            )
        if move in {"music_face_out", "air_breathe"} and sid:
            opportunities.append(
                {
                    "kind": "hinge_stinger",
                    "segment_id": sid,
                    "suggested_role": "theme_emphasis",
                    "why": f"air_script {move}",
                }
            )
        if move in VO_SEAT_MOVES and sid:
            opportunities.append(
                {
                    "kind": "pause_ride",
                    "segment_id": sid,
                    "suggested_role": "theme_underscore",
                    "why": "post-VO air swell",
                }
            )
    for sid in _pause_tail_segment_ids(ctx, ordered):
        opportunities.append(
            {
                "kind": "claim_landing",
                "segment_id": sid,
                "suggested_role": "theme_emphasis",
                "why": "pause-tail after claim lands",
            }
        )
    opportunities.append(
        {
            "kind": "episode_close",
            "segment_id": last,
            "suggested_role": "theme_outro",
            "why": "required episode close motif reprise",
        }
    )
    # Dedupe by (kind, segment_id, role)
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in opportunities:
        key = (str(row.get("kind")), str(row.get("segment_id")), str(row.get("suggested_role")))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def attach_sonic_scenes(ctx: RunContext) -> dict[str, Any]:
    plan = load_plan_raw(ctx) or {}
    opps = hunt_sonic_opportunities(ctx)
    scenes: list[dict[str, Any]] = []
    for row in opps:
        if str(row.get("kind")) != "scene_bed":
            continue
        scenes.append(
            {
                "scene_id": f"bed_{row.get('segment_id')}",
                "segment_ids": list(row.get("span_segment_ids") or [row.get("segment_id")]),
                "role": row.get("suggested_role"),
                "why": row.get("why"),
            }
        )
    plan = dict(plan)
    plan["sonic_opportunities"] = opps
    plan["sonic_scenes"] = scenes
    write_plan(ctx, plan)
    return plan


def persist_air_script_omits_on_gap_report(ctx: RunContext) -> int:
    """Stamp skipped_optional on gap lines Pass B did not seat.

    Required orientation stays live; native-open omit does not. Always republishes
    ``air_script.vo_seats``. Returns how many lines were newly omitted.
    """
    try:
        from interview_mux.seat_authority import (
            seat_fingerprint,
            seat_mutation_allowed,
            soft_freeze_active,
            read_seat_freeze,
        )

        if soft_freeze_active(ctx):
            fr = read_seat_freeze(ctx)
            fp = seat_fingerprint(ctx)
            if fr.get("fingerprint") and fr["fingerprint"] == fp:
                return 0
            allowed, _why = seat_mutation_allowed(
                ctx, reason="persist_air_script_omits", require_meta_gate=True
            )
            if not allowed:
                return 0
    except Exception:
        pass
    if not air_script_enabled():
        return 0
    plan = load_plan_raw(ctx)
    if not isinstance(plan, dict) or not load_air_script(plan):
        return 0
    if not ctx.artifact_exists("understanding/gap_report.json"):
        script = dict(load_air_script(plan) or {})
        script["vo_seats"] = build_vo_seats(plan, None)
        plan = dict(plan)
        plan["air_script"] = script
        write_plan(ctx, plan)
        try:
            from interview_mux.vo_contract import clamp_hosted_seats_to_rendered_wavs

            clamp_hosted_seats_to_rendered_wavs(ctx)
        except Exception:
            pass
        return 0
    gap = ctx.read_json("understanding/gap_report.json")
    filtered = filter_gap_lines_for_air_script(gap, plan, ctx=ctx)
    if not isinstance(filtered, dict):
        return 0
    script = dict(load_air_script(plan) or {})
    script["vo_seats"] = build_vo_seats(plan, filtered)
    plan = dict(plan)
    plan["air_script"] = script
    write_plan(ctx, plan)
    before = {
        str(ln.get("line_id") or "")
        for ln in (gap.get("interviewer_lines") or [])
        if isinstance(ln, dict) and (ln.get("skipped_optional") or ln.get("air_script_omit"))
    }
    after = {
        str(ln.get("line_id") or "")
        for ln in (filtered.get("interviewer_lines") or [])
        if isinstance(ln, dict) and (ln.get("skipped_optional") or ln.get("air_script_omit"))
    }
    newly = {lid for lid in (after - before) if lid}
    revived = {lid for lid in (before - after) if lid}
    stamped = bool(newly or revived)
    orig_lines = list(gap.get("interviewer_lines") or [])
    filt_lines = list(filtered.get("interviewer_lines") or [])
    if not stamped:
        for ln, orig in zip(filt_lines, orig_lines):
            if not isinstance(ln, dict) or not isinstance(orig, dict):
                continue
            if bool(ln.get("air_script_omit")) != bool(orig.get("air_script_omit")):
                stamped = True
                break
            if bool(ln.get("skipped_optional")) != bool(orig.get("skipped_optional")):
                stamped = True
                break
    if stamped:
        dest = ctx.write_json("understanding/gap_report.json", filtered)
        try:
            import shutil

            pending_root = ctx.run_dir / ".pending_writes"
            if pending_root.is_dir():
                for stage_dir in pending_root.iterdir():
                    if not stage_dir.is_dir():
                        continue
                    candidate = stage_dir.joinpath("understanding", "gap_report.json")
                    if candidate.is_file():
                        shutil.copy2(dest, candidate)
        except Exception:
            pass
        try:
            from interview_mux.gap_framing import (
                build_gap_framing_plan,
                persist_gap_framing_companion_artifacts,
            )

            lines = [ln for ln in filt_lines if isinstance(ln, dict)]
            persist_gap_framing_companion_artifacts(ctx, {"interviewer_lines": lines})
            live = [ln for ln in lines if not ln.get("skipped_optional")]
            framing = build_gap_framing_plan(ctx, live)
            ctx.write_json("understanding/gap_framing_plan.json", framing)
        except Exception:
            pass
    # Terminal clamp after every omit/seat mutation path (including no-op stamp).
    try:
        from interview_mux.vo_contract import clamp_hosted_seats_to_rendered_wavs

        clamp_hosted_seats_to_rendered_wavs(ctx)
    except Exception:
        pass
    return len(newly) + len(revived) if stamped else 0


def gap_line_air_eligible(row: dict[str, Any] | None) -> bool:
    """True when a gap VO line may be seated on air (not skipped/omitted)."""
    if not isinstance(row, dict):
        return False
    if row.get("skipped_optional"):
        return False
    if row.get("air_script_omit"):
        return False
    if row.get("omit"):
        return False
    return True


def filter_gap_lines_for_air_script(
    gap_report: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    *,
    ctx: Any | None = None,
) -> dict[str, Any] | None:
    """Strip unused VO so EDL cannot leak approved-but-omitted lines.

    Required orientation airs; native-open omit skips it. Fail-open when air_script is missing.
    Hosted framing floor: never omit enough synthesize layups to fall below
    ``min_synthetic_vo_lines`` when G-Framing Yes requires cloned host VO.
    """
    if not isinstance(gap_report, dict):
        return gap_report
    if not air_script_enabled() or not load_air_script(plan):
        return gap_report
    seats = set(requested_vo_line_ids(plan) | seated_vo_line_ids(plan))
    # Reserve high-severity synthesize layups so Pass B omit cannot wipe the floor.
    try:
        from interview_mux.gap_fill_eligibility import (
            hosted_framing_requires_synthetic_vo,
            min_synthetic_vo_lines,
        )

        if ctx is not None and hosted_framing_requires_synthetic_vo(ctx):
            need = min_synthetic_vo_lines(ctx)
            candidates: list[tuple[int, str]] = []
            for line in gap_report.get("interviewer_lines") or []:
                if not isinstance(line, dict):
                    continue
                if _is_orientation_line(line):
                    continue
                if str(line.get("delivery") or "").lower() != "synthesize":
                    continue
                lid = str(line.get("line_id") or "").strip()
                if not lid or not str(line.get("text") or "").strip():
                    continue
                sev = str(line.get("severity") or "medium").lower()
                rank = 0 if sev in {"high", "critical", "blocking"} else 1
                candidates.append((rank, lid))
            candidates.sort()
            seated_syn = {
                lid
                for lid in seats
                if any(
                    isinstance(ln, dict)
                    and str(ln.get("line_id") or "") == lid
                    and str(ln.get("delivery") or "").lower() == "synthesize"
                    and not _is_orientation_line(ln)
                    for ln in (gap_report.get("interviewer_lines") or [])
                )
            }
            for _rank, lid in candidates:
                if len(seated_syn) >= need:
                    break
                if lid in seated_syn:
                    continue
                seats.add(lid)
                seated_syn.add(lid)
    except Exception:
        pass
    try:
        from interview_mux.opening_orientation import orientation_omitted

        skip_orientation = orientation_omitted(gap_report)
    except Exception:
        skip_orientation = False
    lines = []
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        # Durable omit only when opening_orientation meta says so. Stale
        # air_script_omit / skipped_optional on a *required* orientation must not
        # win — ORIENTATION_ALWAYS revives (forensics: count=0 expected=1).
        if _is_orientation_line(line) and skip_orientation:
            skipped = dict(line)
            skipped["skipped_optional"] = True
            skipped["air_script_omit"] = True
            lines.append(skipped)
            continue
        if _is_orientation_line(line) and ORIENTATION_ALWAYS:
            kept = dict(line)
            kept["skipped_optional"] = False
            kept.pop("air_script_omit", None)
            kept.pop("skip_reason_code", None)
            lines.append(kept)
            continue
        lid = str(line.get("line_id") or "")
        if lid and lid in seats:
            # Floor-reserved seats must stay on-air even if a prior pass stamped omit.
            if line.get("skipped_optional") or line.get("air_script_omit"):
                from interview_mux.vo_contract import ensure_gap_line_on_air

                lines.append(ensure_gap_line_on_air(line))
            else:
                lines.append(line)
            continue
        skipped = dict(line)
        skipped["skipped_optional"] = True
        skipped["air_script_omit"] = True
        lines.append(skipped)
    out = dict(gap_report)
    out["interviewer_lines"] = lines
    return out


def unused_required_opportunities(
    plan: dict[str, Any] | None,
    cues: list[dict[str, Any]] | None,
) -> list[str]:
    """Required hunt kinds that compose failed to place (open / beds / outro)."""
    if not isinstance(plan, dict):
        return []
    opps = [o for o in (plan.get("sonic_opportunities") or []) if isinstance(o, dict)]
    if not opps:
        return []
    placed_roles = {
        str(c.get("role") or "")
        for c in (cues or [])
        if isinstance(c, dict)
    }
    placed_under = {
        str(c.get("under_segment_id") or c.get("segment_id") or "")
        for c in (cues or [])
        if isinstance(c, dict) and str(c.get("placement") or "") in {"under_segment", "under_segment_span"}
    }
    unused: list[str] = []
    for row in opps:
        kind = str(row.get("kind") or "")
        sid = str(row.get("segment_id") or "")
        if kind == "open_motif" and not (
            placed_roles & {"theme_cold_open", "motif"}
            or any(
                str(c.get("before_segment_id")) == sid
                for c in (cues or [])
                if isinstance(c, dict)
            )
        ):
            unused.append(kind)
        elif kind == "scene_bed" and sid and sid not in placed_under:
            unused.append(f"scene_bed:{sid}")
        elif kind == "episode_close" and "theme_outro" not in placed_roles:
            unused.append(kind)
    return unused


def filter_transitions_for_air_script(
    transitions: dict[str, Any] | None,
    plan: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(transitions, dict):
        return transitions
    if not air_script_enabled() or not load_air_script(plan):
        return transitions
    kept = []
    for item in transitions.get("transitions") or []:
        if not isinstance(item, dict):
            continue
        before_id = str(item.get("before_segment_id") or "")
        after_id = str(item.get("after_segment_id") or "")
        if transition_allowed_for_pair(plan, after_id, before_id):
            kept.append(item)
    out = dict(transitions)
    out["transitions"] = kept
    return out


def transition_allowed_for_pair(plan: dict[str, Any] | None, after_id: str, before_id: str) -> bool:
    """Spoken transitions only when the destination beat is not a native_handoff/air_breathe.

    music_face_out / vo seats / information_package may still take glue if present.
    """
    if not air_script_enabled() or not load_air_script(plan):
        return True
    move = beat_move_for_segment(plan, before_id)
    if move in {"native_handoff", "air_breathe", "episode_close"}:
        return False
    return True


def cues_from_sonic_plan(
    plan: dict[str, Any] | None,
    *,
    assets_by_kind: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Turn sonic_opportunities into palette cues (reuse existing stems only)."""
    if not isinstance(plan, dict):
        return []
    opps = [o for o in (plan.get("sonic_opportunities") or []) if isinstance(o, dict)]
    if not opps:
        return []

    def _pick(kind: str, *roles: str) -> dict[str, Any] | None:
        for k in (kind, *roles):
            rows = assets_by_kind.get(k) or []
            if rows:
                return rows[0]
        return None

    cues: list[dict[str, Any]] = []
    for i, row in enumerate(opps):
        kind = str(row.get("kind") or "")
        sid = str(row.get("segment_id") or "")
        if not sid:
            continue
        asset = None
        placement = "after_segment"
        role = str(row.get("suggested_role") or "theme_emphasis")
        level = -14
        extra: dict[str, Any] = {}
        if kind == "open_motif":
            asset = _pick("full_bed", "motif", "theme_cold_open")
            placement = "before_segment"
            role = str((asset or {}).get("role") or "theme_cold_open")
            level = -10
        elif kind == "scene_bed":
            want = "optional_loop" if role in {"optional_loop"} else "underscore_loop"
            asset = _pick(want, "underscore_loop", "theme_underscore")
            placement = "under_segment"
            role = str((asset or {}).get("role") or "theme_underscore")
            level = -26
            extra["crossfade_ms"] = 1800
            span = [str(s) for s in (row.get("span_segment_ids") or [sid]) if s]
            for j, span_sid in enumerate(span):
                if not asset:
                    break
                cue = {
                    "cue_id": f"air_bed_{i+1:02d}_{j+1:02d}",
                    "asset_id": str(asset["asset_id"]),
                    "role": role,
                    "placement": "under_segment",
                    "under_segment_id": span_sid,
                    "segment_id": span_sid,
                    "level_db": level,
                    "crossfade_ms": 1800,
                }
                cues.append(cue)
            continue
        elif kind in {"scene_resolve", "package_faceout"}:
            asset = _pick("stinger", "theme_chapter_resolve", "theme_emphasis")
            placement = "after_segment"
            role = str((asset or {}).get("role") or "theme_chapter_resolve")
            level = -12
        elif kind in {"hinge_stinger", "pause_ride", "claim_landing"}:
            if kind == "pause_ride":
                continue  # beds already cover; mix pause-ride handles swell
            asset = _pick("stinger", "theme_emphasis")
            placement = "after_segment"
            role = str((asset or {}).get("role") or "theme_emphasis")
            level = -14
        elif kind == "episode_close":
            asset = _pick("full_bed", "theme_outro", "motif")
            placement = "after_segment"
            role = "theme_outro"
            level = -10
        if not asset:
            continue
        cue = {
            "cue_id": f"air_{kind}_{i+1:02d}",
            "asset_id": str(asset["asset_id"]),
            "role": role,
            "placement": placement,
            "level_db": level,
            **extra,
        }
        if placement == "before_segment":
            cue["before_segment_id"] = sid
        elif placement == "after_segment":
            cue["after_segment_id"] = sid
        else:
            cue["under_segment_id"] = sid
            cue["segment_id"] = sid
        cues.append(cue)
    return cues


def paper_edit_scores(ctx: RunContext) -> dict[str, Any]:
    plan = load_plan_raw(ctx) or {}
    script = load_air_script(plan) or {}
    lint = script.get("story_clarity") if isinstance(script.get("story_clarity"), dict) else None
    if lint is None:
        beats = [b for b in (script.get("beats") or []) if isinstance(b, dict)]
        lint = lint_story_clarity(
            beats=beats,
            ordered=ordered_ids_from_air_script(plan),
            spine=plan.get("story_spine") if isinstance(plan.get("story_spine"), dict) else None,
            cold_open=script.get("cold_open") if isinstance(script.get("cold_open"), dict) else None,
        )
    follow = float(lint.get("story_followability") or 0.85)
    vo_wall = "vo_wall" in (lint.get("warnings") or [])
    conversation = 0.55 if vo_wall else (0.92 if lint.get("ok") else 0.7)
    opps = plan.get("sonic_opportunities") if isinstance(plan.get("sonic_opportunities"), list) else []
    kinds = {str(o.get("kind")) for o in opps if isinstance(o, dict)}
    sonic = 0.85
    if opps:
        sonic = 0.7
        if "open_motif" in kinds:
            sonic += 0.08
        if "scene_bed" in kinds:
            sonic += 0.1
        if "episode_close" in kinds:
            sonic += 0.08
        if "hinge_stinger" in kinds or "scene_resolve" in kinds:
            sonic += 0.04
    return {
        "story_followability": round(max(0.0, min(1.0, follow)), 4),
        "conversation_fit": round(max(0.0, min(1.0, conversation)), 4),
        "sonic_weave": round(max(0.0, min(1.0, sonic)), 4),
        "story_clarity": lint,
        "pass": bool(lint.get("ok")) and follow >= 0.75,
    }


def run_air_script_compose(ctx: RunContext) -> None:
    """Pass A after ranking. Heal-gate: refuse done unless a Pass A script exists."""
    if not air_script_enabled():
        # ASC-B2 / CSP-01: skip latch + heal so seed does not stall pending.
        persist_air_script_disabled_skip(
            ctx, stage="air_script_compose", pass_name="pass_a"
        )
        try:
            from interview_mux.stage_completion import heal_or_refuse_mark

            heal_or_refuse_mark(ctx, "air_script_compose", force=True)
        except Exception:
            pass
        return
    try:
        compose_pass_a(ctx)
    except Exception as exc:
        if "selection_commit_refused" in str(exc):
            raise
        if not air_script_cfg().get("fail_open", True):
            raise
        ctx.log(f"air_script_compose fail-open: {exc}", level="warning", stage="air_script_compose")
    try:
        from interview_mux.stage_completion import heal_or_refuse_mark

        heal_or_refuse_mark(ctx, "air_script_compose")
    except Exception:
        pass


SEAMS_CONTRACT_DRIFT_REL = "operator/air_script_seams_contract_drift.json"


def _snapshot_mastering_plan(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("mastering/mastering_plan.json"):
        return None
    try:
        raw = ctx.read_json("mastering/mastering_plan.json")
    except Exception:
        return None
    return dict(raw) if isinstance(raw, dict) else None


def _restore_mastering_plan(ctx: RunContext, prior: dict[str, Any] | None) -> None:
    if not isinstance(prior, dict):
        return
    write_plan(ctx, dict(prior))


def _stamp_seams_contract_drift(ctx: RunContext, remaining: list[str]) -> None:
    ctx.write_json(
        SEAMS_CONTRACT_DRIFT_REL,
        {
            "version": 1,
            "active": True,
            "remaining": [str(x) for x in remaining[:8] if x],
        },
        skip_handoff=True,
    )


def _clear_seams_contract_drift(ctx: RunContext) -> None:
    if not ctx.artifact_exists(SEAMS_CONTRACT_DRIFT_REL):
        return
    try:
        doc = ctx.read_json(SEAMS_CONTRACT_DRIFT_REL)
        if isinstance(doc, dict):
            doc = dict(doc)
            doc["active"] = False
            ctx.write_json(SEAMS_CONTRACT_DRIFT_REL, doc, skip_handoff=True)
    except Exception:
        pass


def run_air_script_seams(ctx: RunContext) -> None:
    """Pass B + sonic opportunity hunt after layup freeze."""
    if not air_script_enabled():
        # ASS-B2 / CSP-01: skip latch + heal so seed does not stall pending.
        persist_air_script_disabled_skip(
            ctx, stage="air_script_seams", pass_name="pass_b"
        )
        try:
            from interview_mux.stage_completion import heal_or_refuse_mark

            heal_or_refuse_mark(ctx, "air_script_seams", force=True)
        except Exception:
            pass
        return
    prior_plan = _snapshot_mastering_plan(ctx)
    try:
        compose_pass_b(ctx)
        persist_air_script_omits_on_gap_report(ctx)
        attach_sonic_scenes(ctx)
        from interview_mux.vo_contract import sync_vo_contract_after_layup

        remaining = sync_vo_contract_after_layup(ctx)
        if remaining:
            raise RuntimeError(f"VO contract drift after air_script_seams: {remaining[0]}")
    except Exception as exc:
        msg = str(exc)
        is_drift = "VO contract drift after air_script_seams" in msg
        if is_drift:
            from interview_mux.vo_contract import seams_contract_remaining

            leftover = seams_contract_remaining(ctx)
            _restore_mastering_plan(ctx, prior_plan)
            _stamp_seams_contract_drift(ctx, leftover or [msg])
            raise
        # HF-2 leftover: non-drift compose crashes must not swallow. Drift already
        # re-raised above; everything else is fail-closed (stamp refuse sidecar).
        _stamp_seams_contract_drift(ctx, [msg])
        raise
    _clear_seams_contract_drift(ctx)
    try:
        from interview_mux.stage_completion import heal_or_refuse_mark

        heal_or_refuse_mark(ctx, "air_script_seams")
    except Exception:
        pass
