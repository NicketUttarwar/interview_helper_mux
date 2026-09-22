"""Promote best optimizer candidate into live run artifacts (+ optional remaster)."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.timeline_optimizer.state import (
    load_best,
    load_optimizer_state,
    save_optimizer_state,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _guard_candidate_spoken_copy(
    ctx: RunContext, candidate: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Validate optimizer-authored listener copy before any live artifact write."""
    from interview_mux.opening_orientation import is_episode_orientation
    from interview_mux.spoken_copy_guard import guard_spoken_copy

    out = copy.deepcopy(candidate)
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        by_id = {
            str(row.get("segment_id")): row
            for row in ((manifest or {}).get("segments") or [])
            if isinstance(row, dict) and row.get("segment_id")
        }

    transitions = out.get("transitions")
    seen_texts: list[str] = []
    if isinstance(transitions, dict):
        for row in transitions.get("transitions") or []:
            if not isinstance(row, dict) or not str(row.get("text") or "").strip():
                continue
            a = str(row.get("after_segment_id") or "")
            b = str(row.get("before_segment_id") or "")
            evidence = {
                "before_excerpt": (by_id.get(a) or {}).get("text"),
                "after_excerpt": (by_id.get(b) or {}).get("text"),
                "before_topic": (by_id.get(a) or {}).get("topic"),
                "after_topic": (by_id.get(b) or {}).get("topic"),
                "source_gap_ms": row.get("source_gap_ms"),
                "strict_grounding": True,
            }
            decision = guard_spoken_copy(
                str(row.get("text") or ""),
                evidence=evidence,
                required=True,
                purpose=f"optimizer_promote_transition[{a}->{b}]",
                seen_texts=seen_texts,
            )
            if decision["action"] == "block":
                errors.append(f"transition {a}->{b}: {','.join(decision['violations'])}")
            else:
                row["text"] = decision["text"]
                if decision["text"]:
                    seen_texts.append(str(decision["text"]))

    gap = out.get("gap_report")
    if isinstance(gap, dict):
        kept: list[dict[str, Any]] = []
        for row in gap.get("interviewer_lines") or []:
            if not isinstance(row, dict):
                continue
            target = str(row.get("targets_segment_id") or "")
            evidence = {
                "target_excerpt": (by_id.get(target) or {}).get("text"),
                "after_topic": (by_id.get(target) or {}).get("topic"),
            }
            required = is_episode_orientation(row)
            decision = guard_spoken_copy(
                str(row.get("text") or ""),
                evidence=evidence,
                required=required,
                purpose=f"optimizer_promote_gap[{row.get('line_id') or target}]",
                seen_texts=seen_texts,
            )
            if decision["action"] == "block":
                errors.append(
                    f"gap {row.get('line_id') or target}: "
                    + ",".join(decision["violations"])
                )
                continue
            if decision["action"] == "omit":
                continue
            row["text"] = decision["text"]
            if decision["text"]:
                seen_texts.append(str(decision["text"]))
            kept.append(row)
        gap["interviewer_lines"] = kept
    return out, errors


def remaster_sync(ctx: RunContext, *, until_mix: bool = True) -> None:
    """Synchronously rebuild EDL→mix after promoting a new order (no JobRunner)."""
    try:
        from interview_mux.timeline_reopen_meta_gate import (
            INTENT_OPTIMIZER,
            decide_timeline_reopen,
        )

        gate = decide_timeline_reopen(
            ctx,
            intent=INTENT_OPTIMIZER,
            detail={"until_mix": until_mix},
        )
        if not gate.get("allow"):
            ctx.log(
                f"optimizer remaster_sync refused: {gate.get('refuse_reason')}",
                level="info",
                stage="timeline_optimizer",
            )
            return
    except Exception as exc:
        ctx.log(
            f"optimizer remaster_sync fail-closed refuse: {exc}",
            level="info",
            stage="timeline_optimizer",
        )
        return
    from interview_mux.stages import assembly
    from interview_mux.v2.config import DELIVERY_ORDER

    for sid in DELIVERY_ORDER:
        if sid not in {
            "edl",
            "assembly_preview",
            "listen_delight_audit",
            "sfx_prompt_craft",
            "mmaudio_sfx",
            "mix",
            "junction_snip_qa",
            "vo_synthesize",
        }:
            continue
        if sid == "mix" and not until_mix:
            break
        if sid == "junction_snip_qa" and not until_mix:
            break
        marker = ctx.final_path(".stage_done", sid)
        if marker.is_file():
            try:
                marker.unlink()
            except OSError:
                pass

    # Rebuild EDL + mix; reuse existing MMAudio assets when present
    try:
        from interview_mux.transition_vo import commit_current_transition_wavs

        commit_current_transition_wavs(ctx)
    except Exception as exc:
        ctx.log(f"optimizer remaster VO resync: {exc}", level="warning", stage="timeline_optimizer")
    assembly.run_edl(ctx)
    assembly.run_mix(ctx)


