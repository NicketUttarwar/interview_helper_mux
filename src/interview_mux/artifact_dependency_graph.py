"""Artifact dependency graph — produces, requires, invalidates, consumers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from interview_mux.context_resolver import ARTIFACTS_REGISTRY
from interview_mux.llm_flow_hardening import LLM_UPSTREAM_STAGE, resolve_llm_upstream_stage
from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER, FLOW2_ORDER, FLOW3_ORDER
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.stage_contract import all_contract_stage_ids, load_contract

# Legacy propagation seeds — superseded by contract + pipeline closure when present.
_PROPAGATION_SEEDS: dict[str, tuple[str, ...]] = {
    "boundary_detection": (
        "segment_classification",
        "content_brief_reanchor",
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
    ),
    "segment_classification": (
        "content_brief_reanchor",
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
    ),
    "speaker_roles": ("content_context", "boundary_detection", "segment_classification", "source_topology_build"),
    "source_topology_build": (
        "content_context",
        "boundary_detection",
        "segment_classification",
        "missing_framing",
        "optimal_questions",
        "narrative_arc_plan",
        "full_master_ranking",
        "sound_design_plan",
    ),
    "content_context": (
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
        "narrative_arc_plan",
        "full_master_ranking",
        "topic_coverage_audit",
    ),
    "content_brief_reanchor": (
        "boundary_topic_resplit",
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
    ),
    "boundary_topic_resplit": (
        "segment_classification",
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
        "low_conf_island_scan",
        "connector_fuse_pass",
    ),
    "vernacular_segment_sanitize": (
        "low_conf_island_scan",
        "connector_fuse_pass",
    ),
    "low_conf_island_scan": (
        "connector_fuse_pass",
        "full_master_ranking",
    ),
    "connector_fuse_pass": (
        "connector_fuse_pass_pre_ranking",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "nugget_corpus_mine",
        "nugget_layup_compose",
        "transitions",
        "edl",
    ),
    "connector_fuse_pass_pre_ranking": (
        "full_master_ranking",
        "nugget_corpus_mine",
        "nugget_layup_compose",
    ),
    "sound_design_palettes": ("missing_framing", "optimal_questions"),
    "topic_coverage_audit": (
        "narrative_arc_plan",
        "connector_fuse_pass_pre_ranking",
        "full_master_ranking",
        "nugget_corpus_mine",
        "nugget_layup_compose",
        "transitions",
    ),
    "narrative_arc_plan": (
        "chapter_close_hitch",
        "connector_fuse_pass_pre_ranking",
        "full_master_ranking",
        "transitions",
    ),
    "chapter_close_hitch": (
        "connector_fuse_pass_pre_ranking",
        "full_master_ranking",
    ),
    "master_transcript_build": (
        "episode_meta_build",
        "podcast_publish",
    ),
    "full_master_ranking": (
        "nugget_corpus_mine",
        "nugget_layup_compose",
        "transitions",
        "sound_design_plan",
        "vo_synthesize",
        "edl",
    ),
    # Lay-up authority: the plan is only valid for the air order it was composed
    # against, so anything that can reshuffle selection must re-mine/recompose.
    "nugget_corpus_mine": (
        "nugget_layup_compose",
        "gap_framing_recompose",
        "transitions",
        "vo_synthesize",
        "edl",
    ),
    "nugget_layup_compose": (
        "gap_framing_recompose",
        "selection_framing_apply",
        "transitions",
        "vo_synthesize",
        "edl",
    ),
    "transitions": ("sound_design_plan", "vo_synthesize", "edl"),
    "sound_design_plan": ("sfx_prompt_craft", "vo_synthesize", "edl"),
    "edl_narrative_audit": ("vo_synthesize", "edl"),
    "vo_synthesize": ("edl",),
    "g1_vo_pickup": (
        "sound_design_vo_finalize",
        "vo_synthesize",
        "edl",
        "assembly_preview",
        "mix",
        "master_finalize",
    ),
}


@dataclass(frozen=True)
class DepEdge:
    kind: str
    from_id: str
    to_id: str
    artifact_path: str | None = None


def _pipeline_orders() -> list[list[str]]:
    return [list(ANALYSIS_ORDER), list(DELIVERY_ORDER)]


def _downstream_in_order(order: list[str], from_stage: str) -> list[str]:
    if from_stage not in order:
        return []
    idx = order.index(from_stage)
    return order[idx + 1 :]


@lru_cache(maxsize=1)
def build_graph() -> list[DepEdge]:
    edges: list[DepEdge] = []

    for stage, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        edges.append(DepEdge("produces", stage, rel, rel))

    for consumer, paths in ARTIFACTS_REGISTRY.items():
        for rel in paths:
            producer = next((s for s, p in STAGE_ARTIFACT_DISK_PATHS.items() if p == rel), None)
            if producer:
                edges.append(DepEdge("consumes", consumer, producer, rel))

    for stage, upstream in LLM_UPSTREAM_STAGE.items():
        if upstream:
            edges.append(DepEdge("llm_upstream", stage, upstream, None))

    for stage, targets in _PROPAGATION_SEEDS.items():
        for tgt in targets:
            edges.append(DepEdge("invalidates", stage, tgt, None))

    for sid in all_contract_stage_ids():
        c = load_contract(sid)
        if not c:
            continue
        for tgt in c.propagation:
            edges.append(DepEdge("invalidates", sid, tgt, None))
        for inp in c.inputs:
            if inp.producer:
                edges.append(DepEdge("requires", sid, inp.producer, inp.path))

    return edges


def upstream_closure(stage_id: str) -> list[str]:
    edges = build_graph()
    seen: set[str] = set()
    out: list[str] = []

    def walk(sid: str) -> None:
        for e in edges:
            if e.kind in ("requires", "llm_upstream", "consumes") and e.from_id == sid and e.to_id not in seen:
                seen.add(e.to_id)
                out.append(e.to_id)
                walk(e.to_id)

    walk(stage_id)
    return out


def downstream_consumers(stage_id: str, *, ctx: Any | None = None) -> list[str]:
    flow = None
    if ctx and hasattr(ctx, "artifact_exists") and ctx.artifact_exists("run_meta.json"):
        try:
            flow = (ctx.read_json("run_meta.json") or {}).get("selected_flow")
        except Exception:
            flow = None
    edges = build_graph()
    consumers: set[str] = set()
    for e in edges:
        if e.kind == "consumes" and e.to_id == stage_id:
            consumers.add(e.from_id)
        if e.kind == "invalidates" and e.from_id == stage_id:
            consumers.add(e.to_id)
        if e.kind == "produces" and e.from_id == stage_id:
            for cons, paths in ARTIFACTS_REGISTRY.items():
                if e.artifact_path in paths:
                    consumers.add(cons)
    if ctx:
        for cons in list(consumers):
            up = resolve_llm_upstream_stage(ctx, cons)
            if up and up != stage_id:
                consumers.discard(cons)
    for order in _pipeline_orders():
        for s in _downstream_in_order(order, stage_id):
            consumers.add(s)
    return sorted(consumers)


def transitive_invalidate(from_stage: str) -> list[str]:
    edges = build_graph()
    seen: set[str] = set()
    out: list[str] = []

    def walk(sid: str) -> None:
        for order in _pipeline_orders():
            for s in _downstream_in_order(order, sid):
                if s not in seen:
                    seen.add(s)
                    out.append(s)
        for e in edges:
            if e.kind == "invalidates" and e.from_id == sid and e.to_id not in seen:
                seen.add(e.to_id)
                out.append(e.to_id)
                walk(e.to_id)

    walk(from_stage)
    return out


def root_cause_stage(issue_message: str, consumer_stage: str, ctx: Any | None = None) -> str | None:
    from interview_mux.llm_flow_hardening import resolve_llm_upstream_stage

    low = issue_message.lower()
    if "key_claim without evidence" in low or "thesis" in low:
        return "content_context"
    if "boundary" in low or "timeline" in low:
        return "boundary_detection"
    if "not in manifest" in low:
        return "segment_classification"
    return resolve_llm_upstream_stage(ctx, consumer_stage) if ctx else LLM_UPSTREAM_STAGE.get(consumer_stage)


def propagation_map() -> dict[str, tuple[str, ...]]:
    """Stage → direct invalidate targets (union of seeds and contracts)."""
    out: dict[str, set[str]] = {}
    for e in build_graph():
        if e.kind == "invalidates":
            out.setdefault(e.from_id, set()).add(e.to_id)
    return {k: tuple(sorted(v)) for k, v in out.items()}


__all__ = [
    "DepEdge",
    "build_graph",
    "downstream_consumers",
    "propagation_map",
    "root_cause_stage",
    "transitive_invalidate",
    "upstream_closure",
]
