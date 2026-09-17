"""Dimension → stage remutate for listen_delight floors (no soft-pass).

LD5: axis-scoped producers — sonic→music/SFX, mode→Shape/plan, conversation→VO/transitions.
B-07: recommendability maps to argmax of other failing dims; apply uses
``apply_bounded_invalidation(delight_axis_*)`` so predicates flip.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

REMUTATE_REL = "mastering/listen_delight_remutate.json"
MAX_ATTEMPTS = 3

_DIM_STAGES: dict[str, list[str]] = {
    "nugget_retention": [
        "full_master_ranking",
        "nugget_layup_compose",
        "edl",
        "mix",
        "listen_delight_audit",
    ],
    "cut_integrity": ["edl", "junction_snip_qa", "mix", "listen_delight_audit"],
    "conversation_fit": [
        "transitions",
        "vo_line_adjudicate",
        "edl",
        "mix",
        "listen_delight_audit",
    ],
    "story_followability": [
        "air_script_seams",
        "transitions",
        "edl",
        "mix",
        "listen_delight_audit",
    ],
    # LD5: sonic weave is music/SFX density — not EDL-only thrash.
    "sonic_weave": [
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "sound_design_plan",
        "mix",
        "listen_delight_audit",
    ],
    # LD5: mode coherence → Shape / plan producers (not ranking thrash).
    "mode_coherence": [
        "mastering_shape_agenda",
        "mastering_plan_synthesize",
        "gap_framing_compose",
        "edl",
        "mix",
        "listen_delight_audit",
    ],
    "finishability": ["full_master_ranking", "edl", "mix", "listen_delight_audit"],
    # recommendability is a composite — never maps directly (see _expand_recommendability).
}

_DIM_TO_PROFILE: dict[str, str] = {
    "conversation_fit": "delight_axis_story",
    "story_followability": "delight_axis_story",
    "cut_integrity": "delight_axis_cut",
    "sonic_weave": "delight_axis_sonic",
}

_MUSIC_EPOCH_STAGES = frozenset(
    {
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "sound_design_plan",
        "sound_design_palettes",
        "sound_design_vo_finalize",
    }
)


def _expand_recommendability(ctx: RunContext, failed_dimensions: list[str]) -> list[str]:
    """B-07: recommendability → argmax of *other* failing dims only."""
    dims = [str(d) for d in (failed_dimensions or []) if str(d)]
    if "recommendability" not in dims:
        return dims
    others = [d for d in dims if d != "recommendability"]
    if others:
        return others
    # Only recommendability failed — pick lowest-scoring other dim from last audit
    # that is below a soft floor; otherwise leave empty (exhaust — never mix-only).
    scores: dict[str, float] = {}
    try:
        if ctx.artifact_exists("mastering/listen_delight_audit.json"):
            audit = ctx.read_json("mastering/listen_delight_audit.json") or {}
            raw = audit.get("dimensions") if isinstance(audit, dict) else {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if str(k) == "recommendability":
                        continue
                    if str(k) not in _DIM_STAGES:
                        continue
                    try:
                        scores[str(k)] = float(v)
                    except (TypeError, ValueError):
                        continue
    except Exception:
        scores = {}
    if scores:
        worst = min(scores, key=lambda k: scores[k])
        # Only redirect when the other dim is clearly weak (< 0.9).
        if scores[worst] < 0.9:
            return [worst]
    return []


def plan_listen_delight_remutate(
    ctx: RunContext, *, failed_dimensions: list[str]
) -> dict[str, Any]:
    prior = (
        ctx.read_json(REMUTATE_REL)
        if ctx.artifact_exists(REMUTATE_REL)
        else {}
    )
    attempt = int((prior or {}).get("attempt") or 0) + 1
    expanded = _expand_recommendability(ctx, list(failed_dimensions or []))
    stages: list[str] = []
    for dim in expanded:
        mapped = _DIM_STAGES.get(str(dim))
        if not mapped:
            continue
        for sid in mapped:
            if sid not in stages:
                stages.append(sid)
    assembly_ready = ctx.artifact_exists("master/assembly_preview.wav") or ctx.is_done("edl")
    failed_set = {str(x) for x in expanded}
    if assembly_ready and "cut_integrity" not in failed_set:
        # Ranking/layup rewind cannot raise retention without destroying seated air.
        skip = {
            "full_master_ranking",
            "nugget_layup_compose",
            "gap_framing_compose",
            "edl",
        }
        # Sonic-only: also skip edl (already in skip) — keep music producers.
        if failed_set <= {"sonic_weave"}:
            skip |= {"mastering_shape_agenda", "mastering_plan_synthesize"}
        # Conversation/story dims need transition/VO/EDL producers — do not strip edl.
        narrative = failed_set & {"conversation_fit", "story_followability"}
        if narrative:
            skip.discard("edl")
        stages = [s for s in stages if s not in skip]
        if "sonic_weave" in failed_set and not ctx.is_done("mmaudio_sfx"):
            lead = [
                "music_palette_compose",
                "mmaudio_sfx",
                "mix",
                "listen_delight_audit",
            ]
        elif not ctx.is_done("mmaudio_sfx") and not narrative:
            lead = ["mmaudio_sfx", "mix", "listen_delight_audit"]
        else:
            lead = ["mix", "listen_delight_audit"]
        # Remix-only remutate cannot raise conversation/story (forensics exec_10066).
        if narrative:
            narr_lead: list[str] = []
            if "story_followability" in failed_set:
                narr_lead.append("air_script_seams")
            narr_lead.extend(["transitions", "vo_line_adjudicate"])
            lead = narr_lead + [s for s in lead if s not in narr_lead]
        stages = lead + [s for s in stages if s not in lead]
    elif assembly_ready and "cut_integrity" in failed_set:
        lead = ["edl", "junction_snip_qa", "mix", "listen_delight_audit"]
        stages = lead + [s for s in stages if s not in lead]
    # Never lead narrative remutate with mix-only.
    narrative_dims = failed_set & {"conversation_fit", "story_followability"}
    if narrative_dims and stages and stages[0] in {"mix", "mmaudio_sfx", "listen_delight_audit"}:
        preferred = (
            "air_script_seams"
            if "story_followability" in failed_set
            else "transitions"
        )
        stages = [preferred] + [s for s in stages if s != preferred]
    plan = {
        "version": 1,
        "attempt": attempt,
        "max_attempts": MAX_ATTEMPTS,
        "failed_dimensions": list(failed_dimensions or []),
        "expanded_dimensions": expanded,
        "from_stages": stages,
        "from_stage": stages[0] if stages else None,
        "exhausted": attempt > MAX_ATTEMPTS or not stages,
    }
    ctx.write_json(REMUTATE_REL, plan)
    return plan


def apply_listen_delight_remutate(
    ctx: RunContext, plan: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Pack under-duration selection for nugget_retention and clear stage markers."""
    doc = plan or (
        ctx.read_json(REMUTATE_REL) if ctx.artifact_exists(REMUTATE_REL) else None
    )
    if not isinstance(doc, dict) or doc.get("exhausted"):
        return {"ok": False, "reason": "exhausted_or_missing"}
    prior_fp = str(doc.get("dims_fingerprint") or "")

    try:
        from interview_mux.homunculus.issues import emit_issue
        from interview_mux.homunculus.runtime import (
            conductor_owns_control_flow,
            recovery_allowed,
        )

        # Control flow: wait for conductor analysis only when there is a conductor.
        if conductor_owns_control_flow(ctx) and not recovery_allowed(
            ctx, "listen_delight_audit"
        ):
            emit_issue(
                ctx,
                kind="listen_delight_remutate",
                source="listen_delight_remutate",
                stage_id="listen_delight_audit",
                implicated=list(doc.get("from_stages") or ["listen_delight_audit"]),
                evidence={"failed_dimensions": doc.get("failed_dimensions")},
            )
            return {"ok": False, "reason": "awaiting_homunculus_analysis"}
    except Exception:
        pass

    notes: list[str] = []
    # Pillar C: gain meta-gate before invalidating timeline
    try:
        from interview_mux.timeline_reopen_meta_gate import (
            INTENT_DELIGHT,
            decide_timeline_reopen,
        )
        from interview_mux.seat_authority import (
            hard_freeze_active,
            request_seat_rewrite,
            soft_freeze_active,
        )

        failed_dims = [str(x) for x in (doc.get("failed_dimensions") or [])]
        narrative = set(failed_dims) & {"conversation_fit", "story_followability"}
        gate = decide_timeline_reopen(
            ctx,
            intent=INTENT_DELIGHT,
            failed_dims=failed_dims,
            detail={
                "overall": doc.get("overall"),
                "dim_scores": doc.get("dim_scores") or {},
                "from_stage": doc.get("from_stage"),
                "proposed_cost_stages": doc.get("from_stages") or [],
            },
        )
        if not gate.get("allow"):
            doc["status"] = "refused_low_gain"
            doc["gate"] = gate
            ctx.write_json(REMUTATE_REL, doc)
            return {"ok": False, "reason": "refused_low_gain", "gate": gate}
        doc["gate"] = gate
        doc["axes_allowed"] = list(gate.get("axes_allowed") or [])
        # Dual-gate: story remutate under soft/hard seat freeze also needs seat rewrite allow
        if narrative and (
            hard_freeze_active(ctx) or soft_freeze_active(ctx)
        ) and "air_script_seams" in (doc.get("from_stages") or []):
            seat_dec = request_seat_rewrite(
                ctx,
                proposed_delta={"ops": [], "from": "listen_delight_remutate"},
                reason="delight_story_remutate",
                symptoms=failed_dims,
            )
            if not seat_dec.get("allow"):
                # Narrow to transitions/edl without air_script_seams
                stages = [
                    s
                    for s in (doc.get("from_stages") or [])
                    if s != "air_script_seams"
                ]
                if not stages:
                    doc["status"] = "refused_seat_freeze"
                    doc["gate"] = gate
                    doc["seat_gate"] = seat_dec
                    ctx.write_json(REMUTATE_REL, doc)
                    return {
                        "ok": False,
                        "reason": "refused_seat_freeze",
                        "gate": gate,
                        "seat_gate": seat_dec,
                    }
                doc["from_stages"] = stages
                doc["from_stage"] = stages[0]
    except Exception as exc:
        # Fail-closed: do not remutate when the gain/seat gate errors
        doc["status"] = "refused_low_gain"
        doc["gate"] = {
            "allow": False,
            "refuse_reason": f"gain_gate_err:{type(exc).__name__}",
        }
        ctx.write_json(REMUTATE_REL, doc)
        return {
            "ok": False,
            "reason": "refused_low_gain",
            "gate": doc["gate"],
            "notes": [f"gain_gate_err:{exc}"],
        }

    raw_failed = {str(x) for x in (doc.get("failed_dimensions") or [])}
    expanded = list(doc.get("expanded_dimensions") or [])
    if not expanded:
        expanded = _expand_recommendability(ctx, list(raw_failed))
    failed = {str(x) for x in expanded}
    assembly_ready = ctx.artifact_exists("master/assembly_preview.wav") or ctx.is_done("edl")
    if (
        "nugget_retention" in failed
        and not assembly_ready
        and ctx.artifact_exists("master/selection.json")
    ):
        try:
            from interview_mux.creative_delivery import enforce_creative_selection_edit

            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                packed = enforce_creative_selection_edit(
                    ctx, sel, stage="listen_delight_remutate"
                )
                if isinstance(packed, dict):
                    ctx.write_json("master/selection.json", packed)
                    notes.append("packed_selection_for_nugget_retention")
        except Exception as exc:
            notes.append(f"pack_failed:{exc}")

    stages = [str(s) for s in (doc.get("from_stages") or []) if str(s)]
    # c15: honor axes_allowed from gain gate when present (narrow clears).
    axes_allowed = [str(a) for a in (doc.get("axes_allowed") or []) if a]
    if not axes_allowed:
        gate_row = doc.get("gate") if isinstance(doc.get("gate"), dict) else {}
        axes_allowed = [str(a) for a in (gate_row.get("axes_allowed") or []) if a]
    if not axes_allowed:
        try:
            from interview_mux.execution_status import ESR_REL

            if ctx.artifact_exists(ESR_REL):
                esr_doc = ctx.read_json(ESR_REL)
                last = (esr_doc or {}).get("reopen_gate") if isinstance(esr_doc, dict) else None
                if isinstance(last, dict):
                    axes_allowed = [str(a) for a in (last.get("axes_allowed") or []) if a]
        except Exception:
            pass

    # Map axes → stage clears; if axes_allowed set, filter stages to those axes.
    _AXIS_STAGES = {
        "story": {"air_script_seams", "transitions", "edl", "edl_narrative_audit"},
        "conversation_fit": {"air_script_seams", "transitions", "edl"},
        "story_followability": {"air_script_seams", "transitions", "edl"},
        "cut": {"edl", "junction_snip_qa", "mix"},
        "sonic": {"mmaudio_sfx", "music_palette_compose", "sfx_prompt_craft", "mix"},
        "delight_axis_story": {"air_script_seams", "transitions", "edl"},
        "delight_axis_cut": {"edl", "junction_snip_qa", "mix"},
        "delight_axis_sonic": {"mmaudio_sfx", "music_palette_compose", "mix"},
    }
    if axes_allowed:
        allowed_stages: set[str] = set()
        for ax in axes_allowed:
            allowed_stages |= _AXIS_STAGES.get(str(ax).lower(), set())
            if ax in stages:
                allowed_stages.add(ax)
        if allowed_stages:
            stages = [s for s in stages if s in allowed_stages]
            if stages:
                doc["from_stages"] = stages
                doc["from_stage"] = stages[0]
                notes.append(f"axes_allowed_narrowed:{','.join(axes_allowed[:6])}")
            else:
                doc["status"] = "refused_low_gain"
                doc["gate"] = {
                    "allow": False,
                    "refuse_reason": "axes_allowed_empty_intersection",
                    "axes_allowed": axes_allowed,
                }
                ctx.write_json(REMUTATE_REL, doc)
                return {
                    "ok": False,
                    "reason": "refused_low_gain",
                    "gate": doc["gate"],
                    "notes": notes + ["axes_allowed_no_stages"],
                }

    # LD5 / MusicGen↔delight seal: remutating into music epoch must break the seal.
    if any(s in _MUSIC_EPOCH_STAGES for s in stages):
        try:
            from interview_mux.delivery_guardrails import break_music_epoch_seal

            break_music_epoch_seal(ctx, reason="listen_delight_remutate_music_axis")
            notes.append("broke_music_epoch_seal")
        except Exception as exc:
            notes.append(f"break_music_epoch_seal_failed:{exc}")

    cleared: list[str] = []
    from_stage = str(doc.get("from_stage") or "")
    narrative = failed & {"conversation_fit", "story_followability"}
    # Never lead narrative remutate with mix-only.
    if narrative and from_stage in {"mix", "mmaudio_sfx", "listen_delight_audit"}:
        preferred = (
            "air_script_seams"
            if "story_followability" in failed
            else "transitions"
        )
        doc["from_stage"] = preferred
        from_stage = preferred
        notes.append(f"narrative_lead_rewritten:{preferred}")

    # B-07: apply via bounded delight_axis_* profiles so predicates flip.
    profiles_used: list[str] = []
    for dim in failed:
        pid = _DIM_TO_PROFILE.get(dim)
        if not pid or pid in profiles_used:
            continue
        profiles_used.append(pid)
        try:
            from interview_mux.execution_invalidation_profiles import (
                apply_bounded_invalidation,
            )

            result = apply_bounded_invalidation(
                ctx, pid, reason=f"listen_delight_remutate:{dim}"
            )
            for sid in result.get("cleared") or []:
                if sid not in cleared:
                    cleared.append(str(sid))
            notes.append(f"bounded:{pid}")
        except Exception as exc:
            notes.append(f"bounded_failed:{pid}:{exc}")

    # Fallback / supplement: clear planned stages not already cleared (respect narrative).
    preserve_edl = (
        not narrative
        and (
            from_stage
            in {"mmaudio_sfx", "mix", "listen_delight_audit", "music_palette_compose"}
            or (assembly_ready and "nugget_retention" in failed)
            or ("sonic_weave" in failed and "cut_integrity" not in failed)
        )
        and "cut_integrity" not in failed
    )
    for sid in stages:
        if preserve_edl and sid in {
            "full_master_ranking",
            "nugget_layup_compose",
            "edl",
            "assembly_preview",
        }:
            continue
        marker = ctx.run_dir / ".stage_done" / str(sid)
        if marker.is_file():
            marker.unlink(missing_ok=True)
            if sid not in cleared:
                cleared.append(str(sid))
    extra_clear = (
        ("mix", "junction_snip_qa", "listen_delight_audit")
        if preserve_edl
        else ("edl", "assembly_preview", "mix", "junction_snip_qa", "listen_delight_audit")
    )
    if narrative:
        # Narrative must include edl clear even when sonic also failed.
        extra_clear = (
            "edl",
            "assembly_preview",
            "mix",
            "junction_snip_qa",
            "listen_delight_audit",
        )
    for sid in extra_clear:
        marker = ctx.run_dir / ".stage_done" / sid
        if marker.is_file():
            marker.unlink(missing_ok=True)
            if sid not in cleared:
                cleared.append(sid)

    ctx.log(
        f"listen_delight remutate attempt {doc.get('attempt')}: "
        f"dims={doc.get('failed_dimensions')} cleared={cleared[:8]} notes={notes}",
        level="warning",
        stage="listen_delight_audit",
    )
    # Fingerprint failed dims so exhausted / unchanged remutate cannot soft-loop mix.
    try:
        import hashlib

        dim_fp = hashlib.sha256(
            ",".join(sorted(failed)).encode("utf-8")
        ).hexdigest()[:16]
        doc["dims_fingerprint"] = dim_fp
        doc["expanded_dimensions"] = expanded
        if (
            int(doc.get("attempt") or 0) >= int(doc.get("max_attempts") or MAX_ATTEMPTS)
            and prior_fp
            and prior_fp == dim_fp
        ):
            doc["exhausted"] = True
            notes.append("exhausted_unchanged_dims")
        ctx.write_json(REMUTATE_REL, doc, skip_handoff=True)
    except Exception:
        pass
    return {
        "ok": True,
        "cleared": cleared,
        "from_stage": doc.get("from_stage"),
        "notes": notes,
        "exhausted": bool(doc.get("exhausted")),
        "profiles": profiles_used,
    }
