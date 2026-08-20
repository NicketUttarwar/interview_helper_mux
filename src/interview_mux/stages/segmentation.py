"""Boundary detection and segment classification stages."""

from __future__ import annotations

from typing import Any

from interview_mux.stage_input_helpers import attach_disfluency_context
from interview_mux.stage_input_helpers import compact_transcript_for_boundaries
from interview_mux.stage_input_helpers import transcript_quality_for_ctx
from interview_mux.analysis_memory import load_analysis_state
from interview_mux.llm_specialists import maybe_run_post_stage_specialists
from interview_mux.run_context import RunContext
from interview_mux.boundary_observability import observe_boundary_detection_input, pace_class_from_sap
from interview_mux.operator_trace import logged_step
from interview_mux.stage_enrichment import compact_value_features_summary, pause_ladder_hints
from interview_mux.tone_taxonomy import compact_profile_style_hints
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.production_profile import prompt_variant
from interview_mux.source_topology import attach_adaptation_to_payload
from interview_mux.stages.analysis_stage import run_analysis_llm_stage
from interview_mux.segment_timeline_standard import resolved_segmentation_policy, segmentation_cfg


def _attach_segmentation_policy(payload: dict, ctx: RunContext) -> dict:
    policy = resolved_segmentation_policy()
    adapt = payload.get("flow_adaptation") if isinstance(payload.get("flow_adaptation"), dict) else {}
    if isinstance(adapt, dict) and isinstance(adapt.get("segmentation_policy"), dict):
        policy = {**policy, **adapt["segmentation_policy"]}
    payload["segmentation_policy"] = policy
    sc = segmentation_cfg()
    payload["segmentation_config"] = {
        k: sc.get(k)
        for k in (
            "default_granularity",
            "max_segment_duration_ms",
            "min_segment_duration_ms",
            "split_backchannels",
            "backchannel_max_words",
            "prefer_topic_splits",
            "boundary_merge_threshold_ms",
        )
    }
    return payload


