from __future__ import annotations

from typing import Any

from interview_mux.stage_input_helpers import attach_disfluency_context
from interview_mux.llm_specialists import maybe_run_post_stage_specialists
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import (
    compact_manifest_for_volley,
    compact_value_features_summary,
    emphasis_regions_for_segments,
)
from interview_mux.operator_trace import logged_step
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.artifact_repairs import enrich_narrative_plan_for_persist
from interview_mux.production_profile import prompt_variant
from interview_mux.source_topology import attach_adaptation_to_payload
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def run_topic_coverage(ctx: RunContext) -> None:
    from interview_mux.talking_points_authority import try_deterministic_coverage
    from interview_mux.artifact_writes import write_validated_artifact

    det = try_deterministic_coverage(ctx)
    if det is not None:
        write_validated_artifact(
            ctx,
            "master/coverage_audit.json",
            det,
            merge_from_disk=False,
            stage_key="topic_coverage_audit",
        )
        ctx.log(
            "topic_coverage_audit: deterministic from talking points + ideal cuts "
            f"(score={det.get('coverage_score')})",
            level="info",
            stage="topic_coverage_audit",
        )
        if not ctx.is_done("topic_coverage_audit"):
            ctx.mark_done("topic_coverage_audit", force=True)
    else:

        def build_input(c: RunContext) -> dict:
            manifest = c.read_json("segments/manifest.json") if c.artifact_exists("segments/manifest.json") else {}
            payload = {
                "content_brief": c.read_json("understanding/content_brief.json"),
                "segments": compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}, text_max=100),
                "emphasis_regions": emphasis_regions_for_segments(c),
            }
            vf = compact_value_features_summary(c)
            if vf:
                payload["value_features_summary"] = vf
            from interview_mux.coherence import attach_coherence_summary

            attach_coherence_summary(payload, c, "topic_coverage_audit")
            return attach_disfluency_context(
                __import__("interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]).attach_delivery_brief_to_payload(
                    c, attach_adaptation_to_payload(c, payload)
                ),
                c,
            )

        persist = make_stage_persist("master/coverage_audit.json", "topic_coverage_audit")

        with logged_step("topic_coverage_audit/llm_stage", ctx=ctx, stage="topic_coverage_audit"):
            run_flow_llm_stage(
                ctx,
                "topic_coverage_audit",
                prompt_variant("selection/topic-coverage-audit.system.txt", ctx),
                build_input,
                persist,
            )
    if ctx.is_done("topic_coverage_audit"):
        regions = emphasis_regions_for_segments(ctx)
        ctx.log(
            f"topic_coverage_audit: emphasis_regions count={len(regions)}",
            level="info",
            stage="topic_coverage_audit",
        )

    def _coverage_payload(c: RunContext) -> dict:
        manifest = c.read_json("segments/manifest.json") if c.artifact_exists("segments/manifest.json") else {}
        payload = {
            "content_brief": c.read_json("understanding/content_brief.json")
            if c.artifact_exists("understanding/content_brief.json")
            else {},
            "segments": compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}, text_max=100),
            "emphasis_regions": emphasis_regions_for_segments(c),
        }
        return payload

    with logged_step("topic_coverage_audit/post_specialists", ctx=ctx, stage="topic_coverage_audit"):
        maybe_run_post_stage_specialists(ctx, "topic_coverage_audit", _coverage_payload(ctx))
    if ctx.is_done("topic_coverage_audit"):
        with logged_step("topic_coverage_audit/coherence", ctx=ctx, stage="topic_coverage_audit"):
            from interview_mux.coherence import maybe_run_coherence_analysis

            maybe_run_coherence_analysis(ctx, phase="post_coverage")


def run_narrative_arc(ctx: RunContext) -> None:
    from interview_mux.talking_points_authority import try_deterministic_narrative
    from interview_mux.artifact_writes import write_validated_artifact

    det = try_deterministic_narrative(ctx)
    if det is not None:
        enriched = enrich_narrative_plan_for_persist(ctx, det)
        write_validated_artifact(
            ctx,
            "master/narrative_plan.json",
            enriched,
            merge_from_disk=False,
            stage_key="narrative_arc_plan",
        )
        ctx.log(
            f"narrative_arc_plan: deterministic from talking points "
            f"({len(enriched.get('chapters') or [])} chapters)",
            level="info",
            stage="narrative_arc_plan",
        )
        if not ctx.is_done("narrative_arc_plan"):
            ctx.mark_done("narrative_arc_plan", force=True)
        return

    def build_input(c: RunContext) -> dict:
        manifest = c.read_json("segments/manifest.json") if c.artifact_exists("segments/manifest.json") else {}
        payload = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "coverage_audit": c.read_json("master/coverage_audit.json"),
            "segments": compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}, text_max=100),
            "emphasis_regions": emphasis_regions_for_segments(c),
        }
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        from interview_mux.coherence import attach_coherence_summary

        attach_coherence_summary(payload, c, "narrative_arc_plan")
        from interview_mux.episode_structure import attach_episode_structure_to_payload

        return attach_disfluency_context(
            attach_episode_structure_to_payload(
                c,
                __import__("interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]).attach_delivery_brief_to_payload(
                    c, attach_adaptation_to_payload(c, payload)
                ),
            ),
            c,
        )

    def _persist_narrative(c: RunContext, artifacts: dict) -> None:
        enriched = enrich_narrative_plan_for_persist(c, artifacts)
        write = make_stage_persist("master/narrative_plan.json", "narrative_arc_plan")
        write(c, enriched)

    persist = _persist_narrative

    with logged_step("narrative_arc_plan/llm_stage", ctx=ctx, stage="narrative_arc_plan"):
        run_flow_llm_stage(
            ctx,
            "narrative_arc_plan",
            prompt_variant("selection/narrative-arc-plan.system.txt", ctx),
            build_input,
            persist,
        )


