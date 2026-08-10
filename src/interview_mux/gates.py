from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from interview_mux.config import merged_config
from interview_mux.edl_narrative_qc import validate_flow1_edl_narrative
from interview_mux.edl_qc import validate_flow1_edl
from interview_mux.narrative_qc import validate_flow1_narrative
from interview_mux.operator_quality import record_qc_summary
from interview_mux.run_context import RunContext


def _line_requires_vo(line: dict) -> bool:
    """True when a gap line needs pickup VO (record or synthesize)."""
    delivery = str(line.get("delivery") or "").lower()
    if delivery not in {"record", "synthesize"}:
        return False
    if line.get("skipped_optional"):
        return False
    severity = str(line.get("severity") or "blocking").lower()
    return severity in {"blocking", "high", "medium", "critical"}


def _gate_exit(ctx: RunContext, message: str, *, stage: str, level: str = "error") -> None:
    ctx.log(message, level=level, stage=stage)
    raise SystemExit(message)


def check_timeline_optimizer_pending(ctx: RunContext) -> bool:
    """True when finalize should wait for take-best/skip (optional hard mode)."""
    from interview_mux.timeline_optimizer.config import optimizer_cfg

    cfg = optimizer_cfg()
    if not cfg.get("block_finalize_until_take_or_skip"):
        return False
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if isinstance(meta, dict) and (
        meta.get("timeline_optimizer_skipped")
        or meta.get("timeline_optimizer_promoted")
        or meta.get("operator_took_best")
    ):
        return False
    from interview_mux.timeline_optimizer.state import load_optimizer_state
    from interview_mux.timeline_optimizer.daemon import is_optimizer_running

    state = load_optimizer_state(ctx)
    if state.get("operator_took_best") or state.get("auto_promoted_once"):
        return False
    return is_optimizer_running(ctx.run_id) or state.get("status") == "running"


def require_timeline_optimizer_clear(ctx: RunContext, *, stage: str) -> None:
    from interview_mux.timeline_optimizer.config import optimizer_cfg

    cfg = optimizer_cfg()
    if not cfg.get("block_finalize_until_take_or_skip"):
        # Advisory: still log if daemon is running
        try:
            from interview_mux.timeline_optimizer.daemon import is_optimizer_running
            from interview_mux.timeline_optimizer.state import load_optimizer_state

            if is_optimizer_running(ctx.run_id):
                st = load_optimizer_state(ctx)
                ctx.log(
                    f"timeline_optimizer still running (gen={st.get('generation')} "
                    f"best={st.get('best_score')}) — finalize uses current artifacts; "
                    "Take best anytime via GUI",
                    level="info",
                    stage=stage,
                )
        except Exception:
            pass
        return
    if check_timeline_optimizer_pending(ctx):
        _gate_exit(
            ctx,
            "Timeline optimizer pending — Take best or Skip via GUI "
            "(POST …/timeline-optimizer/take-best|skip).",
            stage=stage,
        )


def clear_timeline_optimizer_gate(ctx: RunContext, *, skipped: bool = False) -> None:
    def patch(meta: dict) -> None:
        if skipped:
            meta["timeline_optimizer_skipped"] = True
        else:
            meta["timeline_optimizer_cleared"] = True

    ctx.mutate_run_meta(patch)


def check_g_listen_pending(ctx: RunContext) -> bool:
    """Optional G-Listen when listen_critic recommends a borderline quality review."""
    sound_cfg = merged_config().get("sound_design") or {}
    if not bool(sound_cfg.get("g_listen_enabled", True)):
        return False
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        return False
    if meta.get("g_listen_skipped") or meta.get("g_listen_cleared"):
        return False
    if meta.get("g_listen_pending"):
        return True
    if ctx.artifact_exists("master/listen_critic.json"):
        try:
            critic = ctx.read_json("master/listen_critic.json")
            if isinstance(critic, dict) and critic.get("g_listen_recommended"):
                return True
        except Exception:
            return False
    return False


