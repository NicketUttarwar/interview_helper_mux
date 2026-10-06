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

import json
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
    NARRATIVE_MODES,
    default_pov_for_mode,
    nearest_mode_from_priors,
    prefer_forbid_volley_block,
)
from interview_mux.run_context import RunContext

AGENDA_REL = "mastering/shape/agenda.json"
RUBRIC_REL = "mastering/shape/eval_rubric.json"
CANDIDATES_REL = "mastering/shape/candidates.json"
_NORTH_STAR_PILLARS = ("finishability", "recommendability", "tape_integrity")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _heal_shape_stage(ctx: RunContext, stage: str) -> None:
    from interview_mux.stage_completion import heal_or_refuse_mark

    heal_or_refuse_mark(ctx, stage, force=True)


def ensure_schema_agenda(doc: dict[str, Any] | None) -> dict[str, Any]:
    """HM-1 3A: map heuristic/LLM agenda onto steps / budgets / north_star_pillars."""
    out = dict(doc or {})
    out.setdefault("version", 1)
    out.setdefault("generated_at", _now())
    steps_in = out.get("steps")
    mapped: list[dict[str, Any]] = []
    if isinstance(steps_in, list):
        for i, raw in enumerate(steps_in):
            if not isinstance(raw, dict):
                continue
            sid = str(raw.get("step_id") or raw.get("id") or f"step_{i}").strip()
            goal = str(raw.get("goal") or "").strip() or "shape step"
            row = dict(raw)
            row["step_id"] = sid or f"step_{i}"
            row["goal"] = goal
            mapped.append(row)
    if not mapped:
        # Prompt-shaped LLMs often emit ordered_custom_steps / custom_steps.
        for key in ("ordered_custom_steps", "custom_steps", "ordered_steps"):
            for i, raw in enumerate(out.get(key) or []):
                if not isinstance(raw, dict):
                    continue
                sid = str(
                    raw.get("step_id") or raw.get("id") or raw.get("step") or ""
                ).strip()
                goal = str(raw.get("goal") or "").strip()
                if not sid and goal:
                    sid = f"step_{i}"
                if sid and goal:
                    mapped.append({"step_id": sid, "goal": goal})
            if mapped:
                break
    if not mapped:
        mode = str(out.get("primary_mode_hypothesis") or "sparse_source")
        mapped = [
            {
                "step_id": "compete_modes",
                "goal": f"Compete on {mode} for a finishable listen",
            }
        ]
    out["steps"] = mapped
    budgets = dict(out.get("budgets") or {}) if isinstance(out.get("budgets"), dict) else {}
    try:
        max_steps = int(budgets.get("max_steps") or 0)
    except (TypeError, ValueError):
        max_steps = 0
    budgets["max_steps"] = max(1, max_steps or len(mapped))
    try:
        budgets["max_prompt_edits"] = max(0, int(budgets.get("max_prompt_edits") or 0))
    except (TypeError, ValueError):
        budgets["max_prompt_edits"] = 0
    try:
        budgets["max_flagship_calls"] = max(0, int(budgets.get("max_flagship_calls") or 0))
    except (TypeError, ValueError):
        budgets["max_flagship_calls"] = 0
    out["budgets"] = budgets
    pillars = [str(p).strip() for p in (out.get("north_star_pillars") or []) if str(p).strip()]
    if not pillars:
        seeds = out.get("system_prompt_draft_seeds")
        if isinstance(seeds, dict):
            pillars = [
                str(p).strip()
                for p in (seeds.get("excellence_pillars") or [])
                if str(p).strip()
            ]
    out["north_star_pillars"] = pillars or list(_NORTH_STAR_PILLARS)
    return out


def _invert_prompt_levels(levels: Any) -> dict[str, str] | None:
    """Map prompt-shaped {run:[ids], skip:[…], deepen:[…]} → schema {id: level}."""
    if not isinstance(levels, dict) or not levels:
        return None
    if all(
        isinstance(v, str) and v in {"run", "skip", "deepen"} for v in levels.values()
    ):
        return {str(k): str(v) for k, v in levels.items()}
    inverted: dict[str, str] = {}
    for level in ("run", "skip", "deepen"):
        raw = levels.get(level)
        if isinstance(raw, str) and raw.strip():
            inverted[raw.strip()] = level
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            key = str(item or "").strip()
            if key:
                inverted[key] = level
    return inverted or None


