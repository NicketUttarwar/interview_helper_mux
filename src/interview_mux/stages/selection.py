from __future__ import annotations

import json
from typing import Any

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
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.stage_enrichment import compact_manifest_for_volley
from interview_mux.stages.analysis_stage import run_flow_llm_stage
from interview_mux.stage_completion import heal_or_refuse_mark
from interview_mux.stt_lexicon_islands import (
    enforce_stt_island_selection_guards,
    load_stt_trust_priors,
    scan_stt_lexicon_groups,
    specialist_input_from_ctx,
)


def ranking_artifacts_persistable(artifacts: dict | None) -> bool:
    """True when ranking output has a usable air order (persist can finish the rest)."""
    if not isinstance(artifacts, dict):
        return False
    ordered = [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if str(s).strip()]
    return len(ordered) >= 1


def last_persistable_ranking_artifacts(ctx: RunContext) -> dict | None:
    """Newest ranking envelope artifacts with a non-empty ordered_segment_ids."""
    roots: list[Any] = []
    try:
        committed = ctx.path("understanding", "llm_calls", "full_master_ranking")
        if committed.is_dir():
            roots.append(committed)
    except Exception:
        pass
    pending = ctx.run_dir / ".pending_writes" / "full_master_ranking" / "understanding" / "llm_calls" / "full_master_ranking"
    if pending.is_dir():
        roots.append(pending)
    best: dict | None = None
    best_mtime = -1.0
    for root in roots:
        for path in root.glob("attempt_*/*_primary.json"):
            try:
                mtime = path.stat().st_mtime
                doc = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            env = ((doc.get("response") or {}).get("parsed_envelope") or {})
            arts = env.get("artifacts") if isinstance(env, dict) else None
            if not ranking_artifacts_persistable(arts if isinstance(arts, dict) else None):
                continue
            if mtime >= best_mtime:
                best_mtime = mtime
                best = arts if isinstance(arts, dict) else None
        for path in root.glob("attempt_*/*_collate.json"):
            try:
                mtime = path.stat().st_mtime
                doc = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            env = ((doc.get("response") or {}).get("parsed_envelope") or {})
            arts = env.get("artifacts") if isinstance(env, dict) else None
            if not ranking_artifacts_persistable(arts if isinstance(arts, dict) else None):
                continue
            if mtime >= best_mtime:
                best_mtime = mtime
                best = arts if isinstance(arts, dict) else None
    return best


def commit_persistable_ranking_from_last_envelope(ctx: RunContext) -> bool:
    """Write selection.json from the last persistable ranking envelope and mark done."""
    arts = last_persistable_ranking_artifacts(ctx)
    if not arts:
        return False
    persist_full_master_ranking(ctx, arts)
    heal_or_refuse_mark(ctx, "full_master_ranking", force=True)
    ctx.log(
        "Committed ranking from last persistable envelope "
        f"({len(arts.get('ordered_segment_ids') or [])} ordered)",
        level="warning",
        stage="full_master_ranking",
    )
    return True


def commit_ranking_with_deterministic_fallback(ctx: RunContext) -> bool:
    """Envelope salvage, else chapter/Shape/hard-keep fallback, then mark done."""
    if commit_persistable_ranking_from_last_envelope(ctx):
        return True
    from interview_mux.open_shape_repair import build_deterministic_ranking_fallback

    arts = build_deterministic_ranking_fallback(ctx)
    if not arts or not ranking_artifacts_persistable(arts):
        return False
    persist_full_master_ranking(ctx, arts)
    heal_or_refuse_mark(ctx, "full_master_ranking", force=True)
    ctx.log(
        "Committed ranking from deterministic fallback "
        f"({arts.get('order_bind_reason')}; "
        f"{len(arts.get('ordered_segment_ids') or [])} ordered)",
        level="warning",
        stage="full_master_ranking",
    )
    return True


