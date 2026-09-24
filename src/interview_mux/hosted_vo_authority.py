"""Hosted VO / orientation constitution — single SSOT (Cluster C).

Why hosted VO count goes low (census):
  never_minted | stripped_last_seat | soft_omit_wipe | cta_anchor_lost
  | freeze_pool_empty | counter_skew | edl_survivor_wipe | books_disagree

Disposition priority (first match wins):
  HEARD_KEEP → HOLLOW_MINT → OPERATOR_OMIT → NATIVE_OMIT → KEEP_REQUIRED

Floor: HOLLOW_ZERO (have<1) is playability; PARTIAL may aspirational-continue;
MET/UNWARRANTED/WAIVED are non-blocking for count floors.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.run_context import RunContext

ORIENTATION_LINE_ID = "vo_preface_episode_orientation"
FLOOR_IDENTITY_META_KEY = "hosted_vo_floor_identity"
LAYUP_FLOOR_ESCALATION_REL = "operator/escalations/nugget_layup_compose.json"
LAYUP_PLAN_REL = "understanding/nugget_layup_plan.json"

# After orientation preface on EDL, these before-line classes must still seat
# (i9 + idx==0 open fix). Assembly consults this constant.
EDL_SURVIVORS_AFTER_ORIENTATION: frozenset[str] = frozenset(
    {"nugget_layup", "required", "orientation"}
)

FloorStatus = Literal["UNWARRANTED", "WAIVED", "MET", "PARTIAL", "HOLLOW_ZERO"]
OrientationDisposition = Literal[
    "HEARD_KEEP", "HOLLOW_MINT", "OPERATOR_OMIT", "NATIVE_OMIT", "KEEP_REQUIRED"
]
FloorCause = Literal[
    "never_minted",
    "stripped_last_seat",
    "soft_omit_wipe",
    "cta_anchor_lost",
    "freeze_pool_empty",
    "counter_skew",
    "edl_survivor_wipe",
    "books_disagree",
]


@dataclass(frozen=True)
class FloorIdentity:
    status: FloorStatus
    need: int
    have: int
    have_gap: int
    have_edl: int
    cause: str | None
    resume_producer: str
    prose: str


@dataclass(frozen=True)
class OrientationDecision:
    disposition: OrientationDisposition
    line_id: str
    omit_reason: str | None
    force_remint: bool


@dataclass(frozen=True)
class HostedFloorSnapshot:
    identity: FloorIdentity
    warranted: bool
    need: int
    have_gap: int
    have_edl: int
    have: int
    aspirational_ok: bool
    escalation_should_block: bool
    resume_producer: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gap_vo_count_stages() -> frozenset[str]:
    try:
        from interview_mux.gap_fill_eligibility import _EDL_VO_COUNT_STAGES, _GAP_VO_COUNT_STAGES

        return frozenset(_GAP_VO_COUNT_STAGES) | frozenset(_EDL_VO_COUNT_STAGES)
    except Exception:
        return frozenset(
            {
                "nugget_layup_compose",
                "g1_vo_pickup",
                "vo_synthesize",
                "edl",
                "mix",
                "master_finalize",
            }
        )


def need(ctx: RunContext) -> int:
    from interview_mux.gap_fill_eligibility import min_synthetic_vo_lines

    return int(min_synthetic_vo_lines(ctx))


def have_gap(ctx: RunContext) -> int:
    from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines

    return int(count_active_gap_vo_lines(ctx))


def have_edl(ctx: RunContext) -> int:
    from interview_mux.gap_fill_eligibility import count_edl_vo_pickup

    return int(count_edl_vo_pickup(ctx))


def have(ctx: RunContext, *, stage_id: str | None = None) -> int:
    """Canonical hosted VO count for the stage era."""
    g = have_gap(ctx)
    sid = str(stage_id or "").strip()
    try:
        from interview_mux.gap_fill_eligibility import _EDL_VO_COUNT_STAGES

        if sid and sid in _EDL_VO_COUNT_STAGES:
            return max(g, have_edl(ctx))
    except Exception:
        pass
    if sid in {"", "nugget_layup_compose", "gap_framing_compose"}:
        return g
    # Unknown delivery-ish stages: prefer max so we do not under-count.
    if sid and sid not in {"gap_framing_compose", "missing_framing"}:
        return max(g, have_edl(ctx))
    return g


def floor_identity_to_dict(identity: FloorIdentity) -> dict[str, Any]:
    return {
        "status": identity.status,
        "need": identity.need,
        "have": identity.have,
        "have_gap": identity.have_gap,
        "have_edl": identity.have_edl,
        "cause": identity.cause,
        "resume_producer": identity.resume_producer,
        "prose": identity.prose,
    }


_HOSTED_FLOOR_SEED_PIN_PRODUCERS = frozenset(
    {"nugget_layup_compose", "gap_framing_compose", "gap_framing_recompose"}
)


def seed_walk_pin_for_hollow_hosted_vo(ctx: RunContext, stage: str) -> str:
    """When floor is HOLLOW_ZERO, pin seed walk to compose/layup — not EDL consumers."""
    sid = str(stage or "").strip()
    if not sid or sid in _HOSTED_FLOOR_SEED_PIN_PRODUCERS:
        return sid
    try:
        from interview_mux.v2.config import DELIVERY_ORDER

        anchor = "vo_line_adjudicate"
        if anchor not in DELIVERY_ORDER or sid not in DELIVERY_ORDER:
            return sid
        if DELIVERY_ORDER.index(sid) < DELIVERY_ORDER.index(anchor):
            return sid
    except Exception:
        return sid
    try:
        ident = identify_hosted_vo_floor(ctx, persist=False)
    except Exception:
        return sid
    if ident.status != "HOLLOW_ZERO":
        return sid
    pin = str(ident.resume_producer or resume_producer(ctx) or "").strip()
    return pin or sid


def resume_producer(ctx: RunContext, *, stage_id: str | None = None) -> str:
    sid = str(stage_id or "").strip()
    if sid in {"nugget_layup_compose", "gap_framing_compose"}:
        return sid
    try:
        from interview_mux.stage_completion import high_gap_heal_resume_stage

        return str(high_gap_heal_resume_stage(ctx) or "gap_framing_compose")
    except Exception:
        try:
            from interview_mux.nugget_layup import PLAN_REL

            if ctx.artifact_exists(PLAN_REL):
                return "nugget_layup_compose"
        except Exception:
            pass
        return "gap_framing_compose"


def _floor_waived(ctx: RunContext) -> bool:
    try:
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict) and meta.get("hosted_framing_floor_waived"):
                return True
        from interview_mux.gates import g1_vo_was_skipped_optional

        if g1_vo_was_skipped_optional(ctx):
            return True
    except Exception:
        pass
    return False


def _floor_warranted(ctx: RunContext) -> bool:
    try:
        from interview_mux.gap_fill_eligibility import hosted_framing_requires_synthetic_vo

        return bool(hosted_framing_requires_synthetic_vo(ctx))
    except Exception:
        return False


def _infer_cause(
    ctx: RunContext,
    *,
    status: FloorStatus,
    have_g: int,
    have_e: int,
    need_n: int,
) -> str | None:
    if status not in {"HOLLOW_ZERO", "PARTIAL"}:
        return None
    try:
        from interview_mux.opening_orientation import orientation_omitted

        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
        if isinstance(gap, dict) and orientation_omitted(gap) and have_g < 1:
            if orientation_heard_on_disk(ctx) or orientation_seated_in_edl(ctx):
                return "books_disagree"
            return "stripped_last_seat"
        lines = list(gap.get("interviewer_lines") or []) if isinstance(gap, dict) else []
        soft = 0
        contentful = 0
        for ln in lines:
            if not isinstance(ln, dict) or not str(ln.get("text") or "").strip():
                continue
            contentful += 1
            if ln.get("skipped_optional") or ln.get("air_script_omit"):
                soft += 1
        if contentful > 0 and have_g < 1 and soft >= contentful:
            return "soft_omit_wipe"
        if have_g < 1 and contentful < 1:
            return "never_minted"
        if have_g >= need_n and have_e < need_n:
            return "edl_survivor_wipe"
        if have_g != have_e and abs(have_g - have_e) >= 1 and status == "PARTIAL":
            return "counter_skew"
    except Exception:
        pass
    try:
        from interview_mux.seat_authority import hard_freeze_active

        if hard_freeze_active(ctx) and have_g < need_n:
            return "freeze_pool_empty"
    except Exception:
        pass
    if have_g < 1:
        return "never_minted"
    return None


def identify_hosted_vo_floor(
    ctx: RunContext,
    *,
    stage_id: str | None = None,
    persist: bool = True,
) -> FloorIdentity:
    """First-class low-count identity — all incompleteness/heal must read this."""
    waived = _floor_waived(ctx)
    warranted_raw = _floor_warranted(ctx) if not waived else False
    # When waived, hosted_framing_requires is False — still mark WAIVED.
    if not waived and not warranted_raw:
        # Distinguish UNWARRANTED vs WAIVED already handled; check sticky waive again.
        try:
            from interview_mux.gap_vo_gates import gap_framing_enabled
            from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

            if gap_framing_enabled(ctx) and not gap_fill_was_skipped(ctx) and _floor_waived(ctx):
                waived = True
        except Exception:
            pass

    need_n = need(ctx) if (warranted_raw or waived) else 0
    have_g = have_gap(ctx)
    have_e = have_edl(ctx)
    have_n = have(ctx, stage_id=stage_id)
    producer = resume_producer(ctx, stage_id=stage_id)

    if waived:
        identity = FloorIdentity(
            status="WAIVED",
            need=need_n or need(ctx),
            have=have_n,
            have_gap=have_g,
            have_edl=have_e,
            cause=None,
            resume_producer="",
            prose="hosted_vo_floor waived (G1/skip)",
        )
    elif not warranted_raw:
        identity = FloorIdentity(
            status="UNWARRANTED",
            need=0,
            have=have_n,
            have_gap=have_g,
            have_edl=have_e,
            cause=None,
            resume_producer="",
            prose="hosted_vo_floor unwarranted",
        )
    elif have_n >= need_n:
        identity = FloorIdentity(
            status="MET",
            need=need_n,
            have=have_n,
            have_gap=have_g,
            have_edl=have_e,
            cause=None,
            resume_producer="",
            prose=f"hosted_vo_floor met have={have_n} need={need_n}",
        )
    elif have_n < 1:
        cause = _infer_cause(
            ctx, status="HOLLOW_ZERO", have_g=have_g, have_e=have_e, need_n=need_n
        )
        identity = FloorIdentity(
            status="HOLLOW_ZERO",
            need=need_n,
            have=have_n,
            have_gap=have_g,
            have_edl=have_e,
            cause=cause,
            resume_producer=producer,
            prose=(
                f"hosted_vo_floor HOLLOW_ZERO have={have_n} need={need_n}"
                f"{f' cause={cause}' if cause else ''} — "
                f"gap_report has {have_n} — resume {producer}"
            ),
        )
    else:
        cause = _infer_cause(
            ctx, status="PARTIAL", have_g=have_g, have_e=have_e, need_n=need_n
        )
        identity = FloorIdentity(
            status="PARTIAL",
            need=need_n,
            have=have_n,
            have_gap=have_g,
            have_edl=have_e,
            cause=cause,
            resume_producer=producer,
            prose=(
                f"hosted_vo_floor PARTIAL have={have_n} need={need_n}"
                f"{f' cause={cause}' if cause else ''}"
            ),
        )

    if persist:
        _persist_identity(ctx, identity)
    return identity


def _persist_identity(ctx: RunContext, identity: FloorIdentity) -> None:
    try:

        def patch(meta: dict[str, Any]) -> None:
            meta[FLOOR_IDENTITY_META_KEY] = {
                "status": identity.status,
                "need": identity.need,
                "have": identity.have,
                "have_gap": identity.have_gap,
                "have_edl": identity.have_edl,
                "cause": identity.cause,
                "resume_producer": identity.resume_producer,
                "prose": identity.prose,
                "at": _now(),
            }

        ctx.mutate_run_meta(patch)
    except Exception:
        pass


def floor_snapshot(
    ctx: RunContext,
    *,
    stage_id: str | None = None,
    persist: bool = True,
) -> HostedFloorSnapshot:
    identity = identify_hosted_vo_floor(ctx, stage_id=stage_id, persist=persist)
    warranted = identity.status not in {"UNWARRANTED", "WAIVED"}
    aspirational_ok = identity.status == "PARTIAL"
    # HOLLOW_ZERO always blocks; PARTIAL blocks only when progress floors off.
    escalation_should_block = False
    if identity.status == "HOLLOW_ZERO":
        escalation_should_block = True
    elif identity.status == "PARTIAL":
        try:
            from interview_mux.floor_progress import hosted_vo_aspirational

            escalation_should_block = not hosted_vo_aspirational(ctx)
        except Exception:
            escalation_should_block = True
    snap = HostedFloorSnapshot(
        identity=identity,
        warranted=warranted,
        need=identity.need,
        have_gap=identity.have_gap,
        have_edl=identity.have_edl,
        have=identity.have,
        aspirational_ok=aspirational_ok,
        escalation_should_block=escalation_should_block,
        resume_producer=identity.resume_producer,
    )
    if persist and identity.status in {"MET", "PARTIAL", "WAIVED"}:
        try:
            reconcile_escalations(ctx, snap)
        except Exception:
            pass
    return snap


def may_aspirational_proceed(ctx: RunContext, *, stage_id: str | None = None) -> bool:
    """True only for PARTIAL floors — never HOLLOW_ZERO."""
    snap = floor_snapshot(ctx, stage_id=stage_id, persist=True)
    return bool(snap.aspirational_ok)


def reconcile_escalations(ctx: RunContext, snap: HostedFloorSnapshot | None = None) -> None:
    """Triple-clear escalation JSON + run_meta + plan _meta when floor recovered.

    When status is MET (honest have≥need), also clear stale aspirational stamps and
    hollow ``floor_advisories`` left from an earlier HOLLOW_ZERO episode so heal /
    driver cannot keep seeing a hollow past.
    """
    snap = snap or floor_snapshot(ctx, persist=False)
    clear = snap.identity.status in {"MET", "PARTIAL", "WAIVED", "UNWARRANTED"} or (
        snap.have >= 1
    )
    if not clear:
        return
    floor_met = snap.identity.status == "MET" or (
        snap.need > 0 and snap.have >= snap.need
    )
    # Operator escalation file
    try:
        if ctx.artifact_exists(LAYUP_FLOOR_ESCALATION_REL):
            doc = ctx.read_json(LAYUP_FLOOR_ESCALATION_REL)
            if isinstance(doc, dict):
                status = str(doc.get("status") or "").lower()
                reason = str(doc.get("reason") or "").lower()
                if status in {"open", "blocking", "needs_operator"} and (
                    "hosted_vo_floor" in reason or "unsatisfiable" in reason
                ):
                    doc = dict(doc)
                    doc["status"] = "cleared"
                    doc["cleared_reason"] = (
                        f"identity={snap.identity.status}:have={snap.have}"
                    )
                    doc["cleared_at"] = _now()
                    ctx.write_json(LAYUP_FLOOR_ESCALATION_REL, doc, skip_handoff=True)
    except Exception:
        pass
    # run_meta
    try:

        def patch(meta: dict[str, Any]) -> None:
            meta.pop("hosted_vo_floor_unsatisfiable", None)
            meta.pop("hosted_vo_floor_unsatisfiable_prose", None)
            meta.pop("hosted_vo_floor_unsatisfiable_detail", None)
            meta.pop("hosted_vo_floor_unmet", None)
            meta.pop("hosted_vo_floor_unmet_prose", None)
            meta.pop("hosted_vo_floor_wait", None)
            if meta.get("needs_operator_reason") in {
                "hosted_vo_floor_unmet",
                "hosted_vo_floor_unsatisfiable",
            }:
                meta.pop("needs_operator", None)
                meta.pop("needs_operator_reason", None)
            if floor_met:
                # Stale hollow-era aspirational stamps (exec_13183 residual).
                meta.pop("floor_aspirational_proceeded", None)
                meta.pop("aspirational_proceeded", None)
                adv = meta.get("floor_advisories")
                if isinstance(adv, list):
                    kept: list[Any] = []
                    for row in adv:
                        if not isinstance(row, dict):
                            kept.append(row)
                            continue
                        if str(row.get("gate_id") or "") != "hosted_vo_floor":
                            kept.append(row)
                            continue
                        detail = row.get("detail")
                        have_adv = None
                        if isinstance(detail, dict) and "have" in detail:
                            try:
                                have_adv = int(detail.get("have"))
                            except Exception:
                                have_adv = None
                        # Drop hollow / shortfall advisories once floor is MET.
                        if have_adv is not None and have_adv < snap.need:
                            continue
                        kept.append(row)
                    meta["floor_advisories"] = kept

        ctx.mutate_run_meta(patch)
    except Exception:
        pass
    # plan _meta
    try:
        if ctx.artifact_exists(LAYUP_PLAN_REL):
            plan = ctx.read_json(LAYUP_PLAN_REL)
            if isinstance(plan, dict):
                meta = plan.get("_meta")
                if isinstance(meta, dict) and (
                    meta.get("hosted_vo_floor_unsatisfiable")
                    or meta.get("hosted_vo_floor_unmet")
                    or (floor_met and meta.get("floor_aspirational_proceeded"))
                ):
                    plan = dict(plan)
                    m2 = dict(meta)
                    m2.pop("hosted_vo_floor_unsatisfiable", None)
                    m2.pop("hosted_vo_floor_unsatisfiable_detail", None)
                    m2.pop("hosted_vo_floor_unmet", None)
                    if floor_met:
                        m2.pop("floor_aspirational_proceeded", None)
                    plan["_meta"] = m2
                    ctx.write_json(LAYUP_PLAN_REL, plan, skip_handoff=True)
    except Exception:
        pass


def orientation_wav_path(ctx: RunContext):
    wav = ctx.final_path("vo_pickup", "synthesized", f"{ORIENTATION_LINE_ID}.wav")
    if not (wav.is_file() and wav.stat().st_size > 1000):
        wav = ctx.final_path("vo_pickup", f"{ORIENTATION_LINE_ID}.wav")
    return wav


def orientation_heard_on_disk(ctx: RunContext) -> bool:
    try:
        wav = orientation_wav_path(ctx)
        return bool(wav.is_file() and wav.stat().st_size > 1000)
    except Exception:
        return False


def orientation_seated_in_edl(ctx: RunContext) -> bool:
    try:
        if not ctx.artifact_exists("master/edl.json"):
            return False
        edl = ctx.read_json("master/edl.json")
        for clip in (edl or {}).get("clips") or []:
            if (
                isinstance(clip, dict)
                and str(clip.get("type") or "") == "vo_pickup"
                and str(clip.get("line_id") or "") == ORIENTATION_LINE_ID
            ):
                return True
    except Exception:
        pass
    return False


def _active_synth_in_gap(gap: dict[str, Any]) -> tuple[int, int]:
    """Return (active_doc, active_non_orient)."""
    from interview_mux.opening_orientation import is_episode_orientation

    active_doc = 0
    active_non_orient = 0
    for ln in gap.get("interviewer_lines") or []:
        if (
            not isinstance(ln, dict)
            or not str(ln.get("text") or "").strip()
            or ln.get("skipped_optional")
            or ln.get("air_script_omit")
        ):
            continue
        raw = ln.get("delivery")
        delivery = "synthesize" if raw is None else str(raw).strip().lower() or ""
        if delivery not in {"synthesize", "chatterbox", "voice_clone", "record", ""}:
            continue
        active_doc += 1
        if not is_episode_orientation(ln):
            active_non_orient += 1
    return active_doc, active_non_orient


def decide_orientation(
    ctx: RunContext,
    gap_report: dict[str, Any],
    ordered_segment_ids: list[str],
    *,
    orientation_nugget_ids: list[str] | None = None,
) -> OrientationDecision:
    """Disposition priority — first match wins."""
    from interview_mux.opening_orientation import (
        ORIENTATION_LINE_ID as _OID,
        native_open_already_orients,
        orientation_omitted,
    )

    line_id = _OID
    nugget_ids = [str(x) for x in (orientation_nugget_ids or []) if x]
    if not nugget_ids and isinstance(gap_report.get("orientation_nugget_recovery"), dict):
        nugget_ids = [
            str(x)
            for x in (gap_report["orientation_nugget_recovery"].get("nugget_ids") or [])
            if x
        ]

    # 1. HEARD_KEEP — remint only when gap book still omits / lacks the live line.
    if orientation_heard_on_disk(ctx) or orientation_seated_in_edl(ctx):
        force_remint = True
        try:
            from interview_mux.opening_orientation import is_episode_orientation

            orient_meta = gap_report.get("opening_orientation")
            meta_ok = (
                isinstance(orient_meta, dict)
                and orient_meta.get("omitted") is not True
                and orient_meta.get("required") is True
            )
            line_live = False
            for ln in gap_report.get("interviewer_lines") or []:
                if not isinstance(ln, dict):
                    continue
                if str(ln.get("line_id") or "") != line_id and not is_episode_orientation(
                    ln
                ):
                    continue
                if (
                    str(ln.get("text") or "").strip()
                    and not ln.get("skipped_optional")
                    and not ln.get("air_script_omit")
                ):
                    line_live = True
                    break
            if meta_ok and line_live and not orientation_omitted(gap_report):
                force_remint = False
        except Exception:
            force_remint = True
        return OrientationDecision(
            disposition="HEARD_KEEP",
            line_id=line_id,
            omit_reason=None,
            force_remint=force_remint,
        )

    # 2. HOLLOW_MINT
    hollow = False
    try:
        if _floor_warranted(ctx):
            active_doc, active_non_orient = _active_synth_in_gap(gap_report)
            if active_doc < 1 or active_non_orient < 1:
                hollow = True
    except Exception:
        hollow = False
    if hollow or bool(nugget_ids):
        return OrientationDecision(
            disposition="HOLLOW_MINT" if hollow else "KEEP_REQUIRED",
            line_id=line_id,
            omit_reason=None,
            force_remint=True,
        )

    # 3. OPERATOR_OMIT (durable meta, no heard, not hollow)
    if orientation_omitted(gap_report):
        return OrientationDecision(
            disposition="OPERATOR_OMIT",
            line_id=line_id,
            omit_reason=str(
                ((gap_report.get("opening_orientation") or {}) or {}).get("omit_reason")
                or "operator"
            ),
            force_remint=False,
        )

    # 4. NATIVE_OMIT
    ordered = [str(x) for x in ordered_segment_ids if x]
    first = ordered[0] if ordered else ""
    if first and native_open_already_orients(ctx, ordered, target_segment_id=first):
        return OrientationDecision(
            disposition="NATIVE_OMIT",
            line_id=line_id,
            omit_reason="native_open_self_orients",
            force_remint=False,
        )

    # 5. KEEP_REQUIRED
    return OrientationDecision(
        disposition="KEEP_REQUIRED",
        line_id=line_id,
        omit_reason=None,
        force_remint=False,
    )


def apply_orientation(
    ctx: RunContext,
    gap_report: dict[str, Any],
    ordered_segment_ids: list[str],
    *,
    orientation_nugget_ids: list[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply disposition then run ensure body; reconcile escalations after."""
    from interview_mux.opening_orientation import ensure_episode_orientation_body

    decision = decide_orientation(
        ctx,
        gap_report,
        ordered_segment_ids,
        orientation_nugget_ids=orientation_nugget_ids,
    )
    out, actions = ensure_episode_orientation_body(
        ctx,
        gap_report,
        ordered_segment_ids,
        orientation_nugget_ids=orientation_nugget_ids,
        decision=decision,
    )
    try:
        reconcile_escalations(ctx)
    except Exception:
        pass
    try:
        identify_hosted_vo_floor(ctx, persist=True)
    except Exception:
        pass
    # Republish vo_seats from post-disposition gap when plan exists.
    try:
        if decision.force_remint or decision.disposition in {
            "HEARD_KEEP",
            "HOLLOW_MINT",
            "KEEP_REQUIRED",
            "OPERATOR_OMIT",
            "NATIVE_OMIT",
        }:
            from interview_mux.air_script import build_vo_seats, load_air_script

            if ctx.artifact_exists("mastering/mastering_plan.json"):
                plan = ctx.read_json("mastering/mastering_plan.json")
                if isinstance(plan, dict):
                    seats = build_vo_seats(plan, out if isinstance(out, dict) else None)
                    script = load_air_script(plan) or {}
                    if not isinstance(script, dict):
                        script = {}
                    script = dict(script)
                    script["vo_seats"] = seats
                    plan = dict(plan)
                    plan["air_script"] = script
                    ctx.write_json(
                        "mastering/mastering_plan.json", plan, skip_handoff=True
                    )
                    actions = list(actions) + [
                        {"action": "republish_vo_seats", "disposition": decision.disposition}
                    ]
    except Exception:
        pass
    return out, actions


