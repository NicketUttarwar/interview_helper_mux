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


def _compact_segments_payload(c: RunContext) -> dict[str, Any]:
    manifest = c.read_json("segments/manifest.json") if c.artifact_exists("segments/manifest.json") else {}
    return compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}, text_max=100)


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


def run_missing_framing(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "segments": _compact_segments_payload(c),
            "content_brief": c.read_json("understanding/content_brief.json"),
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
        return payload

    persist = make_stage_persist("understanding/gap_evaluations.json", "missing_framing")

    with logged_step("missing_framing/pre_specialists", ctx=ctx, stage="missing_framing"):
        maybe_run_pre_stage_specialists(ctx, "missing_framing", build_input(ctx))

    with logged_step("missing_framing/llm_stage", ctx=ctx, stage="missing_framing"):
        run_analysis_llm_stage(
            ctx,
            "missing_framing",
            prompt_variant("interviewer-gap/missing-framing.system.txt", ctx),
            build_input,
            persist,
            sync_fn=lambda c, a: sync_gaps_to_state(c, a),
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


def run_gap_framing_compose(ctx: RunContext) -> None:
    """Compose full gap framing script (questions, summaries, prefaces, bridges)."""

    def build_input(c: RunContext) -> dict:
        from interview_mux.gap_framing import gap_framing_cfg
        from interview_mux.config import merged_config
        import math

        payload = {
            "gap_evaluations": c.read_json("understanding/gap_evaluations.json"),
            "segments": _compact_segments_payload(c),
            "content_brief": c.read_json("understanding/content_brief.json"),
            "gap_framing_policy": gap_framing_cfg(),
        }
        if c.artifact_exists("understanding/delivery_brief.json"):
            payload["delivery_brief"] = c.read_json("understanding/delivery_brief.json")
        if c.artifact_exists("understanding/episode_structure.json"):
            payload["episode_structure"] = c.read_json("understanding/episode_structure.json")
        # VO density contract for compose (hard min ≈20% of selected speech).
        gf = ((merged_config().get("analysis") or {}).get("gap_framing") or {})
        min_r = float(gf.get("min_vo_insert_ratio") or 0.20)
        tgt_r = float(gf.get("target_vo_insert_ratio") or 0.35)
        ordered_n = 0
        if c.artifact_exists("master/selection.json"):
            sel = c.read_json("master/selection.json")
            if isinstance(sel, dict):
                ordered_n = len([s for s in (sel.get("ordered_segment_ids") or []) if s])
        if ordered_n <= 0 and c.artifact_exists("segments/manifest.json"):
            man = c.read_json("segments/manifest.json")
            ordered_n = len(
                [r for r in ((man or {}).get("segments") or []) if isinstance(r, dict) and r.get("segment_id")]
            )
        vo_min = max(1, int(math.ceil(ordered_n * min_r))) if ordered_n else 1
        vo_ideal = max(vo_min, int(math.ceil(ordered_n * tgt_r))) if ordered_n else vo_min
        qb = {}
        if isinstance(payload.get("delivery_brief"), dict):
            qb = (payload["delivery_brief"].get("question_budget") or {}) if isinstance(
                payload["delivery_brief"].get("question_budget"), dict
            ) else {}
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
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        from interview_mux.artifact_repairs import repair_gap_report
        from interview_mux.artifact_writes import write_validated_artifact
        from interview_mux.gap_framing import persist_gap_framing_companion_artifacts

        plan = artifacts.pop("gap_framing_plan", None)
        repaired, _ = repair_gap_report(c, artifacts)
        persist_gap_framing_companion_artifacts(c, repaired)
        if isinstance(plan, dict):
            c.write_json("understanding/gap_framing_plan.json", plan)
        write_validated_artifact(
            c,
            "understanding/gap_report.json",
            repaired,
            merge_from_disk=True,
            stage_key="gap_framing_compose",
        )

    with logged_step("gap_framing_compose/llm_stage", ctx=ctx, stage="gap_framing_compose"):
        run_analysis_llm_stage(
            ctx,
            "gap_framing_compose",
            prompt_variant("interviewer-gap/gap-framing-compose.system.txt", ctx),
            build_input,
            persist,
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
                seg = line.get("targets_segment_id", "")
                pickup = ctx.final_path("vo_pickup")
                candidates = [pickup / f"{lid}.wav", pickup / f"{seg}.wav"]
                found = next((p for p in candidates if p.is_file()), None)
            if not found:
                missing.append(lid or line.get("targets_segment_id", ""))
                continue
            if normalize and found.parent == pickup:
                norm_dir = pickup / "normalized"
                norm_dir.mkdir(parents=True, exist_ok=True)
                out = norm_dir / found.name
                from interview_mux.operator_subprocess import run_command

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
    ctx.mark_done("vo_ingest")