def _normalize_llm_shape_agenda(doc: dict[str, Any]) -> dict[str, Any]:
    """Coerce prompt-shaped meta-architect JSON onto mastering_shape_agenda schema."""
    out = dict(doc)
    inverted = _invert_prompt_levels(out.get("levels"))
    if inverted is not None:
        out["levels"] = inverted
    return out


def _persist_shape_agenda_skip(ctx: RunContext, skip_reason: str) -> None:
    ctx.write_json(
        AGENDA_REL,
        ensure_schema_agenda(
            {
                "version": 1,
                "pass": "provisional",
                "source": "stub",
                "skipped": skip_reason,
                "mode_candidates": ["sparse_source"],
                "generated_at": _now(),
            }
        ),
        stage_key="mastering_shape_agenda",
    )


def _persist_shape_candidates_skip(ctx: RunContext, skip_reason: str) -> None:
    ctx.write_json(
        CANDIDATES_REL,
        {
            "version": 1,
            "pass": "provisional",
            "candidates": [],
            "source": "stub",
            "skipped": skip_reason,
            "generated_at": _now(),
        },
        stage_key="mastering_shape_candidates",
    )


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


_COLD_OPEN_KINDS = frozenset(
    {"none", "segment_hook", "vo_clone_open", "vo_plus_segment"}
)


def _slim_brief_for_llm(doc: dict[str, Any]) -> dict[str, Any]:
    topics = []
    for t in (doc.get("topics") or [])[:8]:
        if isinstance(t, dict):
            topics.append(
                {
                    "name": t.get("name") or t.get("topic"),
                    "summary": str(t.get("summary") or "")[:240],
                }
            )
    return {
        "thesis": str(doc.get("thesis") or "")[:400],
        "topics": topics,
        "episode_title": doc.get("episode_title") or doc.get("title"),
    }


def _slim_gaps_for_llm(doc: dict[str, Any]) -> dict[str, Any]:
    rows = doc.get("evaluations") or doc.get("gaps") or []
    if not isinstance(rows, list):
        rows = []
    slim_rows = []
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        slim_rows.append(
            {
                "gap_type": row.get("gap_type") or row.get("type"),
                "severity": str(row.get("severity") or row.get("summary") or "")[:200],
                "severity": row.get("severity"),
            }
        )
    return {"count": len(rows), "top": slim_rows}


def _slim_manifest_for_llm(doc: dict[str, Any]) -> dict[str, Any]:
    segs = doc.get("segments") if isinstance(doc.get("segments"), list) else []
    out_segs = []
    for seg in segs[:40]:
        if not isinstance(seg, dict):
            continue
        out_segs.append(
            {
                "segment_id": seg.get("segment_id") or seg.get("id"),
                "text": str(seg.get("text") or "")[:160],
                "speaker": seg.get("speaker") or seg.get("speaker_id"),
            }
        )
    return {"segment_count": len(segs), "segments": out_segs}


def _slim_evidence_inline(ref: str, inline: Any) -> Any:
    """Slim evidence packet inlines for LLM payload (disk packet stays full)."""
    if not isinstance(inline, dict):
        return inline
    rel = str(ref or "")
    if rel.endswith("content_brief.json"):
        return _slim_brief_for_llm(inline)
    if rel.endswith("gap_evaluations.json") or rel.endswith("gap_report.json"):
        if "interviewer_lines" in inline:
            lines = [
                {
                    "line_id": ln.get("line_id"),
                    "gap_type": ln.get("gap_type"),
                    "text": str(ln.get("text") or "")[:160],
                }
                for ln in (inline.get("interviewer_lines") or [])[:12]
                if isinstance(ln, dict)
            ]
            return {"interviewer_line_count": len(inline.get("interviewer_lines") or []), "lines": lines}
        return _slim_gaps_for_llm(inline)
    if rel.endswith("manifest.json"):
        return _slim_manifest_for_llm(inline)
    if rel.endswith("selection.json"):
        ordered = inline.get("ordered_segment_ids") or inline.get("kept_segment_ids") or []
        if isinstance(ordered, list):
            return {"ordered_segment_ids": [str(x) for x in ordered[:40]]}
    if rel.endswith("source_topology.json"):
        return {
            "topology_class": inline.get("topology_class") or inline.get("class"),
            "speaker_count": len(inline.get("speakers") or [])
            if isinstance(inline.get("speakers"), list)
            else inline.get("speaker_count"),
        }
    if rel.endswith("analysis_state.json"):
        return {
            k: inline.get(k)
            for k in ("status", "phase", "gap_framing_enabled", "pipeline_mode")
            if k in inline
        }
    # Research dossier summary already small; pass through capped.
    try:
        raw = json.dumps(inline, ensure_ascii=False, default=str)
    except Exception:
        return {"status": "unserializable"}
    if len(raw) > 2500:
        return {"_truncated": True, "keys": list(inline.keys())[:24]}
    return inline