def take_best_candidate(
    ctx: RunContext,
    *,
    remaster: bool = False,
    runner: Any | None = None,
    sync_remaster: bool = False,
) -> dict[str, Any]:
    """Write best candidate into selection/transitions/gap/SDP; optionally remaster."""
    from interview_mux.timeline_optimizer.config import optimizer_live_mutate_blocked

    if optimizer_live_mutate_blocked(ctx):
        return {"ok": False, "error": "optimizer_skipped"}
    best = load_best(ctx)
    if not best:
        return {"ok": False, "error": "no_best_candidate"}

    ordered = [str(s) for s in (best.get("ordered_segment_ids") or []) if s]
    if not ordered:
        return {"ok": False, "error": "empty_order"}
    best, spoken_errors = _guard_candidate_spoken_copy(ctx, best)
    if spoken_errors:
        return {
            "ok": False,
            "error": "unsafe_spoken_copy",
            "details": spoken_errors[:8],
        }

    # Selection
    sel = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {"version": 1}
    )
    if not isinstance(sel, dict):
        sel = {"version": 1}
    prev_order = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    order_changed = prev_order != ordered
    sel = dict(sel)
    sel["ordered_segment_ids"] = ordered
    if best.get("excluded_segment_ids"):
        sel["excluded_segment_ids"] = list(best.get("excluded_segment_ids") or [])
    sel["order_authority"] = "timeline_optimizer"
    sel["optimizer_candidate_id"] = best.get("candidate_id")
    sel["optimizer_score"] = best.get("score")
    from interview_mux.air_order import commit as air_commit
    from interview_mux.air_order import rollback as air_rollback
    from interview_mux.air_order import snapshot as air_snapshot
    from interview_mux.artifact_writes import write_validated_artifact
    from interview_mux.order_hash import bump_order_lock

    air_snapshot(ctx)
    setattr(ctx, "_air_order_hold_snapshot", True)
    remaster_started = False
    try:
        sel = bump_order_lock(sel, source="timeline_optimizer")
        ctx.write_json("master/optimizer_pending_selection.json", sel)
        write_validated_artifact(
            ctx,
            "master/selection.json",
            sel,
            merge_from_disk=False,
            stage_key="timeline_optimizer",
        )
        try:
            from interview_mux.air_order_integrity import audit_and_report

            audit_and_report(ctx, stage="timeline_optimizer", repair=False)
        except Exception:
            pass

        from interview_mux.seat_authority import persist_frozen_seat_doc

        if isinstance(best.get("transitions"), dict):
            persist_frozen_seat_doc(
                ctx,
                "master/transitions.json",
                best["transitions"],
                reason="optimizer_promote_transitions",
            )
        if isinstance(best.get("gap_report"), dict):
            persist_frozen_seat_doc(
                ctx,
                "understanding/gap_report.json",
                best["gap_report"],
                reason="optimizer_promote_gap_report",
            )
        if isinstance(best.get("sound_design_plan"), dict):
            persist_frozen_seat_doc(
                ctx,
                "understanding/sound_design_plan.json",
                best["sound_design_plan"],
                reason="optimizer_promote_sdp",
            )
        if order_changed:
            from interview_mux.synthetic_framing import run_synthetic_framing_plan

            run_synthetic_framing_plan(ctx, force=True)

        # Refresh bridges + health for promoted order
        try:
            from interview_mux.bridge_voice_policy import annotate_reorder_bridges
            from interview_mux.reorder_bridges import build_reorder_bridges
            from interview_mux.story_health import evaluate_story_health

            by_id = {}
            if ctx.artifact_exists("segments/manifest.json"):
                man = ctx.read_json("segments/manifest.json")
                by_id = {
                    str(s["segment_id"]): s
                    for s in ((man or {}).get("segments") or [])
                    if isinstance(s, dict) and s.get("segment_id")
                }
            bridges = annotate_reorder_bridges(build_reorder_bridges(ordered, by_id))
            ctx.write_json("understanding/reorder_bridges.json", bridges)
            plan = (
                ctx.read_json("master/narrative_plan.json")
                if ctx.artifact_exists("master/narrative_plan.json")
                else None
            )
            health = evaluate_story_health(
                ordered=ordered,
                narrative_plan=plan if isinstance(plan, dict) else None,
                reorder_bridges=bridges,
                gap_report=best.get("gap_report")
                if isinstance(best.get("gap_report"), dict)
                else None,
                transitions=best.get("transitions")
                if isinstance(best.get("transitions"), dict)
                else None,
            )
            ctx.write_json("master/story_health.json", health)
        except Exception as exc:
            ctx.log(
                f"optimizer promote health refresh: {exc}",
                level="warning",
                stage="timeline_optimizer",
            )

        state = load_optimizer_state(ctx)
        promotions = list(state.get("promotions") or [])
        promotions.append(
            {
                "at": _now(),
                "candidate_id": best.get("candidate_id"),
                "score": best.get("score"),
                "remaster": bool(remaster or sync_remaster),
            }
        )
        state["promotions"] = promotions[-20:]
        state["operator_took_best"] = True
        if order_changed:
            state["promoted_needs_remaster"] = True
        save_optimizer_state(ctx, state)

        def _meta(m: dict) -> None:
            m["timeline_optimizer_promoted"] = {
                "candidate_id": best.get("candidate_id"),
                "score": best.get("score"),
                "at": _now(),
                "needs_remaster": order_changed,
            }

        ctx.mutate_run_meta(_meta)

        if (remaster or sync_remaster) and order_changed:
            if runner is not None and not sync_remaster:
                try:
                    runner.invalidate_from(ctx.run_id, "edl")
                    runner.start(
                        ctx.run_id,
                        mode="delivery",
                        from_stage="edl",
                        until_stage="mix",
                        invalidate=True,
                    )
                    remaster_started = True
                except Exception as exc:
                    air_rollback(ctx)
                    setattr(ctx, "_air_order_rolled_back", True)
                    ctx.log(
                        f"optimizer remaster start failed: {exc}",
                        level="warning",
                        stage="timeline_optimizer",
                    )
                    raise RuntimeError(
                        "optimizer promoted order but could not start remaster"
                    ) from exc
            else:
                try:

                    def _flag(m: dict) -> None:
                        m["timeline_optimizer_remastering"] = True

                    ctx.mutate_run_meta(_flag)
                    remaster_sync(ctx, until_mix=True)
                    remaster_started = True
                    try:
                        from interview_mux.junction_snip_qa import (
                            _set_g_listen_pending_after_remaster,
                            run_junction_snip_qa,
                        )

                        run_junction_snip_qa(ctx)
                        _set_g_listen_pending_after_remaster(ctx)
                    except Exception:
                        try:
                            from interview_mux.junction_snip_qa import (
                                _set_g_listen_pending_after_remaster,
                            )

                            _set_g_listen_pending_after_remaster(ctx)
                        except Exception:
                            pass
                except Exception as exc:
                    air_rollback(ctx)
                    setattr(ctx, "_air_order_rolled_back", True)
                    ctx.log(
                        f"optimizer sync remaster failed: {exc}",
                        level="warning",
                        stage="timeline_optimizer",
                    )
                    raise RuntimeError(
                        "optimizer promoted order but synchronous remaster failed"
                    ) from exc
                finally:

                    def _clear(m: dict) -> None:
                        m["timeline_optimizer_remastering"] = False

                    try:
                        ctx.mutate_run_meta(_clear)
                    except Exception:
                        pass
        sealed = air_commit(ctx, source="timeline_optimizer", snapshot_first=False)
        state = load_optimizer_state(ctx)
        if remaster_started or not order_changed:
            state["promoted_needs_remaster"] = False
        save_optimizer_state(ctx, state)
        live_ids = [str(s) for s in (sealed.get("ordered_segment_ids") or []) if s]
        if live_ids:
            ordered = live_ids
    except Exception:
        if not getattr(ctx, "_air_order_rolled_back", False):
            try:
                air_rollback(ctx)
            except Exception:
                pass
        raise
    finally:
        setattr(ctx, "_air_order_hold_snapshot", False)
        setattr(ctx, "_air_order_rolled_back", False)

    ctx.log(
        f"timeline_optimizer take-best: {best.get('candidate_id')} "
        f"score={best.get('score')} remaster={remaster_started}",
        level="success",
        stage="timeline_optimizer",
    )
    return {
        "ok": True,
        "candidate_id": best.get("candidate_id"),
        "score": best.get("score"),
        "ordered_segment_ids": ordered,
        "remaster_started": remaster_started,
        "order_changed": order_changed,
    }
