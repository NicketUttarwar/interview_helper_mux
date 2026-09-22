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
    if line.get("skipped_optional") or line.get("air_script_omit"):
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


def maybe_auto_clear_g_listen_for_full_auto(
    ctx: RunContext, *, stage: str, reason: str = "full_auto"
) -> bool:
    """Full-auto only: clear pending G-Listen so remaster/finalize do not stall.

    Shared by mix (after successful mix / remaster listen_critic arm) and
    ``require_g_listen_clear`` (master_finalize). Partial and manual keep
    warn/block posture until operator continue/skip.
    """
    from interview_mux.automation_run import is_full_auto_run

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not is_full_auto_run(meta if isinstance(meta, dict) else None):
        return False
    if not check_g_listen_pending(ctx):
        return False
    clear_g_listen(ctx, skipped=False)
    ctx.log(
        f"G-Listen auto-cleared ({reason})",
        level="info",
        stage=stage,
        action_id="gate.g_listen.auto_clear",
        detail={"event": "g_listen_auto_clear", "reason": reason},
    )
    return True


def require_g_listen_clear(ctx: RunContext, *, stage: str) -> None:
    """Block master_finalize when g_listen_mode=block|block_mix (Partial/manual).

    Full-auto auto-clears pending before the block check (product path; not
    driver-only).
    """
    maybe_auto_clear_g_listen_for_full_auto(
        ctx, stage=stage, reason="full_auto_before_finalize"
    )
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
    """True when STT review queue exists but operator has not signed off.

    Staged-but-unflushed ``review_queue.json`` still means G0 is open — treating
    that as clear made reconcile claim \"Transcript review complete\" while the
    queue lived only under ``.pending_writes`` (exec_11871).
    """
    if ctx.is_done("transcript_review"):
        return False
    if ctx.artifact_exists("transcript/review_queue.json"):
        return True
    try:
        from interview_mux.write_staging import has_pending_writes, staging_root

        if has_pending_writes(ctx, "transcript_review_build"):
            staged = (
                staging_root(ctx, "transcript_review_build")
                / "transcript"
                / "review_queue.json"
            )
            if staged.is_file():
                return True
    except Exception:
        pass
    return False


def g0_blocks_analysis(ctx: RunContext) -> bool:
    """True when G0 blocks analysis stages (alias for transcript review pending)."""
    return check_transcript_review_pending(ctx)


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
    """True when the operator skipped optional G1 VO pickup for this run.

    Trust run_meta only — ambient ``skipped_optional`` on air-script preface
    lines must not cascade-wipe every nugget layup (forensics exec_11130).
    """
    if ctx.artifact_exists("run_meta.json"):
        meta = ctx.read_json("run_meta.json")
        if isinstance(meta, dict) and meta.get("g1_vo_skipped_optional"):
            return True
    return False


def _gap_line_has_vo_file(ctx: RunContext, line: dict) -> bool:
    from interview_mux.stages.assembly import resolve_vo_pickup_path

    return resolve_vo_pickup_path(ctx, line) is not None


def vo_gap_line_effectively_optional(ctx: RunContext, line: dict) -> bool:
    """True when a gap VO line should not block downstream narrative QC."""
    if line.get("skipped_optional"):
        return True
    try:
        from interview_mux.omit_ledger import OMIT_LEDGER_REL, effective_air_contract

        ledger = (
            ctx.read_json(OMIT_LEDGER_REL)
            if ctx.artifact_exists(OMIT_LEDGER_REL)
            else None
        )
        contract = effective_air_contract(
            ledger,
            line_id=str(line.get("line_id") or "") or None,
            target_segment_id=str(line.get("targets_segment_id") or "") or None,
        )
        if contract.get("status") in ("omitted", "deferred", "suppressed"):
            return True
    except Exception:
        pass
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


def _g1_vo_cache_fingerprint(ctx: RunContext) -> tuple[float, ...]:
    """Mtimes that affect check_g1_vo — invalidate when gap/plan/VO pickup change."""
    rels = (
        "understanding/gap_report.json",
        "mastering/mastering_plan.json",
    )
    stamps: list[float] = []
    for rel in rels:
        try:
            p = ctx.final_path(*rel.split("/"))
            stamps.append(p.stat().st_mtime if p.is_file() else 0.0)
        except OSError:
            stamps.append(0.0)
    try:
        vo_dir = ctx.final_path("vo_pickup")
        if vo_dir.is_dir():
            stamps.append(vo_dir.stat().st_mtime)
            stamps.append(
                max((p.stat().st_mtime for p in vo_dir.rglob("*") if p.is_file()), default=0.0)
            )
        else:
            stamps.extend([0.0, 0.0])
    except OSError:
        stamps.extend([0.0, 0.0])
    return tuple(stamps)


_G1_VO_CACHE: dict[str, tuple[float, tuple[float, ...], list[str]]] = {}
_G1_VO_CACHE_TTL_SEC = 20.0


