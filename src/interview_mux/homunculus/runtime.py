"""Run helpers: is this execution a homunculus brain, and dispatch stages through rails."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.homunculus.admit import admit
from interview_mux.homunculus.budget import LimitExhausted, check_audio_serialize, check_dispatch
from interview_mux.homunculus.issues import emit_issue, has_analysis
from interview_mux.homunculus.ledger import append_ledger
from interview_mux.homunculus.version import is_homunculus_brain
from interview_mux.run_context import RunContext

_INFLIGHT: dict[str, set[str]] = {}


def homunculus_version(ctx: RunContext) -> str:
    if not ctx.artifact_exists("run_meta.json"):
        return "0.0.0"
    meta = ctx.read_json("run_meta.json") or {}
    return str(meta.get("homunculus_version") or "0.0.0")


def is_homunculus_run(ctx: RunContext) -> bool:
    return is_homunculus_brain(homunculus_version(ctx))


def dispatch_stage(
    ctx: RunContext,
    stage: str,
    impl: Callable[[], None],
    *,
    source: str = "conductor",
) -> None:
    """Budget + serialize + ledger, then host impl, then admit. 0.1.0 only."""
    from interview_mux.homunculus.agenda import (
        _refuse_delivery_timeline_rewind,
        _refuse_g0_locked_rerun,
        prepare_outputs_present,
        unmark_hollow_prepare_stages,
        unmark_stage_only,
    )

    unmark_hollow_prepare_stages(ctx)
    try:
        from interview_mux.delivery_recovery import MUSIC_BEFORE_MIX
        from interview_mux.homunculus.agenda import (
            delivery_sdp_present,
            stage_outputs_present,
        )
        from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

        if (
            stage in MUSIC_BEFORE_MIX
            and delivery_sdp_present(ctx)
            and not missing_sdp_asset_wavs(ctx)
            and stage_outputs_present(ctx, stage)
        ):
            if not ctx.is_done(stage):
                ctx.mark_done(stage, force=True)
            ctx.log(
                f"homunculus skip-run {stage} — SDP theme WAVs already on disk",
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
                ctx.mark_done(stage, force=True)
        elif ctx.is_done(stage):
            unmark_stage_only(ctx, stage)
        raise
    identity = stage
    inflight = _INFLIGHT.setdefault(ctx.run_id, set())
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
        impl()
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
            else:
                raise RuntimeError(
                    f"{stage} finished without required artifact ({', '.join(needed)})"
                )
        protected = stage in PROTECTED_CORE_STAGES or stage in PROTECTED_DELIVERY_OUTPUTS
        if protected and needed and not ctx.is_done(stage):
            defer_done = False
            if stage == "vo_synthesize":
                from interview_mux.transition_vo import current_transition_pairs_missing

                defer_done = bool(current_transition_pairs_missing(ctx))
            if not defer_done:
                ctx.mark_done(stage, force=True)
                if not ctx.is_done(stage):
                    raise RuntimeError(f"{stage} finished without a done marker")
    except Exception as exc:
        inflight.discard(identity)
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


def recovery_allowed(
    ctx: RunContext,
    stage: str,
    exc: BaseException | None = None,
    error_class: str | None = None,
) -> bool:
    """0.1.0: classified playbooks run without analyze_issue; novel failures wait."""
    if not is_homunculus_run(ctx):
        return True
    cls = error_class
    if cls is None and exc is not None:
        from interview_mux.recovery_controller import classify_error_class

        cls = classify_error_class(stage, exc)
    if cls:
        from interview_mux.recovery_controller import has_classified_playbook

        if has_classified_playbook(cls):
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
                "unknown segment_id" in msg or "edl_qc" in msg
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
        "active": is_homunculus_run(ctx),
        "budget": budget_snapshot(ctx),
        "issues": read_issues(ctx)[-12:],
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
