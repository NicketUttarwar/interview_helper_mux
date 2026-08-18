from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.analysis_memory import load_analysis_state, update_completion_from_analysis
from interview_mux.llm_specialists import (
    load_comprehension_risks,
    maybe_run_pre_stage_specialists,
)
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import compact_manifest_for_volley, compact_value_features_summary
from interview_mux.source_topology import attach_adaptation_to_payload, pickup_eligible_speaker_id
from interview_mux.production_profile import prompt_variant
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.stages.analysis_stage import run_analysis_llm_stage, sync_gaps_to_state


def _compact_segments_payload(
    c: RunContext,
    *,
    segment_ids: list[str] | None = None,
) -> dict[str, Any]:
    from interview_mux.transcript_shards import segment_text_max_chars

    manifest = c.read_json("segments/manifest.json") if c.artifact_exists("segments/manifest.json") else {}
    if not isinstance(manifest, dict):
        manifest = {}
    if segment_ids is not None:
        want = {str(x) for x in segment_ids}
        rows = [
            s
            for s in (manifest.get("segments") or [])
            if isinstance(s, dict) and str(s.get("segment_id") or "") in want
        ]
        manifest = {**manifest, "segments": rows}
    return compact_manifest_for_volley(manifest, text_max=segment_text_max_chars())


