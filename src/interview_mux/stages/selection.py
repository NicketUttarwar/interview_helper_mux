from __future__ import annotations

from interview_mux.stage_input_helpers import attach_disfluency_context
from interview_mux.stage_input_helpers import interviewer_sample_lines
from interview_mux.acoustic_profile import compact_for_volley, load_profile, pacing_one_liner
from interview_mux.nle_state import (
    apply_nle_to_selection,
    apply_segments_with_nle,
    load_nle,
    nle_has_operator_edits,
    segments_by_id_with_nle,
)
from interview_mux.gates import check_narrative_qc
from interview_mux.production_profile import prompt_variant
from interview_mux.llm_specialists import maybe_run_post_stage_specialists
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.stage_enrichment import compact_manifest_for_volley
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def _log_nle_apply(ctx: RunContext, *, stage: str, selection: dict) -> None:
    ordered = selection.get("ordered_segment_ids") or []
    excluded = selection.get("excluded_segment_ids") or []
    ctx.log(
        f"Applied NLE timeline edits: {len(ordered)} segments in order, "
        f"{len(excluded)} excluded (re-run from edl if only EDL was stale).",
        level="info",
        stage=stage,
    )


def run_full_master_ranking(ctx: RunContext) -> None:
    check_narrative_qc(ctx, stage="full_master_ranking", require_selection=False)

    def build_input(c: RunContext) -> dict:
        manifest = c.read_json("segments/manifest.json")
        nle = load_nle(c)
        segments_payload = manifest
        if nle_has_operator_edits(nle):
            raw = manifest.get("segments") or []
            segments_payload = {
                **manifest,
                "segments": apply_segments_with_nle(raw, nle),
            }
            c.log(
                "NLE timeline edits included in ranking input "
                "(exclude/split/reorder/trim).",
                level="info",
                stage="full_master_ranking",
            )
        segments_payload = compact_manifest_for_volley(
            segments_payload if isinstance(segments_payload, dict) else {},
            text_max=100,
        )
        payload = {
            "segments": segments_payload,
            "gap_report": c.read_json("understanding/gap_report.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
            "coverage_audit": c.read_json("master/coverage_audit.json"),
            "narrative_plan": c.read_json("master/narrative_plan.json"),
        }
        if nle_has_operator_edits(nle):
            payload["nle_edits"] = nle
        from interview_mux.interview_spine.compact import attach_spine_to_payload

        attach_spine_to_payload(c, payload, "full_master_ranking")
        from interview_mux.source_topology import attach_adaptation_to_payload
        from interview_mux.delivery_brief import attach_delivery_brief_to_payload
        from interview_mux.episode_structure import attach_episode_structure_to_payload

        payload = attach_episode_structure_to_payload(
            c, attach_delivery_brief_to_payload(c, attach_adaptation_to_payload(c, payload))
        )
        from interview_mux.gap_framing import attach_framing_to_ranking_payload

        payload = attach_framing_to_ranking_payload(c, payload)
        return attach_disfluency_context(payload, c)

    def persist(c: RunContext, artifacts: dict) -> None:
        # App-base topo repair BEFORE NLE overlay (NLE is overlay-only).
        plan = (
            c.read_json("master/narrative_plan.json")
            if c.artifact_exists("master/narrative_plan.json")
            else None
        )
        from interview_mux.selection_order_repair import repair_selection_order

        artifacts, topo_notes = repair_selection_order(
            artifacts, plan if isinstance(plan, dict) else None
        )
        if topo_notes:
            c.log(
                f"selection topo repair: {len(topo_notes)} action(s)",
                level="info",
                stage="full_master_ranking",
                detail=topo_notes[:8],
            )

        nle = load_nle(c)
        nle_overlay = False
        if nle_has_operator_edits(nle):
            by_id = segments_by_id_with_nle(c)
            artifacts = apply_nle_to_selection(
                artifacts, nle, segments_by_id=by_id
            )
            nle_overlay = True
            _log_nle_apply(c, stage="full_master_ranking", selection=artifacts)
        from interview_mux.creative_delivery import enforce_creative_selection_edit
        from interview_mux.selection_auto_pack import auto_pack_selection_to_brief

        artifacts = auto_pack_selection_to_brief(c, artifacts, stage="full_master_ranking")
        artifacts = enforce_creative_selection_edit(c, artifacts, stage="full_master_ranking")
        from interview_mux.framing_coverage_guard import enforce_framing_ranking

        artifacts = enforce_framing_ranking(c, artifacts)

        # Dual-candidate stub: keep committed order + pre-NLE snapshot when present
        ordered = [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s]
        c.write_json(
            "master/rank_candidates.json",
            {
                "version": 1,
                "candidates": [{"source": "committed", "ordered_segment_ids": ordered}],
                "winner": "committed",
            },
        )

        from interview_mux.story_health import evaluate_story_health
        from interview_mux.reorder_bridges import build_reorder_bridges
        from interview_mux.bridge_voice_policy import annotate_reorder_bridges
        from interview_mux.speaker_delivery_plan import write_speaker_delivery_plan

        by_id = segments_by_id_with_nle(c) if nle_overlay else {}
        if not by_id and c.artifact_exists("segments/manifest.json"):
            man = c.read_json("segments/manifest.json")
            by_id = {
                str(s["segment_id"]): s
                for s in (man.get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }
        chapter_ends: set[str] = set()
        if isinstance(plan, dict):
            for ch in plan.get("chapters") or []:
                if isinstance(ch, dict):
                    ids = [str(x) for x in (ch.get("segment_ids") or []) if x]
                    if ids:
                        chapter_ends.add(ids[-1])
        bridges = annotate_reorder_bridges(
            build_reorder_bridges(ordered, by_id, chapter_ends=chapter_ends),
            narrative_mode=str((plan or {}).get("narrative_mode") or "")
            if isinstance(plan, dict)
            else None,
        )
        # Prefer mastering_plan narrative_mode when present
        if c.artifact_exists("mastering/mastering_plan.json"):
            try:
                mp = c.read_json("mastering/mastering_plan.json")
                if isinstance(mp, dict) and mp.get("narrative_mode"):
                    bridges = annotate_reorder_bridges(
                        bridges, narrative_mode=str(mp.get("narrative_mode"))
                    )
            except Exception:
                pass
        c.write_json("understanding/reorder_bridges.json", bridges)

        gap = (
            c.read_json("understanding/gap_report.json")
            if c.artifact_exists("understanding/gap_report.json")
            else None
        )
        tr = (
            c.read_json("master/transitions.json")
            if c.artifact_exists("master/transitions.json")
            else None
        )
        cov = (
            c.read_json("master/coverage_audit.json")
            if c.artifact_exists("master/coverage_audit.json")
            else None
        )
        health = evaluate_story_health(
            ordered=ordered,
            narrative_plan=plan if isinstance(plan, dict) else None,
            coverage_audit=cov if isinstance(cov, dict) else None,
            reorder_bridges=bridges,
            gap_report=gap if isinstance(gap, dict) else None,
            transitions=tr if isinstance(tr, dict) else None,
            nle_overlay_applied=nle_overlay,
        )
        c.write_json("master/story_health.json", health)
        if health.get("verdict") == "fail":
            c.log(
                f"story_health fail ({health.get('error_count')} issues) — "
                "repair before delivery when possible",
                level="warning",
                stage="full_master_ranking",
                detail=health.get("issues", [])[:6],
            )
        elif health.get("verdict") == "warn":
            c.log(
                f"story_health warn — shipping with issues "
                f"(nle_overlay={nle_overlay})",
                level="warning",
                stage="full_master_ranking",
                detail=health.get("issues", [])[:6],
            )

        try:
            write_speaker_delivery_plan(c)
        except Exception as exc:
            c.log(
                f"speaker_delivery_plan skipped: {exc}",
                level="warning",
                stage="full_master_ranking",
            )

        write_validated_artifact(
            c,
            "master/selection.json",
            artifacts,
            merge_from_disk=True,
            stage_key="full_master_ranking",
        )

    with logged_step("full_master_ranking/llm_stage", ctx=ctx, stage="full_master_ranking"):
        run_flow_llm_stage(
            ctx,
            "full_master_ranking",
            prompt_variant("selection/full-master-ranking.system.txt", ctx),
            build_input,
            persist,
        )
    with logged_step("full_master_ranking/post_specialists", ctx=ctx, stage="full_master_ranking"):
        maybe_run_post_stage_specialists(ctx, "full_master_ranking", build_input(ctx))


def run_transitions(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        manifest = c.read_json("segments/manifest.json") if c.artifact_exists("segments/manifest.json") else {}
        payload = {
            "selection": c.read_json("master/selection.json"),
            "segments": compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}, text_max=100),
            "content_brief": c.read_json("understanding/content_brief.json"),
            "gap_report": c.read_json("understanding/gap_report.json"),
            "interviewer_sample_lines": interviewer_sample_lines(c),
        }
        from interview_mux.source_topology import attach_adaptation_to_payload
        from interview_mux.delivery_brief import attach_delivery_brief_to_payload

        return attach_disfluency_context(
            attach_delivery_brief_to_payload(c, attach_adaptation_to_payload(c, payload)),
            c,
        )

    persist = make_stage_persist("master/transitions.json", "transitions")

    def persist_with_framing_dedupe(c: RunContext, artifacts: dict) -> None:
        from interview_mux.gap_framing import dedupe_transitions_for_framing

        gap_report = (
            c.read_json("understanding/gap_report.json")
            if c.artifact_exists("understanding/gap_report.json")
            else None
        )
        artifacts = dedupe_transitions_for_framing(gap_report, artifacts)
        persist(c, artifacts)

    with logged_step("transitions/llm_stage", ctx=ctx, stage="transitions"):
        run_flow_llm_stage(
            ctx,
            "transitions",
            prompt_variant("assembly/transitions.system.txt", ctx),
            build_input,
            persist_with_framing_dedupe,
        )


def run_podcast_sfx_brief(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "selection": c.read_json("master/selection.json"),
            "transitions": c.read_json("master/transitions.json"),
            "narrative_plan": c.read_json("master/narrative_plan.json"),
        }
        profile = load_profile(c)
        if profile:
            compact = compact_for_volley(profile)
            payload["source_acoustic_profile"] = compact
            payload["pace_class"] = compact.get("pace_class") or pacing_one_liner(profile)
            mix = compact.get("mix_contract") if isinstance(compact.get("mix_contract"), dict) else {}
            if mix.get("underscore_policy"):
                payload["underscore_policy"] = mix["underscore_policy"]
        return payload

    persist = make_stage_persist("master/podcast_sfx_brief.json", "podcast_sfx_brief")

    with logged_step("podcast_sfx_brief/llm_stage", ctx=ctx, stage="podcast_sfx_brief"):
        run_flow_llm_stage(
            ctx,
            "podcast_sfx_brief",
            "assembly/podcast-sfx-brief.system.txt",
            build_input,
            persist,
        )