def require_g_listen_clear(ctx: RunContext, *, stage: str) -> None:
    """Soft-block master_finalize only when g_listen_mode=block."""
    sound_cfg = merged_config().get("sound_design") or {}
    mode = str(sound_cfg.get("g_listen_mode", "warn")).lower()
    if mode not in {"block", "block_mix"}:
        if check_g_listen_pending(ctx):
            ctx.log(
                "G-Listen recommended (optional) — continue or skip via GUI",
                level="warning",
                stage=stage,
            )
        return
    if check_g_listen_pending(ctx):
        _gate_exit(
            ctx,
            "G-Listen pending — listen to assembly/master preview and continue "
            "(POST …/g-listen/continue) or skip (POST …/g-listen/skip).",
            stage=stage,
        )


def clear_g_listen(ctx: RunContext, *, skipped: bool = False) -> None:
    def patch(meta: dict) -> None:
        meta["g_listen_pending"] = False
        if skipped:
            meta["g_listen_skipped"] = True
        else:
            meta["g_listen_cleared"] = True

    ctx.mutate_run_meta(patch)


def sync_post_listen_gate_state(ctx: RunContext) -> dict:
    """Persist post_listen_gate_state on run_meta from listen results and optional QA block."""
    sound_cfg = merged_config().get("sound_design") or {}
    raw_mode = str(sound_cfg.get("post_listen_gate_mode", "warn")).lower()
    mode = "block_mix" if raw_mode == "block" else raw_mode
    if mode not in {"soft", "warn", "block_mix"}:
        mode = "warn"

    blocked = set(check_post_listen_gate_pending(ctx))
    if bool(sound_cfg.get("block_mix_on_mmaudio_qa_fail", False)):
        from interview_mux.mmaudio_asset_qa import load_mmaudio_qa

        qa = load_mmaudio_qa(ctx)
        for row in qa.get("assets") or []:
            if isinstance(row, dict) and row.get("verdict") == "fail":
                aid = str(row.get("asset_id") or "")
                if aid:
                    blocked.add(aid)

    state = {
        "mode": mode,
        "blocked_assets": sorted(blocked),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    def patch(meta: dict) -> None:
        meta["post_listen_gate_state"] = state

    ctx.mutate_run_meta(patch)
    return state


def check_post_listen_gate_pending(ctx: RunContext) -> list[str]:
    """Return asset_ids with failed listen results when post_listen gate is blocking."""
    sound_cfg = merged_config().get("sound_design") or {}
    post_listen_mode = str(sound_cfg.get("post_listen_gate_mode", "warn")).lower()
    if post_listen_mode not in {"block", "block_mix"}:
        return []
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    listen = meta.get("sfx_listen_results") or []
    latest: dict[str, str] = {}
    for row in listen:
        if isinstance(row, dict) and row.get("asset_id"):
            latest[str(row.get("asset_id"))] = str(row.get("result") or "")
    return sorted(aid for aid, result in latest.items() if result == "fail")


def require_post_listen_clear(ctx: RunContext, *, stage: str) -> None:
    failed = check_post_listen_gate_pending(ctx)
    if failed:
        _gate_exit(
            ctx,
            f"Post-listen gate: failed listen result(s) for {', '.join(failed[:6])}. "
            "Re-listen in the GUI and mark Pass before mix.",
            stage=stage,
        )


def check_transcript_review_pending(ctx: RunContext) -> bool:
    """True when STT review queue exists but operator has not signed off."""
    if ctx.is_done("transcript_review"):
        return False
    return ctx.artifact_exists("transcript/review_queue.json")


def require_transcript_review_clear(ctx: RunContext) -> None:
    if check_transcript_review_pending(ctx):
        _gate_exit(
            ctx,
            "Transcript review gate: open the GUI, listen to ranked clips, correct text, "
            f"then mark review complete → {ctx.path('transcript/review_queue.json')}",
            stage="transcript_review",
        )


def check_disfluency_review_pending(ctx: RunContext) -> bool:
    """Disfluency G0.5 removed in v2."""
    _ = ctx
    return False


def require_disfluency_review_clear(ctx: RunContext) -> None:
    return


def g1_vo_was_skipped_optional(ctx: RunContext) -> bool:
    """True when the operator skipped optional G1 VO pickup for this run."""
    if ctx.artifact_exists("run_meta.json"):
        meta = ctx.read_json("run_meta.json")
        if isinstance(meta, dict) and meta.get("g1_vo_skipped_optional"):
            return True
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return False
    report = ctx.read_json("understanding/gap_report.json")
    for line in report.get("interviewer_lines") or []:
        if isinstance(line, dict) and line.get("skipped_optional"):
            return True
    return False


def _gap_line_has_vo_file(ctx: RunContext, line: dict) -> bool:
    from interview_mux.stages.assembly import resolve_vo_pickup_path

    if resolve_vo_pickup_path(ctx, line) is not None:
        return True
    pickup = ctx.final_path("vo_pickup")
    lid = str(line.get("line_id") or "")
    seg = str(line.get("targets_segment_id") or "")
    return any((pickup / name).is_file() for name in (f"{lid}.wav", f"{seg}.wav") if name)


def vo_gap_line_effectively_optional(ctx: RunContext, line: dict) -> bool:
    """True when a gap VO line should not block downstream narrative QC."""
    if line.get("skipped_optional"):
        return True
    from interview_mux.v2.config import v2_g1_optional

    if not v2_g1_optional():
        return False
    delivery = str(line.get("delivery") or "").lower()
    if delivery not in {"record", "synthesize"}:
        return False
    if _gap_line_has_vo_file(ctx, line):
        return False
    return g1_vo_was_skipped_optional(ctx)


def audit_issue_covers_optional_vo_gap(ctx: RunContext, issue: dict) -> bool:
    """True when an edl_narrative_audit blocking issue is about skipped/unrecorded VO."""
    from interview_mux.v2.config import v2_g1_optional

    if not v2_g1_optional():
        return False
    text = str(
        issue.get("issue") or issue.get("summary") or issue.get("reason") or ""
    ).lower()
    vo_markers = ("vo", "gap", "missing_question", "pickup", "recorded vo", "vo_ingest")
    if not any(marker in text for marker in vo_markers):
        return False
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return g1_vo_was_skipped_optional(ctx)
    report = ctx.read_json("understanding/gap_report.json")
    lines = [row for row in (report.get("interviewer_lines") or []) if isinstance(row, dict)]
    for line in lines:
        if not vo_gap_line_effectively_optional(ctx, line):
            continue
        line_id = str(line.get("line_id") or "")
        segment_id = str(line.get("targets_segment_id") or "")
        if (line_id and line_id.lower() in text) or (segment_id and segment_id.lower() in text):
            return True
    record_lines = [
        row
        for row in lines
        if str(row.get("delivery") or "").lower() in {"record", "synthesize"}
    ]
    optional_lines = [row for row in record_lines if vo_gap_line_effectively_optional(ctx, row)]
    return bool(record_lines) and len(optional_lines) == len(record_lines)


def check_g1_vo(ctx: RunContext) -> list[str]:
    """Return missing line_ids for blocking delivery=record VO (first_try severity filter)."""
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    report = ctx.read_json("understanding/gap_report.json")
    pickup = ctx.final_path("vo_pickup")
    missing: list[str] = []
    for line in report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or not _line_requires_vo(line):
            continue
        lid = line.get("line_id", "")
        seg = line.get("targets_segment_id", "")
        from interview_mux.stages.assembly import resolve_vo_pickup_path

        if resolve_vo_pickup_path(ctx, line) is None:
            candidates = [pickup / f"{lid}.wav", pickup / f"{seg}.wav"]
            if not any(p.is_file() for p in candidates):
                missing.append(lid or seg)
    return missing


def require_g1_clear(ctx: RunContext) -> None:
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
    from interview_mux.v2.config import v2_g1_optional

    if gap_fill_was_skipped(ctx):
        return
    missing = check_g1_vo(ctx)
    if missing:
        if v2_g1_optional():
            ctx.log(
                f"G1 optional: {len(missing)} VO line(s) not recorded — continue or record in GUI.",
                level="info",
                stage="g1_vo_pickup",
            )
            return
        _gate_exit(
            ctx,
            f"G1 gate: record VO for {missing} → {ctx.path('vo_pickup')}\n"
            f"See {ctx.path('understanding', 'interviewer_script.txt')}",
            stage="g1_vo_pickup",
            level="warning",
        )


def is_operator_profile_verified(ctx: RunContext) -> bool:
    """True when analysis_state.meta.operator_verified is set."""
    if not ctx.artifact_exists("understanding/analysis_state.json"):
        return False
    state = ctx.read_json("understanding/analysis_state.json")
    return bool((state.get("meta") or {}).get("operator_verified"))


def check_profile_gate_pending(ctx: RunContext) -> bool:
    """True when profile is not verified before delivery extended analysis."""
    from interview_mux.v2.config import v2_enabled

    if v2_enabled():
        return False
    if is_operator_profile_verified(ctx):
        return False
    from interview_mux.artifact_completeness import analysis_profile_ready_for_review

    if not analysis_profile_ready_for_review(ctx):
        return False
    return not ctx.is_done("topic_coverage_audit")


_DELIVERY_ORDER = (
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "nugget_corpus_mine",
    "information_package_plan",
    "nugget_layup_compose",
    "refinement_agenda",
    "gap_framing_recompose",
    "selection_framing_apply",
    "transitions",
    "sound_design_plan",
    "sound_design_vo_finalize",
    "edl_narrative_audit",
    "edl",
    "assembly_preview",
    "listen_delight_audit",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "mix",
    "junction_snip_qa",
    "master_finalize",
    "episode_meta_build",
    "episode_cover_prompt_craft",
    "podcast_encode_mp3",
    "episode_cover_generate",
    "podcast_publish",
)


_LEGACY_DELIVERY_STAGE_ALIASES = {
    "sound_design_plan_flow1": "sound_design_plan",
    "edl_flow1": "edl",
    "mmaudio_sfx_flow1": "mmaudio_sfx",
    "mix_flow1": "mix",
    "master_flow1": "master_finalize",
}


def _delivery_will_run_topic_coverage(ctx: RunContext, from_stage: str | None) -> bool:
    """Whether the next delivery run would execute topic_coverage_audit."""
    if from_stage:
        from_stage = _LEGACY_DELIVERY_STAGE_ALIASES.get(from_stage, from_stage)
        if from_stage != "topic_coverage_audit":
            if from_stage not in _DELIVERY_ORDER:
                return False
            return _DELIVERY_ORDER.index(from_stage) <= _DELIVERY_ORDER.index("topic_coverage_audit")
    return not ctx.is_done("topic_coverage_audit") or from_stage == "topic_coverage_audit"


def require_profile_verified_for_delivery(ctx: RunContext) -> None:
    return


def check_analysis_artifacts_gate_pending(ctx: RunContext) -> bool:
    _ = ctx
    return False


def require_analysis_artifacts_complete(ctx: RunContext) -> None:
    return


def require_delivery_gates(ctx: RunContext, *, from_stage: str | None = None) -> None:
    _ = (ctx, from_stage)
    return


# Backward-compat aliases
require_profile_verified_for_flow1_extended = require_profile_verified_for_delivery
require_flow1_extended_gates = require_delivery_gates


def get_selected_flow(ctx: RunContext) -> str:
    return "podcast"


def set_selected_flow(ctx: RunContext, flow: str) -> None:
    _ = (ctx, flow)


def require_selected_flow_flow1(ctx: RunContext) -> None:
    return


def narrative_qc_strict_enabled() -> bool:
    nqc = merged_config().get("narrative_qc") or {}
    return bool(nqc.get("strict"))


def check_narrative_qc(
    ctx: RunContext,
    *,
    stage: str,
    require_selection: bool = False,
) -> None:
    """Warn or block on narrative QC before ranking or EDL."""
    errors = validate_flow1_narrative(ctx, require_selection=require_selection)
    strict = narrative_qc_strict_enabled()
    if not errors:
        ctx.log(
            "Narrative QC passed",
            level="success",
            stage=stage,
            detail="narrative_qc_pass",
        )
        record_qc_summary(
            ctx,
            "narrative_qc",
            {"passed": True, "errors": [], "strict": strict, "at_stage": stage},
        )
        return

    summary = "; ".join(errors[:6])
    if len(errors) > 6:
        summary += f" (+{len(errors) - 6} more)"
    ctx.log(
        f"Narrative QC failed ({len(errors)} issue(s)): {summary}",
        level="error" if strict else "warn",
        stage=stage,
        detail="narrative_qc_fail",
    )
    record_qc_summary(
        ctx,
        "narrative_qc",
        {"passed": False, "errors": errors[:12], "strict": strict, "at_stage": stage},
    )
    if strict:
        raise SystemExit(
            f"narrative_qc strict: {len(errors)} issue(s) before {stage}. "
            f"Fix coverage_audit / selection or set narrative_qc.strict=false. "
            f"Run: python tools/validate_narrative.py --run-id {ctx.run_id}"
        )


def edl_qc_strict_enabled() -> bool:
    eqc = merged_config().get("edl_qc") or {}
    return bool(eqc.get("strict"))


def edl_narrative_qc_strict_enabled() -> bool:
    enqc = merged_config().get("edl_narrative_qc") or {}
    return bool(enqc.get("strict"))


def check_edl_qc(
    ctx: RunContext,
    *,
    stage: str,
    edl: dict | None = None,
    strict: bool | None = None,
) -> None:
    """Warn or block on EDL timeline QC before mix or after EDL build."""
    errors = validate_flow1_edl(ctx, edl)
    use_strict = edl_qc_strict_enabled() if strict is None else strict
    if not errors:
        ctx.log(
            "EDL QC passed",
            level="success",
            stage=stage,
            detail="edl_qc_pass",
        )
        record_qc_summary(
            ctx,
            "edl_qc",
            {"passed": True, "errors": [], "strict": use_strict, "at_stage": stage},
        )
        return

    summary = "; ".join(errors[:6])
    if len(errors) > 6:
        summary += f" (+{len(errors) - 6} more)"
    ctx.log(
        f"EDL QC failed ({len(errors)} issue(s)): {summary}",
        level="error" if use_strict else "warn",
        stage=stage,
        detail="edl_qc_fail",
    )
    record_qc_summary(
        ctx,
        "edl_qc",
        {"passed": False, "errors": errors[:12], "strict": use_strict, "at_stage": stage},
    )
    if use_strict:
        raise SystemExit(
            f"edl_qc strict: {len(errors)} issue(s) before {stage}. "
            f"Fix master/edl.json or re-run edl. "
            f"Run: python tools/validate_edl.py --run-id {ctx.run_id}"
        )


def check_edl_narrative_qc(
    ctx: RunContext,
    *,
    stage: str,
    edl: dict | None = None,
    strict: bool | None = None,
) -> None:
    """Warn or block when final EDL violates narrative intent."""
    errors = validate_flow1_edl_narrative(ctx, edl)
    if errors:
        try:
            from interview_mux.artifact_repairs import repair_edl_narrative_selection

            notes = repair_edl_narrative_selection(ctx)
            if notes:
                # Keep validating the in-memory EDL — it is not on disk yet at this gate.
                errors = validate_flow1_edl_narrative(ctx, edl)
                ctx.log(
                    f"EDL narrative repair applied ({len(notes)} action(s))",
                    level="info",
                    stage=stage,
                    detail=notes[:8],
                )
        except Exception as exc:
            ctx.log(f"EDL narrative repair skipped: {exc}", level="warning", stage=stage)
    use_strict = edl_narrative_qc_strict_enabled() if strict is None else strict
    if not errors:
        ctx.log(
            "EDL narrative QC passed",
            level="success",
            stage=stage,
            detail="edl_narrative_qc_pass",
        )
        record_qc_summary(
            ctx,
            "edl_narrative_qc",
            {"passed": True, "errors": [], "strict": use_strict, "at_stage": stage},
        )
        return

    summary = "; ".join(errors[:6])
    if len(errors) > 6:
        summary += f" (+{len(errors) - 6} more)"
    ctx.log(
        f"EDL narrative QC failed ({len(errors)} issue(s)): {summary}",
        level="error" if use_strict else "warn",
        stage=stage,
        detail="edl_narrative_qc_fail",
    )
    record_qc_summary(
        ctx,
        "edl_narrative_qc",
        {"passed": False, "errors": errors[:12], "strict": use_strict, "at_stage": stage},
    )
    if use_strict:
        raise SystemExit(
            f"edl_narrative_qc strict: {len(errors)} issue(s) before {stage}. "
            "Fix final ordering, transitions, coverage, gaps, or audit findings. "
            f"Run: python tools/validate_narrative.py --run-id {ctx.run_id} --include-edl"
        )


def check_show_notes_qc(ctx: RunContext, *, stage: str = "show_notes") -> None:
    """Flow 3 show notes removed in v2."""
    _ = (ctx, stage)
    return


def check_g_publish_pending(ctx: RunContext) -> bool:
    """True when operator has not yet Prepared/Skip'd local RSS packaging."""
    podcast = merged_config().get("podcast") or {}
    if not bool(podcast.get("enabled", True)):
        return False
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        return False
    if meta.get("g_publish_skipped") or meta.get("g_publish_cleared"):
        return False
    if meta.get("g_publish_pending"):
        return True
    # Pending once master exists and local package not finalized
    if ctx.artifact_exists("master/master.wav") and not ctx.is_done("podcast_publish"):
        return True
    return False


def require_g_publish_clear(ctx: RunContext, *, stage: str) -> None:
    """Allow gated packaging only after operator chose Prepare (not Skip)."""
    podcast = merged_config().get("podcast") or {}
    if not bool(podcast.get("enabled", True)):
        return
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if isinstance(meta, dict) and meta.get("g_publish_skipped"):
        _gate_exit(
            ctx,
            "G-Publish was skipped — RSS package not requested for this run.",
            stage=stage,
        )
    if isinstance(meta, dict) and meta.get("g_publish_cleared"):
        return
    if check_g_publish_pending(ctx):
        _gate_exit(
            ctx,
            "G-Publish pending — prepare a local episode package "
            "(POST …/g-publish/continue) or skip (POST …/g-publish/skip). "
            "S3 upload is a separate this-run sync (POST …/g-publish/sync).",
            stage=stage,
        )


def clear_g_publish(ctx: RunContext, *, skipped: bool = False) -> None:
    def patch(meta: dict) -> None:
        meta["g_publish_pending"] = False
        if skipped:
            meta["g_publish_skipped"] = True
            meta.pop("g_publish_cleared", None)
        else:
            meta["g_publish_cleared"] = True
            meta.pop("g_publish_skipped", None)

    ctx.mutate_run_meta(patch)


def mark_g_publish_pending(ctx: RunContext) -> None:
    def patch(meta: dict) -> None:
        if meta.get("g_publish_cleared") or meta.get("g_publish_skipped"):
            return
        meta["g_publish_pending"] = True

    ctx.mutate_run_meta(patch)