def _gap_segment_ids(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    man = ctx.read_json("segments/manifest.json")
    if not isinstance(man, dict):
        return []
    return [
        str(s.get("segment_id"))
        for s in (man.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    ]


def _gap_pass_batch_size(cfg: dict[str, Any] | None = None) -> int:
    from interview_mux.transcript_shards import analysis_context_cfg

    ctx_cfg = analysis_context_cfg(cfg)
    # Prefer explicit gap batch size; fall back to classification shard size.
    raw = ctx_cfg.get("proactive_decompose_gap_segments")
    if raw is None:
        raw = ctx_cfg.get("max_segments_in_gap_pass") or ctx_cfg.get("per_segment_shard_max") or 40
    return max(1, int(raw))


def _merge_gap_evaluations(parts: list[dict[str, Any]], required_ids: list[str]) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        for row in part.get("evaluations") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                by_id[str(row["segment_id"])] = row
    ordered = [by_id[sid] for sid in required_ids if sid in by_id]
    # Keep any extras not in required list (defensive).
    for sid, row in by_id.items():
        if sid not in {str(r.get("segment_id")) for r in ordered}:
            ordered.append(row)
    return {"evaluations": ordered}


def ensure_gap_fill_skipped(
    ctx: RunContext,
    *,
    reason: str,
    signals: dict[str, Any] | None = None,
) -> None:
    """Deterministic gap-path skip — valid artifacts, no LLM spend."""
    from interview_mux.artifact_writes import write_validated_artifact
    from interview_mux.gap_fill_eligibility import GAP_FILL_SKIP_REL, persist_gap_fill_mode
    from interview_mux.gap_fill_eligibility import GapFillDecision

    decision = GapFillDecision(eligible=False, reason=reason, signals=dict(signals or {}))
    skip_doc = {
        "status": "skipped",
        "reason": reason,
        "signals": dict(signals or {}),
        "skipped_at": datetime.now(timezone.utc).isoformat(),
        "eligible": False,
    }
    ctx.write_json(GAP_FILL_SKIP_REL, skip_doc, skip_handoff=True)
    persist_gap_fill_mode(ctx, decision, skipped=True)

    segments: list[dict[str, Any]] = []
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        if isinstance(manifest, dict):
            segments = [
                s for s in (manifest.get("segments") or []) if isinstance(s, dict) and s.get("segment_id")
            ]

    evaluations = [
        {
            "segment_id": str(seg.get("segment_id")),
            "self_explanatory": True,
            "gap_type": "ok_with_light_bridge",
            "severity": "low",
            "listener_confusion": "",
        }
        for seg in segments
    ]
    if not evaluations:
        evaluations = [
            {
                "segment_id": "seg_001",
                "self_explanatory": True,
                "gap_type": "ok_with_light_bridge",
                "severity": "low",
                "listener_confusion": "",
            }
        ]

    eval_doc = {
        "evaluations": evaluations,
        "_meta": {"producer": "gap_fill_skip", "producer_stage": "missing_framing"},
    }
    report_doc = {
        "interviewer_lines": [],
        "gaps": [],
        "_meta": {"producer": "gap_fill_skip", "producer_stage": "optimal_questions"},
    }

    write_validated_artifact(
        ctx,
        "understanding/gap_evaluations.json",
        eval_doc,
        merge_from_disk=False,
        stage_key="missing_framing",
    )
    write_validated_artifact(
        ctx,
        "understanding/gap_report.json",
        report_doc,
        merge_from_disk=False,
        stage_key="optimal_questions",
    )
    ctx.path("understanding", "interviewer_script.txt").write_text(
        "# Interviewer script — gap-fill skipped (no pickup lines required)\n",
        encoding="utf-8",
    )

    sync_gaps_to_state(ctx, eval_doc)
    update_completion_from_analysis(ctx)

    for stage_id in ("missing_framing", "gap_framing_compose", "optimal_questions"):
        if not ctx.is_done(stage_id):
            ctx.mark_done(stage_id, force=True)

    ctx.log(
        f"Gap-fill skipped: {reason}",
        level="info",
        stage="missing_framing",
        action_id="gap_fill.skip",
        detail={"signals": dict(signals or {})},
    )


def _missing_framing_payload(
    c: RunContext,
    *,
    segment_ids: list[str] | None = None,
    shard_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "segments": _compact_segments_payload(c, segment_ids=segment_ids),
        "content_brief": c.read_json("understanding/content_brief.json"),
    }
    if c.artifact_exists("understanding/talking_points.json"):
        tp = c.read_json("understanding/talking_points.json")
        if isinstance(tp, dict):
            payload["talking_points"] = {
                "strategy_summary": tp.get("strategy_summary"),
                "through_line": tp.get("through_line"),
                "talking_points": [
                    {
                        "talking_point_id": row.get("talking_point_id"),
                        "title": row.get("title"),
                        "importance": row.get("importance"),
                        "why_it_matters": row.get("why_it_matters"),
                    }
                    for row in (tp.get("talking_points") or [])
                    if isinstance(row, dict)
                ][:40],
            }
    risks = load_comprehension_risks(c, "missing_framing")
    if risks:
        payload["comprehension_risks"] = risks
    vf = compact_value_features_summary(c)
    if vf:
        payload["value_features_summary"] = vf
    from interview_mux.interview_spine.compact import attach_spine_to_payload

    attach_spine_to_payload(c, payload, "missing_framing")
    from interview_mux.coherence import attach_coherence_summary

    attach_coherence_summary(payload, c, "missing_framing")
    payload = attach_adaptation_to_payload(c, payload)
    try:
        from interview_mux.mastering_shape_runtime import provisional_mode_for_volley

        nm = provisional_mode_for_volley(c)
        if nm:
            payload["narrative_mode_priors"] = nm
    except Exception:
        pass
    from interview_mux.gap_vo_prior_context import (
        attach_prior_native_contexts_to_payload,
        attach_vo_partner_context_to_payload,
    )

    payload = attach_prior_native_contexts_to_payload(c, payload)
    # Shard payloads: keep prior contexts only for requested segment ids.
    if segment_ids and isinstance(payload.get("prior_native_contexts"), dict):
        want = {str(s) for s in segment_ids}
        payload["prior_native_contexts"] = {
            k: v
            for k, v in payload["prior_native_contexts"].items()
            if str(k) in want
        }
        highlights = payload.get("prior_native_context_highlights")
        if isinstance(highlights, list):
            payload["prior_native_context_highlights"] = [
                h
                for h in highlights
                if isinstance(h, dict) and str(h.get("before_target") or "") in want
            ][:40]
    payload = attach_vo_partner_context_to_payload(c, payload, segment_ids=segment_ids)
    if shard_meta:
        payload["_gap_eval_shard"] = shard_meta
    return payload


def run_missing_framing(ctx: RunContext) -> None:
    from interview_mux.llm_simple import run_llm_stage_simple

    persist = make_stage_persist("understanding/gap_evaluations.json", "missing_framing")
    prompt_rel = prompt_variant("interviewer-gap/missing-framing.system.txt", ctx)
    required_ids = _gap_segment_ids(ctx)
    batch_size = _gap_pass_batch_size()

    def build_input(c: RunContext) -> dict:
        return _missing_framing_payload(c)

    # Pre-specialists on the full 300+ segment tape blow mini context; skip when sharding.
    if len(required_ids) <= batch_size:
        with logged_step("missing_framing/pre_specialists", ctx=ctx, stage="missing_framing"):
            maybe_run_pre_stage_specialists(ctx, "missing_framing", build_input(ctx))

    with logged_step("missing_framing/llm_stage", ctx=ctx, stage="missing_framing"):
        if len(required_ids) <= batch_size:
            run_analysis_llm_stage(
                ctx,
                "missing_framing",
                prompt_rel,
                build_input,
                persist,
                sync_fn=lambda c, a: sync_gaps_to_state(c, a),
            )
        else:
            batches = [
                required_ids[i : i + batch_size]
                for i in range(0, len(required_ids), batch_size)
            ]
            ctx.log(
                f"missing_framing proactive batch: {len(required_ids)} segments → "
                f"{len(batches)} shard(s) of ≤{batch_size}",
                level="info",
                stage="missing_framing",
                action_id="missing_framing.proactive_batch",
                detail={
                    "required_count": len(required_ids),
                    "batch_size": batch_size,
                    "batches": len(batches),
                },
            )

            def _noop_persist(_c: RunContext, _artifacts: dict) -> None:
                return None

            parts: list[dict[str, Any]] = []
            for bi, batch_ids in enumerate(batches):

                def build_batch(
                    c: RunContext,
                    *,
                    _ids: list[str] = list(batch_ids),
                    _bi: int = bi,
                    _total: int = len(batches),
                ) -> dict:
                    return _missing_framing_payload(
                        c,
                        segment_ids=_ids,
                        shard_meta={
                            "index": _bi + 1,
                            "total": _total,
                            "segment_ids": list(_ids),
                        },
                    )

                ctx.log(
                    f"missing_framing shard {bi + 1}/{len(batches)} "
                    f"({len(batch_ids)} segment ids)",
                    level="action",
                    stage="missing_framing",
                    action_id="missing_framing.shard",
                )
                envelope = run_llm_stage_simple(
                    ctx,
                    "missing_framing",
                    prompt_rel,
                    build_batch,
                    _noop_persist,
                    auto_complete=False,
                )
                arts = envelope.get("artifacts") if isinstance(envelope.get("artifacts"), dict) else {}
                if isinstance(arts, dict) and arts:
                    parts.append(arts)

            merged = _merge_gap_evaluations(parts, required_ids)
            missing = [
                sid
                for sid in required_ids
                if sid
                not in {
                    str(r.get("segment_id"))
                    for r in (merged.get("evaluations") or [])
                    if isinstance(r, dict)
                }
            ]
            # One coverage pass for LLM-sparse shards (common when context is huge).
            if missing:
                ctx.log(
                    f"missing_framing coverage pass for {len(missing)} uncovered segment(s)",
                    level="warning",
                    stage="missing_framing",
                    action_id="missing_framing.coverage_pass",
                )
                cov_batches = [
                    missing[i : i + max(8, min(batch_size, 20))]
                    for i in range(0, len(missing), max(8, min(batch_size, 20)))
                ]
                for ci, cov_ids in enumerate(cov_batches):

                    def build_cov(
                        c: RunContext,
                        *,
                        _ids: list[str] = list(cov_ids),
                        _ci: int = ci,
                        _total: int = len(cov_batches),
                    ) -> dict:
                        return _missing_framing_payload(
                            c,
                            segment_ids=_ids,
                            shard_meta={
                                "index": _ci + 1,
                                "total": _total,
                                "segment_ids": list(_ids),
                                "coverage_pass": True,
                            },
                        )

                    envelope = run_llm_stage_simple(
                        ctx,
                        "missing_framing",
                        prompt_rel,
                        build_cov,
                        _noop_persist,
                        auto_complete=False,
                    )
                    arts = (
                        envelope.get("artifacts")
                        if isinstance(envelope.get("artifacts"), dict)
                        else {}
                    )
                    if isinstance(arts, dict) and arts:
                        parts.append(arts)
                merged = _merge_gap_evaluations(parts, required_ids)
                missing = [
                    sid
                    for sid in required_ids
                    if sid
                    not in {
                        str(r.get("segment_id"))
                        for r in (merged.get("evaluations") or [])
                        if isinstance(r, dict)
                    }
                ]
            if missing:
                # Deterministic fill — LLM sparsely samples even with sharded ids.
                # Prefer progress over infinite re-runs; severity stays low.
                filled = list(merged.get("evaluations") or [])
                for sid in missing:
                    filled.append(
                        {
                            "segment_id": sid,
                            "self_explanatory": True,
                            "gap_type": "ok_with_light_bridge",
                            "severity": "low",
                            "listener_confusion": "",
                            "_meta": {
                                "filled_by": "missing_framing_batch_coverage",
                                "reason": "llm_sparse_shard_output",
                            },
                        }
                    )
                merged = {"evaluations": filled}
                ctx.log(
                    f"missing_framing: filled {len(missing)} uncovered segment(s) with defaults",
                    level="warning",
                    stage="missing_framing",
                    action_id="missing_framing.batch_fill",
                    detail={"filled_count": len(missing), "examples": missing[:8]},
                )
            persist(ctx, merged)
            sync_gaps_to_state(ctx, merged)
            ctx.mark_done("missing_framing")
            ctx.log(
                f"missing_framing batched complete ({len(merged.get('evaluations') or [])} evaluations)",
                level="success",
                stage="missing_framing",
                action_id="missing_framing.proactive_batch_complete",
            )
    _assert_gap_evaluations_complete(ctx)


def _assert_gap_evaluations_complete(ctx: RunContext) -> None:
    """Fail closed when too many selection-relevant gap rows are unscored stubs."""
    from interview_mux.creative_delivery import creative_delivery_required
    from interview_mux.listenability_guards import gap_eval_scored_ratio, listenability_guards_cfg

    if not creative_delivery_required():
        return
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return
    except Exception:
        pass
    # Default unscored LLM stubs before measuring completeness.
    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        try:
            from interview_mux.artifact_repairs import repair_gap_evaluations
            from interview_mux.artifact_writes import write_validated_artifact

            doc = ctx.read_json("understanding/gap_evaluations.json")
            if isinstance(doc, dict):
                repaired, notes = repair_gap_evaluations(ctx, doc)
                if notes:
                    write_validated_artifact(
                        ctx,
                        "understanding/gap_evaluations.json",
                        repaired,
                        merge_from_disk=False,
                        stage_key="missing_framing",
                    )
        except Exception as exc:
            ctx.log(
                f"gap_evaluations repair before completeness assert failed: {exc}",
                level="warning",
                stage="missing_framing",
            )
    ratio = gap_eval_scored_ratio(ctx)
    floor = float(listenability_guards_cfg().get("gap_eval_scored_min_ratio") or 0.95)
    if ratio + 0.001 >= floor:
        return
    raise RuntimeError(
        f"gap_evaluations incomplete: scored_ratio={ratio:.3f} < min={floor:.3f}. "
        "Re-run missing_framing / fill-artifact-gaps until selection segments have severity+gap_type."
    )


def _filter_gap_evaluations_for_ids(
    doc: dict[str, Any] | None, segment_ids: list[str] | None
) -> dict[str, Any]:
    if not isinstance(doc, dict):
        return {"evaluations": []}
    evals = [e for e in (doc.get("evaluations") or []) if isinstance(e, dict)]
    if segment_ids is None:
        return {"evaluations": evals, **{k: v for k, v in doc.items() if k != "evaluations"}}
    want = {str(s) for s in segment_ids}
    return {
        "evaluations": [e for e in evals if str(e.get("segment_id") or "") in want],
    }


def _trim_prior_contexts_to_ids(payload: dict[str, Any], segment_ids: list[str] | None) -> dict[str, Any]:
    if not segment_ids:
        return payload
    want = {str(s) for s in segment_ids}
    for key in (
        "prior_native_contexts",
        "target_native_contexts",
        "vo_missions",
    ):
        raw = payload.get(key)
        if isinstance(raw, dict):
            payload[key] = {k: v for k, v in raw.items() if str(k) in want}
    highlights = payload.get("prior_native_context_highlights")
    if isinstance(highlights, list):
        payload["prior_native_context_highlights"] = [
            h
            for h in highlights
            if isinstance(h, dict) and str(h.get("before_target") or "") in want
        ][:40]
    return payload


def _merge_gap_report_parts(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge sharded gap_framing_compose artifacts (lines + gaps + plan)."""
    lines_by_id: dict[str, dict[str, Any]] = {}
    gaps: list[Any] = []
    plan: dict[str, Any] | None = None
    for part in parts:
        if not isinstance(part, dict):
            continue
        for line in part.get("interviewer_lines") or []:
            if not isinstance(line, dict):
                continue
            lid = str(line.get("line_id") or "").strip()
            if not lid:
                tgt = str(line.get("targets_segment_id") or line.get("segment_id") or "")
                cat = str(line.get("line_category") or "line")
                lid = f"vo_{cat}_{tgt}" if tgt else f"vo_auto_{len(lines_by_id)+1}"
                line = {**line, "line_id": lid}
            if lid not in lines_by_id:
                lines_by_id[lid] = line
        for g in part.get("gaps") or []:
            gaps.append(g)
        gp = part.get("gap_framing_plan")
        if isinstance(gp, dict) and plan is None:
            plan = gp
    out: dict[str, Any] = {
        "interviewer_lines": list(lines_by_id.values()),
        "gaps": gaps,
    }
    if plan is not None:
        out["gap_framing_plan"] = plan
    return out


def _gap_framing_compose_payload(
    c: RunContext,
    *,
    segment_ids: list[str] | None = None,
    shard_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from interview_mux.gap_framing import gap_framing_cfg
    from interview_mux.config import merged_config
    import math

    evals_doc = (
        c.read_json("understanding/gap_evaluations.json")
        if c.artifact_exists("understanding/gap_evaluations.json")
        else {"evaluations": []}
    )
    payload: dict[str, Any] = {
        "gap_evaluations": _filter_gap_evaluations_for_ids(
            evals_doc if isinstance(evals_doc, dict) else {}, segment_ids
        ),
        "segments": _compact_segments_payload(c, segment_ids=segment_ids),
        "content_brief": c.read_json("understanding/content_brief.json"),
        "gap_framing_policy": gap_framing_cfg(),
    }
    if c.artifact_exists("understanding/delivery_brief.json"):
        payload["delivery_brief"] = c.read_json("understanding/delivery_brief.json")
    if c.artifact_exists("understanding/episode_structure.json"):
        payload["episode_structure"] = c.read_json("understanding/episode_structure.json")
    # VO density contract for compose (hard min ≈20% of selected speech).
    gf = ((merged_config().get("analysis") or {}).get("gap_framing") or {})
    min_r = float(gf.get("min_vo_insert_ratio") or 0.0)
    tgt_r = float(gf.get("target_vo_insert_ratio") or 0.08)
    if segment_ids is not None:
        ordered_n = len(segment_ids)
    else:
        ordered_n = 0
        if c.artifact_exists("master/selection.json"):
            sel = c.read_json("master/selection.json")
            if isinstance(sel, dict):
                ordered_n = len([s for s in (sel.get("ordered_segment_ids") or []) if s])
        if ordered_n <= 0 and c.artifact_exists("segments/manifest.json"):
            man = c.read_json("segments/manifest.json")
            ordered_n = len(
                [
                    r
                    for r in ((man or {}).get("segments") or [])
                    if isinstance(r, dict) and r.get("segment_id")
                ]
            )
    vo_min = int(math.ceil(ordered_n * min_r)) if ordered_n and min_r > 0 else 0
    vo_ideal = max(vo_min, int(math.ceil(ordered_n * tgt_r))) if ordered_n else vo_min
    qb = {}
    if isinstance(payload.get("delivery_brief"), dict) and segment_ids is None:
        qb = (
            (payload["delivery_brief"].get("question_budget") or {})
            if isinstance(payload["delivery_brief"].get("question_budget"), dict)
            else {}
        )
    payload["vo_line_budget"] = {
        "min": int(qb.get("min") or vo_min),
        "ideal": int(qb.get("ideal") or vo_ideal),
        "max": int(qb.get("max") or max(vo_ideal, vo_min)),
    }
    vf = compact_value_features_summary(c)
    if vf:
        payload["value_features_summary"] = vf
    payload = attach_adaptation_to_payload(c, payload)
    try:
        from interview_mux.mastering_plan_loader import best_available_mode, validate_or_degrade
        from interview_mux.narrative_mode import prefer_forbid_volley_block

        plan = validate_or_degrade(c)
        mode = best_available_mode(plan)
        payload["mastering_plan_summary"] = {
            "narrative_mode": mode,
            "pass": plan.get("pass"),
            "plan_status": plan.get("plan_status"),
            "montage_grammar": plan.get("montage_grammar"),
            "pov": plan.get("pov"),
        }
        payload["narrative_mode_priors"] = prefer_forbid_volley_block(mode, plan)
    except Exception:
        pass
    # Address labels for name/group-aware VO (never invent names)
    try:
        from interview_mux.speaker_delivery_plan import (
            build_speaker_delivery_plan,
            write_speaker_delivery_plan,
        )

        if c.artifact_exists("understanding/speaker_delivery_plan.json"):
            sdp = c.read_json("understanding/speaker_delivery_plan.json")
        else:
            sdp = build_speaker_delivery_plan(c)
            try:
                write_speaker_delivery_plan(c)
            except Exception:
                pass
        if isinstance(sdp, dict):
            payload["address_labels"] = sdp.get("address_labels") or {}
            payload["speaker_delivery_plan"] = {
                "clone_speaker_id": sdp.get("clone_speaker_id"),
                "insert_strategy": sdp.get("insert_strategy"),
                "address_mode": sdp.get("address_mode"),
                "group_label": sdp.get("group_label"),
                "speaker_count": sdp.get("speaker_count"),
            }
    except Exception:
        pass
    if c.artifact_exists("understanding/reorder_bridges.json"):
        payload["reorder_bridges"] = c.read_json("understanding/reorder_bridges.json")
    from interview_mux.gap_vo_prior_context import (
        attach_prior_native_contexts_to_payload,
        attach_vo_partner_context_to_payload,
    )

    payload = attach_prior_native_contexts_to_payload(c, payload)
    payload = attach_vo_partner_context_to_payload(c, payload, segment_ids=segment_ids)
    payload = _trim_prior_contexts_to_ids(payload, segment_ids)
    if shard_meta:
        payload["_gap_compose_shard"] = shard_meta
    return payload


def run_gap_framing_compose(ctx: RunContext) -> None:
    """Compose full gap framing script (questions, summaries, prefaces, bridges)."""
    from interview_mux.llm_simple import run_llm_stage_simple

    required_ids = _gap_segment_ids(ctx)
    batch_size = _gap_pass_batch_size()
    prompt_rel = prompt_variant("interviewer-gap/gap-framing-compose.system.txt", ctx)

    def build_input(c: RunContext) -> dict:
        return _gap_framing_compose_payload(c)

    def persist(c: RunContext, artifacts: dict) -> None:
        from interview_mux.artifact_repairs import repair_gap_report
        from interview_mux.artifact_writes import write_validated_artifact
        from interview_mux.gap_framing import persist_gap_framing_companion_artifacts
        from interview_mux.gap_vo_prior_context import (
            stamp_lines_prior_provenance,
            write_gap_vo_context_audit,
        )

        plan = artifacts.pop("gap_framing_plan", None)
        repaired, _ = repair_gap_report(c, artifacts)
        from interview_mux.high_gap_vo import demote_uncovered_high_gaps, fill_uncovered_high_gaps

        fill_applied: list[dict[str, Any]] = []
        filled = fill_uncovered_high_gaps(
            c, repaired, applied=fill_applied, origin="high_gap_vo_fill"
        )
        if filled:
            c.log(
                f"gap_framing_compose: filled {filled} uncovered high gap(s)",
                level="info",
                stage="gap_framing_compose",
            )
        lines = repaired.get("interviewer_lines")
        if isinstance(lines, list):
            repaired["interviewer_lines"] = stamp_lines_prior_provenance(c, lines)
            write_gap_vo_context_audit(c, repaired["interviewer_lines"])
        persist_gap_framing_companion_artifacts(c, repaired)
        if isinstance(plan, dict):
            c.write_json("understanding/gap_framing_plan.json", plan)
        demoted = demote_uncovered_high_gaps(c, gap_report=repaired)
        if demoted:
            c.log(
                f"gap_framing_compose: demoted {demoted} uncovered high gap(s) after fill",
                level="warning",
                stage="gap_framing_compose",
            )
        write_validated_artifact(
            c,
            "understanding/gap_report.json",
            repaired,
            merge_from_disk=True,
            stage_key="gap_framing_compose",
        )

    with logged_step("gap_framing_compose/llm_stage", ctx=ctx, stage="gap_framing_compose"):
        if len(required_ids) <= batch_size:
            try:
                run_analysis_llm_stage(
                    ctx,
                    "gap_framing_compose",
                    prompt_rel,
                    build_input,
                    persist,
                )
            except Exception as exc:
                ctx.log(
                    f"gap_framing_compose flagship failed — high-gap fill: {exc}",
                    level="warning",
                    stage="gap_framing_compose",
                )
                from interview_mux.high_gap_vo import fill_uncovered_high_gaps

                seed = (
                    ctx.read_json("understanding/gap_report.json")
                    if ctx.artifact_exists("understanding/gap_report.json")
                    else {"interviewer_lines": []}
                )
                applied: list[dict[str, Any]] = []
                fill_uncovered_high_gaps(ctx, seed, applied=applied, origin="high_gap_vo_fill")
                persist(ctx, seed)
            return

        batches = [
            required_ids[i : i + batch_size]
            for i in range(0, len(required_ids), batch_size)
        ]
        ctx.log(
            f"gap_framing_compose proactive batch: {len(required_ids)} segments → "
            f"{len(batches)} shard(s) of ≤{batch_size}",
            level="info",
            stage="gap_framing_compose",
            action_id="gap_framing_compose.proactive_batch",
            detail={
                "required_count": len(required_ids),
                "batch_size": batch_size,
                "batches": len(batches),
            },
        )

        def _noop_persist(_c: RunContext, _artifacts: dict) -> None:
            return None

        parts: list[dict[str, Any]] = []
        for bi, batch_ids in enumerate(batches):

            def build_batch(
                c: RunContext,
                *,
                _ids: list[str] = list(batch_ids),
                _bi: int = bi,
                _total: int = len(batches),
            ) -> dict:
                return _gap_framing_compose_payload(
                    c,
                    segment_ids=_ids,
                    shard_meta={
                        "index": _bi + 1,
                        "total": _total,
                        "segment_ids": list(_ids),
                    },
                )

            ctx.log(
                f"gap_framing_compose shard {bi + 1}/{len(batches)} "
                f"({len(batch_ids)} segment ids)",
                level="action",
                stage="gap_framing_compose",
                action_id="gap_framing_compose.shard",
            )
            envelope = run_llm_stage_simple(
                ctx,
                "gap_framing_compose",
                prompt_rel,
                build_batch,
                _noop_persist,
                auto_complete=False,
            )
            arts = envelope.get("artifacts") if isinstance(envelope.get("artifacts"), dict) else {}
            if isinstance(arts, dict) and arts:
                parts.append(arts)

        merged = _merge_gap_report_parts(parts)
        if not (merged.get("interviewer_lines") or []):
            raise RuntimeError(
                f"Batched gap_framing_compose produced no interviewer_lines "
                f"across {len(batches)} shard(s)"
            )
        persist(ctx, merged)
        if not ctx.is_done("gap_framing_compose"):
            ctx.mark_done("gap_framing_compose")
        ctx.log(
            f"gap_framing_compose batched complete "
            f"({len(merged.get('interviewer_lines') or [])} lines)",
            level="success",
            stage="gap_framing_compose",
            action_id="gap_framing_compose.proactive_batch_complete",
        )


def run_optimal_questions(ctx: RunContext) -> None:
    """Legacy alias — delegates to gap_framing_compose."""
    run_gap_framing_compose(ctx)


def run_optimal_questions_legacy(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "gap_evaluations": c.read_json("understanding/gap_evaluations.json"),
            "segments": _compact_segments_payload(c),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        return attach_adaptation_to_payload(c, payload)

    def persist(c: RunContext, artifacts: dict) -> None:
        from interview_mux.artifact_repairs import repair_gap_report
        from interview_mux.artifact_writes import write_validated_artifact

        repaired, _ = repair_gap_report(c, artifacts)
        write_validated_artifact(
            c,
            "understanding/gap_report.json",
            repaired,
            merge_from_disk=True,
            stage_key="optimal_questions",
        )
        persist_optimal_questions_companion_artifacts(c, repaired)

    with logged_step("optimal_questions/llm_stage", ctx=ctx, stage="optimal_questions"):
        run_analysis_llm_stage(
            ctx,
            "optimal_questions",
            prompt_variant("interviewer-gap/optimal-questions.system.txt", ctx),
            build_input,
            persist,
        )


def gap_compose_stage_done(ctx: RunContext) -> bool:
    return ctx.is_done("gap_framing_compose") or ctx.is_done("optimal_questions")


def persist_optimal_questions_companion_artifacts(ctx: RunContext, artifacts: dict) -> None:
    """Write interviewer_script.txt after gap_report.json (resilience + merge persist)."""
    lines = artifacts.get("interviewer_lines") or []
    eligible = pickup_eligible_speaker_id(ctx)
    for i, line in enumerate(lines):
        if "line_id" not in line:
            line["line_id"] = f"line_{i+1:03d}"
        if not line.get("placement"):
            line["placement"] = "before"
        if line.get("delivery") == "synthesize" and not line.get("voice_speaker_id"):
            eligible = pickup_eligible_speaker_id(ctx)
            if eligible:
                line["voice_speaker_id"] = eligible
        if line.get("delivery") == "record" and eligible:
            line["voice_speaker_id"] = eligible
    _write_interviewer_script(ctx, lines)


def _write_interviewer_script(ctx: RunContext, lines: list[dict]) -> None:
    rows = [
        "# Interviewer script — record to vo_pickup/{line_id}.wav or synthesize at G1",
        "",
    ]
    for line in lines:
        lid = line.get("line_id", "line_unknown")
        rows.append(f"## {lid} ({line.get('delivery', 'record')})")
        rows.append(f"Target: {line.get('targets_segment_id', '')} — {line.get('gap_type', '')}")
        rows.append(line.get("text", ""))
        rows.append("")
    ctx.path("understanding", "interviewer_script.txt").write_text("\n".join(rows), encoding="utf-8")


def ingest_vo_pickup(ctx: RunContext) -> None:
    """Validate VO files exist; optionally normalize loudness for mix."""
    import subprocess

    from interview_mux.config import merged_config

    report = ctx.read_json("understanding/gap_report.json")
    pickup = ctx.final_path("vo_pickup")
    missing = []
    normalized = 0
    mix_cfg = merged_config().get("mix") or {}
    normalize = bool(mix_cfg.get("normalize_vo_pickup", True))
    adjacent_match = mix_cfg.get("vo_adjacent_level_match") or {}
    skip_absolute_loudnorm = bool(
        isinstance(adjacent_match, dict) and adjacent_match.get("enabled", False)
    )
    with logged_step("vo_ingest/validate_pickups", ctx=ctx, stage="vo_ingest"):
        from interview_mux.stages.assembly import resolve_vo_pickup_path

        for line in report.get("interviewer_lines") or []:
            delivery = str(line.get("delivery") or "").lower()
            if delivery not in {"record", "synthesize"}:
                continue
            if line.get("skipped_optional"):
                continue
            lid = line.get("line_id", "")
            found = resolve_vo_pickup_path(ctx, line)
            if not found:
                missing.append(lid or line.get("targets_segment_id", ""))
                continue
            if normalize and found.parent == pickup:
                norm_dir = pickup / "normalized"
                norm_dir.mkdir(parents=True, exist_ok=True)
                out = norm_dir / found.name
                from interview_mux.operator_subprocess import run_command

                if skip_absolute_loudnorm:
                    # Adjacent-native level match in mix owns loudness — only
                    # peak-sanitize / resample / mono-copy here.
                    run_command(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(found),
                            "-af",
                            "aresample=48000,pan=mono|c0=c0",
                            "-ar",
                            "48000",
                            "-ac",
                            "1",
                            "-c:a",
                            "pcm_s16le",
                            str(out),
                        ],
                        ctx=ctx,
                        stage="vo_ingest",
                        label=f"ffmpeg peak-sanitize pickup {found.name}",
                        capture_output=True,
                    )
                else:
                    run_command(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(found),
                            "-af",
                            "loudnorm=I=-18:TP=-1.5:LRA=11",
                            "-ar",
                            "48000",
                            "-ac",
                            "1",
                            "-c:a",
                            "pcm_s16le",
                            str(out),
                        ],
                        ctx=ctx,
                        stage="vo_ingest",
                        label=f"ffmpeg normalize pickup {found.name}",
                        capture_output=True,
                    )
                normalized += 1
    if missing:
        raise RuntimeError(
            f"Missing VO pickup files for: {missing}. "
            f"Record and place under {pickup}"
        )
    if normalized:
        ctx.log(
            f"vo_ingest: normalized {normalized} pickup WAV(s) under vo_pickup/normalized/",
            level="info",
            stage="vo_ingest",
        )
    else:
        ctx.log("vo_ingest: all pickup WAVs already normalized.", level="info", stage="vo_ingest")
    try:
        from interview_mux.asset_transcripts import sync_vo_sidecars_from_gap_report

        sync_vo_sidecars_from_gap_report(ctx)
    except Exception as exc:
        ctx.log(f"VO sidecar sync skipped: {exc}", level="warning", stage="vo_ingest")
    ctx.mark_done("vo_ingest")
