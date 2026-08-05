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
from interview_mux.llm_specialists import maybe_run_post_stage_specialists, maybe_run_pre_stage_specialists
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.stage_enrichment import compact_manifest_for_volley
from interview_mux.stages.analysis_stage import run_flow_llm_stage
from interview_mux.stt_lexicon_islands import (
    enforce_stt_island_selection_guards,
    load_stt_trust_priors,
    scan_stt_lexicon_groups,
    specialist_input_from_ctx,
)


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
        priors = load_stt_trust_priors(c)
        if priors:
            payload["stt_trust_priors"] = priors
            payload["stt_lexicon_island_boosts"] = priors
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
        artifacts = enforce_stt_island_selection_guards(c, artifacts, stage="full_master_ranking")

        from interview_mux.story_health import evaluate_story_health
        from interview_mux.reorder_bridges import build_reorder_bridges
        from interview_mux.bridge_voice_policy import annotate_reorder_bridges
        from interview_mux.speaker_delivery_plan import write_speaker_delivery_plan
        from interview_mux.rank_candidates import chapter_order_from_plan, pick_best_order
        from interview_mux.shape_order_bind import resolve_air_order
        from interview_mux.listen_quality import ensure_hook_early
        from interview_mux.split_plan import clear_split_rerank_cascade

        by_id = segments_by_id_with_nle(c) if nle_overlay else {}
        if not by_id and c.artifact_exists("segments/manifest.json"):
            man = c.read_json("segments/manifest.json")
            by_id = {
                str(s["segment_id"]): s
                for s in (man.get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }

        ranking_ordered = [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s]
        candidates: list[dict] = [
            {"source": "ranking", "ordered_segment_ids": ranking_ordered},
        ]
        chapter_cand = chapter_order_from_plan(plan if isinstance(plan, dict) else None)
        if chapter_cand and chapter_cand != ranking_ordered:
            # Intersect with kept ranking ids when ranking already filtered
            kept = set(ranking_ordered) if ranking_ordered else set(chapter_cand)
            filtered_ch = [s for s in chapter_cand if s in kept] or chapter_cand
            candidates.append({"source": "narrative_chapters", "ordered_segment_ids": filtered_ch})

        mp = None
        if c.artifact_exists("mastering/mastering_plan.json"):
            try:
                mp = c.read_json("mastering/mastering_plan.json")
            except Exception:
                mp = None
        if isinstance(mp, dict):
            shape_ids = [str(s) for s in (mp.get("ordered_segment_ids") or []) if s]
            if shape_ids:
                kept = set(ranking_ordered) if ranking_ordered else set(shape_ids)
                filtered_sh = [s for s in shape_ids if s in kept] or shape_ids
                candidates.append({"source": "shape", "ordered_segment_ids": filtered_sh})

        hook_id = None
        if c.artifact_exists("understanding/episode_structure.json"):
            try:
                es = c.read_json("understanding/episode_structure.json")
                if isinstance(es, dict):
                    hook_id = es.get("hook_segment_id") or (
                        (es.get("cold_open") or {}).get("segment_id")
                        if isinstance(es.get("cold_open"), dict)
                        else None
                    )
            except Exception:
                hook_id = None
        if not hook_id and isinstance(mp, dict):
            cold = mp.get("cold_open") if isinstance(mp.get("cold_open"), dict) else {}
            hook_id = cold.get("segment_id") or cold.get("hook_segment_id")

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
        pick = pick_best_order(
            candidates,
            narrative_plan=plan if isinstance(plan, dict) else None,
            segments_by_id=by_id,
            gap_report=gap if isinstance(gap, dict) else None,
            transitions=tr if isinstance(tr, dict) else None,
            hook_segment_id=str(hook_id) if hook_id else None,
        )
        c.write_json("master/rank_candidates.json", pick)
        dual_ordered = [str(s) for s in (pick.get("ordered_segment_ids") or ranking_ordered) if s]
        if dual_ordered:
            artifacts["ordered_segment_ids"] = dual_ordered
            artifacts["rank_candidate_winner"] = pick.get("winner")

        # Hybrid Shape bind (per-run; global consumers_bind stays false)
        bind = resolve_air_order(
            mastering_plan=mp if isinstance(mp, dict) else None,
            selection_ordered=list(artifacts.get("ordered_segment_ids") or []),
            narrative_plan=plan if isinstance(plan, dict) else None,
            prefer_shape=True,
        )
        if bind.get("order_authority") == "shape" and bind.get("ordered_segment_ids"):
            artifacts["ordered_segment_ids"] = list(bind["ordered_segment_ids"])
            c.log(
                f"hybrid Shape bind: using plan order ({bind.get('bind_reason')})",
                level="info",
                stage="full_master_ranking",
            )
        artifacts["order_authority"] = bind.get("order_authority") or "ranking"
        artifacts["order_bind_reason"] = bind.get("bind_reason")

        # Guarantee hook in first 30–60s window (first three slots)
        ordered, hook_moved = ensure_hook_early(
            [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s],
            str(hook_id) if hook_id else None,
        )
        if hook_moved:
            artifacts["ordered_segment_ids"] = ordered
            c.log(
                f"hook guarantee: moved {hook_id} to open",
                level="info",
                stage="full_master_ranking",
            )

        chapter_ends: set[str] = set()
        if isinstance(plan, dict):
            for ch in plan.get("chapters") or []:
                if isinstance(ch, dict):
                    ids = [str(x) for x in (ch.get("segment_ids") or []) if x]
                    if ids:
                        chapter_ends.add(ids[-1])
        narrative_mode = None
        if isinstance(mp, dict) and mp.get("narrative_mode"):
            narrative_mode = str(mp.get("narrative_mode"))
        elif isinstance(plan, dict) and plan.get("narrative_mode"):
            narrative_mode = str(plan.get("narrative_mode"))
        bridges = annotate_reorder_bridges(
            build_reorder_bridges(ordered, by_id, chapter_ends=chapter_ends),
            narrative_mode=narrative_mode,
        )
        c.write_json("understanding/reorder_bridges.json", bridges)

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
            hook_segment_id=str(hook_id) if hook_id else None,
        )
        c.write_json("master/story_health.json", health)
        if health.get("verdict") == "fail":
            # Bounded app-base re-topo then re-score once
            from interview_mux.selection_order_repair import repair_selection_order

            repaired, notes = repair_selection_order(
                artifacts, plan if isinstance(plan, dict) else None
            )
            if notes:
                artifacts = repaired
                ordered = [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s]
                bridges = annotate_reorder_bridges(
                    build_reorder_bridges(ordered, by_id, chapter_ends=chapter_ends),
                    narrative_mode=narrative_mode,
                )
                c.write_json("understanding/reorder_bridges.json", bridges)
                health = evaluate_story_health(
                    ordered=ordered,
                    narrative_plan=plan if isinstance(plan, dict) else None,
                    coverage_audit=cov if isinstance(cov, dict) else None,
                    reorder_bridges=bridges,
                    gap_report=gap if isinstance(gap, dict) else None,
                    transitions=tr if isinstance(tr, dict) else None,
                    nle_overlay_applied=nle_overlay,
                    hook_segment_id=str(hook_id) if hook_id else None,
                )
                c.write_json("master/story_health.json", health)
                c.log(
                    f"story_health fail → topo re-pass ({len(notes)} notes); "
                    f"verdict now {health.get('verdict')}",
                    level="warning",
                    stage="full_master_ranking",
                )
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

        try:
            clear_split_rerank_cascade(c)
        except Exception:
            pass

        # Final topo repair after Shape/hook/story_health — order may have drifted.
        from interview_mux.selection_order_repair import (
            finale_tail_errors,
            repair_selection_order,
        )

        artifacts, final_notes = repair_selection_order(
            artifacts, plan if isinstance(plan, dict) else None
        )
        if final_notes:
            c.log(
                f"selection final topo repair: {len(final_notes)} action(s)",
                level="info",
                stage="full_master_ranking",
                detail=final_notes[:8],
            )
        final_ordered = [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s]
        tail_errs = finale_tail_errors(final_ordered, plan if isinstance(plan, dict) else None)
        if tail_errs:
            # One more forced rebuild; still fail post-commit if unresolved.
            artifacts, _ = repair_selection_order(
                artifacts, plan if isinstance(plan, dict) else None
            )
            c.log(
                f"selection finale-tail still present after repair: {tail_errs[:2]}",
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

    with logged_step("full_master_ranking/stt_lexicon_scan", ctx=ctx, stage="full_master_ranking"):
        try:
            scan = scan_stt_lexicon_groups(ctx)
            ctx.log(
                f"STT lexicon island scan: {scan.get('group_count', 0)} group(s), "
                f"{scan.get('candidate_count', 0)} candidate(s)",
                level="info",
                stage="full_master_ranking",
                action_id="stt_island.scan",
                detail={
                    "group_count": scan.get("group_count"),
                    "candidate_count": scan.get("candidate_count"),
                },
            )
        except Exception as exc:
            ctx.log(
                f"STT lexicon island scan failed (fail-open): {exc}",
                level="warning",
                stage="full_master_ranking",
            )

    with logged_step("full_master_ranking/pre_specialists", ctx=ctx, stage="full_master_ranking"):
        try:
            maybe_run_pre_stage_specialists(ctx, "full_master_ranking", specialist_input_from_ctx(ctx))
        except Exception as exc:
            ctx.log(
                f"STT lexicon island pre-specialist failed (fail-open): {exc}",
                level="warning",
                stage="full_master_ranking",
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
    # Synthetic framing is authoritative only after the native air order is
    # stable.  This nested LLM stage builds the complete context packet first.
    from interview_mux.synthetic_framing import run_synthetic_framing_plan

    synthetic_plan = run_synthetic_framing_plan(ctx)

    def build_input(c: RunContext) -> dict:
        manifest = c.read_json("segments/manifest.json") if c.artifact_exists("segments/manifest.json") else {}
        payload = {
            "selection": c.read_json("master/selection.json"),
            "segments": compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}, text_max=100),
            "content_brief": c.read_json("understanding/content_brief.json"),
            "gap_report": c.read_json("understanding/gap_report.json"),
            "interviewer_sample_lines": interviewer_sample_lines(c),
            "synthetic_framing_plan": synthetic_plan,
        }
        if c.artifact_exists("understanding/reorder_bridges.json"):
            payload["reorder_bridges"] = c.read_json("understanding/reorder_bridges.json")
        if c.artifact_exists("understanding/speaker_delivery_plan.json"):
            try:
                sdp = c.read_json("understanding/speaker_delivery_plan.json")
                if isinstance(sdp, dict):
                    payload["speaker_delivery_plan"] = {
                        "clone_speaker_id": sdp.get("clone_speaker_id"),
                        "insert_strategy": sdp.get("insert_strategy"),
                        "address_mode": sdp.get("address_mode"),
                        "group_label": sdp.get("group_label"),
                    }
                    payload["address_labels"] = sdp.get("address_labels") or {}
            except Exception:
                pass
        else:
            try:
                from interview_mux.speaker_delivery_plan import build_speaker_delivery_plan

                sdp = build_speaker_delivery_plan(c)
                payload["address_labels"] = sdp.get("address_labels") or {}
                payload["speaker_delivery_plan"] = {
                    "clone_speaker_id": sdp.get("clone_speaker_id"),
                    "insert_strategy": sdp.get("insert_strategy"),
                    "group_label": sdp.get("group_label"),
                }
            except Exception:
                pass
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