def run_boundaries(ctx: RunContext) -> None:
    from interview_mux.ideal_cuts import (
        bind_boundaries_enabled,
        boundaries_already_from_ideal_cuts,
        ideal_cuts_cfg,
    )

    # Talking-points-first bind: skip LLM when materialize already published
    # a *quality* boundary contract from ideal cuts. Sparse keep-windows must
    # not short-circuit full segmentation — fall through to the LLM path.
    conf = ideal_cuts_cfg()
    if (
        bind_boundaries_enabled(conf)
        and conf.get("skip_boundary_llm_when_bound", True)
        and boundaries_already_from_ideal_cuts(ctx)
    ):
        doc = ctx.read_json("segments/boundaries.json")
        report = evaluate_boundary_quality(
            doc if isinstance(doc, dict) else {},
            duration_ms=_transcript_duration_ms(ctx),
        )
        if not report.get("reject") and bool(segmentation_cfg().get("reject_coarse_fallback", True)):
            if not ctx.is_done("boundary_detection"):
                ctx.mark_done("boundary_detection", force=True)
            ctx.log(
                "boundary_detection: skipped LLM — using ideal_cuts_materialize boundaries "
                f"(n={report.get('segment_count')} coverage={report.get('coverage_ratio')})",
                level="info",
                stage="boundary_detection",
            )
            try:
                from interview_mux.boundary_edge_score import apply_boundary_confidence_pass

                apply_boundary_confidence_pass(ctx, stage="boundary_detection", repair=True)
            except Exception as exc:
                ctx.log(
                    f"boundary edge confidence pass skipped: {exc}",
                    level="warning",
                    stage="boundary_detection",
                )
            return
        if not report.get("reject") and not bool(segmentation_cfg().get("reject_coarse_fallback", True)):
            if not ctx.is_done("boundary_detection"):
                ctx.mark_done("boundary_detection", force=True)
            ctx.log(
                "boundary_detection: skipped LLM — ideal_cuts bind (reject_coarse_fallback=false)",
                level="info",
                stage="boundary_detection",
            )
            try:
                from interview_mux.boundary_edge_score import apply_boundary_confidence_pass

                apply_boundary_confidence_pass(ctx, stage="boundary_detection", repair=True)
            except Exception as exc:
                ctx.log(
                    f"boundary edge confidence pass skipped: {exc}",
                    level="warning",
                    stage="boundary_detection",
                )
            return
        ctx.log(
            "boundary_detection: ideal_cuts bind too coarse "
            f"(n={report.get('segment_count')} coverage={report.get('coverage_ratio')} "
            f"expected_min≈{report.get('expected_min_segments')}) — running LLM segmentation",
            level="warning",
            stage="boundary_detection",
        )

    def build_input(c: RunContext) -> dict:
        transcript = compact_transcript_for_boundaries(c.read_json("transcript/full.json"))
        payload = {
            "transcript": transcript,
            "speakers": c.read_json("understanding/speakers.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
        if c.artifact_exists("understanding/talking_points.json"):
            payload["talking_points"] = c.read_json("understanding/talking_points.json")
        if c.artifact_exists("understanding/ideal_cuts.json"):
            payload["ideal_cuts"] = c.read_json("understanding/ideal_cuts.json")
        if c.artifact_exists("understanding/ideal_cuts_materialized.json"):
            payload["ideal_cuts_materialized"] = c.read_json(
                "understanding/ideal_cuts_materialized.json"
            )
        quality = transcript_quality_for_ctx(c)
        if quality:
            payload["transcript_quality"] = quality
        payload["pause_ladder_hints"] = pause_ladder_hints(c)
        pace = pace_class_from_sap(c)
        raw_hints = payload["pause_ladder_hints"]
        from interview_mux.stage_enrichment import thin_pause_ladder_hints

        payload["pause_ladder_hints"] = thin_pause_ladder_hints(raw_hints, pace, ctx=c)
        pre_thin = {"candidates": list(raw_hints.get("candidates") or [])}
        if c.artifact_exists("understanding/source_acoustic_profile.json"):
            payload["source_acoustic_profile"] = {
                "pacing": {"pace_class": pace},
            }
        from interview_mux.interview_spine.compact import attach_spine_to_payload

        from interview_mux.conversation_context import attach_conversation_context

        attach_spine_to_payload(c, payload, "boundary_detection")
        observe_boundary_detection_input(c, payload, pre_thin_counts=pre_thin)
        payload = attach_conversation_context(c, payload, "boundary_detection")
        payload = attach_disfluency_context(payload, c)
        payload = attach_adaptation_to_payload(c, payload)
        return _attach_segmentation_policy(payload, c)

    persist = make_stage_persist("segments/boundaries.json", "boundary_detection")

    with logged_step("boundary_detection/llm_stage", ctx=ctx, stage="boundary_detection"):
        run_analysis_llm_stage(
            ctx,
            "boundary_detection",
            "segmentation/boundary-detection.system.txt",
            build_input,
            persist,
        )
    with logged_step("boundary_detection/edge_confidence", ctx=ctx, stage="boundary_detection"):
        try:
            from interview_mux.boundary_edge_score import apply_boundary_confidence_pass

            apply_boundary_confidence_pass(ctx, stage="boundary_detection", repair=True)
        except Exception as exc:
            ctx.log(
                f"boundary edge confidence pass skipped: {exc}",
                level="warning",
                stage="boundary_detection",
            )
    _assert_boundary_quality(ctx)


def evaluate_boundary_quality(
    doc: dict,
    *,
    duration_ms: int = 0,
) -> dict:
    """Metric-only boundary quality report (no I/O, no raises).

    Ideal-cut keep windows are sparse by design; use this before binding them as
    the full segment contract, and before hard-failing LLM boundaries.
    """
    rows = [r for r in (doc.get("boundaries") or []) if isinstance(r, dict)]
    invalid_rows: list[str] = []
    durs_ms: list[int] = []
    last_end = 0
    intervals: list[tuple[int, int]] = []
    for row in rows:
        sid = str(row.get("segment_id") or "")
        start = int(row.get("start_ms") or 0)
        end = int(row.get("end_ms") or start)
        if end <= start:
            invalid_rows.append(sid or f"{start}:{end}")
            continue
        durs_ms.append(end - start)
        last_end = max(last_end, end)
        intervals.append((start, end))

    sc = segmentation_cfg()
    max_ms = int(sc.get("max_segment_duration_ms") or 180_000)
    over_max = [d for d in durs_ms if d > max_ms + 250]
    mean_ms = (sum(durs_ms) / len(durs_ms)) if durs_ms else 0.0
    if duration_ms <= 0:
        duration_ms = last_end
    expected_min_segments = max(8, int(duration_ms / max(max_ms, 1)) + 1) if duration_ms else 0
    covered_ms = 0
    if intervals:
        intervals.sort()
        cur_s, cur_e = intervals[0]
        for s, e in intervals[1:]:
            if s <= cur_e:
                cur_e = max(cur_e, e)
            else:
                covered_ms += max(0, cur_e - cur_s)
                cur_s, cur_e = s, e
        covered_ms += max(0, cur_e - cur_s)
    coverage_ratio = (covered_ms / duration_ms) if duration_ms > 0 else 1.0
    near_ceiling = sum(1 for d in durs_ms if d >= int(max_ms * 0.92))
    near_ceiling_ratio = (near_ceiling / len(durs_ms)) if durs_ms else 0.0
    # Do not reject ideal-cut / complete-thought binds solely because there are
    # fewer rows than duration/max_ms. Near-ceiling slabs still fail.
    # Coverage holes alone must not fail fine-grained turn maps (e.g. 1:1 diarization
    # with ~84% covered — silence/gaps, not coarse time-boxing).
    coverage_min = float(sc.get("boundary_quality_min_coverage_ratio") or 0.85)
    critical_coverage = float(sc.get("boundary_quality_critical_coverage_ratio") or 0.70)
    fine_grained = bool(
        durs_ms
        and len(durs_ms) >= max(8, expected_min_segments or 8)
        and mean_ms < max_ms * 0.55
        and near_ceiling_ratio < 0.20
    )
    coverage_fail = bool(
        duration_ms > 0
        and (
            coverage_ratio < critical_coverage
            or (coverage_ratio < coverage_min and not fine_grained)
        )
    )
    is_metric_coarse = bool(
        durs_ms
        and (
            (mean_ms >= max_ms * 0.85 and near_ceiling_ratio >= 0.45)
            or coverage_fail
        )
    )
    warnings = [str(x) for x in (doc.get("warnings") or [])]
    self_labeled = [
        w
        for w in warnings
        if "coarse" in w.lower() or "mid-sentence" in w.lower() or "token limit" in w.lower()
    ]
    reject = bool(invalid_rows or over_max or is_metric_coarse)
    return {
        "reject": reject,
        "invalid_segment_ids": invalid_rows,
        "over_max_count": len(over_max),
        "segment_count": len(durs_ms),
        "mean_ms": round(mean_ms),
        "coverage_ratio": round(coverage_ratio, 3),
        "near_ceiling_ratio": round(near_ceiling_ratio, 3),
        "metric_coarse": is_metric_coarse,
        "self_labeled_warnings": self_labeled,
        "duration_ms": duration_ms,
        "expected_min_segments": expected_min_segments,
    }


def _transcript_duration_ms(ctx: RunContext) -> int:
    try:
        from interview_mux.interview_duration_policy import transcript_duration_ms

        return int(transcript_duration_ms(ctx) or 0)
    except Exception:
        return 0


def _assert_boundary_quality(ctx: RunContext) -> None:
    """Reject truly unsafe boundaries — judge metrics, not LLM warning prose.

    Models often self-label fine-grained long-tape cuts as "coarse" / "token limit"
    even when hundreds of valid edit blocks exist. Keyword-matching those warnings
    falsely blocked a previously shippable Full-auto run. Fail only on structural defects
    or metric evidence of time-boxed coarse fallback.

    Before rejecting on over-max spans, attempt a deterministic max-duration split
    so a raised ``max_segment_duration_ms`` (complete-thought policy) cannot soft-lock
    the pipeline when the LLM leaves a few long beds.
    """
    if not bool(segmentation_cfg().get("reject_coarse_fallback", True)):
        return
    if not ctx.artifact_exists("segments/boundaries.json"):
        return
    doc = ctx.read_json("segments/boundaries.json")
    if not isinstance(doc, dict):
        return
    duration_ms = _transcript_duration_ms(ctx)
    report = evaluate_boundary_quality(doc, duration_ms=duration_ms)

    # Deterministic repair: split beds that exceed max_segment_duration_ms.
    if int(report.get("over_max_count") or 0) > 0:
        try:
            from interview_mux.boundary_collate import normalize_boundary_timeline
            from interview_mux.boundary_enrich import enforce_max_segment_duration
            from interview_mux.stage_coupling import publish_boundary_contract

            transcript = (
                ctx.read_json("transcript/full.json")
                if ctx.artifact_exists("transcript/full.json")
                else None
            )
            rows = [dict(r) for r in (doc.get("boundaries") or []) if isinstance(r, dict)]
            fixed, applied = enforce_max_segment_duration(rows, transcript)
            if applied:
                normalized, _notes = normalize_boundary_timeline(fixed)
                out = dict(doc)
                out["boundaries"] = normalized
                out = publish_boundary_contract(out, publisher_stage="boundary_detection")
                ctx.write_json("segments/boundaries.json", out)
                ctx.log(
                    f"boundary_detection: enforced max duration on {len(applied)} split(s) "
                    f"→ {len(normalized)} segments",
                    level="info",
                    stage="boundary_detection",
                )
                doc = out
                report = evaluate_boundary_quality(doc, duration_ms=duration_ms)
        except Exception as exc:
            ctx.log(
                f"boundary max-duration repair skipped: {exc}",
                level="warning",
                stage="boundary_detection",
            )

    self_labeled = list(report.get("self_labeled_warnings") or [])
    if (
        self_labeled
        and not report.get("reject")
    ):
        ctx.log(
            "Boundary warnings mention coarse/token-limit but metrics look fine "
            f"(n={report.get('segment_count')} mean_ms={report.get('mean_ms')} "
            f"coverage={report.get('coverage_ratio')}) — accepting.",
            level="warning",
            stage="boundary_detection",
        )

    if report.get("reject"):
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "Boundary detection produced unsafe cuts; delivery is blocked.",
            stage="boundary_detection",
            reason="coarse_or_invalid_segmentation",
            detail={
                "invalid_segment_ids": (report.get("invalid_segment_ids") or [])[:20],
                "over_max_count": report.get("over_max_count"),
                "segment_count": report.get("segment_count"),
                "mean_ms": report.get("mean_ms"),
                "coverage_ratio": report.get("coverage_ratio"),
                "near_ceiling_ratio": report.get("near_ceiling_ratio"),
                "metric_coarse": report.get("metric_coarse"),
                "self_labeled_warnings": self_labeled[:4],
                "hint": "Re-run boundary detection with sharded volleys / pause-ladder refine.",
            },
        )


def run_boundary_topic_resplit(ctx: RunContext) -> None:
    """Post-reanchor deterministic + optional LLM resplit for overloaded segments."""
    from interview_mux.boundary_collate import normalize_boundary_timeline
    from interview_mux.boundary_enrich import detect_overloaded_segment_ids, enrich_boundary_rows
    from interview_mux.ideal_cuts import (
        boundaries_already_from_ideal_cuts,
        ideal_cuts_cfg,
    )
    from interview_mux.stage_coupling import publish_boundary_contract
    from interview_mux.v2.config import ANALYSIS_ORDER

    def _run_post_reanchor_edge_confidence() -> None:
        """Score existing boundaries even when no re-split is necessary.

        A no-overload result is the normal fast path, not evidence that the
        original cut edges were editorially safe.  Re-running the scorer here
        is also what lets its post-reanchor context inform the review queue.
        """
        try:
            from interview_mux.boundary_edge_score import apply_boundary_confidence_pass

            apply_boundary_confidence_pass(
                ctx,
                stage="boundary_topic_resplit",
                repair=True,
            )
        except Exception as exc:
            ctx.log(
                f"boundary post-reanchor edge confidence pass skipped: {exc}",
                level="warning",
                stage="boundary_topic_resplit",
            )

    # One invalidation cycle per run — re-entering after resume-from-classification
    # must not clear markers again (clear_from(from_stage) would wipe this stage's
    # .stage_done and loop forever).
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if isinstance(meta, dict) and meta.get("boundary_topic_resplit_cycle_done"):
        ctx.log(
            "boundary_topic_resplit cycle already completed this run — skipping re-invalidation",
            level="info",
            stage="boundary_topic_resplit",
        )
        _run_post_reanchor_edge_confidence()
        ctx.mark_done("boundary_topic_resplit", force=True)
        return

    # Talking-points-first: ideal-cut windows are the keep authority — do not
    # re-partition them via topic resplit unless explicitly re-enabled.
    conf = ideal_cuts_cfg()
    if (
        conf.get("skip_topic_resplit_when_bound", True)
        and boundaries_already_from_ideal_cuts(ctx)
    ):
        def _mark_cycle(m: dict) -> None:
            m["boundary_topic_resplit_cycle_done"] = True

        ctx.mutate_run_meta(_mark_cycle)
        ctx.log(
            "boundary_topic_resplit: skipped — ideal_cuts boundaries are authoritative",
            level="info",
            stage="boundary_topic_resplit",
        )
        _run_post_reanchor_edge_confidence()
        ctx.mark_done("boundary_topic_resplit", force=True)
        return

    if not ctx.artifact_exists("segments/boundaries.json"):
        ctx.log("boundary_topic_resplit skipped — no boundaries", level="warning", stage="boundary_topic_resplit")
        ctx.mark_done("boundary_topic_resplit", force=True)
        return

    boundaries = ctx.read_json("segments/boundaries.json")
    manifest = ctx.read_json("segments/manifest.json") if ctx.artifact_exists("segments/manifest.json") else {}
    brief = ctx.read_json("understanding/content_brief.json") if ctx.artifact_exists("understanding/content_brief.json") else {}
    transcript = ctx.read_json("transcript/full.json") if ctx.artifact_exists("transcript/full.json") else {}
    speakers = ctx.read_json("understanding/speakers.json") if ctx.artifact_exists("understanding/speakers.json") else {}

    overloaded = detect_overloaded_segment_ids(boundaries, content_brief=brief, manifest=manifest)
    adapt = ctx.read_json("understanding/flow_adaptation.json") if ctx.artifact_exists("understanding/flow_adaptation.json") else {}
    policy = resolved_segmentation_policy()
    if isinstance(adapt, dict) and isinstance(adapt.get("segmentation_policy"), dict):
        policy = {**policy, **adapt["segmentation_policy"]}

    rows = [dict(r) for r in (boundaries.get("boundaries") or []) if isinstance(r, dict)]
    if not overloaded:
        def _mark_cycle(m: dict) -> None:
            m["boundary_topic_resplit_cycle_done"] = True

        ctx.mutate_run_meta(_mark_cycle)
        _run_post_reanchor_edge_confidence()
        ctx.mark_done("boundary_topic_resplit", force=True)
        return

    if policy.get("resegment_pass"):
        def build_resplit_input(c: RunContext) -> dict:
            payload = {
                "boundaries": boundaries,
                "segments/manifest": manifest,
                "content_brief": brief,
                "transcript": compact_transcript_for_boundaries(transcript if isinstance(transcript, dict) else {}),
                "overloaded_segment_ids": sorted(overloaded),
                "segmentation_policy": policy,
            }
            return attach_adaptation_to_payload(c, payload)

        persist = make_stage_persist("segments/boundaries.json", "boundary_topic_resplit")
        with logged_step("boundary_topic_resplit/llm_stage", ctx=ctx, stage="boundary_topic_resplit"):
            run_analysis_llm_stage(
                ctx,
                "boundary_topic_resplit",
                "segmentation/boundary-detection-refine.system.txt",
                build_resplit_input,
                persist,
            )
    else:
        enriched, _actions = enrich_boundary_rows(
            rows,
            transcript=transcript if isinstance(transcript, dict) else None,
            speakers_doc=speakers if isinstance(speakers, dict) else None,
            content_brief=brief if isinstance(brief, dict) else None,
            manifest=manifest if isinstance(manifest, dict) else None,
        )
        normalized, _ = normalize_boundary_timeline(enriched)
        out = dict(boundaries)
        out["boundaries"] = normalized
        publish_boundary_contract(out)
        ctx.write_json("segments/boundaries.json", out, stage_key="boundary_topic_resplit")

    # Classification/reanchor consumed pre-resplit boundaries — drop their done markers
    # without clear_from(segment_classification), which would archive this write.
    for sid in ("segment_classification", "content_brief_reanchor"):
        marker = ctx.final_path(".stage_done", sid)
        if marker.is_file():
            marker.unlink()
    next_idx = list(ANALYSIS_ORDER).index("boundary_topic_resplit") + 1
    if next_idx < len(ANALYSIS_ORDER):
        ctx.clear_from(ANALYSIS_ORDER[next_idx], list(ANALYSIS_ORDER))

    def _mark_cycle_done(m: dict) -> None:
        m["boundary_topic_resplit_cycle_done"] = True

    ctx.mutate_run_meta(_mark_cycle_done)

    # Propose + auto-apply split_plan for duration/overload (operator can undo via NLE)
    try:
        from interview_mux.split_plan import (
            apply_split_plan,
            mark_split_rerank_cascade,
            propose_split_plan,
            write_split_plan,
        )

        plan_doc = write_split_plan(ctx, propose_split_plan(ctx))
        if plan_doc.get("proposals"):
            applied = apply_split_plan(ctx, plan=plan_doc)
            if applied.get("applied") and (
                int(applied.get("boundary_count_after") or 0)
                > int(applied.get("boundary_count_before") or 0)
            ):
                mark_split_rerank_cascade(ctx, reason="split_plan_auto_apply")
                ctx.log(
                    f"split_plan auto-applied: "
                    f"{applied.get('boundary_count_before')}→{applied.get('boundary_count_after')} boundaries",
                    level="info",
                    stage="boundary_topic_resplit",
                )
    except Exception as exc:
        ctx.log(f"split_plan skipped: {exc}", level="warning", stage="boundary_topic_resplit")

    # Propose → score → repair: primary confidence pass (post-reanchor context).
    _run_post_reanchor_edge_confidence()

    _assert_boundary_quality(ctx)
    ctx.mark_done("boundary_topic_resplit", force=True)
    try:
        _patch_brief_ids_after_resplit(ctx)
    except Exception as exc:
        ctx.log(f"brief id patch after resplit skipped: {exc}", level="warning", stage="boundary_topic_resplit")
    ctx.log(
        "boundary_topic_resplit: re-running classification in-process (no clear_from)",
        level="info",
        stage="boundary_topic_resplit",
    )
    from interview_mux.write_staging import run_nested_staged_stage
    from interview_mux.stages.understanding import run_content_brief_reanchor

    run_nested_staged_stage(ctx, "segment_classification", lambda: run_classification(ctx))
    run_nested_staged_stage(ctx, "content_brief_reanchor", lambda: run_content_brief_reanchor(ctx))


def _patch_brief_ids_after_resplit(ctx: RunContext) -> None:
    """Remap content_brief topic segment_ids onto the post-resplit manifest."""
    if not ctx.artifact_exists("understanding/content_brief.json"):
        return
    if not ctx.artifact_exists("segments/manifest.json"):
        return
    brief = ctx.read_json("understanding/content_brief.json")
    man = ctx.read_json("segments/manifest.json")
    if not isinstance(brief, dict) or not isinstance(man, dict):
        return
    segs = [s for s in (man.get("segments") or []) if isinstance(s, dict) and s.get("segment_id")]
    live = {str(s["segment_id"]) for s in segs}
    changed = False
    for topic in brief.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        ids = [str(x) for x in (topic.get("segment_ids") or []) if x]
        if not ids or all(i in live for i in ids):
            continue
        mapped: list[str] = []
        for oid in ids:
            if oid in live:
                mapped.append(oid)
                continue
            # Best-effort: keep any live id that shares a prefix (seg_012 → seg_012a).
            hits = [sid for sid in sorted(live) if sid.startswith(oid) or oid.startswith(sid)]
            mapped.extend(hits[:3] or [])
        topic["segment_ids"] = list(dict.fromkeys(mapped))
        changed = True
    if changed:
        from interview_mux.artifact_lifecycle import restamp_committed_artifact

        # Commit under the brief producer key and re-stamp so sonic_context_build
        # does not see a fingerprint mismatch after resplit remaps.
        restamp_committed_artifact(
            ctx,
            "understanding/content_brief.json",
            producer_stage="content_brief_reanchor",
            doc=brief,
        )


def run_classification(ctx: RunContext) -> None:
    from interview_mux.artifact_writes import write_validated_artifact
    from interview_mux.boundary_enrich import restamp_run_span_speakers
    from interview_mux.classification_obligation import classification_context_cfg
    from interview_mux.llm_simple import StageError, run_llm_stage_simple
    from interview_mux.segmentation_input_resolver import build_classification_payload
    from interview_mux.talking_points_authority import try_deterministic_classification

    restamp_run_span_speakers(ctx)

    det = try_deterministic_classification(ctx)
    if det is not None and (det.get("segments") or []):
        write_validated_artifact(
            ctx,
            "segments/manifest.json",
            det,
            merge_from_disk=False,
            stage_key="segment_classification",
        )
        ctx.log(
            f"segment_classification: deterministic from ideal cuts "
            f"({len(det.get('segments') or [])} segments)",
            level="info",
            stage="segment_classification",
        )
        if not ctx.is_done("segment_classification"):
            ctx.mark_done("segment_classification", force=True)
        try:
            from interview_mux.asset_transcripts import sync_speech_sidecars

            sync_speech_sidecars(ctx)
        except Exception as exc:
            ctx.log(
                f"speech sidecar sync after classification skipped: {exc}",
                level="warning",
                stage="segment_classification",
            )
        return

    def build_input(c: RunContext) -> dict:
        return build_classification_payload(c)

    def _manifest_transform(artifacts: dict) -> dict:
        segments = artifacts.get("segments") or artifacts
        if isinstance(segments, dict):
            segments = segments.get("segments", [])
        from interview_mux.boundary_enrich import stamp_span_speakers

        transcript = (
            ctx.read_json("transcript/full.json")
            if ctx.artifact_exists("transcript/full.json")
            else None
        )
        speakers_doc = (
            ctx.read_json("understanding/speakers.json")
            if ctx.artifact_exists("understanding/speakers.json")
            else None
        )
        rows = [s for s in segments if isinstance(s, dict)]
        stamped = stamp_span_speakers(rows, transcript, speakers_doc)
        role_map: dict[str, str] = {}
        if isinstance(speakers_doc, dict):
            for sp in speakers_doc.get("speakers") or []:
                if isinstance(sp, dict) and sp.get("speaker_id"):
                    role_map[str(sp["speaker_id"])] = str(sp.get("role") or "unknown")
        for row in stamped:
            sid = str(row.get("speaker_id") or "")
            role = role_map.get(sid)
            if not role:
                continue
            row["speaker_role"] = role
            typ = str(row.get("type") or "")
            if role == "interviewee" and typ == "interviewer_question":
                row["type"] = "interviewee_answer"
            elif role == "interviewer" and typ == "interviewee_answer":
                row["type"] = "interviewer_question"
        return {"segments": stamped}

    persist = make_stage_persist(
        "segments/manifest.json",
        "segment_classification",
        transform=_manifest_transform,
    )

    prompt_rel = prompt_variant("segmentation/segment-classification.system.txt", ctx)
    full_payload = build_classification_payload(ctx)
    obligation = full_payload.get("classification_obligation") or {}
    required_ids = [str(x) for x in (obligation.get("required_segment_ids") or []) if x]
    cfg = classification_context_cfg()
    shard_max = max(1, int(cfg.get("per_segment_shard_max") or 20))
    proactive = int(cfg.get("proactive_decompose_segments") or 0)
    # When proactive is 0, still batch once the obligation exceeds one shard.
    threshold = proactive if proactive > 0 else shard_max

    with logged_step("segment_classification/llm_stage", ctx=ctx, stage="segment_classification"):
        if len(required_ids) <= threshold:
            run_analysis_llm_stage(
                ctx,
                "segment_classification",
                prompt_rel,
                build_input,
                persist,
            )
        else:
            batches = [required_ids[i : i + shard_max] for i in range(0, len(required_ids), shard_max)]
            ctx.log(
                f"segment_classification proactive batch: {len(required_ids)} segments → "
                f"{len(batches)} shard(s) of ≤{shard_max}",
                level="info",
                stage="segment_classification",
                action_id="classification.proactive_batch",
                detail={"required_count": len(required_ids), "shard_max": shard_max, "batches": len(batches)},
            )
            by_id: dict[str, dict] = {}

            def _noop_persist(_c: RunContext, _artifacts: dict) -> None:
                return None

            for bi, batch_ids in enumerate(batches):
                batch_set = set(batch_ids)

                def build_batch(
                    c: RunContext,
                    *,
                    _ids: list[str] = list(batch_ids),
                    _set: set[str] = batch_set,
                    _bi: int = bi,
                    _total: int = len(batches),
                ) -> dict:
                    payload = build_classification_payload(c)
                    obl = dict(payload.get("classification_obligation") or {})
                    obl["required_segment_ids"] = list(_ids)
                    obl["required_count"] = len(_ids)
                    obl["segments"] = [
                        s
                        for s in (obl.get("segments") or [])
                        if isinstance(s, dict) and str(s.get("segment_id") or "") in _set
                    ]
                    payload["classification_obligation"] = obl
                    payload["_classification_shard"] = {
                        "index": _bi + 1,
                        "total": _total,
                        "segment_ids": list(_ids),
                    }
                    return payload

                ctx.log(
                    f"segment_classification shard {bi + 1}/{len(batches)} "
                    f"({len(batch_ids)} segment ids)",
                    level="action",
                    stage="segment_classification",
                    action_id="classification.shard",
                )
                try:
                    envelope = run_llm_stage_simple(
                        ctx,
                        "segment_classification",
                        prompt_rel,
                        build_batch,
                        _noop_persist,
                        auto_complete=False,
                    )
                except StageError:
                    raise
                arts = envelope.get("artifacts") if isinstance(envelope.get("artifacts"), dict) else {}
                segs = arts.get("segments") or arts
                if isinstance(segs, dict):
                    segs = segs.get("segments") or []
                if not isinstance(segs, list):
                    segs = []
                for row in segs:
                    if isinstance(row, dict) and row.get("segment_id"):
                        by_id[str(row["segment_id"])] = row

            missing = [sid for sid in required_ids if sid not in by_id]
            if missing:
                raise RuntimeError(
                    f"Batched segment_classification incomplete: "
                    f"{len(required_ids) - len(missing)}/{len(required_ids)} classified; "
                    f"missing e.g. {missing[:5]}"
                )
            merged = {"segments": [by_id[sid] for sid in required_ids if sid in by_id]}
            persist(ctx, merged)
            ctx.mark_done("segment_classification")
            ctx.log(
                f"segment_classification batched complete ({len(merged['segments'])} segments)",
                level="success",
                stage="segment_classification",
            )

    with logged_step("segment_classification/post_specialists", ctx=ctx, stage="segment_classification"):
        maybe_run_post_stage_specialists(ctx, "segment_classification", build_input(ctx))
    with logged_step("segment_classification/topic_bootstrap", ctx=ctx, stage="segment_classification"):
        from interview_mux.topic_tag_bootstrap import bootstrap_manifest_topic_tags

        patched = bootstrap_manifest_topic_tags(ctx)
        if patched:
            ctx.log(
                f"Deterministic topic-tag bootstrap patched {patched} segment(s) after classification.",
                level="info",
                stage="segment_classification",
                action_id="classification.topic_tag_bootstrap",
            )
    with logged_step(
        "segment_classification/ideal_cuts_seed",
        ctx=ctx,
        stage="segment_classification",
    ):
        from interview_mux.ideal_cuts import refresh_selection_seed_from_boundaries

        seed = refresh_selection_seed_from_boundaries(ctx)
        if seed and seed.get("ordered_segment_ids"):
            ctx.log(
                f"ideal_cuts selection seed refreshed ({len(seed['ordered_segment_ids'])} ids)",
                level="info",
                stage="segment_classification",
            )
    try:
        from interview_mux.asset_transcripts import sync_speech_sidecars

        sync_speech_sidecars(ctx)
    except Exception as exc:
        ctx.log(
            f"speech sidecar sync after classification skipped: {exc}",
            level="warning",
            stage="segment_classification",
        )
