"""Boundary detection and segment classification stages."""

from __future__ import annotations

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
    def build_input(c: RunContext) -> dict:
        transcript = compact_transcript_for_boundaries(c.read_json("transcript/full.json"))
        payload = {
            "transcript": transcript,
            "speakers": c.read_json("understanding/speakers.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
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


def run_boundary_topic_resplit(ctx: RunContext) -> None:
    """Post-reanchor deterministic + optional LLM resplit for overloaded segments."""
    from interview_mux.boundary_collate import normalize_boundary_timeline
    from interview_mux.boundary_enrich import detect_overloaded_segment_ids, enrich_boundary_rows
    from interview_mux.stage_coupling import publish_boundary_contract
    from interview_mux.v2.config import ANALYSIS_ORDER

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
    ctx.mark_done("boundary_topic_resplit", force=True)
    # Stop this analysis pass — continuing would hit sonic_context without a fresh
    # manifest. The next execute must resume from segment_classification.
    msg = (
        "boundary_topic_resplit invalidated segment_classification/content_brief_reanchor; "
        "resume analysis from stage segment_classification"
    )
    ctx.log(msg, level="warning", stage="boundary_topic_resplit")
    raise SystemExit(msg)


def run_classification(ctx: RunContext) -> None:
    from interview_mux.classification_obligation import classification_context_cfg
    from interview_mux.llm_simple import StageError, run_llm_stage_simple
    from interview_mux.segmentation_input_resolver import build_classification_payload

    def build_input(c: RunContext) -> dict:
        return build_classification_payload(c)

    def _manifest_transform(artifacts: dict) -> dict:
        segments = artifacts.get("segments") or artifacts
        if isinstance(segments, dict):
            segments = segments.get("segments", [])
        return {"segments": segments}

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