def _source_start_ms_map(ctx) -> dict[str, int]:
    starts: dict[str, int] = {}
    for rel in ("segments/boundaries.json", "segments/segments.json", "segments/manifest.json"):
        if not ctx.artifact_exists(rel):
            continue
        doc = ctx.read_json(rel)
        rows = []
        if isinstance(doc, dict):
            rows = list(doc.get("boundaries") or doc.get("segments") or [])
        for row in rows:
            if not isinstance(row, dict) or not row.get("segment_id"):
                continue
            try:
                starts[str(row["segment_id"])] = int(
                    row.get("start_ms") or row.get("source_start_ms") or 0
                )
            except (TypeError, ValueError):
                continue
    return starts


def finalize_selection_order(
    ctx: RunContext,
    artifacts: dict[str, Any],
    *,
    stage: str = "full_master_ranking",
    plan: dict[str, Any] | None = None,
    apply_cta: bool = True,
    write_integrity_report: bool = True,
    block_on_critical: bool | None = None,
    skip_lifecycle: bool = False,
) -> dict[str, Any]:
    """Single authoritative selection finalize: topo, hard-keep, CTA, integrity, health."""
    from interview_mux.air_order_integrity import (
        block_ranking_on_critical,
        collect_violations,
        critical_violations,
        on_selection_order_changed,
        repair_air_order_integrity,
        write_air_order_integrity_report,
    )
    from interview_mux.hard_keep import enforce_hard_keeps
    from interview_mux.order_hash import bump_order_lock
    from interview_mux.selection_order_repair import (
        finale_tail_errors,
        repair_selection_order,
    )
    from interview_mux.story_health import evaluate_story_health

    if plan is None and ctx.artifact_exists("master/narrative_plan.json"):
        raw = ctx.read_json("master/narrative_plan.json")
        plan = raw if isinstance(raw, dict) else None

    previous = dict(artifacts)
    starts = _source_start_ms_map(ctx) or None

    artifacts, _ = repair_selection_order(
        artifacts, plan, source_start_ms=starts
    )
    artifacts = enforce_hard_keeps(ctx, artifacts)
    artifacts, _ = repair_air_order_integrity(ctx, artifacts)

    if apply_cta:
        from interview_mux.media_ip_cta import apply_cta_judgments, apply_editorial_omits

        artifacts = apply_cta_judgments(ctx, artifacts)
        artifacts = bump_order_lock(artifacts, source=stage)
        artifacts = apply_editorial_omits(ctx, artifacts)
        artifacts = bump_order_lock(artifacts, source=stage)
        artifacts = enforce_hard_keeps(ctx, artifacts)
        artifacts, _ = repair_selection_order(
            artifacts, plan, source_start_ms=starts
        )
        artifacts, _ = repair_air_order_integrity(ctx, artifacts)

    final_ordered = [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s]
    tail_errs = finale_tail_errors(final_ordered, plan)
    if tail_errs:
        artifacts, _ = repair_selection_order(
            artifacts, plan, source_start_ms=starts
        )
        artifacts, _ = repair_air_order_integrity(ctx, artifacts)

    gap = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else None
    )
    tr = (
        ctx.read_json("master/transitions.json")
        if ctx.artifact_exists("master/transitions.json")
        else None
    )
    cov = (
        ctx.read_json("master/coverage_audit.json")
        if ctx.artifact_exists("master/coverage_audit.json")
        else None
    )
    bridges = (
        ctx.read_json("understanding/reorder_bridges.json")
        if ctx.artifact_exists("understanding/reorder_bridges.json")
        else None
    )
    hook_id = artifacts.get("native_cold_open_segment_id")
    health = evaluate_story_health(
        ordered=[str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s],
        narrative_plan=plan,
        coverage_audit=cov if isinstance(cov, dict) else None,
        reorder_bridges=bridges if isinstance(bridges, dict) else None,
        gap_report=gap if isinstance(gap, dict) else None,
        transitions=tr if isinstance(tr, dict) else None,
        hook_segment_id=str(hook_id) if hook_id else None,
        ctx=ctx,
    )
    ctx.write_json("master/story_health.json", health, stage_key=stage)

    from interview_mux.air_order_policy import resolve_air_order_policy

    policy = resolve_air_order_policy(ctx, selection=artifacts)
    violations = collect_violations(ctx, artifacts, policy=policy)
    integrity_actions: list[dict[str, Any]] = []
    if write_integrity_report:
        write_air_order_integrity_report(
            ctx,
            violations=violations,
            actions=integrity_actions,
            stage=stage,
            repaired=True,
            resolved_policy=policy,
        )

    should_block = block_ranking_on_critical() if block_on_critical is None else block_on_critical
    if should_block and critical_violations(violations):
        raise ValueError(
            "air_order_integrity critical violations: "
            + "; ".join(
                str(v.get("message") or v.get("code") or "")
                for v in critical_violations(violations)[:3]
            )
        )
    if should_block and health.get("verdict") == "fail":
        raise ValueError(
            "story_health fail: "
            + "; ".join(
                str(i.get("message") or i.get("code") or "")
                for i in (health.get("issues") or [])[:3]
                if isinstance(i, dict)
            )
        )

    artifacts = bump_order_lock(artifacts, source=stage)
    if not skip_lifecycle:
        on_selection_order_changed(
            ctx, source=f"{stage}:finalize", previous=previous, current=artifacts
        )
    return artifacts