def assert_books_agree(ctx: RunContext) -> list[str]:
    """Gap omit XOR (EDL seat or WAV) is dual-book drift."""
    errs: list[str] = []
    try:
        from interview_mux.opening_orientation import orientation_omitted

        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
        omitted = orientation_omitted(gap if isinstance(gap, dict) else None)
        heard = orientation_heard_on_disk(ctx) or orientation_seated_in_edl(ctx)
        if omitted and heard:
            errs.append(
                "hosted_vo_books_agree: opening_orientation omitted but "
                "EDL/WAV still seats vo_preface_episode_orientation"
            )
        if not omitted and isinstance(gap, dict):
            lines = gap.get("interviewer_lines") or []
            has_orient = any(
                isinstance(ln, dict)
                and str(ln.get("line_id") or "") == ORIENTATION_LINE_ID
                and str(ln.get("text") or "").strip()
                and not ln.get("skipped_optional")
                for ln in lines
            )
            if heard and not has_orient:
                errs.append(
                    "hosted_vo_books_agree: EDL/WAV seats orientation but "
                    "gap_report lacks live orientation line"
                )
    except Exception as exc:
        errs.append(f"hosted_vo_books_agree:probe_failed:{exc}")
    return errs


def edl_before_line_survives(line: dict[str, Any], *, after_vo_stack: bool = True) -> bool:
    """Survivor predicate for ``build_flow1_edl`` (i9 / Cluster D).

    After a ``vo_pickup``/``transition`` stack (or contiguous same-speaker skip),
    only classes in ``EDL_SURVIVORS_AFTER_ORIENTATION`` may still seat — otherwise
    layup WAVs become ``phantom_vo``. ``after_vo_stack`` is retained for call-site
    clarity; survivor classes are identical on both paths so books stay aligned.
    """
    from interview_mux.opening_orientation import is_episode_orientation

    if not isinstance(line, dict):
        return False
    _ = after_vo_stack  # API: contiguous vs post-VO; same survivor set (i9)
    classes: set[str] = set()
    if is_episode_orientation(line):
        classes.add("orientation")
    origin = str(line.get("origin") or "").strip()
    if origin:
        classes.add(origin)
    if bool(line.get("required")):
        classes.add("required")
    return bool(classes & EDL_SURVIVORS_AFTER_ORIENTATION)


