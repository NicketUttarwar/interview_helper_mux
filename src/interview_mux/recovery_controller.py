"""Product recovery controller — one typed playbook per (stage, signature).

Not an e2e waiver layer. Playbooks produce a legal artifact or escalate.
Budget: at most one attempt per signature per run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

RECOVERY_LOG_REL = "operator/recovery_actions.jsonl"
FRAMING_VO_MAX_OBSERVATIONS = 3

# Explicit consumer → producer for fingerprint restamp (never guess).
FINGERPRINT_PRODUCER_BY_CONSUMER: dict[str, str] = {
    "sonic_context_build": "content_brief_reanchor",
    "topic_coverage_audit": "content_brief_reanchor",
}


@dataclass
class RecoveryResult:
    status: str  # recovered | escalate
    playbook_id: str
    signature: str
    resume_stage: str
    artifacts_written: list[str] = field(default_factory=list)
    detail: str = ""


def classify_error_class(stage_id: str, exc: BaseException) -> str | None:
    """Map a stage exception to a closed error_class (no fuzzy driver substrings)."""
    msg = str(exc).lower()
    stage = str(stage_id or "")
    if stage == "ideal_cuts_materialize" and (
        "no valid cuts after snap" in msg or "bind_mode requires boundaries" in msg
    ):
        return "empty_snap"
    if stage in {"nugget_layup_compose", "gap_framing_recompose"} and "never_touch_cta" in msg:
        return "never_touch_cta"
    if stage in {"nugget_layup_compose", "gap_framing_recompose"} and (
        "layup_coverage" in msg
        or "min_layup_coverage" in msg
        or "nugget layup qc failed" in msg
        or "nugget_layup_qc_failed" in msg
        or "layup authority" in msg
    ):
        return "layup_coverage"
    if stage == "edl" and "preceding framing vo" in msg:
        return "framing_vo_unseated"
    if stage == "edl" and "targets_segment_id" in msg and "does not match gap_report" in msg:
        return "orientation_target_mismatch"
    if stage in {"edl", "mix", "junction_snip_qa", "master_finalize"} and (
        "naked seam" in msg or "naked_seam" in msg
    ):
        return "naked_seam"
    if stage in {"mix", "mmaudio_sfx"} and "mmaudio_qa" in msg:
        return "mmaudio_qa_missing"
    if stage in {"mix", "mmaudio_sfx", "sfx_prompt_craft"} and (
        "missing wav for asset_id" in msg or "missing wav for asset" in msg
    ):
        return "sdp_theme_wavs_missing"
    if stage in {"master_finalize", "mix"} and (
        "episode_close_outro" in msg or "missing_episode_close_outro" in msg
    ):
        return "episode_close_outro"
    if stage in {"edl", "g1_vo", "g1_vo_pickup"} and (
        "g1 vo pickup missing" in msg or "stale_or_missing_pickup" in msg
    ):
        return "missing_g1_pickup"
    if stage == "listen_delight_audit" and (
        "listen delight floors" in msg or "listen_delight_floors" in msg
    ):
        return "listen_delight_floors"
    if "fingerprint mismatch" in msg:
        return "fingerprint_mismatch"
    if stage == "speaker_roles" and (
        "rerun_stage" in msg
        and ("diarization" in msg or "speaker_diarization" in msg)
    ):
        return "mixed_diarization"
    if stage == "edl" and (
        "unknown segment_id" in msg or "edl_qc strict" in msg or "edl_qc" in msg
    ):
        return "unknown_nle_split_child"
    if stage == "nugget_layup_compose" and (
        "cta_omit_applied" in msg
        or (
            "rerun_stage" in msg
            and "selection" in msg
            and any(
                token in msg
                for token in (
                    "sponsor",
                    "media_ip",
                    "subscribe",
                    "monetiz",
                    "cta",
                    "outro",
                    "credits",
                    "direct listener",
                )
            )
        )
    ):
        return "selection_cta_omit"
    reason = str(getattr(exc, "reason", "") or "").lower()
    if stage in {"edl", "mix", "junction_snip_qa", "master_finalize"} and (
        "selection_edl_order_drift" in msg
        or "ordered_segment_ids drifted" in msg
        or "speech clip order diverges" in msg
        or "speech clip order" in msg
    ):
        return "selection_edl_order_drift"
    if (
        "assembly_not_rendered_from_current_edl" in msg
        or "air_order generation mismatch" in msg
        or reason == "assembly_not_rendered_from_current_edl"
    ):
        return "assembly_not_rendered_from_current_edl"
    if (
        "opening_slot_conflict" in msg
        or "duplicate opening layup" in msg
        or "opening_orientation_owns_target" in msg
    ):
        return "opening_slot_conflict"
    if (
        reason == "post_master_quality_missing"
        or "post_master_quality_missing" in msg
        or "post-master quality artifact is missing" in msg
    ):
        return "post_master_quality_missing"
    if "high_gap_unframed" in msg or (
        "high gap segment" in msg and "no interviewer line" in msg
    ):
        return "high_gap_unframed"
    return None


CLASSIFIED_PLAYBOOKS = frozenset(
    {
        "empty_snap",
        "never_touch_cta",
        "layup_coverage",
        "orientation_target_mismatch",
        "unknown_nle_split_child",
        "framing_vo_unseated",
        "naked_seam",
        "mmaudio_qa_missing",
        "sdp_theme_wavs_missing",
        "episode_close_outro",
        "missing_g1_pickup",
        "listen_delight_floors",
        "fingerprint_mismatch",
        "mixed_diarization",
        "selection_cta_omit",
        "selection_edl_order_drift",
        "assembly_not_rendered_from_current_edl",
        "opening_slot_conflict",
        "post_master_quality_missing",
        "high_gap_unframed",
    }
)


def has_classified_playbook(error_class: str | None) -> bool:
    return bool(error_class) and error_class in CLASSIFIED_PLAYBOOKS


def signature_key(stage_id: str, error_class: str) -> str:
    return f"{stage_id}:{error_class}"


def _log_path(ctx: RunContext) -> Path:
    dest = Path(ctx.run_dir) / RECOVERY_LOG_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def _read_actions(ctx: RunContext) -> list[dict[str, Any]]:
    path = _log_path(ctx)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append_action(ctx: RunContext, row: dict[str, Any]) -> None:
    path = _log_path(ctx)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def already_attempted(ctx: RunContext, signature: str) -> bool:
    for row in _read_actions(ctx):
        if str(row.get("signature") or "") == signature:
            return True
    return False


def vo_seats_fingerprint(ctx: RunContext) -> str:
    try:
        from interview_mux.air_script import load_air_script
        from interview_mux.mastering_plan_loader import load_plan_raw

        script = load_air_script(load_plan_raw(ctx)) or {}
        seats = script.get("vo_seats") if isinstance(script.get("vo_seats"), dict) else {}
        blob = json.dumps(seats, sort_keys=True, ensure_ascii=False)
    except Exception:
        blob = ""
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _signature_hash_hits(ctx: RunContext, signature: str, vo_seats_hash: str) -> int:
    n = 0
    for row in _read_actions(ctx):
        if str(row.get("signature") or "") != signature:
            continue
        if str(row.get("vo_seats_hash") or "") != vo_seats_hash:
            continue
        n += 1
    return n


def playbook_stamp_air_script_omits(ctx: RunContext) -> list[str]:
    from interview_mux.air_script import persist_air_script_omits_on_gap_report

    persist_air_script_omits_on_gap_report(ctx)
    written: list[str] = []
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        written.append("mastering/mastering_plan.json")
    if ctx.artifact_exists("understanding/gap_report.json"):
        written.append("understanding/gap_report.json")
    return written


def _result(
    *,
    status: str,
    playbook_id: str,
    signature: str,
    resume_stage: str,
    artifacts: list[str] | None = None,
    detail: str = "",
) -> RecoveryResult:
    return RecoveryResult(
        status=status,
        playbook_id=playbook_id,
        signature=signature,
        resume_stage=resume_stage,
        artifacts_written=list(artifacts or []),
        detail=detail,
    )


def playbook_stamp_valueless_skips(ctx: RunContext) -> list[str]:
    from interview_mux.nugget_layup import (
        PLAN_REL,
        prepare_layup_plan_for_persist,
        publish_layup_plan_to_gap_report,
        stamp_valueless_skips,
    )

    if not ctx.artifact_exists(PLAN_REL):
        return []
    plan = ctx.read_json(PLAN_REL)
    plan, notes = stamp_valueless_skips(ctx, plan if isinstance(plan, dict) else {})
    plan = prepare_layup_plan_for_persist(ctx, plan)
    ctx.write_json(PLAN_REL, plan, stage_key="nugget_layup_compose")
    publish_layup_plan_to_gap_report(ctx, plan)
    return [PLAN_REL] if notes else []


def playbook_orientation_retarget(ctx: RunContext) -> list[str]:
    from interview_mux.opening_orientation import retarget_orientation_to_open

    return retarget_orientation_to_open(ctx)


def playbook_place_episode_close(ctx: RunContext) -> list[str]:
    from interview_mux.listen_quality import place_episode_close_cue

    return place_episode_close_cue(ctx)


def playbook_ensure_mmaudio_qa(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_recovery import ensure_mmaudio_qa_before_mix

    state = ensure_mmaudio_qa_before_mix(ctx, run_if_missing=True)
    if state.get("ok"):
        return [str(state.get("path") or "sound_design/mmaudio_qa.json")]
    return []


def playbook_generate_sdp_theme_wavs(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_recovery import resume_theme_generation
    from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

    missing = missing_sdp_asset_wavs(ctx)
    resume_theme_generation(ctx)
    return [f"missing:{aid}" for aid in missing[:12]]


def playbook_ensure_g1(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_recovery import ensure_g1_pickups

    result = ensure_g1_pickups(ctx)
    if isinstance(result, dict) and result.get("ok"):
        return list(result.get("synthesized") or []) or ["vo_pickup"]
    return []


def playbook_listen_delight_remutate(ctx: RunContext) -> list[str]:
    from interview_mux.listen_delight import evaluate_listen_delight
    from interview_mux.listen_delight_remutate import (
        apply_listen_delight_remutate,
        plan_listen_delight_remutate,
    )

    result = evaluate_listen_delight(ctx)
    plan = plan_listen_delight_remutate(
        ctx, failed_dimensions=list(result.get("failed_dimensions") or [])
    )
    if plan.get("exhausted"):
        return []
    applied = apply_listen_delight_remutate(ctx, plan)
    if applied.get("ok"):
        return [str(plan.get("from_stage") or "mix")]
    return []


def playbook_mint_reorder_glue(ctx: RunContext) -> list[str]:
    from interview_mux.seam_glue import ensure_seam_glue

    selection = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {}
    )
    ordered = [
        str(s)
        for s in ((selection or {}).get("ordered_segment_ids") or [])
        if s
    ]
    if not ordered:
        return []
    manifest = (
        ctx.read_json("segments/manifest.json")
        if ctx.artifact_exists("segments/manifest.json")
        else {}
    )
    by_id = {
        str(s.get("segment_id") or ""): s
        for s in ((manifest or {}).get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    gap = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else None
    )
    transitions = (
        ctx.read_json("master/transitions.json")
        if ctx.artifact_exists("master/transitions.json")
        else {"transitions": []}
    )
    _bridges, transitions_doc, completeness = ensure_seam_glue(
        ctx,
        ordered=ordered,
        segments_by_id=by_id,
        gap_report=gap if isinstance(gap, dict) else None,
        transitions=transitions if isinstance(transitions, dict) else None,
        soft=False,
    )
    written = ["master/bridge_completeness.json"]
    if isinstance(transitions_doc, dict):
        ctx.write_json("master/transitions.json", transitions_doc)
        written.append("master/transitions.json")
    waived: set[str] = set()
    try:
        from interview_mux.air_script import native_handoff_segment_ids
        from interview_mux.mastering_plan_loader import load_plan_raw

        waived = native_handoff_segment_ids(load_plan_raw(ctx))
    except Exception:
        waived = set()
    if isinstance(completeness, dict) and not completeness.get("complete"):
        leftover = []
        for row in completeness.get("missing") or []:
            if not isinstance(row, dict):
                continue
            dest = str(
                row.get("before_segment_id")
                or row.get("before_id")
                or row.get("to")
                or ""
            )
            if dest and dest not in waived:
                leftover.append(dest)
        if leftover:
            return []
        # Remaining incompleteness is native_handoff / air_breathe — dressed, not missing glue.
        return written
    return written



def _unmark_stages(ctx: RunContext, *stage_ids: str) -> None:
    for sid in stage_ids:
        (Path(ctx.run_dir) / ".stage_done" / sid).unlink(missing_ok=True)


def playbook_selection_edl_order_drift(ctx: RunContext) -> list[str]:
    from interview_mux.air_order import commit, rollback
    from interview_mux.order_hash import order_drift_heal_action
    from interview_mux.timeline_optimizer.config import optimizer_live_mutate_blocked
    from interview_mux.timeline_optimizer.daemon import stop_optimizer_daemon

    sel = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else None
    )
    edl = ctx.read_json("master/edl.json") if ctx.artifact_exists("master/edl.json") else None
    if (
        isinstance(sel, dict)
        and sel.get("order_authority") == "timeline_optimizer"
        and optimizer_live_mutate_blocked(ctx)
    ):
        rollback(ctx)
        return ["master/selection.json"]
    action = order_drift_heal_action(
        sel if isinstance(sel, dict) else None,
        edl if isinstance(edl, dict) else None,
    )
    if action == "exclude_unseated":
        commit(ctx, source="recovery_exclude_unseated")
        return ["master/selection.json", "master/edl.json"]
    if action == "stamp":
        commit(ctx, source="recovery_stamp")
        return ["master/selection.json", "master/edl.json"]
    if action == "rebuild":
        stop_optimizer_daemon(ctx)
        from interview_mux.stages.assembly import run_edl

        run_edl(ctx)
        return ["master/edl.json"]
    if ctx.artifact_exists("master/edl.json"):
        commit(ctx, source="recovery_order_ok")
        return ["master/edl.json"]
    return []


def playbook_assembly_not_rendered(ctx: RunContext) -> list[str]:
    _unmark_stages(ctx, "mix", "junction_snip_qa", "master_finalize")
    return ["master/edl.json"] if ctx.artifact_exists("master/edl.json") else []


def playbook_opening_slot_conflict(ctx: RunContext) -> list[str]:
    from interview_mux.opening_adjacency_repair import (
        drop_orphan_opening_vo_when_native_orients,
        suppress_opening_layup_when_orientation_owns_slot,
    )

    suppress_opening_layup_when_orientation_owns_slot(ctx)
    drop_orphan_opening_vo_when_native_orients(ctx)
    if ctx.artifact_exists("master/edl.json"):
        from interview_mux.air_order import commit

        commit(ctx, source="opening_slot_conflict")
    written = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        written.append("understanding/gap_report.json")
    if ctx.artifact_exists("master/edl.json"):
        written.append("master/edl.json")
    return written


def playbook_post_master_quality_missing(ctx: RunContext) -> list[str]:
    from interview_mux.post_master_quality import QUALITY_REL, run_post_master_quality

    run_post_master_quality(ctx, block=False)
    return [QUALITY_REL] if ctx.artifact_exists(QUALITY_REL) else []


def playbook_high_gap_unframed(ctx: RunContext) -> list[str]:
    from interview_mux.artifact_repairs import repair_gap_report

    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    doc = ctx.read_json("understanding/gap_report.json")
    if not isinstance(doc, dict):
        return []
    repaired, _notes = repair_gap_report(ctx, doc)
    ctx.write_json("understanding/gap_report.json", repaired)
    return ["understanding/gap_report.json"]


def playbook_skip_never_touch_cta_layups(ctx: RunContext) -> list[str]:
    from interview_mux.nugget_layup import PLAN_REL, skip_never_touch_cta_layups

    plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    out, _notes = skip_never_touch_cta_layups(ctx, plan if isinstance(plan, dict) else {})
    ctx.write_json(PLAN_REL, out)
    return [PLAN_REL]


def playbook_materialize_nle_split_children(ctx: RunContext) -> list[str]:
    from interview_mux.nle_state import materialize_all_nle_split_children

    materialize_all_nle_split_children(ctx)
    return ["segments/manifest.json"] if ctx.artifact_exists("segments/manifest.json") else []


def playbook_host_cta_omit(ctx: RunContext) -> list[str]:
    from interview_mux.media_ip_cta import execute_cta_omit_from_needs, heal_on_air_cta_residue

    needs: list[dict[str, Any]] = []
    try:
        from interview_mux.homunculus.issues import read_issues

        for issue in read_issues(ctx):
            ev = issue.get("evidence") or {}
            msg = str(ev.get("message") or "")
            if "cta" in msg.lower() or "media_ip" in msg.lower():
                needs.append({"message": msg})
    except Exception:
        pass
    execute_cta_omit_from_needs(ctx, needs)
    heal_on_air_cta_residue(ctx)
    return ["master/selection.json"] if ctx.artifact_exists("master/selection.json") else []


def handle_stage_failure(
    ctx: RunContext,
    stage_id: str,
    exc: BaseException,
) -> RecoveryResult:
    """Run at most one playbook for this signature, then recovered or escalate."""
    try:
        from interview_mux.homunculus.issues import ingest_catch
        from interview_mux.homunculus.runtime import is_homunculus_run, recovery_allowed

        ingest_catch(
            ctx,
            kind="stage_failure",
            source="recovery_controller",
            stage_id=stage_id,
            implicated=[stage_id],
            evidence={"error_class": type(exc).__name__, "message": str(exc)[:400]},
        )
        early_class = classify_error_class(stage_id, exc)
        if is_homunculus_run(ctx) and not recovery_allowed(
            ctx, stage_id, exc=exc, error_class=early_class
        ):
            return _result(
                status="escalate",
                playbook_id="awaiting_homunculus_analysis",
                signature=signature_key(stage_id, early_class or "unknown"),
                resume_stage=stage_id,
                detail="homunculus_analysis_required",
            )
    except Exception:
        pass
    error_class = classify_error_class(stage_id, exc)
    if not error_class:
        return _result(
            status="escalate",
            playbook_id="none",
            signature=signature_key(stage_id, "unknown"),
            resume_stage=stage_id,
            detail="no_matching_playbook",
        )
    from interview_mux.identical_failures import (
        failure_signature,
        is_halted,
        record_identical_failure,
    )

    halt_sig = failure_signature(
        failed_stage=stage_id,
        producer=error_class,
        reason=str(exc)[:400],
    )
    if is_halted(ctx, halt_sig):
        return _result(
            status="escalate",
            playbook_id="identical_failure_halt",
            signature=signature_key(stage_id, error_class),
            resume_stage=stage_id,
            detail="identical_failures_halted",
        )
    sig = signature_key(stage_id, error_class)
    vo_hash = ""
    if error_class == "framing_vo_unseated":
        vo_hash = vo_seats_fingerprint(ctx)
        hits = _signature_hash_hits(ctx, sig, vo_hash)
        if hits + 1 >= FRAMING_VO_MAX_OBSERVATIONS:
            result = _result(
                status="escalate",
                playbook_id="identical_vo_seats_x3",
                signature=sig,
                resume_stage=stage_id,
                detail="unchanged_vo_seats_hash",
            )
            _append_action(
                ctx,
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "signature": sig,
                    "playbook_id": result.playbook_id,
                    "status": result.status,
                    "detail": result.detail,
                    "vo_seats_hash": vo_hash,
                },
            )
            return result
    elif already_attempted(ctx, sig):
        resume_on_budget = (
            "music_palette_compose" if error_class == "sdp_theme_wavs_missing" else stage_id
        )
        result = _result(
            status="escalate",
            playbook_id="budget_exhausted",
            signature=sig,
            resume_stage=resume_on_budget,
            detail="already_attempted",
        )
        _append_action(
            ctx,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "signature": sig,
                "playbook_id": result.playbook_id,
                "status": result.status,
                "detail": result.detail,
            },
        )
        record_identical_failure(
            ctx,
            failed_stage=stage_id,
            producer=error_class,
            reason=str(exc)[:400],
            resume_attempted=resume_on_budget,
        )
        return result

    playbook_id = error_class
    artifacts: list[str] = []
    recovered = False
    detail = ""
    resume_stage = stage_id
    try:
        if error_class == "empty_snap":
            playbook_id = "cuts_empty_snap_demote"
            from interview_mux.ideal_cuts import MATERIALIZED_REL, run_ideal_cuts_materialize

            # In-stage demote writes materialized without raising; re-run once.
            try:
                run_ideal_cuts_materialize(ctx)
            except Exception:
                pass
            recovered = ctx.artifact_exists(MATERIALIZED_REL)
        elif error_class == "layup_coverage":
            playbook_id = "stamp_valueless_skips"
            artifacts = playbook_stamp_valueless_skips(ctx)
            recovered = True
        elif error_class == "orientation_target_mismatch":
            playbook_id = "orientation_retarget_open"
            artifacts = playbook_orientation_retarget(ctx)
            recovered = True
        elif error_class == "framing_vo_unseated":
            playbook_id = "stamp_air_script_omits"
            artifacts = playbook_stamp_air_script_omits(ctx)
            recovered = True
            resume_stage = "edl"
        elif error_class == "naked_seam":
            playbook_id = "seam_mint_reorder"
            artifacts = playbook_mint_reorder_glue(ctx)
            recovered = bool(artifacts)
        elif error_class == "mmaudio_qa_missing":
            playbook_id = "ensure_mmaudio_qa"
            artifacts = playbook_ensure_mmaudio_qa(ctx)
            recovered = bool(artifacts)
            resume_stage = "mmaudio_sfx"
        elif error_class == "sdp_theme_wavs_missing":
            playbook_id = "generate_sdp_theme_wavs"
            artifacts = playbook_generate_sdp_theme_wavs(ctx)
            recovered = True
            resume_stage = "music_palette_compose"
        elif error_class == "episode_close_outro":
            playbook_id = "place_episode_close_cue"
            artifacts = playbook_place_episode_close(ctx)
            recovered = bool(artifacts)
            if recovered:
                resume_stage = "mix"
        elif error_class == "missing_g1_pickup":
            playbook_id = "ensure_g1_pickups"
            artifacts = playbook_ensure_g1(ctx)
            recovered = bool(artifacts)
        elif error_class == "listen_delight_floors":
            playbook_id = "listen_delight_remutate"
            artifacts = playbook_listen_delight_remutate(ctx)
            recovered = bool(artifacts)
            resume_stage = "mix"
            try:
                if ctx.artifact_exists("mastering/listen_delight_remutate.json"):
                    plan = ctx.read_json("mastering/listen_delight_remutate.json")
                    if isinstance(plan, dict) and plan.get("from_stage"):
                        resume_stage = str(plan.get("from_stage") or "mix")
            except Exception:
                pass
        elif error_class == "fingerprint_mismatch":
            playbook_id = "fingerprint_restamp_or_rerun"
            producer = FINGERPRINT_PRODUCER_BY_CONSUMER.get(stage_id)
            recovered = bool(producer)
            detail = producer or "no_mapped_producer"
            if producer:
                resume_stage = producer
        elif error_class == "mixed_diarization":
            playbook_id = "speaker_roles_dominant_fallback"
            from interview_mux.speaker_role_evidence import persist_mixed_diarization_fallback

            artifacts = persist_mixed_diarization_fallback(ctx)
            recovered = bool(artifacts)
            if recovered:
                resume_stage = "source_topology_build"
        elif error_class == "never_touch_cta":
            playbook_id = "skip_never_touch_cta_layups"
            artifacts = playbook_skip_never_touch_cta_layups(ctx)
            recovered = True
        elif error_class == "unknown_nle_split_child":
            playbook_id = "materialize_nle_split_children"
            artifacts = playbook_materialize_nle_split_children(ctx)
            recovered = True
            resume_stage = "edl"
        elif error_class == "selection_cta_omit":
            playbook_id = "host_cta_omit"
            artifacts = playbook_host_cta_omit(ctx)
            recovered = True
            resume_stage = "nugget_layup_compose"
        elif error_class == "selection_edl_order_drift":
            playbook_id = "selection_edl_order_drift"
            artifacts = playbook_selection_edl_order_drift(ctx)
            recovered = bool(artifacts)
            resume_stage = (
                "mix"
                if stage_id in {"mix", "junction_snip_qa", "master_finalize"}
                else "edl"
            )
        elif error_class == "assembly_not_rendered_from_current_edl":
            playbook_id = "assembly_not_rendered_from_current_edl"
            artifacts = playbook_assembly_not_rendered(ctx)
            recovered = True
            resume_stage = "mix"
        elif error_class == "opening_slot_conflict":
            playbook_id = "opening_slot_conflict"
            artifacts = playbook_opening_slot_conflict(ctx)
            recovered = bool(artifacts)
            resume_stage = "edl"
        elif error_class == "post_master_quality_missing":
            playbook_id = "post_master_quality_missing"
            artifacts = playbook_post_master_quality_missing(ctx)
            recovered = bool(artifacts)
            resume_stage = "master_finalize"
        elif error_class == "high_gap_unframed":
            playbook_id = "high_gap_unframed"
            artifacts = playbook_high_gap_unframed(ctx)
            recovered = bool(artifacts)
            resume_stage = "gap_framing_compose"
        else:
            recovered = False
            detail = "unhandled_class"
    except Exception as play_exc:
        recovered = False
        detail = str(play_exc)[:240]

    result = _result(
        status="recovered" if recovered else "escalate",
        playbook_id=playbook_id,
        signature=sig,
        resume_stage=resume_stage,
        artifacts=artifacts,
        detail=detail,
    )
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": result.playbook_id,
            "status": result.status,
            "artifacts": result.artifacts_written,
            "detail": result.detail,
            **({"vo_seats_hash": vo_hash} if vo_hash else {}),
        },
    )
    if result.status != "recovered":
        row = record_identical_failure(
            ctx,
            failed_stage=stage_id,
            producer=error_class,
            reason=str(exc)[:400],
            resume_attempted=result.resume_stage,
        )
        if row.get("halt"):
            result.status = "escalate"
            result.playbook_id = "identical_failure_halt"
            result.detail = (result.detail + " identical_failures_halted").strip()
    return result
