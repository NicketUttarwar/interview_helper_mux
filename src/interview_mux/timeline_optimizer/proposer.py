"""Propose mutations — heuristics always; LLM periodically (surface=maximum)."""

from __future__ import annotations

import random
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.timeline_optimizer.config import optimizer_cfg


def _hook_id(ctx: RunContext) -> str | None:
    if ctx.artifact_exists("understanding/episode_structure.json"):
        try:
            es = ctx.read_json("understanding/episode_structure.json")
            if isinstance(es, dict) and es.get("hook_segment_id"):
                return str(es["hook_segment_id"])
        except Exception:
            return None
    return None


def _narrative_plan(ctx: RunContext) -> dict[str, Any] | None:
    if ctx.artifact_exists("master/narrative_plan.json"):
        try:
            p = ctx.read_json("master/narrative_plan.json")
            return p if isinstance(p, dict) else None
        except Exception:
            return None
    return None


def heuristic_proposals(
    ctx: RunContext,
    candidate: dict[str, Any],
    *,
    score_breakdown: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic + light stochastic proposals custom to this candidate."""
    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or []) if s]
    props: list[dict[str, Any]] = []
    hook = _hook_id(ctx)
    plan = _narrative_plan(ctx)

    if hook and ordered and hook in ordered and hook not in ordered[:3]:
        props.append({"op": "ensure_hook_early", "hook_segment_id": hook, "priority": 90})

    props.append({"op": "topo_repair", "narrative_plan": plan, "priority": 85})
    props.append({"op": "drop_redundant_sibling", "priority": 70})
    props.append({"op": "remap_cold_open_music", "priority": 55})

    # Mint bridges for missing joins
    missing_n = int((score_breakdown or {}).get("missing_bridges") or 0)
    if missing_n > 0 and ctx.artifact_exists("understanding/reorder_bridges.json"):
        try:
            from interview_mux.bridge_completeness import missing_reorder_bridges
            from interview_mux.seam_glue import default_bridge_text, enrich_bridge_pair_excerpts

            bridges = ctx.read_json("understanding/reorder_bridges.json")
            # Rebuild against candidate order
            from interview_mux.reorder_bridges import build_reorder_bridges
            from interview_mux.bridge_voice_policy import annotate_reorder_bridges

            by_id = {}
            if ctx.artifact_exists("segments/manifest.json"):
                man = ctx.read_json("segments/manifest.json")
                by_id = {
                    str(s["segment_id"]): s
                    for s in ((man or {}).get("segments") or [])
                    if isinstance(s, dict) and s.get("segment_id")
                }
            br = annotate_reorder_bridges(build_reorder_bridges(ordered, by_id))
            for row in missing_reorder_bridges(
                br,
                gap_report=candidate.get("gap_report")
                if isinstance(candidate.get("gap_report"), dict)
                else None,
                transitions=candidate.get("transitions")
                if isinstance(candidate.get("transitions"), dict)
                else None,
            )[:4]:
                enriched = enrich_bridge_pair_excerpts(row, by_id)
                props.append(
                    {
                        "op": "mint_bridge",
                        "after_segment_id": enriched["after_segment_id"],
                        "before_segment_id": enriched["before_segment_id"],
                        "kind": enriched.get("kind"),
                        "source_gap_ms": enriched.get("source_gap_ms"),
                        "suggested_line_category": enriched.get("suggested_line_category"),
                        "after_excerpt": enriched.get("after_excerpt"),
                        "before_excerpt": enriched.get("before_excerpt"),
                        # Content-anchored hinge — not a global stock stub.
                        "suggested_text": default_bridge_text(enriched),
                        "type": "bridge",
                        "priority": 80,
                    }
                )
                props.append(
                    {
                        "op": "hinge_punctuator",
                        "after_segment_id": row["after_segment_id"],
                        "priority": 50,
                    }
                )
        except Exception:
            pass

    # Stochastic local search
    if len(ordered) >= 4:
        i, j = sorted(random.sample(range(len(ordered)), 2))
        props.append(
            {
                "op": "swap",
                "a": ordered[i],
                "b": ordered[j],
                "priority": 40,
            }
        )
        if len(ordered) >= 6:
            start = random.randint(0, len(ordered) - 3)
            end = min(len(ordered), start + random.randint(2, 4))
            props.append(
                {
                    "op": "rotate_block",
                    "start_index": start,
                    "end_index": end,
                    "rotate_by": 1,
                    "priority": 35,
                }
            )

    # Dual-candidate style: try chapter flatten
    try:
        from interview_mux.rank_candidates import chapter_order_from_plan

        ch = chapter_order_from_plan(plan)
        if ch and ch != ordered:
            kept = set(ordered)
            head = [s for s in ch if s in kept]
            tail = [s for s in ordered if s not in set(head)]
            filtered = head + tail
            if filtered and filtered != ordered:
                props.append(
                    {
                        "op": "set_order",
                        "ordered_segment_ids": filtered,
                        "priority": 65,
                        "source": "narrative_chapters",
                    }
                )
    except Exception:
        pass

    # Shape bind order if present
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        try:
            mp = ctx.read_json("mastering/mastering_plan.json")
            if isinstance(mp, dict):
                shape_ids = [str(s) for s in (mp.get("ordered_segment_ids") or []) if s]
                if shape_ids:
                    kept = set(ordered)
                    filtered = [s for s in shape_ids if s in kept]
                    if filtered and filtered != ordered:
                        props.append(
                            {
                                "op": "set_order",
                                "ordered_segment_ids": filtered,
                                "priority": 68,
                                "source": "shape_bind",
                            }
                        )
        except Exception:
            pass

    props.sort(key=lambda p: float(p.get("priority") or 0), reverse=True)
    return props


def llm_proposals(ctx: RunContext, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Ask flagship LLM for a small set of mutations (fail-open to [])."""
    cfg = optimizer_cfg()
    if not cfg.get("use_llm_proposer"):
        return []
    try:
        import json

        from interview_mux.stages.llm_runner import run_prompt_envelope
    except Exception:
        return []

    ordered = [str(s) for s in (candidate.get("ordered_segment_ids") or []) if s]
    payload = {
        "ordered_segment_ids": ordered[:80],
        "mutations_so_far": (candidate.get("mutations") or [])[-8:],
        "score": candidate.get("score"),
        "goal": "Propose 1-4 mutations to make a more finishable, beautiful podcast master.",
        "allowed_ops": [
            "swap",
            "move_before",
            "rotate_block",
            "exclude",
            "set_order",
            "mint_bridge",
            "rewrite_bridge",
            "gap_line_hint",
            "ensure_hook_early",
            "hinge_punctuator",
        ],
        "constraints": [
            "Never invent speaker names",
            "Never speak chapter/act numbers in bridge text",
            "Prefer succinct bridges",
            "Keep most segments; exclude sparingly",
        ],
    }
    try:
        envelope = run_prompt_envelope(
            "timeline_optimizer_propose",
            "mastering/timeline-optimizer-propose.system.txt",
            user_content=json.dumps(payload, ensure_ascii=False),
            ctx=ctx,
            include_preamble=True,
        )
    except Exception:
        return []

    arts = envelope.get("artifacts") if isinstance(envelope, dict) else None
    if not isinstance(arts, dict):
        arts = envelope if isinstance(envelope, dict) else {}
    raw = arts.get("mutations") or arts.get("timeline_mutations") or []
    out: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for row in raw[:4]:
            if isinstance(row, dict) and row.get("op"):
                row = dict(row)
                row["priority"] = float(row.get("priority") or 75)
                row["source"] = "llm"
                out.append(row)
    order = arts.get("ordered_segment_ids")
    if isinstance(order, list) and order:
        out.append(
            {
                "op": "set_order",
                "ordered_segment_ids": [str(s) for s in order if s],
                "priority": 78,
                "source": "llm_order",
            }
        )
    return out


def propose_batch(
    ctx: RunContext,
    candidate: dict[str, Any],
    *,
    generation: int,
    score_breakdown: dict[str, Any] | None = None,
    allow_llm: bool = True,
) -> list[dict[str, Any]]:
    cfg = optimizer_cfg()
    props = heuristic_proposals(ctx, candidate, score_breakdown=score_breakdown)
    if (
        allow_llm
        and cfg.get("use_llm_proposer")
        and generation > 0
        and generation % max(1, int(cfg.get("llm_every_n_gens") or 3)) == 0
    ):
        props = llm_proposals(ctx, candidate) + props
    # Beam: keep top by priority
    props.sort(key=lambda p: float(p.get("priority") or 0), reverse=True)
    width = max(1, int(cfg.get("beam_width") or 4))
    return props[:width]
