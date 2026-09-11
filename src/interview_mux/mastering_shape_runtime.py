"""Two-pass Shape soft-gate runtime → mastering_plan.json.

Shape is a **mutation engine**, not a linear pass: candidates here are points
in the Essence mutation space — native keep/order, synthetic inserts
(cold open/VO/montage grammar), music/SFX/air (bed coverage, hinge stinger),
and soft duration ideal — that capability modules, critics, and auditions
mutate and re-score. See
docs/cross-cutting/mastering-shape-engine.md#shape-as-mutation-engine and
docs/cross-cutting/mastering-construction-decisions.md#decisions--essence-mutation-space.

Pass1 provisional before missing_framing; Pass2 confirm after gap evals.
Fail-open degradation ladder; no spend/timeout caps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_plan_loader import (
    claim_plan_complete,
    evidence_packet_hash,
    forced_sparse_plan,
    shape_llm_enabled,
    soft_gate_enabled,
    write_plan,
)
from interview_mux.mastering_research import compile_shape_evidence, load_dossier
from interview_mux.config import merged_config
from interview_mux.narrative_mode import (
    GRAMMAR_MOVES,
    default_pov_for_mode,
    nearest_mode_from_priors,
    prefer_forbid_volley_block,
)
from interview_mux.run_context import RunContext

AGENDA_REL = "mastering/shape/agenda.json"
RUBRIC_REL = "mastering/shape/eval_rubric.json"
CANDIDATES_REL = "mastering/shape/candidates.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _style_hints(ctx: RunContext) -> dict[str, str]:
    hints: dict[str, str] = {}
    if ctx.artifact_exists("understanding/analysis_state.json"):
        st = ctx.read_json("understanding/analysis_state.json")
        if isinstance(st, dict):
            style = st.get("style") if isinstance(st.get("style"), dict) else {}
            if style.get("tone_class"):
                hints["tone_class"] = str(style["tone_class"])
            if style.get("format_class"):
                hints["format_class"] = str(style["format_class"])
            meta = st.get("meta") if isinstance(st.get("meta"), dict) else {}
            if meta.get("production_style"):
                hints["production_style"] = str(meta["production_style"])
    if ctx.artifact_exists("run_meta.json"):
        meta = ctx.read_json("run_meta.json")
        if isinstance(meta, dict) and meta.get("production_style"):
            hints.setdefault("production_style", str(meta["production_style"]))
    return hints


def _competitive_modes(primary: str, *, max_candidates: int = 2) -> list[str]:
    pool = [
        "conversational_host",
        "guide_summary",
        "documentary_bridge",
        "hook_montage",
        "sparse_source",
    ]
    limit = max(1, int(max_candidates or 2))
    out = [primary]
    for m in pool:
        if m not in out:
            out.append(m)
        if len(out) >= limit:
            break
    return out


def _shape_soft_gate_cfg() -> dict[str, Any]:
    raw = ((merged_config().get("mastering") or {}).get("shape") or {}).get("soft_gate") or {}
    defaults = {
        "enable": True,
        "max_mode_candidates": 2,
        "skip_diversity": True,
        "prefer_talking_points_mode": True,
    }
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def _talking_points_bound(ctx: RunContext) -> bool:
    from interview_mux.ideal_cuts import boundaries_already_from_ideal_cuts, ideal_cuts_cfg

    if not ideal_cuts_cfg().get("enable", True):
        return False
    if not ctx.artifact_exists("understanding/talking_points.json"):
        return False
    return boundaries_already_from_ideal_cuts(ctx) or ctx.artifact_exists(
        "understanding/ideal_cuts_materialized.json"
    )


def _shape_llm_user_payload(
    ctx: RunContext,
    *,
    consumer_id: str,
    pass_name: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet = compile_shape_evidence(ctx, consumer_id=consumer_id, pass_name=pass_name)
    payload: dict[str, Any] = {
        "pass": pass_name,
        "evidence_packet_hash": evidence_packet_hash(packet),
        "goal": (
            "Produce the best bespoke mastering shape artifact for this tape — "
            "not a generic template. Prefer finishable, recommendable listen."
        ),
    }
    dossier = load_dossier(ctx)
    if isinstance(dossier, dict):
        payload["research_dossier"] = {
            "complete_fields": dossier.get("complete_fields"),
            "thin_fields": dossier.get("thin_fields"),
            "field_count": len(dossier.get("fields") or {}),
        }
    for rel, key in (
        ("understanding/content_brief.json", "content_brief"),
        ("understanding/gap_evaluations.json", "gap_evaluations"),
        ("mastering/shape/agenda.json", "agenda"),
        ("mastering/shape/candidates.json", "candidates_doc"),
        ("mastering/mastering_plan.json", "prior_plan"),
        ("segments/manifest.json", "manifest"),
    ):
        if ctx.artifact_exists(rel):
            try:
                doc = ctx.read_json(rel)
            except Exception:
                continue
            if isinstance(doc, dict) and doc:
                payload[key] = doc
    if extra:
        payload.update(extra)
    return payload


def _heuristic_agenda_and_rubric(
    ctx: RunContext, *, llm_failed: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    packet = compile_shape_evidence(ctx, consumer_id="shape_agenda_pass1", pass_name="provisional")
    hints = _style_hints(ctx)
    primary = nearest_mode_from_priors(hints)
    sg = _shape_soft_gate_cfg()
    max_cand = int(sg.get("max_mode_candidates") or 2)
    if sg.get("prefer_talking_points_mode", True) and _talking_points_bound(ctx):
        max_cand = min(max_cand, 2)
    modes = _competitive_modes(primary, max_candidates=max_cand)
    agenda: dict[str, Any] = {
        "version": 1,
        "pass": "provisional",
        "primary_mode_hypothesis": primary,
        "mode_candidates": modes,
        "style_hints": hints,
        "evidence_packet_hash": evidence_packet_hash(packet),
        "custom_steps": [
            {"id": "compete_modes", "goal": "best finishable recommendable listen"},
            {"id": "cold_open_ensemble", "goal": "bespoke cold open + body + VO/SFX"},
        ],
        "anti_patterns": [
            "generic_five_act_paste",
            "vo_restates_next_clip",
            "sensational_cold_open",
            "invented_unspoken_dialogue",
        ],
        "source": "heuristic",
        "generated_at": _now(),
    }
    if llm_failed:
        agenda["status"] = "degraded"
        agenda["notes"] = ["llm_failed"]
    rubric = {
        "version": 1,
        "style_axes": [
            {"axis": "narrative_mode_bias", "value": primary, "confidence": 0.6},
            {"axis": "tone", "value": hints.get("tone_class") or "unknown", "confidence": 0.5},
        ],
        # Each criterion below scores a candidate on one or more Essence mutation
        # axes (native keep/order, synthetic inserts, music/SFX/air, soft duration
        # ideal) — see mastering-shape-engine.md#shape-as-mutation-engine. Weight 0.0
        # criteria (nugget_density, sonic_weave) are informational for this advisory
        # L0 panel today; the authoritative hard-delight audit (listen_delight) is
        # what actually forces a remutate loop or blocks on those axes downstream.
        "criteria": [
            {
                "criterion_id": "finishability",
                "description": "Would a first-time listener finish?",
                "weight": 0.25,
                "higher_is_better": True,
                "owning_critics": ["engagement_listener"],
            },
            {
                "criterion_id": "recommendability",
                "description": "Would they recommend the episode?",
                "weight": 0.25,
                "higher_is_better": True,
                "owning_critics": ["engagement_listener"],
            },
            {
                "criterion_id": "mode_fit",
                "description": "Narrative mode fits the tape",
                "weight": 0.2,
                "higher_is_better": True,
                "owning_critics": ["narrative_editor", "style_fit"],
            },
            {
                "criterion_id": "information_clarity",
                "description": "Real knowledge conveyed without fabrication",
                "weight": 0.3,
                "higher_is_better": True,
                "owning_critics": ["narrative_editor", "integrity"],
            },
            {
                "criterion_id": "nugget_density",
                "description": (
                    "Essence mutation axis — native keep/order (optional/informational): golden "
                    "nuggets over padded tape, idea-per-minute density; hard floor is only "
                    "~10% of source runtime, this criterion judges quality above that floor"
                ),
                "weight": 0.0,
                "higher_is_better": True,
                "owning_critics": ["narrative_editor", "engagement_listener"],
            },
            {
                "criterion_id": "sonic_weave",
                "description": (
                    "Essence mutation axis — synthetic inserts + music/SFX/air (optional/"
                    "informational): native + synthetic + music/SFX/air read as one "
                    "conversation; soft bands are bed coverage 0.40-0.88, hinge stinger 0.3-1.0"
                ),
                "weight": 0.0,
                "higher_is_better": True,
                "owning_critics": ["audio_intelligibility", "style_fit"],
            },
        ],
        "anti_patterns": [
            {"id": "dull_template", "description": "Valid but dull checklist shape", "severity": "kill"},
            {"id": "fabricated_quotes", "description": "Invented unspoken dialogue", "severity": "kill"},
        ],
        "hard_requirements": [
            "never_invent_unspoken_dialogue",
            "consent_required_for_clone_voice",
        ],
        "rationale": (
            "Per-run delight rubric for Shape candidates (this L0 panel stays advisory); "
            "the actual ship gate for finishability/recommendability is the authoritative "
            "mastering.listen_delight audit downstream, not this rubric"
        ),
        "evidence_refs": ["mastering/evidence_packets/shape_agenda_pass1.json"],
        "source": "heuristic",
        "generated_at": _now(),
    }
    return agenda, rubric


def _agenda_from_llm(arts: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(arts, dict):
        return None
    cand = arts.get("agenda") if isinstance(arts.get("agenda"), dict) else arts
    if not isinstance(cand, dict):
        return None
    # Soft acceptance: either soft-gate shape (mode_candidates) or schema steps.
    if not (cand.get("mode_candidates") or cand.get("steps") or cand.get("primary_mode_hypothesis")):
        return None
    out = dict(cand)
    out.setdefault("version", 1)
    out.setdefault("pass", "provisional")
    out["source"] = "llm"
    out.setdefault("generated_at", _now())
    return out


def _rubric_from_llm(arts: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(arts, dict):
        return None
    cand = arts.get("eval_rubric") if isinstance(arts.get("eval_rubric"), dict) else arts
    if not isinstance(cand, dict):
        return None
    if not (cand.get("criteria") or cand.get("style_axes")):
        return None
    out = dict(cand)
    out.setdefault("version", 1)
    out["source"] = "llm"
    out.setdefault("generated_at", _now())
    return out


def run_mastering_shape_agenda(ctx: RunContext) -> None:
    if not soft_gate_enabled():
        return
    try:
        if shape_llm_enabled():
            from interview_mux.mastering_llm import invoke_mastering_prompt

            payload = _shape_llm_user_payload(
                ctx, consumer_id="shape_agenda_pass1", pass_name="provisional"
            )
            arts = invoke_mastering_prompt(
                ctx,
                "mastering_shape_agenda",
                "mastering/shape-meta-architect.system.txt",
                payload,
                max_attempts=2,
            )
            agenda = _agenda_from_llm(arts)
            rubric = None
            if agenda is not None:
                rubric_arts = invoke_mastering_prompt(
                    ctx,
                    "mastering_shape_agenda",
                    "mastering/eval-rubric-mint.system.txt",
                    {**payload, "agenda": agenda},
                    max_attempts=2,
                )
                rubric = _rubric_from_llm(rubric_arts)
                if rubric is None:
                    _, heuristic_rubric = _heuristic_agenda_and_rubric(ctx, llm_failed=False)
                    rubric = heuristic_rubric
                    rubric["notes"] = list(rubric.get("notes") or []) + ["rubric_llm_failed"]
                ctx.write_json(AGENDA_REL, agenda)
                ctx.write_json(RUBRIC_REL, rubric)
                return
            agenda, rubric = _heuristic_agenda_and_rubric(ctx, llm_failed=True)
            ctx.write_json(AGENDA_REL, agenda)
            ctx.write_json(RUBRIC_REL, rubric)
            return

        agenda, rubric = _heuristic_agenda_and_rubric(ctx, llm_failed=False)
        ctx.write_json(AGENDA_REL, agenda)
        ctx.write_json(RUBRIC_REL, rubric)
    except Exception as exc:
        ctx.write_json(
            AGENDA_REL,
            {
                "version": 1,
                "pass": "provisional",
                "status": "degraded",
                "error": str(exc),
                "mode_candidates": ["sparse_source", "conversational_host"],
                "generated_at": _now(),
            },
        )
        ctx.write_json(
            RUBRIC_REL,
            {
                "version": 1,
                "style_axes": [{"axis": "narrative_mode_bias", "value": "sparse_source"}],
                "criteria": [
                    {"criterion_id": "finishability", "description": "finish", "weight": 0.5},
                    {"criterion_id": "recommendability", "description": "recommend", "weight": 0.5},
                ],
                "generated_at": _now(),
            },
        )


def _heuristic_candidates(ctx: RunContext, *, llm_failed: bool = False) -> dict[str, Any]:
    agenda = ctx.read_json(AGENDA_REL) if ctx.artifact_exists(AGENDA_REL) else {}
    modes = list((agenda or {}).get("mode_candidates") or ["conversational_host", "sparse_source"])
    candidates = []
    for i, mode in enumerate(modes):
        grammar = list(prefer_forbid_volley_block(mode).get("prefer_grammar_moves") or [])[:3]
        candidates.append(
            {
                "candidate_id": f"cand_{i}_{mode}",
                "narrative_mode": mode,
                "montage_grammar": grammar,
                "cold_open_kind": "vo_plus_segment" if mode == "hook_montage" else "none",
                "pov": default_pov_for_mode(mode),
                "rationale": f"Compete on {mode} for best listen",
                "scores": {"bespoke_fit": 0.7 - i * 0.05, "finishability": 0.75 - i * 0.03},
            }
        )
    sg = _shape_soft_gate_cfg()
    if not sg.get("skip_diversity", True):
        try:
            from interview_mux.mastering_diversity import build_diversity_report, write_diversity_report

            div = build_diversity_report(candidates)
            write_diversity_report(ctx, div)
        except Exception:
            pass
    if not candidates:
        candidates = [
            {
                "candidate_id": "cand_forced_sparse",
                "narrative_mode": "sparse_source",
                "montage_grammar": [],
                "cold_open_kind": "none",
                "pov": "host_first_person",
                "rationale": "Guaranteed survivor",
                "scores": {"bespoke_fit": 0.4, "finishability": 0.5},
            }
        ]
    doc: dict[str, Any] = {
        "version": 1,
        "pass": "provisional",
        "candidates": candidates,
        "source": "heuristic",
        "generated_at": _now(),
    }
    if llm_failed:
        doc["notes"] = ["llm_failed"]
        doc["status"] = "degraded"
    return doc


def _candidates_from_llm(arts: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(arts, dict):
        return None
    raw = arts.get("candidates")
    if isinstance(raw, list) and raw:
        cands = [c for c in raw if isinstance(c, dict) and c.get("narrative_mode")]
        if not cands:
            return None
        return {
            "version": 1,
            "pass": "provisional",
            "candidates": cands,
            "source": "llm",
            "generated_at": _now(),
        }
    return None


def run_mastering_shape_candidates(ctx: RunContext) -> None:
    if not soft_gate_enabled():
        return
    try:
        if shape_llm_enabled():
            from interview_mux.mastering_llm import invoke_mastering_prompt

            arts = invoke_mastering_prompt(
                ctx,
                "mastering_shape_candidates",
                "mastering/shape-l2-candidates.system.txt",
                _shape_llm_user_payload(
                    ctx, consumer_id="shape_candidates_pass1", pass_name="provisional"
                ),
                max_attempts=2,
            )
            doc = _candidates_from_llm(arts)
            if doc is not None:
                ctx.write_json(CANDIDATES_REL, doc)
                return
            ctx.write_json(CANDIDATES_REL, _heuristic_candidates(ctx, llm_failed=True))
            return
        ctx.write_json(CANDIDATES_REL, _heuristic_candidates(ctx, llm_failed=False))
    except Exception as exc:
        ctx.write_json(
            CANDIDATES_REL,
            {
                "version": 1,
                "pass": "provisional",
                "candidates": [
                    {
                        "candidate_id": "cand_forced_sparse",
                        "narrative_mode": "sparse_source",
                        "montage_grammar": [],
                        "cold_open_kind": "none",
                        "rationale": f"candidates_failed:{exc}",
                    }
                ],
                "generated_at": _now(),
            },
        )


def _plan_from_candidate(
    cand: dict[str, Any],
    *,
    pass_name: str,
    plan_status: str,
    evidence_hash: str,
    provisional_mode: str | None = None,
    degradation_reasons: list[str] | None = None,
    source: str = "soft_gate",
) -> dict[str, Any]:
    from interview_mux.information_packages import default_episode_close

    mode = str(cand.get("narrative_mode") or "sparse_source")
    grammar = list(cand.get("montage_grammar") or [])
    grammar = [g for g in grammar if g in GRAMMAR_MOVES]
    cold_kind = str(cand.get("cold_open_kind") or "none")
    return {
        "version": 1,
        "pass": pass_name,
        "plan_status": plan_status,
        "source": source,
        "narrative_mode": mode,
        "montage_grammar": grammar,
        "provisional_mode": provisional_mode or mode,
        "confirmed_mode": mode if pass_name == "confirmed" else None,
        "pov": cand.get("pov") or default_pov_for_mode(mode),
        "cold_open": {
            "kind": cold_kind if cold_kind in ("none", "segment_hook", "vo_clone_open", "vo_plus_segment") else "none",
            "rationale": cand.get("rationale") or mode,
            "evidence_refs": ["mastering/shape/candidates.json"],
            "confidence": 0.65,
        },
        "information_packages": [],
        "episode_close": default_episode_close(),
        "decisions": [
            {
                "id": "narrative_mode",
                "owner_module": "structure_candidates",
                "decision": {"narrative_mode": mode, "montage_grammar": grammar},
                "rationale": cand.get("rationale") or "",
                "evidence_refs": ["mastering/shape/agenda.json"],
                "confidence": 0.65,
            }
        ],
        "bespoke_rationale": cand.get("rationale") or f"Selected {mode}",
        # Essence mutation-space hints alongside the delight pair: nugget_density tracks
        # the native keep/order axis, sonic_weave tracks synthetic+music/SFX/air. These
        # stay advisory here — the authoritative scorer is mastering.listen_delight.
        "listener_outcome": {
            "finishability": "optimize",
            "recommendability": "optimize",
            "nugget_density": "optimize",
            "sonic_weave": "optimize",
            "rationale": "Advisory delight criteria; hard ship gate is mastering.listen_delight downstream",
        },
        "invariants": {
            "never_invent_unspoken_dialogue": True,
            "prefer_pickup_voice": True,
            "pickup_voice_only": False,
        },
        "degradation_reasons": list(degradation_reasons or []),
        "evidence_packet_hash": evidence_hash,
        "generated_at": _now(),
    }


def _plan_looks_valid(plan: dict[str, Any]) -> bool:
    if plan.get("version") != 1:
        return False
    if not isinstance(plan.get("narrative_mode"), str) or not plan.get("narrative_mode"):
        return False
    if "cold_open" not in plan:
        return False
    return True


def _plan_from_llm_artifacts(
    arts: dict[str, Any] | None,
    *,
    pass_name: str,
    evidence_hash: str,
) -> dict[str, Any] | None:
    if not isinstance(arts, dict):
        return None
    plan = arts
    nested = arts.get("mastering_plan") or arts.get("plan")
    if isinstance(nested, dict):
        plan = nested
    if not _plan_looks_valid(plan):
        return None
    out = dict(plan)
    out["version"] = 1
    out["pass"] = pass_name
    out["plan_status"] = claim_plan_complete(source="llm")
    out["source"] = "llm"
    out["evidence_packet_hash"] = evidence_hash
    out.setdefault("generated_at", _now())
    out.setdefault("montage_grammar", list(out.get("montage_grammar") or []))
    out.setdefault("degradation_reasons", [])
    if out.get("plan_status") != "complete":
        reasons = list(out.get("degradation_reasons") or [])
        if "llm_not_authoritative" not in reasons:
            reasons.append("llm_not_authoritative")
        out["degradation_reasons"] = reasons
    return out


def run_mastering_plan_synthesize(ctx: RunContext) -> None:
    """Pass1 synthesize → provisional plan."""
    if not soft_gate_enabled():
        write_plan(ctx, forced_sparse_plan(reason="soft_gate_disabled"))
        return
    try:
        packet = compile_shape_evidence(ctx, consumer_id="shape_synthesize_pass1", pass_name="provisional")
        eh = evidence_packet_hash(packet)

        if shape_llm_enabled():
            from interview_mux.mastering_llm import invoke_mastering_prompt

            arts = invoke_mastering_prompt(
                ctx,
                "mastering_plan_synthesize",
                "mastering/flagship-synthesize.system.txt",
                _shape_llm_user_payload(
                    ctx, consumer_id="shape_synthesize_pass1", pass_name="provisional"
                ),
                max_attempts=2,
            )
            llm_plan = _plan_from_llm_artifacts(arts, pass_name="provisional", evidence_hash=eh)
            if llm_plan is not None:
                from interview_mux.shape_order_emit import attach_shape_order

                llm_plan = attach_shape_order(ctx, llm_plan)
                write_plan(ctx, llm_plan)
                return

        cdoc = ctx.read_json(CANDIDATES_REL) if ctx.artifact_exists(CANDIDATES_REL) else {}
        cands = list((cdoc or {}).get("candidates") or [])
        if not cands:
            plan = forced_sparse_plan(reason="no_survivors", evidence_hash=eh)
            write_plan(ctx, plan)
            return
        chosen = cands[0]
        # A-03: soft_gate/heuristic never claims authoritative complete.
        status = claim_plan_complete(source="soft_gate")
        reasons = ["soft_gate_not_authoritative"]
        if shape_llm_enabled() and "llm_failed" not in reasons:
            reasons.append("llm_failed")
        plan = _plan_from_candidate(
            chosen,
            pass_name="provisional",
            plan_status=status,
            evidence_hash=eh,
            degradation_reasons=reasons,
            source="soft_gate",
        )
        from interview_mux.shape_order_emit import attach_shape_order

        plan = attach_shape_order(ctx, plan)
        write_plan(ctx, plan)
    except Exception as exc:
        write_plan(ctx, forced_sparse_plan(reason=f"synthesize_failed:{exc}"))


def run_mastering_plan_confirm(ctx: RunContext) -> None:
    """Pass2 confirm after gap evaluations."""
    if not soft_gate_enabled():
        return
    try:
        packet = compile_shape_evidence(ctx, consumer_id="shape_confirm_pass2", pass_name="confirmed")
        eh = evidence_packet_hash(packet)
        prev = ctx.read_json("mastering/mastering_plan.json") if ctx.artifact_exists("mastering/mastering_plan.json") else {}
        if not isinstance(prev, dict):
            prev = {}

        if shape_llm_enabled():
            from interview_mux.mastering_llm import invoke_mastering_prompt

            arts = invoke_mastering_prompt(
                ctx,
                "mastering_plan_confirm",
                "mastering/flagship-synthesize.system.txt",
                _shape_llm_user_payload(
                    ctx,
                    consumer_id="shape_confirm_pass2",
                    pass_name="confirmed",
                    extra={"confirm": True, "prior_plan": prev},
                ),
                max_attempts=2,
            )
            llm_plan = _plan_from_llm_artifacts(arts, pass_name="confirmed", evidence_hash=eh)
            if llm_plan is not None:
                llm_plan["confirmed_mode"] = llm_plan.get("narrative_mode") or llm_plan.get(
                    "confirmed_mode"
                )
                if isinstance(prev.get("ordered_segment_ids"), list) and prev.get("ordered_segment_ids"):
                    llm_plan.setdefault("ordered_segment_ids", list(prev["ordered_segment_ids"]))
                if isinstance(prev.get("information_packages"), list):
                    llm_plan.setdefault("information_packages", list(prev["information_packages"]))
                if isinstance(prev.get("episode_close"), dict):
                    llm_plan.setdefault("episode_close", dict(prev["episode_close"]))
                from interview_mux.shape_order_emit import attach_shape_order

                llm_plan = attach_shape_order(ctx, llm_plan)
                write_plan(ctx, llm_plan)
                _maybe_shadow_diff(ctx, llm_plan)
                return

        provisional_mode = str(prev.get("narrative_mode") or prev.get("provisional_mode") or "conversational_host")
        # Re-score with gap evidence if present
        mode = provisional_mode
        if ctx.artifact_exists("understanding/gap_evaluations.json"):
            ge = ctx.read_json("understanding/gap_evaluations.json")
            n = 0
            if isinstance(ge, dict):
                ev = ge.get("evaluations") or ge.get("items") or []
                n = len(ev) if isinstance(ev, list) else 0
            if n == 0 and provisional_mode in ("documentary_bridge", "guide_summary"):
                mode = "sparse_source"  # refine toward sparse when no gaps
            elif n >= 8 and provisional_mode == "sparse_source":
                mode = "guide_summary"
        grammar = list(prefer_forbid_volley_block(mode).get("prefer_grammar_moves") or [])[:4]
        cand = {
            "narrative_mode": mode,
            "montage_grammar": grammar,
            "cold_open_kind": (prev.get("cold_open") or {}).get("kind") if isinstance(prev.get("cold_open"), dict) else "none",
            "pov": default_pov_for_mode(mode),
            "rationale": f"Pass2 confirm {provisional_mode}→{mode}",
        }
        reasons = []
        if mode != provisional_mode:
            reasons.append("pass2_mode_changed")
        status = claim_plan_complete(source="soft_gate")
        reasons.append("soft_gate_not_authoritative")
        if shape_llm_enabled() and "llm_failed" not in reasons:
            reasons.append("llm_failed")
        plan = _plan_from_candidate(
            cand,
            pass_name="confirmed",
            plan_status=status,
            evidence_hash=eh,
            provisional_mode=provisional_mode,
            degradation_reasons=reasons,
            source="soft_gate",
        )
        plan["confirmed_mode"] = mode
        # Preserve provisional order when confirm rebuilds from mode-only cand
        if isinstance(prev.get("ordered_segment_ids"), list) and prev.get("ordered_segment_ids"):
            plan["ordered_segment_ids"] = list(prev["ordered_segment_ids"])
        if isinstance(prev.get("information_packages"), list):
            plan["information_packages"] = list(prev["information_packages"])
        if isinstance(prev.get("episode_close"), dict):
            plan["episode_close"] = dict(prev["episode_close"])
        from interview_mux.shape_order_emit import attach_shape_order

        plan = attach_shape_order(ctx, plan)
        write_plan(ctx, plan)
        _maybe_shadow_diff(ctx, plan)
    except Exception as exc:
        # Keep provisional if present
        if ctx.artifact_exists("mastering/mastering_plan.json"):
            try:
                prev = ctx.read_json("mastering/mastering_plan.json")
                if isinstance(prev, dict):
                    prev = dict(prev)
                    reasons = list(prev.get("degradation_reasons") or [])
                    reasons.append(f"pass2_failed:{exc}")
                    prev["degradation_reasons"] = reasons
                    prev["plan_status"] = prev.get("plan_status") or "degraded"
                    if prev.get("plan_status") == "complete":
                        prev["plan_status"] = "degraded"
                    write_plan(ctx, prev)
                    return
            except Exception:
                pass
        write_plan(ctx, forced_sparse_plan(reason=f"pass2_failed:{exc}"))


def _maybe_shadow_diff(ctx: RunContext, plan: dict[str, Any]) -> None:
    from interview_mux.config import merged_config

    shape = ((merged_config().get("mastering") or {}).get("shape") or {}).get("soft_gate") or {}
    if not isinstance(shape, dict) or not shape.get("shadow_compare", True):
        return
    vo_density_air = 0
    if ctx.artifact_exists("understanding/gap_report.json"):
        gr = ctx.read_json("understanding/gap_report.json")
        if isinstance(gr, dict):
            lines = gr.get("interviewer_lines") or []
            vo_density_air = len(lines) if isinstance(lines, list) else 0
    legacy_proxy = {
        "production_style": None,
        "chapter_count": None,
        "vo_line_count": vo_density_air,
    }
    if ctx.artifact_exists("run_meta.json"):
        meta = ctx.read_json("run_meta.json")
        if isinstance(meta, dict):
            legacy_proxy["production_style"] = meta.get("production_style")
    if ctx.artifact_exists("master/narrative_plan.json"):
        np = ctx.read_json("master/narrative_plan.json")
        if isinstance(np, dict):
            ch = np.get("chapters") or []
            legacy_proxy["chapter_count"] = len(ch) if isinstance(ch, list) else 0
    diff = {
        "version": 1,
        "provisional_mode": plan.get("provisional_mode"),
        "confirmed_mode": plan.get("confirmed_mode") or plan.get("narrative_mode"),
        "legacy_structure_proxy": legacy_proxy,
        "vo_density_plan": len(plan.get("montage_grammar") or []),
        "vo_density_air": vo_density_air,
        "exclude_overlap_ratio": None,
        "cold_open_plan": (plan.get("cold_open") or {}).get("kind") if isinstance(plan.get("cold_open"), dict) else None,
        "cold_open_present": False,
        "delta_summary": "shadow compare advisory",
        "would_prefer_plan": 0.6,
        "advisory": True,
        "generated_at": _now(),
    }
    ctx.write_json("mastering/shadow_diff.json", diff)


def provisional_mode_for_volley(ctx: RunContext) -> dict[str, Any] | None:
    """Prefer/forbid block for missing_framing from provisional plan."""
    from interview_mux.mastering_plan_loader import best_available_mode, load_plan_raw

    plan = load_plan_raw(ctx)
    if not plan:
        return None
    mode = best_available_mode(plan)
    return prefer_forbid_volley_block(mode, plan)