def drop_orphan_orientation_allowed(ctx: RunContext, gap_report: dict[str, Any]) -> bool:
    """WAV/EDL delete only under OPERATOR/NATIVE omit — never HEARD/HOLLOW."""
    ordered: list[str] = []
    try:
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            ordered = [
                str(x)
                for x in ((sel or {}).get("ordered_segment_ids") or [])
                if x
            ]
    except Exception:
        ordered = []
    decision = decide_orientation(ctx, gap_report, ordered)
    return decision.disposition in {"OPERATOR_OMIT", "NATIVE_OMIT"}


__all__ = [
    "EDL_SURVIVORS_AFTER_ORIENTATION",
    "FLOOR_IDENTITY_META_KEY",
    "FloorIdentity",
    "HostedFloorSnapshot",
    "ORIENTATION_LINE_ID",
    "OrientationDecision",
    "apply_orientation",
    "assert_books_agree",
    "decide_orientation",
    "drop_orphan_orientation_allowed",
    "edl_before_line_survives",
    "floor_identity_to_dict",
    "floor_snapshot",
    "have",
    "have_edl",
    "have_gap",
    "identify_hosted_vo_floor",
    "may_aspirational_proceed",
    "need",
    "orientation_heard_on_disk",
    "orientation_seated_in_edl",
    "reconcile_escalations",
    "resume_producer",
    "seed_walk_pin_for_hollow_hosted_vo",
]
