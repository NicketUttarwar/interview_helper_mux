"""Run helpers: is this execution a homunculus brain, and dispatch stages through rails."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from interview_mux.homunculus.admit import admit
from interview_mux.homunculus.budget import LimitExhausted, check_audio_serialize, check_dispatch
from interview_mux.homunculus.issues import emit_issue, has_analysis
from interview_mux.homunculus.ledger import append_ledger
from interview_mux.homunculus.version import (
    brain_has_dispatch_ledger,
    brain_has_homunculus_features,
    is_homunculus_brain,
    llm_owns_control_flow,
)
from interview_mux.run_context import RunContext

_INFLIGHT: dict[str, set[str]] = {}


def homunculus_version(ctx: RunContext) -> str:
    if not ctx.artifact_exists("run_meta.json"):
        return "0.0.0"
    meta = ctx.read_json("run_meta.json") or {}
    return str(meta.get("homunculus_version") or "0.0.0")


def is_homunculus_run(ctx: RunContext) -> bool:
    """Brain identity only: is this run a ``kind="homunculus"`` brain?

    Kept as an alias for the two questions it used to conflate. Ask
    ``has_dispatch_ledger`` for rails and ``conductor_owns_control_flow`` for
    control flow — a call site that asks "should I write a ledger row?" must not
    accidentally ask "is an LLM picking the next stage?".
    """
    return is_homunculus_brain(homunculus_version(ctx))


def has_dispatch_ledger(ctx: RunContext) -> bool:
    """Rails: dispatch ledger, admit, telemetry, budget bookkeeping, packing.

    True on 0.2.0 — the seed walk keeps every rail.
    """
    return brain_has_dispatch_ledger(homunculus_version(ctx))


def has_homunculus_features(ctx: RunContext) -> bool:
    """Content tier: per-stage brain features, not rails and not control flow.

    CTA copy, perspective prompt blocks, VO line adjudication, framing posture,
    gate auto-resolve, publishability enforcement. True on 0.1.0+ and 0.2.0.
    """
    return brain_has_homunculus_features(homunculus_version(ctx))


def conductor_owns_control_flow(ctx: RunContext) -> bool:
    """True only on the legacy 0.1.0 brain id (not offered on Start).

    Brain 0.2.0 uses a fixed seed walk — this returns False there.
    """
    return llm_owns_control_flow(homunculus_version(ctx))


def _seed_prereq_block(ctx: RunContext, stage: str) -> str | None:
    """Earliest incomplete seed-order stage that must run before ``stage``."""
    from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    if stage not in ANALYSIS_ORDER and stage not in DELIVERY_ORDER:
        return None
    # A committed, non-truncated master is stronger completion evidence than a
    # missing mix marker after an infrastructure/process interruption. Finalize
    # must be allowed to validate/promote it instead of rewinding into mix.
    if stage == "master_finalize":
        try:
            from interview_mux.delivery_invariants import committed_master_integrity_ok

            if committed_master_integrity_ok(ctx):
                return None
        except Exception:
            pass
    # G1 already green: do not force vo_line_adjudicate over fresh WAVs.
    if stage in {"vo_synthesize", "edl_narrative_audit", "edl"}:
        try:
            from interview_mux.delivery_guardrails import seal_adjudicate_stale_when_g1_green

            seal_adjudicate_stale_when_g1_green(ctx)
        except Exception:
            pass
    earliest = _earliest_incomplete_seed_stage(ctx, stage)
    if earliest and earliest != stage:
        # Seams already seed-complete (outputs + no incompleteness): do not
        # block transitions on a hollow/false earliest token.
        if stage == "transitions" and earliest == "air_script_seams":
            try:
                from interview_mux.delivery_guardrails import seed_stage_complete

                if seed_stage_complete(ctx, "air_script_seams"):
                    return None
            except Exception:
                pass
        # After seal, adjudicate may still be earliest if marker missing — recheck.
        if earliest == "vo_line_adjudicate" and stage in {
            "vo_synthesize",
            "edl_narrative_audit",
            "edl",
        }:
            try:
                from interview_mux.delivery_guardrails import (
                    seed_stage_complete,
                    seal_adjudicate_stale_when_g1_green,
                )
                from interview_mux.gates import check_g1_vo

                seal_adjudicate_stale_when_g1_green(ctx)
                if seed_stage_complete(ctx, "vo_line_adjudicate") or not check_g1_vo(ctx):
                    return None
            except Exception:
                pass
        # Junction remaster unlinks .stage_done/mix at the start of remaster_mix_only.
        # Re-dispatch mid-remaster (or after a loud fail) must not seed-block on mix
        # when assembly already exists — junction owns the remaster (exec_11130).
        if stage == "junction_snip_qa" and earliest == "mix":
            try:
                if ctx.artifact_exists("master/assembly.wav"):
                    return None
            except Exception:
                pass
            # exec_11871: mix refuses on live incomplete-cut residuals and pins
            # junction_snip_qa, but seed order put mix first — nobody could recut
            # (predicate x3/3 halt). The junction ladder owns recut/fuse/omit on
            # the EDL and drives its own remaster, so let it run before first mix.
            try:
                from interview_mux.junction_snip_qa import junction_recut_precedes_mix

                if junction_recut_precedes_mix(ctx):
                    ctx.log(
                        "seed order: junction_snip_qa runs before first mix — "
                        "live incomplete-cut residuals need recut/fuse/omit",
                        level="info",
                        stage="junction_snip_qa",
                    )
                    return None
            except Exception:
                pass
        return earliest
    return None


def _call_stage_impl(impl: Callable[..., Any], stage: str) -> None:
    """HC-4: host is impl(stage). 0-arg callables stay for older test fixtures."""
    try:
        sig = inspect.signature(impl)
    except (TypeError, ValueError):
        impl(stage)
        return
    positional = [
        p
        for p in sig.parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if not positional:
        impl()
        return
    impl(stage)


def dispatch_stage(
    ctx: RunContext,
    stage: str,
    impl: Callable[..., Any],
    *,
    source: str = "conductor",
    _recovery_depth: int = 0,
) -> None:
    """Budget + serialize + ledger, then host impl(stage), then admit. 0.1.0 only."""
    from interview_mux.homunculus.agenda import (
        _refuse_delivery_timeline_rewind,
        _refuse_g0_locked_rerun,
        _refuse_music_before_assembly,
        prepare_outputs_present,
        unmark_hollow_prepare_stages,
        unmark_stage_only,
    )

    unmark_hollow_prepare_stages(ctx)
    # HP-4 3A: pin is operator-must-act. Remainder / conductor must not sign G0 off.
    if stage == "transcript_review":
        from interview_mux.gates import check_transcript_review_pending

        if check_transcript_review_pending(ctx):
            raise RuntimeError(
                "g0_pending: transcript_review operator must-act — "
                "driver owns complete_g0 / wait_for_operator_g0"
            )
        return
    try:
        from interview_mux.delivery_recovery import MUSIC_BEFORE_MIX
        from interview_mux.delivery_guardrails import (
            music_skip_allowed,
            prepare_fingerprint_blocks_rerun,
        )

        blocked_prep = prepare_fingerprint_blocks_rerun(ctx, stage)
        if blocked_prep == "g0_locked":
            pass
        elif blocked_prep and ctx.is_done(stage):
            ctx.log(
                f"homunculus skip-run {stage} — {blocked_prep}",
                level="info",
                stage=stage,
            )
            admit(
                ctx,
                identity=stage,
                action="keep",
                payload={"stage": stage, "source": source, "prepare_fingerprint": blocked_prep},
            )
            append_ledger(
                ctx,
                {
                    "kind": "stage",
                    "identity": stage,
                    "status": "done",
                    "source": source,
                    "prepare_fingerprint": blocked_prep,
                },
            )
            return

        if stage in MUSIC_BEFORE_MIX and music_skip_allowed(ctx, stage):
            from interview_mux.delivery_guardrails import music_epoch_complete
            from interview_mux.stage_completion import heal_or_refuse_mark

            if music_epoch_complete(ctx):
                if not ctx.is_done(stage):
                    heal_or_refuse_mark(ctx, stage, force=True)
                if stage == "mmaudio_sfx":
                    from datetime import datetime, timezone

                    from interview_mux.delivery_guardrails import stamp_delivery_epoch

                    stamp_delivery_epoch(
                        ctx, music_complete_at=datetime.now(timezone.utc).isoformat()
                    )
                ctx.log(
                    f"homunculus skip-run {stage} — music epoch complete",
                    level="info",
                    stage=stage,
                )
                admit(ctx, identity=stage, action="keep", payload={"stage": stage, "source": source, "skipped_existing_wavs": True})
                append_ledger(ctx, {"kind": "stage", "identity": stage, "status": "done", "source": source, "skipped_existing_wavs": True})
                return
    except Exception:
        pass
    try:
        _refuse_g0_locked_rerun(ctx, stage, action="run")
        _refuse_delivery_timeline_rewind(ctx, stage, action="run")
    except RuntimeError:
        if prepare_outputs_present(ctx, stage):
            if not ctx.is_done(stage):
                from interview_mux.stage_completion import heal_or_refuse_mark

                heal_or_refuse_mark(ctx, stage, force=True)
        elif ctx.is_done(stage):
            unmark_stage_only(ctx, stage)
        raise
    _refuse_music_before_assembly(ctx, stage, action="run")
    try:
        from interview_mux.delivery_guardrails import refuse_skip_then_consume

        skip_refuse = refuse_skip_then_consume(ctx, stage)
        if skip_refuse:
            raise RuntimeError(
                f"refuse {stage}: {skip_refuse} — compensate producer artifacts "
                "before consume (heal ≠ skip-then-consume)"
            )
    except RuntimeError:
        raise
    except Exception:
        pass
    try:
        from datetime import datetime, timezone

        from interview_mux.delivery_guardrails import (
            EXPENSIVE_STAGES,
            G1_CONSUMERS,
            MIX_EPOCH_RUN_BLOCK,
            mix_epoch_block,
            record_wasted_work,
            stamp_delivery_epoch,
            upstream_stale_blockers,
            vo_synthesize_stability_block,
        )
        from interview_mux.stage_input_checks import StageInputError, collect_stage_input_issues

        if stage in EXPENSIVE_STAGES or stage in G1_CONSUMERS:
            issues = [
                issue
                for issue in collect_stage_input_issues(ctx, stage)
                if issue.kind != "write_approval"
            ]
            if issues:
                record_wasted_work(
                    ctx,
                    event="avoided_expensive_start",
                    stage=stage,
                    detail={"reason": issues[0].message},
                )
                try:
                    from interview_mux.recovery_controller import handle_stage_failure

                    result = handle_stage_failure(
                        ctx,
                        stage,
                        RuntimeError(issues[0].message),
                    )
                    if result.status == "recovered" and result.resume_stage:
                        # RC10: recursive recovery depth ≤2.
                        if int(_recovery_depth or 0) >= 2:
                            raise StageInputError(stage, issues)
                        resume = str(result.resume_stage).strip()
                        if not resume:
                            raise StageInputError(stage, issues)
                        try:
                            return dispatch_stage(
                                ctx,
                                resume,
                                impl,
                                source=source,
                                _recovery_depth=int(_recovery_depth or 0) + 1,
                            )
                        except StageInputError:
                            raise
                        except Exception:
                            # 2A: resume host cannot run — do not execute the consumer.
                            raise StageInputError(stage, issues) from None
                except StageInputError:
                    raise
                except Exception:
                    pass
                raise StageInputError(stage, issues)

        if stage == "vo_synthesize":
            vo_b = vo_synthesize_stability_block(ctx)
            if vo_b:
                raise RuntimeError(
                    f"seed order: complete {vo_b} before running vo_synthesize"
                )
        if stage in MIX_EPOCH_RUN_BLOCK:
            mix_b = mix_epoch_block(ctx)
            if mix_b:
                raise RuntimeError(
                    f"cannot run {stage}: delivery epoch {mix_b} (wait for mmaudio_sfx)"
                )
        stale = upstream_stale_blockers(ctx, stage)
        if stale:
            raise RuntimeError(
                f"cannot run {stage}: stale upstream {', '.join(stale[:4])}"
            )
        if stage in {"mmaudio_sfx", "vo_synthesize", "mix"}:
            record_wasted_work(ctx, event="expensive_start", stage=stage)
            now = datetime.now(timezone.utc).isoformat()
            if stage == "mmaudio_sfx":
                stamp_delivery_epoch(ctx, music_started_at=now)
            if stage == "mix":
                stamp_delivery_epoch(ctx, mix_started_at=now)
    except RuntimeError:
        raise
    except Exception:
        pass
    blocked = _seed_prereq_block(ctx, stage)
    if blocked:
        raise RuntimeError(
            f"seed order: complete {blocked} before running {stage}"
        )
    try:
        from interview_mux.web.job_progress import notify_stage_start

        notify_stage_start(
            ctx.run_id,
            stage,
            index=0,
            total=0,
            stages_planned=[],
            ctx=ctx,
        )
    except Exception:
        pass
    identity = stage
    inflight = _INFLIGHT.setdefault(ctx.run_id, set())
    from interview_mux.dispatch_door import (
        evaluate_dispatch,
        note_dispatch_outcome,
        refuse_dispatch,
    )

    # One door for driver-issued dispatches: existing caps + state delta (§5.2/§5.3).
    # A refusal records a defect and returns; D1 forbids stranding the walk here.
    verdict = evaluate_dispatch(ctx, stage, source=source, layer="dispatch")
    if verdict.refused:
        refuse_dispatch(ctx, stage, verdict, source=source)
        return
    note_dispatch_outcome(ctx, stage, outcome="started", source=source)
    check_dispatch(ctx, identity=identity, kind="stage")
    check_audio_serialize(ctx, identity, inflight)
    append_ledger(
        ctx,
        {
            "kind": "stage",
            "identity": identity,
            "source": source,
            "status": "started",
        },
    )
    inflight.add(identity)
    try:
        _call_stage_impl(impl, stage)
        from interview_mux.homunculus.agenda import (
            PROTECTED_CORE_STAGES,
            PROTECTED_DELIVERY_OUTPUTS,
            stage_outputs_present,
            unmark_hollow_delivery_producers,
        )

        unmark_hollow_delivery_producers(ctx, {stage})
        needed = ()
        if stage in PROTECTED_CORE_STAGES:
            needed = PROTECTED_CORE_STAGES.get(stage) or ()
        elif stage in PROTECTED_DELIVERY_OUTPUTS:
            needed = PROTECTED_DELIVERY_OUTPUTS.get(stage) or ()
        if needed and not stage_outputs_present(ctx, stage):
            if stage == "vo_synthesize" and ctx.artifact_exists("mastering/vo_synthesize.json"):
                pass
            elif stage == "mmaudio_sfx":
                raise RuntimeError(
                    "mmaudio_sfx finished without WAV parity in sound_design/mmaudio_qa.json"
                )
            elif stage == "mix":
                final_asm = ctx.final_path("master", "assembly.wav")
                if final_asm.is_file():
                    raise RuntimeError(
                        "mix finished without live EDL seating "
                        "(wav flushed, mix not seated)"
                    )
                raise RuntimeError(
                    f"{stage} finished without required artifact ({', '.join(needed)})"
                )
            else:
                raise RuntimeError(
                    f"{stage} finished without required artifact ({', '.join(needed)})"
                )
        protected = stage in PROTECTED_CORE_STAGES or stage in PROTECTED_DELIVERY_OUTPUTS
        if protected and needed and not ctx.is_done(stage):
            defer_done = False
            if stage == "vo_synthesize":
                from interview_mux.stage_completion import vo_synthesize_should_defer_done

                defer_done = bool(vo_synthesize_should_defer_done(ctx, stage))
            if not defer_done:
                from interview_mux.stage_completion import heal_or_refuse_mark

                out = heal_or_refuse_mark(ctx, stage, force=True)
                if out.get("refused") or not ctx.is_done(stage):
                    raise RuntimeError(
                        f"{stage} finished without a done marker"
                        + (f" ({out.get('reason')})" if out.get("reason") else "")
                    )
                if stage == "mmaudio_sfx":
                    from datetime import datetime, timezone

                    from interview_mux.delivery_guardrails import stamp_delivery_epoch

                    stamp_delivery_epoch(
                        ctx, music_complete_at=datetime.now(timezone.utc).isoformat()
                    )
    except Exception as exc:
        inflight.discard(identity)
        note_dispatch_outcome(ctx, stage, outcome="failed", source=source)
        if stage == "speaker_roles":
            try:
                from interview_mux.recovery_controller import classify_error_class
                from interview_mux.speaker_role_evidence import persist_mixed_diarization_fallback

                if classify_error_class(stage, exc) == "mixed_diarization":
                    artifacts = persist_mixed_diarization_fallback(ctx)
                    if artifacts:
                        ctx.log(
                            "speaker_roles mixed-diarization fallback — dominant roles from talk stats",
                            level="warning",
                            stage=stage,
                        )
                        admit(
                            ctx,
                            identity=identity,
                            action="keep",
                            payload={
                                "stage": stage,
                                "source": source,
                                "mixed_diarization_fallback": True,
                            },
                        )
                        append_ledger(
                            ctx,
                            {
                                "kind": "stage",
                                "identity": identity,
                                "status": "done",
                                "source": source,
                                "mixed_diarization_fallback": True,
                            },
                        )
                        return
            except Exception:
                pass
        issue = emit_issue(
            ctx,
            kind="stage_failure",
            source=source,
            stage_id=stage,
            implicated=[stage],
            evidence={"error_class": type(exc).__name__, "message": str(exc)[:400]},
        )
        ev = issue.get("evidence") or {}
        if ev.get("heal_from_stage"):
            append_ledger(
                ctx,
                {
                    "kind": "heal_route",
                    "identity": identity,
                    "family": ev.get("heal_family"),
                    "from_stage": ev.get("heal_from_stage"),
                    "issue_id": issue.get("issue_id"),
                },
            )
        append_ledger(
            ctx,
            {
                "kind": "stage",
                "identity": identity,
                "status": "failed",
                "issue_id": issue.get("issue_id"),
            },
        )
        raise
    except BaseException:
        inflight.discard(identity)
        append_ledger(
            ctx,
            {"kind": "stage", "identity": identity, "status": "failed", "source": source},
        )
        raise
    inflight.discard(identity)
    admit(ctx, identity=identity, action="keep", payload={"stage": stage, "source": source})
    append_ledger(ctx, {"kind": "stage", "identity": identity, "status": "done", "source": source})
    note_dispatch_outcome(ctx, stage, outcome="done", source=source)


def recovery_allowed(
    ctx: RunContext,
    stage: str,
    exc: BaseException | None = None,
    error_class: str | None = None,
) -> bool:
    """0.1.0: classified playbooks run without analyze_issue; novel failures wait.

    Control flow, not rails: the last resort below waits for an ``analyze_issue``
    verdict, and only the conductor loop can produce one. Under 0.2.0 no conductor
    turn is ever spent, so gating this on the rails predicate would defer every
    novel failure to an analysis that can never arrive.
    """
    if not conductor_owns_control_flow(ctx):
        return True
    cls = error_class
    if cls is None and exc is not None:
        from interview_mux.recovery_controller import classify_error_class

        cls = classify_error_class(stage, exc)
    if cls:
        from interview_mux.recovery_controller import has_classified_playbook

        if has_classified_playbook(cls):
            return True
    try:
        from interview_mux.remediation_framework import read_active_remediation_plan
        from interview_mux.execution_contract import read_active_vo_repair_plan

        plan = read_active_remediation_plan(ctx) or read_active_vo_repair_plan(ctx)
        if isinstance(plan, dict):
            from interview_mux.refinement_passes import filter_retired_refine_stages

            raw_allowed = plan.get("allowed_rerun_stages") or plan.get("invalidate_set") or []
            allowed = set(filter_retired_refine_stages(raw_allowed))
            if stage in allowed or str(plan.get("consumer_stage") or "") == stage:
                return True
    except Exception:
        pass
    if cls in {
        "vo_seated_coverage",
        "vo_contract_repair",
        "upstream_stale_rerun",
        "air_script_omit_sync",
        "layup_stale",
        "selection_edl_order_drift",
        "assembly_not_rendered_from_current_edl",
    }:
        return True
    # G0-locked mixed diarization: deterministic dominant-role write, no conductor packet.
    if stage == "speaker_roles":
        return True
    if stage == "listen_delight_audit":
        return True
    if stage == "nugget_layup_compose":
        return True
    if stage == "edl":
        from interview_mux.homunculus.issues import read_issues

        for issue in read_issues(ctx):
            ev = issue.get("evidence") or {}
            msg = str(ev.get("message") or "").lower()
            if issue.get("stage_id") == "edl" and (
                "unknown segment_id" in msg
                or ("edl_qc" in msg and "overlapping source range" not in msg)
            ):
                return True
    from interview_mux.homunculus.issues import read_issues

    for issue in read_issues(ctx):
        if issue.get("stage_id") == stage and has_analysis(ctx, str(issue.get("issue_id"))):
            return True
    return False


def snapshot_status(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.homunculus.admit import read_admitted, read_memory
    from interview_mux.homunculus.budget import snapshot as budget_snapshot
    from interview_mux.homunculus.issues import read_issues
    from interview_mux.homunculus.ledger import last_fact_ids, read_ledger

    packs = []
    pack_dir = ctx.path("mastering/homunculus/volley_packs")
    if pack_dir.is_dir():
        packs = sorted(p.name for p in pack_dir.glob("*.json"))[-8:]
    exhausted = None
    if ctx.artifact_exists("mastering/homunculus/limit_exhausted.json"):
        exhausted = ctx.read_json("mastering/homunculus/limit_exhausted.json")
    from interview_mux.homunculus.gates import category_status

    kb_lessons = 0
    last_implicated: list[Any] = []
    musicgen: dict[str, Any] = {}
    try:
        from interview_mux.homunculus.kb import lessons, read_kb

        rows = lessons(ctx)
        kb_lessons = len(rows)
        if rows:
            last_implicated = list((rows[-1] or {}).get("implicated_groups") or [])
        musicgen = dict(read_kb(ctx).get("musicgen") or {})
    except Exception:
        pass
    return {
        "homunculus_version": homunculus_version(ctx),
        "active": has_dispatch_ledger(ctx),
        "conductor_owns_control_flow": conductor_owns_control_flow(ctx),
        "budget": budget_snapshot(ctx),
        "issues": read_issues(ctx)[-12:],
        "homunculus_plan": (
            ctx.read_json("mastering/homunculus/plan.json")
            if ctx.artifact_exists("mastering/homunculus/plan.json")
            else None
        ),
        "admitted_tail": read_admitted(ctx)[-12:],
        "memory_fact_count": len(read_memory(ctx).get("facts") or []),
        "last_fact_ids": last_fact_ids(ctx),
        "recent_packs": packs,
        "ledger_len": len(read_ledger(ctx)),
        "limit_exhausted": exhausted,
        "gates": category_status(ctx),
        "kb_lessons": kb_lessons,
        "last_implicated": last_implicated,
        "musicgen": musicgen,
    }