def persist_full_master_ranking(ctx: RunContext, artifacts: dict) -> None:
    """Commit ranking artifacts without re-running the LLM."""
    if not ranking_artifacts_persistable(artifacts):
        raise ValueError("ranking artifacts missing ordered_segment_ids")
    from interview_mux.framing_coverage_guard import inject_ranking_lattice_keeps

    artifacts = inject_ranking_lattice_keeps(
        ctx, artifacts, stage="full_master_ranking"
    )
    artifacts = finalize_selection_order(
        ctx, artifacts, stage="full_master_ranking", skip_lifecycle=True
    )
    from interview_mux.open_shape_repair import cover_ranking_manifest_membership
    from interview_mux.selection_constraints import seal_selection_lattice

    artifacts = cover_ranking_manifest_membership(ctx, artifacts)
    artifacts = seal_selection_lattice(ctx, artifacts, fail_closed=True)
    from interview_mux.air_order_boundary import commit_selection_mutation

    commit_selection_mutation(
        ctx,
        artifacts,
        producer="full_master_ranking",
        stage_key="full_master_ranking",
        checkpoint_mode="detect",
        merge_from_disk=True,
        skip_checkpoint=True,
    )
    # FMR S6: bridges / SDP / gap VO rebudget land on selection_order_sanitize.


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
        from interview_mux.gap_framing import compact_gap_report_for_ranking

        gap_raw = (
            c.read_json("understanding/gap_report.json")
            if c.artifact_exists("understanding/gap_report.json")
            else {}
        )
        payload = {
            "segments": segments_payload,
            "gap_report": compact_gap_report_for_ranking(
                gap_raw if isinstance(gap_raw, dict) else {}
            ),
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
        try:
            from interview_mux.segment_fuse import (
                FUSE_AUDIT_PATH,
                FUSE_ROUNDS_PRE_RANKING_PATH,
            )

            if c.artifact_exists(FUSE_ROUNDS_PRE_RANKING_PATH):
                rounds = c.read_json(FUSE_ROUNDS_PRE_RANKING_PATH)
                if isinstance(rounds, dict) and str(rounds.get("pass_id") or "") == "pre_ranking":
                    applied_rows: list[dict] = []
                    if c.artifact_exists(FUSE_AUDIT_PATH):
                        try:
                            audit = c.read_json(FUSE_AUDIT_PATH)
                            for row in (audit.get("applied_fuses") or []) if isinstance(audit, dict) else []:
                                if isinstance(row, dict):
                                    applied_rows.append(
                                        {
                                            "pair_id": row.get("pair_id"),
                                            "reason_code": row.get("reason_code"),
                                            "fused_into": row.get("fused_into"),
                                        }
                                    )
                        except Exception:
                            pass
                    payload["connector_fuse_pre_ranking"] = {
                        "pass_id": "pre_ranking",
                        "total_applied": rounds.get("total_applied"),
                        "fixed_point": rounds.get("fixed_point"),
                        "oscillation_halt": rounds.get("oscillation_halt"),
                        "settled_skipped": rounds.get("settled_skipped"),
                        "reopened_seams": (rounds.get("reopened_seams") or [])[:20],
                        "adjudication_stats": rounds.get("adjudication_stats") or {},
                        "applied_fuses": applied_rows[-20:],
                        "guidance": (
                            "Fused slabs reflect incomplete-thought merges; "
                            "prefer order over re-splitting fused ids."
                        ),
                    }
        except Exception:
            pass
        priors = load_stt_trust_priors(c)
        if priors:
            payload["stt_trust_priors"] = priors
            payload["stt_lexicon_island_boosts"] = priors
        if c.artifact_exists("analysis/high_value_speech_boosts.json"):
            try:
                hv = c.read_json("analysis/high_value_speech_boosts.json")
                if isinstance(hv, dict) and hv.get("priors"):
                    payload["high_value_speech_boosts"] = hv
            except Exception:
                pass
        if c.artifact_exists("analysis/high_value_speech_islands.json"):
            try:
                hv_islands = c.read_json("analysis/high_value_speech_islands.json")
                if isinstance(hv_islands, dict):
                    payload["high_value_speech_islands"] = {
                        "island_count": hv_islands.get("island_count"),
                        "segment_ids_touched": hv_islands.get("segment_ids_touched") or [],
                    }
            except Exception:
                pass
        payload = attach_disfluency_context(payload, c)
        try:
            from interview_mux.media_ip_cta import ranking_cta_omit_ids

            cta_omit = ranking_cta_omit_ids(c)
        except Exception:
            cta_omit = set()
        if cta_omit:
            payload["cta_omit_segment_ids"] = sorted(cta_omit)
            keeps = [
                str(s)
                for s in (payload.get("must_keep_segment_ids") or [])
                if str(s) and str(s) not in cta_omit
            ]
            payload["must_keep_segment_ids"] = keeps
        # Soft-upstream membership floor: expand must_keep when coverage/framing hollow.
        try:
            from interview_mux.stages.selection_membership import (
                expand_must_keep_for_soft_upstream,
            )

            payload = expand_must_keep_for_soft_upstream(c, payload)
        except Exception:
            pass
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        # Membership-only path (FMR S1–S4): repair → bind → keeps → finalize CTA →
        # cover → one seal → commit. Side artifacts run fail-open after commit.
        plan = (
            c.read_json("master/narrative_plan.json")
            if c.artifact_exists("master/narrative_plan.json")
            else None
        )
        from interview_mux.selection_order_repair import repair_selection_order

        artifacts, topo_notes = repair_selection_order(
            artifacts, plan if isinstance(plan, dict) else None,
            source_start_ms=_source_start_ms_map(c) or None,
        )
        if topo_notes:
            c.log(
                f"selection topo repair: {len(topo_notes)} action(s)",
                level="info",
                stage="full_master_ranking",
                detail=topo_notes[:8],
            )

        nle = load_nle(c)
        if nle_has_operator_edits(nle):
            by_id = segments_by_id_with_nle(c)
            artifacts = apply_nle_to_selection(
                artifacts, nle, segments_by_id=by_id
            )
            _log_nle_apply(c, stage="full_master_ranking", selection=artifacts)
        from interview_mux.creative_delivery import enforce_creative_selection_edit
        from interview_mux.selection_auto_pack import auto_pack_selection_to_brief

        artifacts = auto_pack_selection_to_brief(c, artifacts, stage="full_master_ranking")
        artifacts = enforce_creative_selection_edit(c, artifacts, stage="full_master_ranking")
        try:
            from interview_mux.stages.selection_membership import (
                enforce_membership_duration_floor,
            )

            artifacts = enforce_membership_duration_floor(
                c, artifacts, stage="full_master_ranking"
            )
        except Exception:
            pass
        # S1: no mid-pipeline seal — only seal once immediately before commit.
        artifacts = enforce_stt_island_selection_guards(c, artifacts, stage="full_master_ranking")

        from interview_mux.shape_order_bind import resolve_air_order
        from interview_mux.listen_quality import ensure_hook_early
        from interview_mux.open_shape_repair import (
            preserve_ranking_membership,
            repair_open_shape_selection,
        )
        from interview_mux.framing_coverage_guard import inject_ranking_lattice_keeps

        by_id: dict[str, Any] = {}
        if c.artifact_exists("segments/manifest.json"):
            man = c.read_json("segments/manifest.json")
            by_id = {
                str(s["segment_id"]): s
                for s in (man.get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }
            if nle_has_operator_edits(nle):
                by_id = segments_by_id_with_nle(c) or by_id

        ranking_ordered = [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s]
        membership_prior = list(ranking_ordered)
        manifest_ids = set(by_id.keys()) if by_id else None

        mp = None
        if c.artifact_exists("mastering/mastering_plan.json"):
            try:
                mp = c.read_json("mastering/mastering_plan.json")
            except Exception:
                mp = None

        # S3: one order bind — ideal_cuts seed XOR Shape head; never pick_best_order.
        from interview_mux.ideal_cuts import (
            SELECTION_SEED_REL,
            bind_ranking_enabled,
            ideal_cuts_cfg,
            resolve_ideal_cuts_air_order,
        )

        icfg = ideal_cuts_cfg()
        bound = False
        if bind_ranking_enabled(icfg) and icfg.get("prefer_seed_over_ranking", True):
            if c.artifact_exists(SELECTION_SEED_REL):
                seed = c.read_json(SELECTION_SEED_REL)
                seed_bind = resolve_ideal_cuts_air_order(
                    seed=seed if isinstance(seed, dict) else None,
                    selection_ordered=list(ranking_ordered),
                )
                if seed_bind.get("order_authority") == "ideal_cuts":
                    artifacts["ordered_segment_ids"] = preserve_ranking_membership(
                        membership_prior,
                        list(seed_bind.get("ordered_segment_ids") or []),
                        manifest_ids=manifest_ids,
                    )
                    artifacts["order_authority"] = "ideal_cuts"
                    artifacts["order_bind_reason"] = seed_bind.get("bind_reason")
                    bound = True
                    c.log(
                        f"ideal_cuts seed bind: {seed_bind.get('bind_reason')}",
                        level="info",
                        stage="full_master_ranking",
                    )
        if not bound:
            bind = resolve_air_order(
                mastering_plan=mp if isinstance(mp, dict) else None,
                selection_ordered=list(artifacts.get("ordered_segment_ids") or ranking_ordered),
                narrative_plan=plan if isinstance(plan, dict) else None,
                prefer_shape=True,
            )
            if bind.get("order_authority") == "shape" and bind.get("ordered_segment_ids"):
                artifacts["ordered_segment_ids"] = preserve_ranking_membership(
                    membership_prior,
                    list(bind["ordered_segment_ids"]),
                    manifest_ids=manifest_ids,
                )
                artifacts["order_authority"] = "shape"
                artifacts["order_bind_reason"] = bind.get("bind_reason")
                c.log(
                    f"hybrid Shape bind: using plan order ({bind.get('bind_reason')})",
                    level="info",
                    stage="full_master_ranking",
                )
            else:
                artifacts["order_authority"] = bind.get("order_authority") or "ranking"
                artifacts["order_bind_reason"] = bind.get("bind_reason") or "llm_ranking"

        # Metrics-only candidate ledger (does not edit membership).
        try:
            c.write_json(
                "master/rank_candidates.json",
                {
                    "winner": artifacts.get("order_authority") or "ranking",
                    "ordered_segment_ids": list(
                        artifacts.get("ordered_segment_ids") or ranking_ordered
                    ),
                    "sources": [artifacts.get("order_authority") or "ranking"],
                    "bind_reason": artifacts.get("order_bind_reason"),
                },
            )
        except Exception:
            pass

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

        artifacts, _open_actions = repair_open_shape_selection(
            c,
            artifacts,
            hook_segment_id=str(hook_id) if hook_id else None,
            stage="full_master_ranking",
        )

        # S2: lattice keeps before CTA/finalize so omit cannot re-break membership.
        artifacts = inject_ranking_lattice_keeps(
            c, artifacts, stage="full_master_ranking"
        )

        final_ordered = [
            str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s
        ]
        if hook_id and final_ordered and str(hook_id) == final_ordered[0]:
            artifacts["native_cold_open_segment_id"] = str(hook_id)
        else:
            artifacts.pop("native_cold_open_segment_id", None)

        artifacts = finalize_selection_order(
            c,
            artifacts,
            stage="full_master_ranking",
            plan=plan if isinstance(plan, dict) else None,
        )
        from interview_mux.open_shape_repair import cover_ranking_manifest_membership
        from interview_mux.selection_constraints import seal_selection_lattice
        from interview_mux.air_order_boundary import commit_selection_mutation

        artifacts = cover_ranking_manifest_membership(c, artifacts)
        # S1: single seal immediately before commit.
        artifacts = seal_selection_lattice(c, artifacts, fail_closed=True)
        commit_selection_mutation(
            c,
            artifacts,
            producer="full_master_ranking",
            stage_key="full_master_ranking",
            checkpoint_mode="detect",
            merge_from_disk=True,
            skip_checkpoint=True,
        )
        # FMR S6: bridges / SDP / gap VO rebudget land on selection_order_sanitize.

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
    # S1: detect-only — never mutate selection; dirty air-order pins sanitize.
    if ctx.artifact_exists("master/selection.json"):
        from interview_mux.air_order_integrity import audit_and_report
        from interview_mux.artifact_repairs import reconcile_ordered_vs_excluded
        from interview_mux.loud_fail import raise_loud_failure

        report = audit_and_report(ctx, stage="transitions", repair=False)
        sel = ctx.read_json("master/selection.json")
        exclude_drift = False
        if isinstance(sel, dict):
            repaired = reconcile_ordered_vs_excluded(sel)
            exclude_drift = (
                repaired.get("exclude_rationales") != sel.get("exclude_rationales")
                or repaired.get("ordered_segment_ids") != sel.get("ordered_segment_ids")
                or repaired.get("excluded_segment_ids") != sel.get("excluded_segment_ids")
            )
        critical_count = int((report or {}).get("critical_count") or 0)
        if critical_count > 0 or exclude_drift:
            raise_loud_failure(
                ctx,
                "transitions: selection air-order dirty — resume selection_order_sanitize",
                stage="transitions",
                reason="selection_air_order_dirty",
                detail={
                    "critical_count": critical_count,
                    "exclude_drift": exclude_drift,
                    "resume": "selection_order_sanitize",
                },
            )

    # S3A: under layup, demote-empty only — never re-LLM synthetic content.
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
        try:
            from interview_mux.speaker_delivery_plan import episode_vo_identity

            payload["episode_vo_identity"] = episode_vo_identity(c)
            payload["vo_shape_lock"] = payload["episode_vo_identity"].get("vo_shape")
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
        from interview_mux.gap_framing import (
            dedupe_transitions_by_adjacency,
            dedupe_transitions_for_framing,
        )
        from interview_mux.spoken_copy_guard import assert_guarded_spoken_copy

        gap_report = (
            c.read_json("understanding/gap_report.json")
            if c.artifact_exists("understanding/gap_report.json")
            else None
        )
        artifacts = dedupe_transitions_for_framing(gap_report, artifacts, ctx=c)
        artifacts = dedupe_transitions_by_adjacency(artifacts)
        from interview_mux.air_order_integrity import (
            opening_body_start_index,
            opening_tape_segment_ids,
            pair_source_gap_ms,
            resolved_segment_starts,
            reverse_jump_margin_ms,
        )

        starts = resolved_segment_starts(c)
        sel_order: list[str] = []
        if c.artifact_exists("master/selection.json"):
            sel = c.read_json("master/selection.json")
            if isinstance(sel, dict):
                sel_order = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
        pos = {sid: idx for idx, sid in enumerate(sel_order)}
        opening_ids = opening_tape_segment_ids(sel_order, starts) if sel_order else set()
        margin = reverse_jump_margin_ms(ctx=c)
        body_start = opening_body_start_index(ctx=c)
        kept_transitions: list[dict[str, Any]] = []
        for row in artifacts.get("transitions") or []:
            if not isinstance(row, dict):
                continue
            a = str(row.get("after_segment_id") or "")
            b = str(row.get("before_segment_id") or "")
            gap = row.get("source_gap_ms")
            if gap is None and a and b:
                gap = pair_source_gap_ms(a, b, starts)
                if gap is not None:
                    row["source_gap_ms"] = gap
            if gap is not None and int(gap) < -margin:
                continue
            if b in opening_ids and pos.get(b, 0) >= body_start:
                continue
            kept_transitions.append(row)
        artifacts["transitions"] = kept_transitions
        manifest = (
            c.read_json("segments/manifest.json")
            if c.artifact_exists("segments/manifest.json")
            else {}
        )
        by_id = {
            str(row.get("segment_id")): row
            for row in ((manifest or {}).get("segments") or [])
            if isinstance(row, dict) and row.get("segment_id")
        }
        from interview_mux.spoken_copy_guard import enrich_evidence_from_run

        seen_texts: list[str] = []
        if isinstance(gap_report, dict):
            for ln in gap_report.get("interviewer_lines") or []:
                if isinstance(ln, dict) and not ln.get("skipped_optional"):
                    txt = str(ln.get("text") or "").strip()
                    if txt:
                        seen_texts.append(txt)
        for row in artifacts.get("transitions") or []:
            if not isinstance(row, dict) or not str(row.get("text") or "").strip():
                continue
            a = str(row.get("after_segment_id") or "")
            b = str(row.get("before_segment_id") or "")
            evidence = enrich_evidence_from_run(
                c,
                {
                    "before_excerpt": (by_id.get(a) or {}).get("text"),
                    "after_excerpt": (by_id.get(b) or {}).get("text"),
                    "before_topic": (by_id.get(a) or {}).get("topic"),
                    "after_topic": (by_id.get(b) or {}).get("topic"),
                    "source_gap_ms": row.get("source_gap_ms"),
                    "before_segment_id": b,
                    "before_air_index": pos.get(b),
                    "before_is_opening_tape": b in opening_ids,
                    "strict_grounding": True,
                },
            )
            decision = assert_guarded_spoken_copy(
                str(row.get("text") or ""),
                evidence=evidence,
                purpose=f"transition_plan[{a}->{b}]",
                seen_texts=seen_texts,
                ctx=c,
            )
            row["text"] = decision["text"]
            row["spoken_copy_guard"] = {
                "action": decision["action"],
                "script_hash": decision["script_hash"],
                "context_hash": decision["context_hash"],
            }
            if decision["text"]:
                seen_texts.append(str(decision["text"]))
        # Mint required reorder hinges before mark_done. Otherwise Done Authority
        # refuses auto_complete on missing bridges and the post-LLM glue pass
        # never runs (exec_002).
        if sel_order:
            try:
                from interview_mux.nle_state import segments_by_id_with_nle
                from interview_mux.seam_glue import ensure_seam_glue

                _bridges, minted, _comp = ensure_seam_glue(
                    c,
                    ordered=sel_order,
                    segments_by_id=segments_by_id_with_nle(c),
                    gap_report=gap_report if isinstance(gap_report, dict) else None,
                    transitions=artifacts if isinstance(artifacts, dict) else None,
                    soft=False,
                )
                if isinstance(minted, dict):
                    artifacts = minted
            except SystemExit:
                raise
            except Exception:
                pass
        try:
            from interview_mux.speaker_delivery_plan import stamp_episode_vo_identity

            for row in artifacts.get("transitions") or []:
                if not isinstance(row, dict):
                    continue
                stamped = stamp_episode_vo_identity(c, row)
                row["voice_speaker_id"] = stamped.get("voice_speaker_id")
                if stamped.get("vo_shape"):
                    row["vo_shape"] = stamped.get("vo_shape")
        except Exception:
            pass
        persist(c, artifacts)

    with logged_step("transitions/llm_stage", ctx=ctx, stage="transitions"):
        run_flow_llm_stage(
            ctx,
            "transitions",
            prompt_variant("assembly/transitions.system.txt", ctx),
            build_input,
            persist_with_framing_dedupe,
        )
    # S4: seam glue + air-script filter land here; VO WAV mint stays on vo_synthesize.
    try:
        from interview_mux.air_script import filter_transitions_for_air_script
        from interview_mux.mastering_plan_loader import load_plan_raw
        from interview_mux.nle_state import segments_by_id_with_nle
        from interview_mux.seam_glue import ensure_seam_glue

        sel = (
            ctx.read_json("master/selection.json")
            if ctx.artifact_exists("master/selection.json")
            else {}
        )
        ordered = [
            str(s)
            for s in ((sel.get("ordered_segment_ids") if isinstance(sel, dict) else None) or [])
            if s
        ]
        gap_report = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else None
        )
        transitions_doc = (
            ctx.read_json("master/transitions.json")
            if ctx.artifact_exists("master/transitions.json")
            else {"transitions": []}
        )
        _bridges, transitions_doc, completeness = ensure_seam_glue(
            ctx,
            ordered=ordered,
            segments_by_id=segments_by_id_with_nle(ctx),
            gap_report=gap_report if isinstance(gap_report, dict) else None,
            transitions=transitions_doc if isinstance(transitions_doc, dict) else None,
            soft=False,
        )
        filtered = filter_transitions_for_air_script(
            transitions_doc if isinstance(transitions_doc, dict) else None,
            load_plan_raw(ctx),
        )
        if isinstance(filtered, dict):
            transitions_doc = filtered
            ctx.write_json(
                "master/transitions.json",
                transitions_doc,
                stage_key="transitions",
            )
        # S4: incomplete glue is refuse — never soft-warn mark_done.
        if not completeness.get("complete"):
            raise SystemExit(
                "transitions: bridge_completeness incomplete after glue mint: "
                f"missing={completeness.get('missing_count')} "
                f"detail={completeness.get('missing', [])[:6]}"
            )
    except SystemExit:
        raise
    except Exception as glue_exc:
        raise SystemExit(f"transitions: seam glue incomplete: {glue_exc}") from glue_exc
    try:
        from interview_mux.gates import check_g1_vo, g1_vo_was_skipped_optional
        from interview_mux.transition_vo import stamp_transitions_pair_freeze

        if g1_vo_was_skipped_optional(ctx) or not check_g1_vo(ctx):
            stamp_transitions_pair_freeze(ctx)
    except Exception:
        pass


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