def check_g1_vo(ctx: RunContext) -> list[str]:
    """Return missing line_ids — presence means resolve_vo_pickup_path succeeds."""
    import time

    now = time.monotonic()
    fp = _g1_vo_cache_fingerprint(ctx)
    hit = _G1_VO_CACHE.get(ctx.run_id)
    if hit and hit[1] == fp and (now - hit[0]) < _G1_VO_CACHE_TTL_SEC:
        return list(hit[2])

    missing = _check_g1_vo_uncached(ctx)
    _G1_VO_CACHE[ctx.run_id] = (now, fp, list(missing))
    return missing


def _check_g1_vo_uncached(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    report = ctx.read_json("understanding/gap_report.json")
    omitted: set[str] = set()
    try:
        from interview_mux.air_script import omitted_vo_line_ids
        from interview_mux.mastering_plan_loader import load_plan_raw

        if ctx.artifact_exists("mastering/mastering_plan.json"):
            omitted = omitted_vo_line_ids(load_plan_raw(ctx))
    except Exception:
        omitted = set()
    missing: list[str] = []
    by_line: dict[str, list[dict]] = {}
    for line in report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or not _line_requires_vo(line):
            continue
        lid = str(line.get("line_id") or "").strip()
        if not lid or lid in omitted:
            continue
        by_line.setdefault(lid, []).append(line)
    from interview_mux.stages.assembly import resolve_vo_pickup_path

    for lid, rows in by_line.items():
        if any(resolve_vo_pickup_path(ctx, row) is not None for row in rows):
            continue
        seg = rows[0].get("targets_segment_id", "")
        missing.append(lid or str(seg))
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
    "master_transcript_build",
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
    """Warn or block on narrative QC before ranking or EDL.

    FMR-B2 / X-3: unattended (Full-auto + Partial) softens a strict QC fail to
    advisory continue. Manual keeps ``narrative_qc.strict``.
    """
    errors = validate_flow1_narrative(ctx, require_selection=require_selection)
    strict = narrative_qc_strict_enabled()
    effective_strict = strict
    unattended_softened = False
    if strict:
        try:
            from interview_mux.operator_gates import is_unattended_run

            meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
            if is_unattended_run(meta if isinstance(meta, dict) else None):
                effective_strict = False
                unattended_softened = True
        except Exception:
            pass
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
            {
                "passed": True,
                "errors": [],
                "strict": strict,
                "effective_strict": effective_strict,
                "at_stage": stage,
            },
        )
        return

    summary = "; ".join(errors[:6])
    if len(errors) > 6:
        summary += f" (+{len(errors) - 6} more)"
    ctx.log(
        f"Narrative QC failed ({len(errors)} issue(s)): {summary}",
        level="error" if effective_strict else "warn",
        stage=stage,
        detail=(
            "narrative_qc_fail_unattended_soft"
            if unattended_softened
            else "narrative_qc_fail"
        ),
    )
    record_qc_summary(
        ctx,
        "narrative_qc",
        {
            "passed": False,
            "errors": errors[:12],
            "strict": strict,
            "effective_strict": effective_strict,
            "full_auto_softened": unattended_softened,
            "unattended_softened": unattended_softened,
            "at_stage": stage,
        },
    )
    if effective_strict:
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
    gap_report: dict | None = None,
) -> None:
    """Warn or block on EDL timeline QC before mix or after EDL build."""
    errors = validate_flow1_edl(ctx, edl, gap_report=gap_report)
    use_strict = edl_qc_strict_enabled() if strict is None else strict
    if any("Overlapping source range" in e for e in errors):
        from interview_mux.edl_overlap_repair import repair_overlapping_source_ranges

        result = repair_overlapping_source_ranges(ctx, edl)
        if result.get("repaired"):
            errors = validate_flow1_edl(
                ctx, result.get("edl") if edl is None else edl, gap_report=gap_report
            )
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
        head = errors[0] if errors else ""
        raise SystemExit(
            f"edl_qc strict: {len(errors)} issue(s) before {stage}. "
            f"{head} Fix master/edl.json or re-run edl. "
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
    if edl is None and ctx.artifact_exists("master/edl.json"):
        loaded = ctx.read_json("master/edl.json")
        edl = loaded if isinstance(loaded, dict) else None
    if isinstance(edl, dict):
        try:
            from interview_mux.speaker_delivery_plan import apply_episode_vo_identity_to_edl

            apply_episode_vo_identity_to_edl(ctx, edl)
        except Exception:
            pass
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
    # PPUB-B2: Full-auto local-done + honest remote refuse must not hang journey.
    if meta.get("g_publish_remote_refused") and ctx.is_done("podcast_publish"):
        try:
            from interview_mux.automation_run import is_full_auto_run

            if is_full_auto_run(meta):
                return False
        except Exception:
            pass
    if meta.get("g_publish_pending"):
        return True
    # Pending once a committed master exists and local package not finalized.
    from interview_mux.delivery_invariants import committed_master_wav

    if committed_master_wav(ctx) and not ctx.is_done("podcast_publish"):
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
    try:
        from interview_mux.homunculus.gates import try_set_gate_decision

        try_set_gate_decision(ctx, "publish_package", "skip" if skipped else "complete")
    except Exception:
        pass


def mark_g_publish_pending(ctx: RunContext) -> None:
    def patch(meta: dict) -> None:
        if meta.get("g_publish_cleared") or meta.get("g_publish_skipped"):
            return
        meta["g_publish_pending"] = True

    ctx.mutate_run_meta(patch)