def run_nugget_corpus_mine(ctx: RunContext) -> None:
    """Flagship mine of grounded nuggets from the full tape (kept + excluded)."""
    from interview_mux.nugget_layup import (
        CORPUS_REL,
        build_corpus_mine_input,
        nugget_layup_enabled,
    )

    if not nugget_layup_enabled():
        ctx.write_json(CORPUS_REL, {"nuggets": [], "warnings": ["nugget_layup_disabled"]})
        if not ctx.is_done("nugget_corpus_mine"):
            ctx.mark_done("nugget_corpus_mine", force=True)
        return

    persist = make_stage_persist(CORPUS_REL, "nugget_corpus_mine")
    with logged_step("nugget_corpus_mine/llm_stage", ctx=ctx, stage="nugget_corpus_mine"):
        run_flow_llm_stage(
            ctx,
            "nugget_corpus_mine",
            prompt_variant("nugget_layup/nugget-corpus-mine.system.txt", ctx),
            build_corpus_mine_input,
            persist,
        )


def run_nugget_layup_compose(ctx: RunContext) -> None:
    """Flagship per-native lay-up plan → authoritative gap_report before-VO lines."""
    from interview_mux.nugget_layup import (
        PLAN_REL,
        assert_gap_report_layup_authority,
        assert_layup_fresh_vs_selection,
        assert_layup_qc_or_raise,
        build_layup_compose_input,
        degraded_layup_cfg,
        evaluate_layup_qc,
        merge_layup_plan_parts,
        nugget_layup_cfg,
        nugget_layup_enabled,
        publish_layup_plan_to_gap_report,
    )
    from interview_mux.operator_trace import log_step

    if not nugget_layup_enabled():
        ctx.write_json(
            PLAN_REL,
            {
                "ordered_segment_ids": [],
                "layups": [],
                "warnings": ["nugget_layup_disabled"],
            },
        )
        if not ctx.is_done("nugget_layup_compose"):
            ctx.mark_done("nugget_layup_compose", force=True)
        return

    persist_plan = make_stage_persist(PLAN_REL, "nugget_layup_compose")
    deg = degraded_layup_cfg()
    cfg = nugget_layup_cfg()
    degraded_retry_used = {"n": 0}
    batch_size = max(4, int(cfg.get("compose_batch_max_natives") or 32))

    def persist(c: RunContext, artifacts: dict) -> None:
        doc = dict(artifacts) if isinstance(artifacts, dict) else {}
        if "ordered_segment_ids" not in doc:
            sel = c.read_json("master/selection.json") if c.artifact_exists("master/selection.json") else {}
            doc["ordered_segment_ids"] = list((sel or {}).get("ordered_segment_ids") or [])
        from interview_mux.nugget_layup import normalize_layup_talking_point_ledger

        doc = normalize_layup_talking_point_ledger(c, doc)
        assert_layup_fresh_vs_selection(c, doc)
        persist_plan(c, doc)
        report = publish_layup_plan_to_gap_report(c, doc)
        qc = evaluate_layup_qc(c, doc)
        # Layer-4: one dedicated degraded regenerate with stronger no-invent addendum.
        if (
            not qc.get("ok")
            and deg.get("enabled", True)
            and deg.get("extra_degraded_regenerate", True)
            and degraded_retry_used["n"] < 1
            and any("invented_island" in e or "canned_air" in e or "thin_layup" in e for e in (qc.get("errors") or []))
        ):
            degraded_retry_used["n"] += 1
            from interview_mux.llm_simple import StageError

            raise StageError(
                "nugget_layup_compose",
                "Degraded layup QC failed — regenerate with work-around doctrine "
                "(no invent / no canned / spine-first unlock). Errors: "
                + "; ".join((qc.get("errors") or [])[:4]),
            )
        # After exhaustion: thinner grounded unlock may still pass grace floors;
        # fail-closed only when analysis minimum / canned / invent remain.
        assert_layup_qc_or_raise(c, qc)
        assert_gap_report_layup_authority(c, report)

    def build_input(c: RunContext, *, target_ids: list[str] | None = None) -> dict:
        packet = build_layup_compose_input(c, target_segment_ids=target_ids)
        if degraded_retry_used["n"]:
            packet["degraded_regenerate"] = True
            packet["degraded_doctrine_addendum"] = (
                "REGENERATE: work around missing/incomprehensible spans using "
                "comprehensible_text + corpus only. Never invent unclear lexicon. "
                "Keep a thinner but concrete forward_unlock. No canned hinges."
            )
        packet["min_layup_words"] = int(cfg["min_layup_words"])
        return packet

    with logged_step("nugget_layup_compose/llm_stage", ctx=ctx, stage="nugget_layup_compose"):
        ordered = []
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                ordered = [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]
        # Fresh compose — drop any stale/partial plan so shard uniqueness starts clean.
        if ctx.artifact_exists(PLAN_REL):
            try:
                ctx.write_json(
                    PLAN_REL,
                    {"ordered_segment_ids": list(ordered), "layups": [], "warnings": ["compose_restart"]},
                )
            except Exception:
                pass
        if len(ordered) <= batch_size:
            run_flow_llm_stage(
                ctx,
                "nugget_layup_compose",
                prompt_variant("nugget_layup/nugget-layup-compose.system.txt", ctx),
                lambda c: build_input(c),
                persist,
            )
            return

        batches = [
            ordered[i : i + batch_size]
            for i in range(0, len(ordered), batch_size)
        ]
        log_step(
            f"nugget_layup_compose proactive batch: {len(ordered)} natives → "
            f"{len(batches)} shard(s) of ≤{batch_size}",
            ctx=ctx,
            stage="nugget_layup_compose",
            level="action",
            detail={
                "action_id": "nugget_layup_compose.proactive_batch",
                "batch_size": batch_size,
                "batches": len(batches),
                "natives": len(ordered),
            },
        )
        parts: list[dict[str, Any]] = []
        prompt_rel = prompt_variant("nugget_layup/nugget-layup-compose.system.txt", ctx)
        for bi, batch_ids in enumerate(batches):
            shard_box: dict[str, Any] = {"doc": {}}

            def build_batch(
                c: RunContext,
                _ids: list[str] = list(batch_ids),
                _i: int = bi,
                _total: int = len(batches),
            ) -> dict:
                packet = build_input(c, target_ids=_ids)
                packet["_layup_compose_shard"] = {
                    "index": _i + 1,
                    "total": _total,
                    "target_segment_ids": list(_ids),
                }
                packet["compose_instruction"] = (
                    f"Compose lay-ups ONLY for the {len(_ids)} natives in this shard "
                    f"({_i + 1}/{_total}). Look up claim/evidence in nugget_corpus. "
                    "Honor already_aired_nugget_ids from earlier air-order natives."
                )
                return packet

            def persist_shard(c: RunContext, artifacts: dict) -> None:
                doc = dict(artifacts) if isinstance(artifacts, dict) else {}
                # Intermediate write so later shards see claimed nuggets via prior_plan.
                # ordered_segment_ids stays shard-local here; final merge restores full order.
                merged_so_far = merge_layup_plan_parts(
                    parts + [doc],
                    ordered_segment_ids=ordered,
                )
                c.write_json(PLAN_REL, merged_so_far)
                shard_box["doc"] = doc

            log_step(
                f"nugget_layup_compose shard {bi + 1}/{len(batches)} "
                f"({len(batch_ids)} natives)",
                ctx=ctx,
                stage="nugget_layup_compose",
                level="action",
                detail={
                    "action_id": "nugget_layup_compose.shard",
                    "shard": bi + 1,
                    "total": len(batches),
                    "natives": len(batch_ids),
                },
            )
            run_flow_llm_stage(
                ctx,
                "nugget_layup_compose",
                prompt_rel,
                build_batch,
                persist_shard,
                auto_complete=False,
            )
            parts.append(shard_box["doc"] if isinstance(shard_box.get("doc"), dict) else {})

        merged = merge_layup_plan_parts(parts, ordered_segment_ids=ordered)
        log_step(
            f"nugget_layup_compose batched complete ({len(merged.get('layups') or [])} layups "
            f"across {len(batches)} shard(s))",
            ctx=ctx,
            stage="nugget_layup_compose",
            level="success",
            detail={
                "action_id": "nugget_layup_compose.proactive_batch_complete",
                "layups": len(merged.get("layups") or []),
                "batches": len(batches),
            },
        )
        persist(ctx, merged)
        if not ctx.is_done("nugget_layup_compose"):
            ctx.mark_done("nugget_layup_compose", force=True)
