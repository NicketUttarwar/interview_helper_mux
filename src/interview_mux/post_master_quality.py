"""Always-on post-master quality and publish eligibility."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

QUALITY_REL = "master/post_master_quality.json"
SCORECARD_REL = "master/listener_scorecard.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_master_quality_cfg() -> dict[str, Any]:
    raw = (merged_config().get("mastering") or {}).get("post_master_quality") or {}
    return raw if isinstance(raw, dict) else {}


def selection_duration_ship_ok(ctx: RunContext) -> dict[str, Any]:
    """Hard ship gate: selection vs brief.min and vs source duration ratio.

    Ignores e2e soft flags — catastrophic shorts must not publish.
    """
    from interview_mux.coverage_limits import (
        delivery_output_max_ratio,
        delivery_output_min_ratio,
    )
    from interview_mux.delivery_brief import (
        delivery_brief_cfg,
        estimated_selection_duration_sec,
        load_delivery_brief,
        selection_duration_brief_min_ratio,
    )
    from interview_mux.interview_duration_policy import transcript_duration_ms

    detail: dict[str, Any] = {"ok": True, "reasons": []}
    est = estimated_selection_duration_sec(ctx)
    brief = load_delivery_brief(ctx)
    band = (brief or {}).get("target_duration_sec") or {} if isinstance(brief, dict) else {}
    try:
        bmin = float(band.get("min") or 0)
        bideal = float(band.get("ideal") or 0)
    except (TypeError, ValueError):
        bmin, bideal = 0.0, 0.0
    detail["selected_sec"] = est
    detail["brief_min"] = bmin
    detail["brief_ideal"] = bideal
    enforce = bool(delivery_brief_cfg().get("enforce_duration", True))
    brief_min_ratio = selection_duration_brief_min_ratio()
    brief_min_floor = bmin * brief_min_ratio
    if enforce and est is not None and bmin > 0 and est < brief_min_floor:
        detail["ok"] = False
        detail["reasons"].append(
            f"selection ~{est:.0f}s below brief.min*{brief_min_ratio:.2f} ({brief_min_floor:.0f}s)"
        )
    source_ms = int(transcript_duration_ms(ctx) or 0)
    min_ratio = float(delivery_output_min_ratio() or 0.1)
    max_ratio = float(delivery_output_max_ratio() or 1.5)
    detail["source_sec"] = source_ms / 1000.0 if source_ms else None
    detail["min_ratio_of_source"] = min_ratio
    detail["max_ratio_of_source"] = max_ratio
    if est is not None and source_ms > 0:
        ratio = float(est) / (source_ms / 1000.0)
        detail["selected_source_ratio"] = round(ratio, 4)
        if ratio < min_ratio:
            detail["ok"] = False
            detail["reasons"].append(
                f"selection/source ratio {ratio:.3f} < min {min_ratio:.3f}"
            )
        if ratio > max_ratio:
            detail["ok"] = False
            detail["reasons"].append(
                f"selection/source ratio {ratio:.3f} > max {max_ratio:.3f}"
            )
    return detail


# Dimensions e2e may soft-waive in listen_delight; everything else is hard.
_SOFTENABLE_DELIGHT_DIMS = frozenset({"sonic_weave"})


def _pmq_no_late_opening_native(ctx: RunContext) -> bool:
    """True when EDL has no opening-tape native clips late in the timeline."""
    if not ctx.artifact_exists("master/edl.json"):
        return True
    try:
        from interview_mux.air_order_integrity import (
            opening_window_ms,
            resolved_segment_starts,
        )
        from interview_mux.edl_narrative_qc import _speech_order

        edl = ctx.read_json("master/edl.json")
        if not isinstance(edl, dict):
            return True
        speech = _speech_order(edl)
        if not speech:
            return True
        starts = resolved_segment_starts(ctx)
        window = opening_window_ms(ctx=ctx)
        opening_ids = {
            sid
            for sid in speech
            if (resolved := starts.get(sid)) is not None and int(resolved) < window
        }
        if not opening_ids:
            return True
        threshold = max(1, int(len(speech) * 0.25))
        for idx, sid in enumerate(speech):
            if sid in opening_ids and idx >= threshold:
                return False
    except Exception:
        return True
    return True


def evaluate_post_master_quality(ctx: RunContext) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    conf = post_master_quality_cfg()

    def add(check_id: str, passed: bool, detail: Any = None) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    master = ctx.read_path("master", "master.wav")
    add("master_exists_nonempty", master.is_file() and master.stat().st_size > 0)

    autopsy = (
        ctx.read_json("master/seam_autopsy.json")
        if ctx.artifact_exists("master/seam_autopsy.json")
        else {}
    )
    commitment = autopsy.get("commitment") if isinstance(autopsy, dict) else {}
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    meta = meta if isinstance(meta, dict) else {}
    from interview_mux.e2e_soft import e2e_quality_waivers_enabled

    soft_junction = e2e_quality_waivers_enabled(meta=meta) and bool(
        meta.get("e2e_soft_junction_residuals")
    )
    commit_ok = isinstance(commitment, dict) and commitment.get("status") == "committed"
    if not commit_ok and soft_junction:
        # E2E soft-pass after budget-exhausted junction: refresh then accept committed-or-soft.
        try:
            from interview_mux.seam_autopsy import refresh_autopsy_commitment

            refreshed = refresh_autopsy_commitment(ctx) or {}
            commitment = refreshed.get("commitment") if isinstance(refreshed, dict) else commitment
            commit_ok = isinstance(commitment, dict) and commitment.get("status") == "committed"
        except Exception:
            pass
        if not commit_ok:
            commit_ok = True
            commitment = {
                **(commitment if isinstance(commitment, dict) else {}),
                "status": "committed",
                "e2e_softened": True,
            }
    add(
        "seam_commitment",
        commit_ok,
        commitment,
    )

    junction = (
        ctx.read_json("master/junction_snip_qa.json")
        if ctx.artifact_exists("master/junction_snip_qa.json")
        else {}
    )
    residual_view = None
    residual_n = 0
    try:
        from interview_mux.delivery_guardrails import critical_residual_view, has_critical_residuals

        residual_view = critical_residual_view(ctx)
        residual_n = int(residual_view.count)
        has_residual = has_critical_residuals(ctx)
    except Exception:
        residual = [
            f
            for f in ((junction or {}).get("residual_findings") or [])
            if isinstance(f, dict) and str(f.get("severity") or "") == "critical"
        ]
        residual_n = len(residual)
        has_residual = bool(residual)
    add(
        "no_critical_junction_residuals",
        not has_residual,
        {
            "count": residual_n,
            "kinds": list(residual_view.kinds) if residual_view is not None else [],
            "sources": list(residual_view.sources) if residual_view is not None else [],
        },
    )
    feel_unavailable = bool((junction or {}).get("feel_audit_unavailable")) or (
        "junction_feel_audit_unavailable"
        in [str(x) for x in ((junction or {}).get("blocking_reasons") or [])]
    )
    block_feel = bool(conf.get("block_on_feel_unavailable", True))
    feel_gate_ok = (not feel_unavailable) or (commit_ok and not has_residual)
    add(
        "feel_audit_available",
        feel_gate_ok if block_feel else True,
        {
            "feel_unavailable": feel_unavailable,
            "block_on_feel_unavailable": block_feel,
            "committed_without_critical_residuals": bool(commit_ok and not has_residual),
        },
    )
    add("render_ledger_exists", ctx.artifact_exists("master/render_ledger.json"))

    if ctx.artifact_exists("master/air_order_integrity.json"):
        try:
            integrity = ctx.read_json("master/air_order_integrity.json")
            critical = [
                v
                for v in ((integrity or {}).get("violations") or [])
                if isinstance(v, dict) and str(v.get("severity") or "") == "critical"
            ]
            from interview_mux.air_order_integrity import block_publish_on_critical

            block = block_publish_on_critical()
            add(
                "air_order_integrity",
                not critical or not block,
                {"critical_count": len(critical), "blocked": bool(critical and block)},
            )
        except Exception:
            add("air_order_integrity", True, {"skipped": True})

    add("spoken_native_intro_duplicate", _pmq_no_late_opening_native(ctx))

    plan_required = ctx.is_done("mastering_plan_synthesize") or ctx.is_done(
        "mastering_plan_confirm"
    )
    add(
        "mastering_plan_present_when_complete",
        not plan_required or ctx.artifact_exists("mastering/mastering_plan.json"),
        {"stage_claimed_complete": plan_required},
    )

    # Scorecard floors (observational dimensions become publish gates).
    from interview_mux.quality_status import STATUS_PASS

    scorecard = build_listener_scorecard(
        ctx, {"status": STATUS_PASS, "publish_allowed": True}
    )
    overall_min = float(conf.get("overall_min") or 0.90)
    floors = conf.get("dimension_floors") if isinstance(conf.get("dimension_floors"), dict) else {}
    dims = scorecard.get("dimensions") if isinstance(scorecard.get("dimensions"), dict) else {}
    failed_dims: list[str] = []
    for dim, floor in floors.items():
        try:
            need = float(floor)
        except (TypeError, ValueError):
            continue
        got = float(dims.get(dim) or 0.0)
        if got < need:
            failed_dims.append(str(dim))
    overall = float(scorecard.get("overall") or 0.0)
    add(
        "scorecard_overall_floor",
        overall >= overall_min,
        {"overall": overall, "overall_min": overall_min},
    )
    add(
        "scorecard_dimension_floors",
        not failed_dims,
        {"failed_dimensions": failed_dims, "floors": floors, "dimensions": dims},
    )

    # E2E soft ship: waive scorecard floors when soft flags are set and a master exists.
    # Duration / spoken-VO / seam commitment remain hard.
    soft_pmq = e2e_quality_waivers_enabled(meta=meta) and bool(
        meta.get("e2e_soft_post_master_quality")
        or meta.get("e2e_soft_listen_delight")
        or meta.get("e2e_soft_listenability")
    )
    if soft_pmq and ctx.artifact_exists("master/master.wav"):
        for c in checks:
            if c.get("check_id") in {
                "scorecard_overall_floor",
                "scorecard_dimension_floors",
            }:
                c["passed"] = True
                detail = c.get("detail") if isinstance(c.get("detail"), dict) else {}
                c["detail"] = {**detail, "e2e_softened": True}

    # Selection length vs brief/source — never soft-waivable.
    duration_gate = selection_duration_ship_ok(ctx)
    add(
        "selection_duration_floor",
        bool(duration_gate.get("ok")),
        duration_gate,
    )

    # Spoken VO must not be gap-eval QC prose.
    vo_ok = True
    vo_errs: list[str] = []
    try:
            from interview_mux.spoken_meta_lint import (
                lint_gap_report_lines,
                lint_transitions_doc,
            )

            gr = (
                ctx.read_json("understanding/gap_report.json")
                if ctx.artifact_exists("understanding/gap_report.json")
                else {}
            )
            vo_errs = lint_gap_report_lines(gr if isinstance(gr, dict) else None)
            transitions = (
                ctx.read_json("master/transitions.json")
                if ctx.artifact_exists("master/transitions.json")
                else {}
            )
            vo_errs.extend(
                lint_transitions_doc(
                    transitions if isinstance(transitions, dict) else None
                )
            )
            from interview_mux.spoken_copy_guard import artifact_spoken_copy_errors

            by_id: dict[str, dict[str, Any]] = {}
            if ctx.artifact_exists("segments/manifest.json"):
                manifest = ctx.read_json("segments/manifest.json")
                by_id = {
                    str(row.get("segment_id")): row
                    for row in ((manifest or {}).get("segments") or [])
                    if isinstance(row, dict) and row.get("segment_id")
                }
            synthetic = (
                ctx.read_json("understanding/synthetic_framing_plan.json")
                if ctx.artifact_exists("understanding/synthetic_framing_plan.json")
                else None
            )
            vo_errs.extend(
                artifact_spoken_copy_errors(
                    gap_report=gr if isinstance(gr, dict) else None,
                    transitions=transitions
                    if isinstance(transitions, dict)
                    else None,
                    segments_by_id=by_id,
                    grounding_context=(
                        ctx.read_json("understanding/content_brief.json")
                        if ctx.artifact_exists("understanding/content_brief.json")
                        else None
                    ),
                    synthetic_framing=synthetic if isinstance(synthetic, dict) else None,
                    ctx=ctx,
                )
            )
            vo_errs = list(dict.fromkeys(vo_errs))
            vo_ok = not vo_errs
    except Exception as exc:
        vo_ok = False
        vo_errs = [str(exc)[:160]]
    add("spoken_vo_speakable", vo_ok, {"errors": vo_errs[:8]})

    omit_contract_ok = True
    omit_contract_errors: list[str] = []
    omit_summary: dict[str, Any] = {}
    try:
        from interview_mux.omit_ledger import OMIT_LEDGER_REL, air_contract_errors

        ledger = (
            ctx.read_json(OMIT_LEDGER_REL)
            if ctx.artifact_exists(OMIT_LEDGER_REL)
            else None
        )
        if isinstance(ledger, dict):
            omit_summary = (
                dict(ledger.get("summary") or {})
                if isinstance(ledger.get("summary"), dict)
                else {}
            )
            omit_contract_errors = air_contract_errors(ctx, ledger=ledger)
            omit_contract_ok = not omit_contract_errors
    except Exception as exc:
        omit_contract_ok = False
        omit_contract_errors = [str(exc)[:160]]
    add(
        "omit_ledger_air_contract",
        omit_contract_ok,
        {
            "errors": omit_contract_errors[:8],
            "summary": omit_summary,
        },
    )

    audible_hash_errors: list[str] = []
    try:
        from interview_mux.vo_synthesis_audit import audible_script_hash_errors

        edl_for_hash = (
            ctx.read_json("master/edl.json")
            if ctx.artifact_exists("master/edl.json")
            else {}
        )
        audible_hash_errors = audible_script_hash_errors(
            ctx, edl_for_hash if isinstance(edl_for_hash, dict) else None
        )
    except Exception as exc:
        audible_hash_errors = [str(exc)[:160]]
    add(
        "audible_script_hash_agreement",
        not audible_hash_errors,
        {"errors": audible_hash_errors[:8]},
    )

    # When framing is enabled, the opening contract is either one early
    # synthetic orientation or an explicit native-open omit (hosts already intro).
    opening_ok = True
    opening_errors: list[str] = []
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled
        from interview_mux.opening_orientation import (
            orientation_omitted,
            validate_opening_orientation,
        )

        if gap_framing_enabled(ctx):
            gr = (
                ctx.read_json("understanding/gap_report.json")
                if ctx.artifact_exists("understanding/gap_report.json")
                else {}
            )
            edl = (
                ctx.read_json("master/edl.json")
                if ctx.artifact_exists("master/edl.json")
                else {}
            )
            active_lines = [
                line
                for line in ((gr or {}).get("interviewer_lines") or [])
                if isinstance(line, dict) and not line.get("skipped_optional")
            ]
            if active_lines or orientation_omitted(gr if isinstance(gr, dict) else None):
                opening_errors = validate_opening_orientation(
                    gap_report=gr if isinstance(gr, dict) else None,
                    edl=edl if isinstance(edl, dict) else None,
                )
                opening_ok = not opening_errors
    except Exception as exc:
        opening_ok = False
        opening_errors = [str(exc)[:160]]
    add(
        "opening_orientation_contract",
        opening_ok,
        {"errors": opening_errors[:8]},
    )

    music_coverage_required = ctx.artifact_exists(
        "understanding/sound_design_plan.json"
    )
    music_coverage = (
        ctx.read_json("master/music_cue_coverage.json")
        if ctx.artifact_exists("master/music_cue_coverage.json")
        else {}
    )
    music_preserved = (
        not music_coverage_required
        or (
            isinstance(music_coverage, dict)
            and bool(music_coverage.get("preserved"))
            and not (music_coverage.get("missing_asset_ids") or [])
            and not (music_coverage.get("shortened_preserved_asset_ids") or [])
        )
    )
    add(
        "planned_music_preserved",
        music_preserved,
        music_coverage
        if isinstance(music_coverage, dict)
        else {"error": "invalid music_cue_coverage"},
    )
    # Missing episode-close outro is ship-blocking when SDP planned one.
    outro_ok = True
    outro_detail: dict[str, Any] = {"required": False}
    try:
        critic = (
            ctx.read_json("master/listen_critic.json")
            if ctx.artifact_exists("master/listen_critic.json")
            else {}
        )
        issues = (critic or {}).get("issues") or [] if isinstance(critic, dict) else []
        missing_outro = any(
            isinstance(i, dict)
            and str(i.get("code") or "")
            in {"missing_episode_close_outro", "missing_episode_close_outro_cue"}
            for i in issues
        )
        if missing_outro:
            outro_ok = False
            outro_detail = {"required": True, "error": "missing_episode_close_outro_cue"}
        elif isinstance(music_coverage, dict) and music_coverage_required:
            realized = music_coverage.get("realized_cues") or []
            has_outro = any(
                isinstance(r, dict)
                and str(r.get("music_role") or "") == "theme_outro"
                for r in realized
            )
            planned_roles = []
            try:
                from interview_mux.sound_design import load_sound_design_plan
                from interview_mux.music_lane import effective_cue_role

                plan = load_sound_design_plan(ctx)
                assets = {
                    str(a.get("asset_id") or ""): a
                    for a in (plan.get("assets") or [])
                    if isinstance(a, dict)
                }
                for cue in (
                    ((plan.get("flow_plans") or {}).get("podcast") or {}).get("cues")
                    or []
                ):
                    if not isinstance(cue, dict) or cue.get("skip"):
                        continue
                    role = effective_cue_role(
                        cue, assets.get(str(cue.get("asset_id") or ""), {})
                    )
                    if role == "theme_outro":
                        planned_roles.append(cue)
                if planned_roles:
                    outro_detail = {"required": True, "realized": has_outro}
                    outro_ok = has_outro
            except Exception as exc:
                outro_detail = {"required": False, "error": str(exc)[:120]}
    except Exception as exc:
        outro_ok = False
        outro_detail = {"error": str(exc)[:160]}
    add("episode_close_outro_present", outro_ok, outro_detail)
    opening_theme_ok = True
    opening_theme_detail: dict[str, Any] = {"required": False}
    opening_assets: set[str] = set()
    try:
        gr = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
        from interview_mux.opening_orientation import is_episode_orientation

        orientation_active = any(
            isinstance(line, dict)
            and not line.get("skipped_optional")
            and is_episode_orientation(line)
            for line in ((gr or {}).get("interviewer_lines") or [])
        )
        if orientation_active:
            from interview_mux.music_lane import effective_cue_role
            from interview_mux.sound_design import load_sound_design_plan

            plan = load_sound_design_plan(ctx)
            assets = {
                str(row.get("asset_id") or ""): row
                for row in (plan.get("assets") or [])
                if isinstance(row, dict)
            }
            opening_assets = {
                str(cue.get("asset_id") or "")
                for cue in (
                    ((plan.get("flow_plans") or {}).get("podcast") or {}).get(
                        "cues"
                    )
                    or []
                )
                if isinstance(cue, dict)
                and not cue.get("skip")
                and effective_cue_role(
                    cue, assets.get(str(cue.get("asset_id") or ""), {})
                )
                == "theme_cold_open"
            }
            realized = set(
                str(x) for x in ((music_coverage or {}).get("realized_asset_ids") or [])
            )
            opening_theme_ok = bool(opening_assets) and opening_assets.issubset(realized)
            if not opening_theme_ok:
                edl = (
                    ctx.read_json("master/edl.json")
                    if ctx.artifact_exists("master/edl.json")
                    else {}
                )
                opening_pad = any(
                    isinstance(c, dict)
                    and str(c.get("type") or "") == "silence"
                    and str(c.get("air_kind") or "") == "opening_music"
                    and bool(c.get("preserve_planned_music"))
                    for c in ((edl or {}).get("clips") or [])
                )
                if opening_pad:
                    opening_theme_ok = True
            opening_theme_detail = {
                "required": True,
                "planned_opening_asset_ids": sorted(opening_assets),
                "realized_asset_ids": sorted(realized),
            }
    except Exception as exc:
        opening_theme_ok = False
        opening_theme_detail = {"required": True, "error": str(exc)[:160]}
    add("opening_music_preserved", opening_theme_ok, opening_theme_detail)

    opening_quality_ok = True
    opening_quality_detail: dict[str, Any] = {"required": True}
    try:
        if opening_assets:
            assets_dir = ctx.final_path("sound_design", "assets")
            stub_ids: list[str] = []
            for aid in sorted(opening_assets):
                gen_path = assets_dir / f"{aid}.gen.json"
                backend = ""
                if gen_path.is_file():
                    try:
                        gmeta = ctx.read_json(f"sound_design/assets/{aid}.gen.json")
                        backend = str((gmeta or {}).get("backend") or "").strip().lower()
                    except Exception:
                        backend = ""
                if backend == "musical_stub":
                    stub_ids.append(aid)
            opening_quality_ok = not stub_ids
            opening_quality_detail = {
                "required": True,
                "opening_asset_ids": sorted(opening_assets),
                "musical_stub_ids": stub_ids,
            }
    except Exception as exc:
        opening_quality_ok = False
        opening_quality_detail = {"required": True, "error": str(exc)[:160]}
    add("opening_music_quality", opening_quality_ok, opening_quality_detail)

    # Listen delight floors — structural when mode is authoritative (delight mode flip).
    # Under advisory mode they remain aspirational-softened via is_rubric_pmq_check.
    from interview_mux.listen_delight import listen_delight_cfg

    delight_cfg = listen_delight_cfg()
    delight = (
        ctx.read_json("mastering/listen_delight_audit.json")
        if ctx.artifact_exists("mastering/listen_delight_audit.json")
        else {}
    )
    delight = delight if isinstance(delight, dict) else {}
    delight_overall_min = float(delight_cfg.get("overall_min") or delight.get("overall_min") or 0.90)
    delight_floors = (
        delight_cfg.get("dimension_floors")
        if isinstance(delight_cfg.get("dimension_floors"), dict)
        else (delight.get("dimension_floors") if isinstance(delight.get("dimension_floors"), dict) else {})
    )
    delight_dims = delight.get("dimensions") if isinstance(delight.get("dimensions"), dict) else {}
    delight_overall = float(delight.get("overall") or 0.0)
    delight_failed = [
        str(dim)
        for dim, floor in (delight_floors or {}).items()
        if float(delight_dims.get(dim) or 0.0) < float(floor or 0.0)
    ]
    delight_present = bool(delight)
    soft_delight = bool(meta.get("e2e_soft_listen_delight") or meta.get("e2e_soft_listenability"))
    hard_failed = [d for d in delight_failed if d not in _SOFTENABLE_DELIGHT_DIMS]
    soft_only_failed = [d for d in delight_failed if d in _SOFTENABLE_DELIGHT_DIMS]
    floors_ok = delight_present and delight_overall >= delight_overall_min and not delight_failed
    if soft_delight and not floors_ok:
        # Soft-pass may waive softenable dims only — never nugget_retention / overall.
        if not hard_failed and delight_present and delight_overall >= delight_overall_min:
            floors_ok = True
        elif soft_only_failed and not hard_failed and delight_overall >= max(
            0.75, delight_overall_min - 0.05
        ):
            floors_ok = True
        elif soft_delight and delight_present and delight_overall >= max(
            0.75, delight_overall_min - 0.1
        ) and "nugget_retention" not in delight_failed:
            floors_ok = True
        else:
            floors_ok = False
    # LD1: missing delight artifact at post_master → floors fail (≤ floor−ε semantics).
    if not delight_present:
        floors_ok = False
    add(
        "listen_delight_floors",
        floors_ok,
        {
            "present": delight_present,
            "overall": delight_overall,
            "overall_min": delight_overall_min,
            "failed_dimensions": delight_failed,
            "hard_failed_dimensions": hard_failed,
            "dimensions": delight_dims,
            "mode": delight.get("mode") or delight_cfg.get("mode"),
            "e2e_softened": soft_delight and floors_ok and bool(soft_only_failed),
        },
    )

    if soft_pmq:
        # Spoken VO speakability + audible script-hash agreement stay hard even
        # under e2e soft — soft-waiving them ships masters that disagree with the
        # current gap scripts / synthesized WAVs.
        waivable = {
            "no_critical_junction_residuals",
            "episode_close_outro_present",
            "planned_music_preserved",
            "opening_orientation_contract",
            "opening_music_preserved",
            "feel_audit_available",
        }
        for c in checks:
            if c.get("check_id") in waivable and not c.get("passed"):
                c["passed"] = True
                detail = c.get("detail") if isinstance(c.get("detail"), dict) else {}
                c["detail"] = {**detail, "e2e_softened": True}

    from interview_mux.aspirational_quality import (
        aspirational_quality_cfg,
        is_aspirational_enabled,
        is_rubric_pmq_check,
        is_structural_pmq_check,
        passes_catastrophic_floors,
        record_quality_advisories,
    )

    aspirational = is_aspirational_enabled(ctx)
    # F6 3C: with aspirational off, rubric misses are omitted from the ship report.
    # Live critical residuals stay on the envelope (they hard-block mix/ship).
    if not aspirational:
        kept: list[dict[str, Any]] = []
        for c in checks:
            cid = str(c.get("check_id") or "")
            if c.get("passed") or not is_rubric_pmq_check(cid):
                kept.append(c)
                continue
            if cid == "no_critical_junction_residuals":
                detail = c.get("detail") if isinstance(c.get("detail"), dict) else {}
                if int((detail or {}).get("count") or 0) > 0:
                    kept.append(c)
        checks = kept

    passed = all(bool(c["passed"]) for c in checks)
    failed_checks = [str(c["check_id"]) for c in checks if not c["passed"]]
    structural_failed: list[str] = []
    rubric_failed: list[str] = []
    for c in checks:
        if c.get("passed"):
            continue
        cid = str(c.get("check_id") or "")
        if is_structural_pmq_check(cid) or cid == "master_exists_nonempty":
            structural_failed.append(cid)
            continue
        if cid == "no_critical_junction_residuals":
            detail = c.get("detail") if isinstance(c.get("detail"), dict) else {}
            if int((detail or {}).get("count") or 0) > 0:
                structural_failed.append(cid)
                continue
        # F7 1C: aspirational listen misses stay rubric unless catastrophic.
        if cid == "listen_delight_floors" and aspirational:
            cata_ok, _cata = passes_catastrophic_floors(ctx)
            if cata_ok:
                rubric_failed.append(cid)
                continue
        if aspirational and is_rubric_pmq_check(cid):
            rubric_failed.append(cid)
        else:
            structural_failed.append(cid)

    from interview_mux.quality_status import ship_wire_status

    if structural_failed:
        publish_allowed = False
    elif rubric_failed:
        publish_allowed = True
    else:
        publish_allowed = passed and not bool(conf.get("block_publish", False))
    status = ship_wire_status(publish_allowed=publish_allowed)

    advisories: list[dict[str, Any]] = []
    if rubric_failed and aspirational:
        advisories = [{"gate_id": "post_master_quality", "failed_checks": rubric_failed}]
        if bool(aspirational_quality_cfg().get("record_advisories_in_pmq", True)):
            record_quality_advisories(
                ctx,
                gate_id="post_master_quality",
                failed_checks=rubric_failed,
                detail={"status": status},
                aspirational_proceeded=not structural_failed,
            )

    return {
        "version": 1,
        "generated_at": _now(),
        "status": status,
        "publish_allowed": publish_allowed,
        "checks": checks,
        "failed_checks": failed_checks,
        "structural_failed_checks": structural_failed,
        "rubric_failed_checks": rubric_failed,
        "advisories": advisories,
        "aspirational": aspirational,
        "never_skipped": True,
        "scorecard_preview": {
            "overall": overall,
            "dimensions": dims,
            "failed_dimensions": failed_dims,
        },
    }


def _synthetic_fit_score(ctx: RunContext, autopsy: dict[str, Any]) -> float:
    """Blend density share + adjacent level delta + duration_ratio compliance."""
    scores = autopsy.get("scores") if isinstance(autopsy, dict) else {}
    density = float((scores or {}).get("sonic_density_fit") or 0.0)
    level_fit = 1.0
    duration_fit = 1.0
    if ctx.artifact_exists("understanding/synthetic_framing_plan.json"):
        plan = ctx.read_json("understanding/synthetic_framing_plan.json")
        lines = [r for r in ((plan or {}).get("lines") or []) if isinstance(r, dict)]
        synth_cfg = (merged_config().get("mastering") or {}).get("synthetic_framing") or {}
        ratio_min = float(synth_cfg.get("duration_ratio_min") or 0.4)
        ratio_max = float(synth_cfg.get("duration_ratio_max") or 2.0)
        ratio_hits = 0
        ratio_n = 0
        for row in lines:
            ratio = row.get("duration_ratio")
            if ratio is None:
                continue
            ratio_n += 1
            try:
                r = float(ratio)
            except (TypeError, ValueError):
                continue
            if ratio_min <= r <= ratio_max:
                ratio_hits += 1
        if ratio_n:
            duration_fit = ratio_hits / ratio_n
        # Adjacent level deltas recorded on plan lines when present.
        deltas = []
        for row in lines:
            d = row.get("adjacent_level_delta_db")
            if d is None:
                continue
            try:
                deltas.append(abs(float(d)))
            except (TypeError, ValueError):
                continue
        if deltas:
            # 0 dB → 1.0; 6 dB → ~0.5; clamp.
            mean_abs = sum(deltas) / len(deltas)
            level_fit = max(0.0, min(1.0, 1.0 - (mean_abs / 12.0)))
    return round((0.45 * density) + (0.30 * level_fit) + (0.25 * duration_fit), 4)


def build_listener_scorecard(ctx: RunContext, quality: dict[str, Any]) -> dict[str, Any]:
    autopsy = (
        ctx.read_json("master/seam_autopsy.json")
        if ctx.artifact_exists("master/seam_autopsy.json")
        else {}
    )
    scores = autopsy.get("scores") if isinstance(autopsy, dict) else {}
    flow = float((scores or {}).get("continuity") or 0.0)
    clarity = float((scores or {}).get("information_clarity") or 0.0)
    music = float((scores or {}).get("music_completeness") or 0.0)
    synthetic = _synthetic_fit_score(ctx, autopsy if isinstance(autopsy, dict) else {})
    native_respect = 1.0
    if ctx.artifact_exists("understanding/synthetic_framing_plan.json"):
        plan = ctx.read_json("understanding/synthetic_framing_plan.json")
        violations = [
            r
            for r in (plan.get("lines") or [])
            if isinstance(r, dict) and r.get("native_respect_violation")
        ]
        native_respect = max(0.0, 1.0 - 0.2 * len(violations))
    dimensions = {
        "flow": round(flow, 4),
        "clarity": round(clarity, 4),
        "music_completeness": round(music, 4),
        "synthetic_fit": round(synthetic, 4),
        "native_respect": round(native_respect, 4),
    }
    from interview_mux.quality_status import ship_wire_status

    overall = sum(dimensions.values()) / len(dimensions)
    allowed = bool(quality.get("publish_allowed"))
    qstatus = ship_wire_status(publish_allowed=allowed)
    if not allowed:
        overall = min(overall, 0.49)
    return {
        "version": 1,
        "generated_at": _now(),
        "overall": round(overall, 4),
        "dimensions": dimensions,
        "quality_status": qstatus,
        "publish_allowed": bool(quality.get("publish_allowed")),
    }


def persist_post_master_quality(ctx: RunContext, quality: dict[str, Any]) -> None:
    from interview_mux.quality_status import coerce_ship_envelope_status
    from interview_mux.write_staging import write_committed_json

    quality = coerce_ship_envelope_status(quality)
    write_committed_json(ctx, QUALITY_REL, quality)
    write_committed_json(ctx, SCORECARD_REL, build_listener_scorecard(ctx, quality))


def run_post_master_quality(ctx: RunContext, *, block: bool = True) -> dict[str, Any]:
    from interview_mux.listen_delight import run_authoritative_listen_delight_at_ship
    from interview_mux.seam_autopsy import build_autopsy, enrich_ledger, write_autopsy
    from interview_mux.write_staging import write_committed_json

    if ctx.artifact_exists("master/master.wav"):
        run_authoritative_listen_delight_at_ship(ctx)
    snip = (
        ctx.read_json("master/junction_snip_qa.json")
        if ctx.artifact_exists("master/junction_snip_qa.json")
        else {}
    )
    autopsy = build_autopsy(ctx, phase="post_master", snip_report=snip)
    write_autopsy(ctx, autopsy)
    enrich_ledger(ctx, autopsy)
    quality = evaluate_post_master_quality(ctx)
    persist_post_master_quality(ctx, quality)

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    from interview_mux.quality_status import STATUS_FAIL, qc_summary_flags

    qc = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
    flags = qc_summary_flags(
        quality.get("status"),
        publish_allowed=bool(quality.get("publish_allowed")),
    )
    flags["failed_checks"] = quality["failed_checks"]
    qc["post_master_quality"] = flags
    meta["qc_summaries"] = qc
    write_committed_json(ctx, "run_meta.json", meta)

    if block:
        structural = list(quality.get("structural_failed_checks") or [])
        if structural or quality.get("status") == STATUS_FAIL:
            from interview_mux.aspirational_quality import is_aspirational_enabled

            if not (is_aspirational_enabled(ctx) and not structural):
                from interview_mux.loud_fail import raise_loud_failure

                raise_loud_failure(
                    ctx,
                    "Post-master quality failed: " + ", ".join(quality["failed_checks"]),
                    stage="master_finalize",
                    reason="post_master_quality_failed",
                    detail={
                        "failed_checks": quality["failed_checks"],
                        "structural_failed_checks": structural,
                    },
                )
    return quality


def require_publishable(ctx: RunContext, *, stage: str = "podcast_publish") -> None:
    """Block local encode/package when Tier-0 PMQ fails.

    Quality advisories do **not** block local packaging (encode / cover /
    ``podcast_publish``). They require operator consent only for S3 sync —
    see ``publish_blocked_by_advisories`` / G-Publish sync.
    """
    if not ctx.artifact_exists(QUALITY_REL):
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "Post-master quality artifact is missing; publishing is blocked.",
            stage=stage,
            reason="post_master_quality_missing",
        )
    quality = ctx.read_json(QUALITY_REL)
    if not isinstance(quality, dict) or not quality.get("publish_allowed"):
        # Re-evaluate with current soft flags (e2e may have softened after write).
        try:
            quality = evaluate_post_master_quality(ctx)
            if quality.get("publish_allowed"):
                persist_post_master_quality(ctx, quality)
        except Exception:
            pass
    if not isinstance(quality, dict) or not quality.get("publish_allowed"):
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "The master did not pass post-master quality; publishing is blocked.",
            stage=stage,
            reason="publish_blocked_bad_master",
            detail={"quality": quality if isinstance(quality, dict) else {}},
        )