def _shape_llm_user_payload(
    ctx: RunContext,
    *,
    consumer_id: str,
    pass_name: str,
    extra: dict[str, Any] | None = None,
    artifact: str = "agenda",
) -> dict[str, Any]:
    """Pack a bounded, structured Shape LLM packet (Q6B + honesty slim).

    Prefer the budgeted evidence packet over dumping full artifacts. Slim
    companion docs and evidence inlines so the model sees finishability signal.

    ``artifact`` selects the response contract: agenda | rubric | candidates | plan.
    """
    packet = compile_shape_evidence(ctx, consumer_id=consumer_id, pass_name=pass_name)
    items = list(packet.get("items") or []) if isinstance(packet, dict) else []
    omitted = list(packet.get("omitted") or []) if isinstance(packet, dict) else []
    art = str(artifact or "agenda").strip().lower()
    if art == "rubric":
        goal = (
            "Mint a source-specific eval rubric for THIS tape only — style_axes + "
            "weighted criteria + anti_patterns + hard_requirements. Do NOT return a "
            "mastering shape plan, agenda, or narrative_mode. Schema-valid JSON only."
        )
        response_contract = {
            "required_artifact": "mastering_eval_rubric",
            "must_include": [
                "style_axes (list or object with evidence)",
                "criteria[] with criterion_id, description, weight (sum ~1)",
                "anti_patterns[] with severity kill|penalize|note",
                "hard_requirements[]",
            ],
            "forbid": [
                "mastering_shape",
                "narrative_mode plan body",
                "empty criteria",
                "empty {}",
                "invented guest evidence",
            ],
        }
    elif art == "candidates":
        goal = (
            "Produce Shape mode candidates for this tape — not a generic template. "
            "Return schema-valid JSON only (no prose wrapper)."
        )
        response_contract = {
            "required_artifact": "mastering_shape_candidates",
            "candidates": [
                "candidates[] with narrative_mode",
                "optional scores.bespoke_fit / finishability",
            ],
            "forbid": ["empty {}", "template five-act checklists", "invented guest evidence"],
        }
    elif art == "plan":
        goal = (
            "Synthesize the authoritative mastering plan for this tape from the "
            "agenda, rubric, and candidates. Return schema-valid JSON only."
        )
        response_contract = {
            "required_artifact": "mastering_plan",
            "must_include": [
                "narrative_mode",
                "cold_open",
                "bespoke_rationale or decisions",
            ],
            "forbid": [
                "mastering_shape_agenda",
                "mastering_eval_rubric",
                "mastering_shape_candidates",
                "empty {}",
            ],
        }
    else:
        goal = (
            "Produce the best bespoke mastering shape agenda for this tape — "
            "not a generic template. Prefer finishable, recommendable listen. "
            "Return schema-valid JSON only (no prose wrapper)."
        )
        response_contract = {
            "required_artifact": "mastering_shape_agenda",
            "agenda": [
                "mode_candidates or steps/ordered_custom_steps or primary_mode_hypothesis",
                "budgets.max_steps",
                "north_star_pillars or system_prompt_draft_seeds.excellence_pillars",
            ],
            "forbid": ["empty {}", "template five-act checklists", "invented guest evidence"],
        }
    payload: dict[str, Any] = {
        "pass": pass_name,
        "consumer_id": consumer_id,
        "artifact": art,
        "evidence_packet_hash": evidence_packet_hash(packet),
        "evidence": {
            "items": [
                {
                    "ref": it.get("ref"),
                    "kind": it.get("kind"),
                    "salience": it.get("salience"),
                    "inline": _slim_evidence_inline(
                        str(it.get("ref") or ""), it.get("inline")
                    ),
                }
                for it in items
                if isinstance(it, dict)
            ],
            "omitted_refs": [
                (o.get("ref") if isinstance(o, dict) else None) for o in omitted
            ],
            "token_estimate": packet.get("token_estimate") if isinstance(packet, dict) else None,
        },
        "goal": goal,
        "response_contract": response_contract,
    }
    dossier = load_dossier(ctx)
    if isinstance(dossier, dict):
        payload["research_dossier"] = {
            "complete_fields": dossier.get("complete_fields"),
            "thin_fields": dossier.get("thin_fields"),
            "field_count": len(dossier.get("fields") or {}),
        }

    for rel, key, slim in (
        ("understanding/content_brief.json", "content_brief", _slim_brief_for_llm),
        ("understanding/gap_evaluations.json", "gap_evaluations", _slim_gaps_for_llm),
        ("mastering/shape/agenda.json", "agenda", None),
        ("mastering/shape/candidates.json", "candidates_doc", None),
        ("mastering/mastering_plan.json", "prior_plan", None),
        ("segments/manifest.json", "manifest", _slim_manifest_for_llm),
    ):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        if not isinstance(doc, dict) or not doc:
            continue
        if slim is not None:
            payload[key] = slim(doc)
        elif key == "prior_plan":
            payload[key] = {
                "plan_status": doc.get("plan_status"),
                "narrative_mode": doc.get("narrative_mode"),
                "source": doc.get("source"),
                "pass": doc.get("pass"),
            }
        elif key == "agenda":
            payload[key] = {
                "mode_candidates": doc.get("mode_candidates"),
                "primary_mode_hypothesis": doc.get("primary_mode_hypothesis"),
                "steps": (doc.get("steps") or [])[:8],
                "source": doc.get("source"),
            }
        elif key == "candidates_doc":
            cands = [
                {
                    "candidate_id": c.get("candidate_id"),
                    "narrative_mode": c.get("narrative_mode"),
                    "rationale": str(c.get("rationale") or "")[:200],
                }
                for c in (doc.get("candidates") or [])[:6]
                if isinstance(c, dict)
            ]
            payload[key] = {
                "pass": doc.get("pass"),
                "candidates": cands,
                "source": doc.get("source"),
            }
        else:
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
                    "conversation; soft bands are bed coverage 0.40-0.99, hinge stinger 0.3-1.0"
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
    return ensure_schema_agenda(agenda), rubric


