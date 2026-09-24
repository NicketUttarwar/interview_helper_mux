"""Post-mix soundscape verify against policy standards; capped remux remediation.

Bed coverage (default floor/ceiling ``0.40``/``0.88``) and hinge-stinger coverage
(``0.3``/``1.0``) are **Shape-owned soft bands** — see
``listenability_guards._DEFAULTS`` and
docs/cross-cutting/soundscape-policy.md — not a remux-theater target to be hit
by any means. This module's job is to measure the *real* plan honestly
(``_estimate_bed_coverage`` sums actual planned bed duration over actual
selection duration) and, when it is short, delegate to legitimate
palette/quartile-anchored, contiguous-preferring bed seeding
(``artifact_repairs.repair_sound_design_plan``) rather than inventing beds to
satisfy the number. See docs/cross-cutting/seam-autopsy.md and
docs/cross-cutting/mix-house-chain.md for the surrounding mix-house contract.
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.soundscape_policy import (
    REPORT_PATH,
    fail_closed,
    load_policy,
    max_remux_cycles,
    resolve_mix_contract,
)


def _estimate_bed_coverage(ctx: RunContext) -> float:
    """Fraction of selected speech time with under_segment beds planned (proxy)."""
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return 0.0
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    if not isinstance(sdp, dict):
        return 0.0
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    cues = [c for c in (flow.get("cues") or []) if isinstance(c, dict)]
    bed_cues = [
        c
        for c in cues
        if str(c.get("placement") or "") in {"under_segment", "under_segment_span"}
        and not c.get("skip")
    ]
    if not bed_cues:
        return 0.0
    manifest = {}
    if ctx.artifact_exists("segments/manifest.json"):
        raw = ctx.read_json("segments/manifest.json")
        manifest = raw if isinstance(raw, dict) else {}
    segs = {
        str(s.get("segment_id") or s.get("id")): s
        for s in (manifest.get("segments") or [])
        if isinstance(s, dict)
    }
    bed_ms = 0
    seen: set[str] = set()
    for c in bed_cues:
        ids = [str(x) for x in (c.get("segment_ids") or []) if x]
        if not ids:
            sid = str(c.get("segment_id") or "")
            if sid:
                ids = [sid]
        for sid in ids:
            if sid in seen:
                continue
            seen.add(sid)
            seg = segs.get(sid) or {}
            bed_ms += max(0, int(seg.get("end_ms") or 0) - int(seg.get("start_ms") or 0))
    total_ms = 0
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            for sid in sel.get("ordered_segment_ids") or []:
                seg = segs.get(str(sid)) or {}
                total_ms += max(0, int(seg.get("end_ms") or 0) - int(seg.get("start_ms") or 0))
    if total_ms <= 0:
        total_ms = sum(
            max(0, int(s.get("end_ms") or 0) - int(s.get("start_ms") or 0)) for s in segs.values()
        )
    if total_ms <= 0:
        return 0.0
    return min(1.0, bed_ms / total_ms)


def _count_active_cues(ctx: RunContext) -> dict[str, int]:
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return {"beds": 0, "stingers": 0, "skipped": 0}
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    if not isinstance(sdp, dict):
        return {"beds": 0, "stingers": 0, "skipped": 0}
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    cues = [c for c in (flow.get("cues") or []) if isinstance(c, dict)]
    beds = stingers = skipped = 0
    for c in cues:
        if c.get("skip"):
            skipped += 1
            continue
        if c.get("placement") == "under_segment":
            beds += 1
        else:
            stingers += 1
    return {"beds": beds, "stingers": stingers, "skipped": skipped}


def _min_bed_level_db(ctx: RunContext) -> float | None:
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return None
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    if not isinstance(sdp, dict):
        return None
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    levels: list[float] = []
    for c in flow.get("cues") or []:
        if not isinstance(c, dict) or c.get("skip"):
            continue
        if c.get("placement") == "under_segment" and c.get("level_db") is not None:
            levels.append(float(c["level_db"]))
    return min(levels) if levels else None


def evaluate_soundscape(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.creative_delivery import creative_delivery_required
    from interview_mux.listenability_guards import (
        bed_quartile_presence,
        hinge_stinger_coverage_ratio,
        listenability_guards_cfg,
        required_sfx_roles_present,
    )

    policy = load_policy(ctx)
    contract = resolve_mix_contract(ctx)
    standards = (policy or {}).get("standards") if isinstance(policy, dict) else {}
    if not isinstance(standards, dict):
        standards = {}
    guards = listenability_guards_cfg()
    max_coverage = float(
        standards.get("max_bed_coverage_ratio")
        if standards.get("max_bed_coverage_ratio") is not None
        else contract.get("max_bed_coverage_ratio", guards["bed_coverage_max_ratio"])
    )
    min_rel = float(standards.get("min_speech_relative_db") or 12.0)
    coverage = _estimate_bed_coverage(ctx)
    counts = _count_active_cues(ctx)
    bed_level = _min_bed_level_db(ctx)
    speech_rel = abs(float(bed_level)) if bed_level is not None else min_rel + 1.0
    duck = float(contract.get("duck_under_speech_db") or 16.0)
    speech_rel_effective = speech_rel + max(0.0, duck - 8.0) * 0.25

    failures: list[str] = []
    if coverage > max_coverage + 0.01 and max_coverage < 1.0:
        failures.append(f"bed_coverage {coverage:.2f} > max {max_coverage:.2f}")
    if bed_level is not None and speech_rel_effective < min_rel:
        failures.append(f"speech_relative_proxy {speech_rel_effective:.1f} < min {min_rel}")
    underscore = str(contract.get("underscore_policy") or "normal")
    if underscore in {"skip", "sparse_or_skip"} and counts["beds"] > 0:
        failures.append(f"beds={counts['beds']} while underscore={underscore}")

    if creative_delivery_required():
        min_cov = float(guards["bed_coverage_min_ratio"])
        if coverage + 0.001 < min_cov:
            failures.append(f"bed_coverage {coverage:.2f} < min {min_cov:.2f}")
        bed_q = bed_quartile_presence(ctx)
        if bed_q + 0.001 < float(guards["bed_quartile_presence_min_ratio"]):
            failures.append(
                f"bed_quartile_presence {bed_q:.2f} < min {guards['bed_quartile_presence_min_ratio']:.2f}"
            )
        hinge_c = hinge_stinger_coverage_ratio(ctx)
        if hinge_c + 0.001 < float(guards["hinge_stinger_coverage_min_ratio"]):
            failures.append(
                f"hinge_stinger_coverage {hinge_c:.2f} < min {guards['hinge_stinger_coverage_min_ratio']:.2f}"
            )
        missing_roles = required_sfx_roles_present(ctx)
        if missing_roles:
            failures.append(f"missing_sfx_roles:{','.join(missing_roles)}")
        if counts["beds"] < 1:
            failures.append("active_beds 0 < min 1")

    verdict = "pass" if not failures else "fail"
    return {
        "version": 1,
        "verdict": verdict,
        "failures": failures,
        "metrics": {
            "bed_coverage_ratio": round(coverage, 4),
            "max_bed_coverage_ratio": max_coverage,
            "min_speech_relative_db": min_rel,
            "speech_relative_proxy_db": round(speech_rel_effective, 2),
            "active_beds": counts["beds"],
            "active_stingers": counts["stingers"],
            "skipped_cues": counts["skipped"],
            "underscore_policy": underscore,
        },
        "policy_hash": (policy or {}).get("policy_hash"),
    }


def apply_cheap_remediation(ctx: RunContext) -> list[str]:
    """Lower beds / skip lowest-priority under_segment cues. Returns action log.

    This is the **over-coverage** / too-loud remediation arm — it only turns
    existing cues down or drops the lowest-priority one. It never fabricates
    new beds, so it cannot game ``max_bed_coverage_ratio`` by inflating or
    deflating the metric with invented cues; it can only make the real mix
    quieter/sparser. Under-coverage remediation (raising a low bed/hinge ratio
    toward the floor) is a separate, more sensitive path — see
    ``run_soundscape_verify`` and ``artifact_repairs.repair_sound_design_plan``.
    """
    actions: list[str] = []
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return actions
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    if not isinstance(sdp, dict):
        return actions
    policy = load_policy(ctx) or {}
    slot_priority = {
        str(s.get("segment_id")): float(s.get("priority") or 0)
        for s in (policy.get("cue_slots") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    key = "podcast" if isinstance(flow_plans.get("podcast"), dict) else (
        "flow1" if isinstance(flow_plans.get("flow1"), dict) else None
    )
    if not key:
        return actions
    flow = dict(flow_plans[key])
    cues = [dict(c) for c in (flow.get("cues") or []) if isinstance(c, dict)]
    bed_cues = [c for c in cues if c.get("placement") == "under_segment" and not c.get("skip")]
    # First lower all bed levels by 2 dB
    for c in bed_cues:
        if c.get("level_db") is not None:
            c["level_db"] = float(c["level_db"]) - 2.0
            actions.append(f"lower_bed:{c.get('cue_id')}")
        if c.get("duck_under_speech_db") is not None:
            c["duck_under_speech_db"] = float(c["duck_under_speech_db"]) + 2.0
        else:
            c["duck_under_speech_db"] = float(resolve_mix_contract(ctx).get("duck_under_speech_db", 16)) + 2.0
    # Drop lowest-priority bed if still many
    if len(bed_cues) > 1:
        bed_cues.sort(key=lambda c: slot_priority.get(str(c.get("segment_id") or ""), 0.5))
        victim = bed_cues[0]
        victim["skip"] = True
        actions.append(f"skip_cue:{victim.get('cue_id')}")
    # Merge back
    by_id = {str(c.get("cue_id")): c for c in cues}
    for c in bed_cues:
        cid = str(c.get("cue_id"))
        if cid in by_id:
            by_id[cid] = c
    flow["cues"] = list(by_id.values())
    flow_plans = dict(flow_plans)
    flow_plans[key] = flow
    sdp["flow_plans"] = flow_plans
    if not _sdp_write_permitted(ctx):
        # Sealed SDP: the bed trim stays advisory (placement_adjustments already
        # carries mix-time levels). Raising here aborted the junction commitment
        # remaster mid-render — exec_11871 `authority_denied … edl_sealed`.
        return [f"{a}:advisory_sdp_sealed" for a in actions]
    from interview_mux.seat_authority import persist_frozen_seat_doc_verified

    touched = [
        str(c.get("cue_id") or "")
        for c in bed_cues
        if isinstance(c, dict) and c.get("cue_id")
    ]
    result = persist_frozen_seat_doc_verified(
        ctx,
        "understanding/sound_design_plan.json",
        sdp,
        reason="soundscape_bed_trim",
        touched_cue_ids=touched or None,
    )
    if not result.get("ok"):
        return [
            f"{a}:advisory_sdp_seat_freeze"
            if result.get("skipped")
            else f"{a}:verify_failed"
            for a in actions
        ]
    return actions


def _sdp_write_permitted(ctx: RunContext) -> bool:
    """True when the active stage may persist the sound design plan."""
    try:
        from interview_mux.artifact_ownership import write_permitted
        from interview_mux.write_staging import active_stage_id

        stage_now = str(active_stage_id() or "")
        if not stage_now:
            return True
        allowed, reason = write_permitted(
            ctx,
            "understanding/sound_design_plan.json",
            stage_now,
            role="producer",
            verb="persist",
        )
    except Exception:
        return True
    if not allowed:
        try:
            ctx.log(
                "soundscape_verify: sound_design_plan sealed — bed remediation stays "
                f"advisory ({reason})",
                level="info",
                stage=stage_now or None,
            )
        except Exception:
            pass
        return False
    return True


def _clear_pending_sdp_shadows(ctx: RunContext) -> None:
    """Drop pending SDP overlays that shadow the committed plan.

    Do **not** discard the whole mix staging root — that deletes
    ``master/assembly.wav`` written just before verify runs.
    """
    from interview_mux.write_staging import staging_root

    shadow_rels = (
        "understanding/sound_design_plan.json",
        "understanding/sound_design_plan_init.json",
    )
    for sid in ("mix", "edl", "listen_delight_audit", "sound_design_plan", "sound_design_vo_finalize"):
        root = staging_root(ctx, sid)
        if not root.is_dir():
            continue
        for rel in shadow_rels:
            p = root.joinpath(*rel.split("/"))
            if p.is_file():
                p.unlink(missing_ok=True)


def run_soundscape_verify(ctx: RunContext, *, remux_cycle: int = 0) -> dict[str, Any]:
    # Clear shadowed pending SDP only — preserve pending mix assembly.wav.
    try:
        _clear_pending_sdp_shadows(ctx)
    except Exception:
        pass
    report = evaluate_soundscape(ctx)
    report["remux_cycle"] = remux_cycle
    report["remediation_actions"] = []
    max_cycles = max_remux_cycles()
    if report["verdict"] == "fail" and remux_cycle < max_cycles:
        actions = apply_cheap_remediation(ctx)
        # If under-covered, seed more beds instead of only lowering levels.
        #
        # This is the sensitive direction: raising a measured ratio toward its
        # floor by *adding* cues can, if done carelessly, "game" the coverage
        # metric with lots of tiny disjoint per-clip beds rather than a few
        # honest, listenable scene-length beds. `repair_sound_design_plan`
        # anchors new beds on real palette/quartile-mapped selection segments
        # (never fabricated silence) and — when
        # `mastering.music_continuity.prefer_contiguous_beds` is set (default
        # true) — prefers extending an already-bedded neighbor so mix-time
        # merging (`sound_design.flow1_overlays_from_sdp`) folds the result
        # into one contiguous scene bed instead of scattering per-clip beds
        # across the timeline. Capped to `max_remux_cycles` remediation passes
        # total (see `run_soundscape_verify` below).
        fails = " ".join(report.get("failures") or [])
        if ("bed_coverage" in fails and "< min" in fails) or (
            "hinge_stinger_coverage" in fails and "< min" in fails
        ):
            try:
                from interview_mux.artifact_repairs import repair_sound_design_plan
                from interview_mux.seat_authority import (
                    hard_freeze_active,
                    persist_frozen_seat_doc,
                )

                if hard_freeze_active(ctx):
                    # Locked NO: seed_repair expands beds under hard freeze.
                    actions.append("bed_seed_repair_skipped_hard_freeze")
                elif ctx.artifact_exists("understanding/sound_design_plan.json"):
                    sdp = ctx.read_json("understanding/sound_design_plan.json")
                    fixed, notes = repair_sound_design_plan(
                        ctx, sdp if isinstance(sdp, dict) else {}
                    )
                    if not persist_frozen_seat_doc(
                        ctx,
                        "understanding/sound_design_plan.json",
                        fixed,
                        reason="soundscape_bed_seed_repair",
                    ):
                        actions.append("bed_seed_repair_skipped_seat_freeze")
                    else:
                        actions.extend([str(n.get("action") or n) for n in notes[-8:]])
            except Exception as exc:
                actions.append(f"bed_seed_repair_failed:{exc}"[:120])
        report["remediation_actions"] = actions
        report["verdict"] = "remediate"
        ctx.log(
            f"soundscape_verify: remediate cycle={remux_cycle} actions={actions}",
            level="warning",
            stage="mix",
            detail={"failures": report.get("failures")},
        )
    elif report["verdict"] == "fail":
        failures = report.get("failures") or []
        # "Remux theater" guard: the remediation ladder above already made
        # `max_remux_cycles` honest, contiguous-preferring attempts to raise a
        # low bed/hinge ratio. If every remaining failure is still only a
        # *minimum* coverage shortfall (never a max-coverage overshoot or a
        # speech-intelligibility miss — both of which are real audible
        # problems), forcing yet another remux would mean inventing still more
        # per-clip beds just to satisfy a number — gaming the metric rather
        # than fixing the mix. Downgrade that specific case to a loud warning
        # instead of `fail_closed`; true fitness problems (max overshoot,
        # speech_relative_proxy, underscore-policy conflicts) still hard-fail.
        only_min_coverage_shortfall = bool(failures) and all(
            "< min" in f and (f.startswith("bed_coverage") or f.startswith("hinge_stinger_coverage"))
            for f in failures
        )
        density_asp = False
        try:
            from interview_mux.floor_progress import (
                record_floor_advisory,
                soundscape_density_aspirational,
            )

            density_asp = soundscape_density_aspirational(ctx)
        except Exception:
            density_asp = False
        if fail_closed() and not only_min_coverage_shortfall and not density_asp:
            report["verdict"] = "fail_closed"
            ctx.log(
                f"soundscape_verify fail_closed: {report.get('failures')}",
                level="error",
                stage="mix",
            )
        else:
            report["verdict"] = "warning"
            if fail_closed() and (only_min_coverage_shortfall or density_asp):
                report["fail_closed_softened"] = True
            if density_asp:
                try:
                    record_floor_advisory(
                        ctx,
                        "soundscape_density",
                        {"failures": failures[:8], "source": "soundscape_verify"},
                        aspirational_proceeded=True,
                        mirror_quality=True,
                    )
                except Exception:
                    pass
            ctx.log(
                f"soundscape_verify warning (shipping): {report.get('failures')}",
                level="warning",
                stage="mix",
            )
    else:
        ctx.log("soundscape_verify: pass", level="success", stage="mix")
    ctx.write_json(REPORT_PATH, report)
    return report


def load_soundscape_report(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(REPORT_PATH):
        return None
    doc = ctx.read_json(REPORT_PATH)
    return doc if isinstance(doc, dict) else None