def _lint_shape_agenda_llm(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reject hollow / schema-invalid agenda before ingest (Q6B)."""
    if not isinstance(doc, dict):
        return None
    has_signal = bool(
        doc.get("mode_candidates")
        or doc.get("steps")
        or doc.get("ordered_custom_steps")
        or doc.get("custom_steps")
        or doc.get("primary_mode_hypothesis")
        or (isinstance(doc.get("levels"), dict) and doc.get("levels"))
    )
    if not has_signal:
        return None
    ensured = ensure_schema_agenda(_normalize_llm_shape_agenda(doc))
    try:
        from interview_mux.prompt_validation import validate_mastering_shape_agenda

        errs = validate_mastering_shape_agenda(ensured)
        if errs:
            return None
    except Exception:
        pass
    return ensured


def _agenda_from_llm(arts: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(arts, dict):
        return None
    if isinstance(arts.get("agenda"), dict):
        cand = dict(arts["agenda"])
    elif isinstance(arts.get("mastering_shape_agenda"), dict):
        cand = dict(arts["mastering_shape_agenda"])
    else:
        cand = dict(arts)
    out = dict(cand)
    out.setdefault("version", 1)
    out.setdefault("pass", "provisional")
    out["source"] = "llm"
    out.setdefault("generated_at", _now())
    return _lint_shape_agenda_llm(out)


def _rubric_from_llm(arts: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(arts, dict):
        return None
    if isinstance(arts.get("eval_rubric"), dict):
        cand = dict(arts["eval_rubric"])
    elif isinstance(arts.get("mastering_eval_rubric"), dict):
        cand = dict(arts["mastering_eval_rubric"])
    else:
        cand = dict(arts)
    # Wrong-shaped plan/agenda body is not a rubric (exec_13157 mastering_shape).
    if cand.get("narrative_mode") and not (cand.get("criteria") or cand.get("style_axes")):
        return None
    if "mastering_shape" in arts and not (cand.get("criteria") or cand.get("style_axes")):
        nested = arts.get("mastering_shape")
        if isinstance(nested, dict) and not (
            nested.get("criteria") or nested.get("style_axes")
        ):
            return None
    if not (cand.get("criteria") or cand.get("style_axes")):
        return None
    # Empty criteria with empty style_axes list is hollow.
    criteria = cand.get("criteria")
    style_axes = cand.get("style_axes")
    if criteria == [] and style_axes in ([], {}, None):
        return None
    out = dict(cand)
    out.setdefault("version", 1)
    out["source"] = "llm"
    out.setdefault("generated_at", _now())
    try:
        from interview_mux.prompt_validation import validate_mastering_eval_rubric

        if validate_mastering_eval_rubric(out):
            return None
    except Exception:
        return None
    return out


def run_mastering_shape_agenda(ctx: RunContext) -> None:
    if not soft_gate_enabled():
        _persist_shape_agenda_skip(ctx, "soft_gate_disabled")
        _heal_shape_stage(ctx, "mastering_shape_agenda")
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
            if agenda is None:
                # CSP-05 / MSA: hollow agenda after ≤2 attempts — incomplete (no heuristic heal).
                from interview_mux.openai_primary_honesty import raise_hollow_openai_primary

                raise_hollow_openai_primary("mastering_shape_agenda", "agenda_llm_hollow")
            rubric_payload = _shape_llm_user_payload(
                ctx,
                consumer_id="shape_agenda_pass1",
                pass_name="provisional",
                artifact="rubric",
                extra={"agenda": agenda},
            )
            rubric_arts = invoke_mastering_prompt(
                ctx,
                "mastering_shape_agenda",
                "mastering/eval-rubric-mint.system.txt",
                rubric_payload,
                max_attempts=2,
            )
            rubric = _rubric_from_llm(rubric_arts)
            if rubric is None:
                # CSP-05 / MSA: rubric LLM fail → incomplete (no soft heuristic heal-done).
                ctx.write_json(AGENDA_REL, ensure_schema_agenda(agenda))
                ctx.write_json(
                    RUBRIC_REL,
                    {
                        "version": 1,
                        "source": "stub",
                        "llm_failed": True,
                        "notes": ["rubric_llm_failed"],
                        "criteria": [],
                        "style_axes": [],
                        "generated_at": _now(),
                    },
                )
                from interview_mux.openai_primary_honesty import raise_hollow_openai_primary

                raise_hollow_openai_primary("mastering_shape_agenda", "rubric_llm_failed")
            ctx.write_json(AGENDA_REL, ensure_schema_agenda(agenda))
            ctx.write_json(RUBRIC_REL, rubric)
            _heal_shape_stage(ctx, "mastering_shape_agenda")
            return

        agenda, rubric = _heuristic_agenda_and_rubric(ctx, llm_failed=False)
        ctx.write_json(AGENDA_REL, ensure_schema_agenda(agenda))
        ctx.write_json(RUBRIC_REL, rubric)
        _heal_shape_stage(ctx, "mastering_shape_agenda")
    except Exception as exc:
        from interview_mux.llm_simple import StageError
        from interview_mux.openai_primary_honesty import raise_hollow_openai_primary

        if isinstance(exc, StageError):
            raise
        if shape_llm_enabled():
            # CSP-05: shape.llm on + invoke/exception → incomplete, not soft stub heal.
            raise_hollow_openai_primary(
                "mastering_shape_agenda",
                f"agenda_exception:{type(exc).__name__}",
            )
        ctx.write_json(
            AGENDA_REL,
            ensure_schema_agenda(
                {
                    "version": 1,
                    "pass": "provisional",
                    "status": "degraded",
                    "error": str(exc),
                    "source": "stub",
                    "skipped": "agenda_exception",
                    "mode_candidates": ["sparse_source", "conversational_host"],
                    "generated_at": _now(),
                }
            ),
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
        _heal_shape_stage(ctx, "mastering_shape_agenda")


def _heuristic_candidates(ctx: RunContext, *, llm_failed: bool = False) -> dict[str, Any]:
    agenda = ctx.read_json(AGENDA_REL) if ctx.artifact_exists(AGENDA_REL) else {}
    agenda = agenda if isinstance(agenda, dict) else {}
    # Explicit empty mode_candidates → forced sparse survivor (not the missing-key default).
    if "mode_candidates" in agenda:
        modes = [m for m in list(agenda.get("mode_candidates") or []) if m]
    else:
        modes = ["conversational_host", "sparse_source"]
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


def _lint_shape_candidates_llm(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reject hollow / invalid candidates before ingest (Q6B)."""
    if not isinstance(doc, dict):
        return None
    raw = doc.get("candidates")
    if not isinstance(raw, list) or not raw:
        return None
    cands = [
        c
        for c in raw
        if isinstance(c, dict) and str(c.get("narrative_mode") or "").strip()
    ]
    if not cands:
        return None
    out = {
        "version": int(doc.get("version") or 1),
        "pass": str(doc.get("pass") or "provisional"),
        "candidates": cands,
        "source": "llm",
        "generated_at": doc.get("generated_at") or _now(),
    }
    try:
        from interview_mux.prompt_validation import validate_mastering_shape_candidates

        errs = validate_mastering_shape_candidates(out)
        if errs:
            return None
    except Exception:
        pass
    return out


def _candidates_from_llm(arts: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(arts, dict):
        return None
    if isinstance(arts.get("candidates"), list):
        return _lint_shape_candidates_llm(arts)
    for key in ("mastering_shape_candidates", "candidates_doc", "shape_candidates"):
        nested = arts.get(key)
        if isinstance(nested, dict):
            return _lint_shape_candidates_llm(nested)
    # Wrong artifact (agenda/plan) is hollow for this stage.
    if arts.get("mastering_shape_agenda") or arts.get("mastering_shape"):
        return None
    return None


def run_mastering_shape_candidates(ctx: RunContext) -> None:
    if not soft_gate_enabled():
        _persist_shape_candidates_skip(ctx, "soft_gate_disabled")
        _heal_shape_stage(ctx, "mastering_shape_candidates")
        return
    llm_on = shape_llm_enabled()
    try:
        if llm_on:
            from interview_mux.mastering_llm import invoke_mastering_prompt

            arts = invoke_mastering_prompt(
                ctx,
                "mastering_shape_candidates",
                "mastering/shape-l2-candidates.system.txt",
                _shape_llm_user_payload(
                    ctx,
                    consumer_id="shape_candidates_pass1",
                    pass_name="provisional",
                    artifact="candidates",
                ),
                max_attempts=2,
            )
            doc = _candidates_from_llm(arts)
            if doc is not None:
                ctx.write_json(CANDIDATES_REL, doc)
                _heal_shape_stage(ctx, "mastering_shape_candidates")
                return
            # MSC-B2 / CSP-05: shape.llm on → no heuristic soft-heal on hollow.
            from interview_mux.openai_primary_honesty import raise_hollow_openai_primary

            raise_hollow_openai_primary(
                "mastering_shape_candidates", "candidates_llm_hollow"
            )
        ctx.write_json(CANDIDATES_REL, _heuristic_candidates(ctx, llm_failed=False))
        _heal_shape_stage(ctx, "mastering_shape_candidates")
    except Exception as exc:
        from interview_mux.llm_simple import StageError

        if isinstance(exc, StageError):
            raise
        if llm_on:
            from interview_mux.openai_primary_honesty import raise_hollow_openai_primary

            raise_hollow_openai_primary(
                "mastering_shape_candidates", f"candidates_llm_failed:{exc}"
            )
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
        _heal_shape_stage(ctx, "mastering_shape_candidates")


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


def _lint_shape_plan_llm(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reject weak/hollow LLM plans before stamping complete (honesty pass)."""
    if not isinstance(plan, dict):
        return None
    mode = str(plan.get("narrative_mode") or "").strip()
    if mode not in NARRATIVE_MODES:
        return None
    cold = plan.get("cold_open")
    if not isinstance(cold, dict):
        return None
    kind = str(cold.get("kind") or "").strip() or "none"
    if kind not in _COLD_OPEN_KINDS:
        return None
    rationale = str(plan.get("bespoke_rationale") or "").strip()
    decisions = plan.get("decisions") if isinstance(plan.get("decisions"), list) else []
    if not rationale and not decisions:
        return None
    grammar_raw = plan.get("montage_grammar") or []
    if not isinstance(grammar_raw, list):
        grammar_raw = []
    grammar = [g for g in grammar_raw if g in GRAMMAR_MOVES]
    out = dict(plan)
    out["narrative_mode"] = mode
    out["cold_open"] = {**cold, "kind": kind}
    out["montage_grammar"] = grammar
    if rationale:
        out["bespoke_rationale"] = rationale
    return out


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
    linted = _lint_shape_plan_llm(plan)
    if linted is None:
        return None
    out = dict(linted)
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
    """Pass1 synthesize → provisional plan.

    MPS-B1 / A-03: under defaults soft_gate / heuristic paths never stamp
    ``plan_status=complete``. Authoritative complete only via accepted Shape-LLM
    artifacts that pass ``_lint_shape_plan_llm``.
    """
    if not soft_gate_enabled():
        write_plan(ctx, forced_sparse_plan(reason="soft_gate_disabled"))
        return
    try:
        packet = compile_shape_evidence(ctx, consumer_id="shape_synthesize_pass1", pass_name="provisional")
        eh = evidence_packet_hash(packet)
        llm_miss = False

        if shape_llm_enabled():
            from interview_mux.mastering_llm import invoke_mastering_prompt

            arts = invoke_mastering_prompt(
                ctx,
                "mastering_plan_synthesize",
                "mastering/flagship-synthesize.system.txt",
                _shape_llm_user_payload(
                    ctx,
                    consumer_id="shape_synthesize_pass1",
                    pass_name="provisional",
                    artifact="plan",
                ),
                max_attempts=2,
            )
            llm_plan = _plan_from_llm_artifacts(arts, pass_name="provisional", evidence_hash=eh)
            if llm_plan is not None:
                from interview_mux.shape_order_emit import attach_shape_order

                llm_plan = attach_shape_order(ctx, llm_plan)
                write_plan(ctx, llm_plan)
                return
            llm_miss = True

        cdoc = ctx.read_json(CANDIDATES_REL) if ctx.artifact_exists(CANDIDATES_REL) else {}
        cands = list((cdoc or {}).get("candidates") or [])
        if not cands:
            reason = "no_survivors"
            if llm_miss:
                reason = "llm_failed_no_survivors"
            plan = forced_sparse_plan(reason=reason, evidence_hash=eh)
            if llm_miss:
                reasons = list(plan.get("degradation_reasons") or [])
                if "llm_failed" not in reasons:
                    reasons.append("llm_failed")
                plan["degradation_reasons"] = reasons
                plan["source"] = "soft_gate"
            write_plan(ctx, plan)
            return
        chosen = cands[0]
        # MPS-B1 / A-03: soft_gate/heuristic never claims authoritative complete.
        status = claim_plan_complete(source="soft_gate")
        reasons = ["soft_gate_not_authoritative"]
        if llm_miss and "llm_failed" not in reasons:
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
    """Pass2 confirm after gap evaluations.

    MPC-B1: soft_gate off must not silent-return — write forced confirmed sparse
    and heal (CSP-01 / synthesize soft_gate_disabled precedent).
    """
    if not soft_gate_enabled():
        write_plan(ctx, forced_sparse_plan(reason="soft_gate_disabled"))
        _heal_shape_stage(ctx, "mastering_plan_confirm")
        return
    try:
        packet = compile_shape_evidence(ctx, consumer_id="shape_confirm_pass2", pass_name="confirmed")
        eh = evidence_packet_hash(packet)
        prev = ctx.read_json("mastering/mastering_plan.json") if ctx.artifact_exists("mastering/mastering_plan.json") else {}
        if not isinstance(prev, dict):
            prev = {}
        llm_miss = False

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
                    artifact="plan",
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
                from interview_mux.stage_completion import heal_or_raise

                heal_or_raise(ctx, "mastering_plan_confirm")
                return
            llm_miss = True

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
        if llm_miss and "llm_failed" not in reasons:
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
        from interview_mux.stage_completion import heal_or_raise

        heal_or_raise(ctx, "mastering_plan_confirm")
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
