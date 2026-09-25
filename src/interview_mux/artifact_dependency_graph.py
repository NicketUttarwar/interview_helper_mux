"""Artifact dependency graph — produces, requires, invalidates, consumers."""

from __future__ import annotations

import os
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
    ),
    "segment_classification": (
        "content_brief_reanchor",
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
    ),
    "speaker_roles": ("content_context", "boundary_detection", "segment_classification", "source_topology_build"),
    "source_topology_build": (
        "content_context",
        "boundary_detection",
        "segment_classification",
        "missing_framing",
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
    # EMB-B3: episode_meta_build does not read master transcript — only podcast_publish
    # consumes VTT/txt; stop over-invalidate of meta on transcript rebuild.
    "master_transcript_build": (
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
        "vo_line_adjudicate",
        "vo_synthesize",
        "edl",
    ),
    # GRS-B3: match artifact_sanitize.invalidate `_SANITIZE_CASCADE` for
    # understanding/gap_report.json (marker-only VO/EDL; no music wipe).
    "gap_report_sanitize": (
        "vo_line_adjudicate",
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
    ),
    "transitions": ("sound_design_plan", "vo_line_adjudicate", "vo_synthesize", "edl"),
    "sound_design_plan": ("sfx_prompt_craft", "vo_line_adjudicate", "vo_synthesize", "edl"),
    # SDVF-B3 / ENA-B3 (8B): no reverse invalidate of VO adjudicate/synth (thrash).
    "sound_design_vo_finalize": ("edl_narrative_audit", "edl"),
    "vo_line_adjudicate": ("vo_synthesize", "edl_narrative_audit", "edl"),
    "edl_narrative_audit": ("edl",),
    "vo_synthesize": ("edl_narrative_audit", "edl"),
    "g1_vo_pickup": (
        "sound_design_vo_finalize",
        "vo_line_adjudicate",
        "vo_synthesize",
        "edl",
        "assembly_preview",
        "mix",
        "master_finalize",
    ),
}


# ---------------------------------------------------------------------------
# Contract `requires` edges — gated (plan §3.4, todo `p1-gate-requires`)
# ---------------------------------------------------------------------------
# `inputs[].producer` is the one contract field that is NOT inert: it mints
# `requires` edges, which feed `upstream_closure()` -> `resolve_stage_plan()
# .prereq_chain` -> heal pins in `homunculus/agenda.py` and
# `publishability_boundary.py`. Populating contracts would therefore silently
# re-route healing for brain 0.1.0 and the current 0.2.0 walk.
#
# So contract-derived `requires` edges are consumed only under
# `MUX_CONTRACT_REQUIRES=1`. With the flag OFF (the default) the graph emits
# exactly `_BASELINE_REQUIRES_EDGES` below — the frozen set that HEAD produced
# before any group was populated — so newly declared dependencies are provably
# inert. `tests/test_contract_requires_gate.py` pins both halves.
#
# This list may only SHRINK, and only when the edge it drops is proven dead.
_ENV_CONTRACT_REQUIRES = "MUX_CONTRACT_REQUIRES"
_ENV_PRECISION = "MUX_PRECISION_INVALIDATE"

# Plan §5.4 rail 1: an AUDIO_MUTATING stage may only go precise once a fixture
# proves its precise edge set is a superset of the observed consumer set. Nothing
# has cleared that bar, so this set is empty and every audio stage stays
# whole-tail. `tests/test_precision_invalidation.py` fails if it grows without
# such a fixture.
_AUDIO_PRECISION_PROVEN: frozenset[str] = frozenset()

# Plan §5.4 made `propagation` / `consumers` SUBTRACTIVE: since precision landed,
# declaring them can REMOVE a stage from an invalidation set. So an absent or
# empty edge list must never be read as "nothing depends on this, safe to drop" —
# absent means *unknown*, and unknown resolves to the blanket set. A contract that
# genuinely has no consumers says so out loud instead:
#
#     edges:
#       consumers: terminal   # nothing downstream reads this stage's outputs
#       inputs: complete      # `inputs` enumerates every read this stage performs
#
# `complete` is the affirmative form for a non-empty list; `terminal` is the only
# way to spell an affirmatively *empty* consumer set. The field is documented in
# `docs/cross-cutting/stage-contracts/_contract-schema.json`.
_EDGES_KEY = "edges"
_EDGE_COMPLETE = "complete"
_EDGE_TERMINAL = "terminal"

_BASELINE_REQUIRES_EDGES: tuple[tuple[str, str, str], ...] = (
    ('air_script_compose', 'full_master_ranking', 'master/selection.json'),
    ('air_script_compose', 'mastering_plan_synthesize', 'mastering/mastering_plan.json'),
    ('air_script_seams', 'air_script_compose', 'mastering/mastering_plan.json'),
    ('air_script_seams', 'nugget_layup_compose', 'understanding/nugget_layup_plan.json'),
    ('air_script_seams', 'nugget_layup_compose', 'understanding/gap_report.json'),
    ('boundary_detection', 'content_context', 'understanding/content_brief.json'),
    ('boundary_topic_resplit', 'content_brief_reanchor', 'understanding/content_brief.json'),
    ('chapter_close_hitch', 'narrative_arc_plan', 'master/narrative_plan.json'),
    ('chapter_close_hitch', 'segment_classification', 'segments/manifest.json'),
    ('chapter_close_hitch', 'transcribe', 'transcript/full.json'),
    ('connector_seam_adjudicate', 'connector_fuse_pass', 'analysis/connector_seam_packets.json'),
    ('connector_seam_adjudicate', 'segment_classification', 'segments/manifest.json'),
    ('content_brief_reanchor', 'segment_classification', 'segments/manifest.json'),
    ('content_context', 'speaker_roles', 'understanding/speakers.json'),
    ('delivery_brief_build', 'gap_framing_compose', 'understanding/gap_report.json'),
    ('edl_narrative_audit', 'sound_design_plan', 'understanding/sound_design_plan.json'),
    ('episode_cover_prompt_craft', 'episode_meta_build', 'publish/episode_meta.json'),
    ('full_master_ranking', 'connector_fuse_pass_pre_ranking', 'analysis/connector_fuse_rounds_pre_ranking.json'),
    ('gap_framing_compose', 'missing_framing', 'understanding/gap_evaluations.json'),
    ('information_package_plan', 'nugget_corpus_mine', 'understanding/nugget_corpus.json'),
    ('island_cluster_structure_adjudicate', 'low_conf_island_scan', 'analysis/high_value_speech_islands.json'),
    ('island_cluster_structure_adjudicate', 'connector_fuse_pass', 'analysis/high_value_island_clusters.json'),
    ('island_cluster_structure_adjudicate', 'segment_classification', 'segments/manifest.json'),
    ('island_cluster_structure_adjudicate', 'transcribe', 'transcript/full.json'),
    ('junction_feel_audit', 'junction_snip_qa', 'master/junction_snip_qa.json'),
    ('junction_feel_audit', 'edl', 'master/edl.json'),
    ('junction_thought_complete', 'edl', 'master/edl.json'),
    ('junction_thought_complete', 'transcription', 'transcript/full.json'),
    ('master_transcript_build', 'master_finalize', 'master/master.wav'),
    ('master_transcript_build', 'edl', 'master/edl.json'),
    ('missing_framing', 'boundary_topic_resplit', 'segments/boundaries.json'),
    ('mmaudio_sfx', 'sound_design_plan', 'understanding/sound_design_plan.json'),
    ('mmaudio_sfx', 'sfx_prompt_craft', 'sound_design/sfx_prompts.json'),
    ('narrative_arc_plan', 'topic_coverage_audit', 'master/coverage_audit.json'),
    ('nugget_corpus_mine', 'air_script_compose', 'mastering/mastering_plan.json'),
    ('nugget_corpus_mine', 'full_master_ranking', 'master/selection.json'),
    ('nugget_corpus_mine', 'segment_classification', 'segments/manifest.json'),
    ('nugget_corpus_mine', 'talking_points_compose', 'understanding/talking_points.json'),
    ('nugget_corpus_mine', 'ideal_cuts_propose', 'understanding/ideal_cuts.json'),
    ('nugget_layup_compose', 'information_package_plan', 'mastering/shape/information_packages_audit.json'),
    ('nugget_layup_compose', 'full_master_ranking', 'master/selection.json'),
    ('nugget_layup_compose', 'nugget_corpus_mine', 'understanding/nugget_corpus.json'),
    ('nugget_layup_compose', 'segment_classification', 'segments/manifest.json'),
    ('nugget_layup_compose', 'talking_points_compose', 'understanding/talking_points.json'),
    ('optimal_questions', 'missing_framing', 'understanding/gap_evaluations.json'),
    ('segment_classification', 'boundary_detection', 'segments/boundaries.json'),
    ('sfx_prompt_craft', 'sound_design_plan', 'understanding/sound_design_plan.json'),
    ('sound_design_palettes', 'boundary_topic_resplit', 'segments/boundaries.json'),
    ('sound_design_plan', 'transitions', 'master/transitions.json'),
    ('topic_coverage_audit', 'delivery_brief_build', 'understanding/delivery_brief.json'),
    ('transitions', 'nugget_layup_compose', 'understanding/nugget_layup_plan.json'),
)


def contract_requires_enabled() -> bool:
    """Consume contract-derived `requires` edges? Default OFF."""
    raw = os.environ.get(_ENV_CONTRACT_REQUIRES)
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


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


def build_graph() -> list[DepEdge]:
    """Full dependency graph. `requires` edges follow `contract_requires_enabled()`."""
    return _build_graph_cached(contract_requires_enabled())


@lru_cache(maxsize=2)
def _build_graph_cached(requires_from_contracts: bool) -> list[DepEdge]:
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
        if requires_from_contracts:
            for inp in c.inputs:
                if inp.producer:
                    edges.append(DepEdge("requires", sid, inp.producer, inp.path))
        else:
            # Frozen baseline, emitted in this stage's slot so edge *order* — and
            # therefore `upstream_closure()`'s return order — is unchanged too.
            for from_id, to_id, rel in _baseline_requires_by_stage().get(sid, ()):
                edges.append(DepEdge("requires", from_id, to_id, rel))

    return edges


@lru_cache(maxsize=1)
def _baseline_requires_by_stage() -> dict[str, tuple[tuple[str, str, str], ...]]:
    grouped: dict[str, list[tuple[str, str, str]]] = {}
    for edge in _BASELINE_REQUIRES_EDGES:
        grouped.setdefault(edge[0], []).append(edge)
    return {sid: tuple(rows) for sid, rows in grouped.items()}


def _clear_graph_caches() -> None:
    """One cache-clear for every contract-derived cache in this module.

    Tests mutate contracts on disk and then call `build_graph.cache_clear()`; the
    precision caches are derived from the same contracts, so they must go with it
    or a test would decide invalidation off a stale edge set.
    """
    _build_graph_cached.cache_clear()
    _declared_downstream_cached.cache_clear()
    _declared_upstream_map.cache_clear()
    _precision_eligible_cached.cache_clear()
    _precision_droppable_cached.cache_clear()
    _audio_touching_cached.cache_clear()
    _on_master_path_cached.cache_clear()
    _outputs_owned.cache_clear()


# `build_graph` is a thin wrapper now, but callers (and every contract test) still
# clear its cache by name.
build_graph.cache_clear = _clear_graph_caches  # type: ignore[attr-defined]
build_graph.cache_info = _build_graph_cached.cache_info  # type: ignore[attr-defined]


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
    # Deliberately *not* `declared_downstream()`: this function's edge set is
    # consumed by callers outside invalidation, so it stays byte-identical to
    # today. `declared_downstream()` is the wider, invalidation-only view.
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


def declared_downstream(stage_id: str) -> tuple[str, ...]:
    """Every stage some declaration says depends on ``stage_id`` — one hop.

    The union of *all* available evidence, never a single field: contract
    `consumers` and `propagation`, the `ARTIFACTS_REGISTRY` consume edges, and the
    reverse `requires` edges. Unioning is what makes populating a contract a
    monotone operation — a new `consumers` entry can only widen the invalidation
    set, never narrow it (`tests/test_precision_invalidation.py` pins that, and
    plan §7 of the previous task is why it is pinned).

    An empty result means "nothing declares a dependency", which is *not* the
    same as "nothing downstream cares" — see `precision_eligible`, which refuses
    precision for exactly that case.
    """
    return _declared_downstream_cached(stage_id, contract_requires_enabled())


@lru_cache(maxsize=256)
def _declared_downstream_cached(stage_id: str, requires_from_contracts: bool) -> tuple[str, ...]:
    out: set[str] = set()
    for e in _build_graph_cached(requires_from_contracts):
        if e.kind == "consumes" and e.to_id == stage_id:
            out.add(e.from_id)
        if e.kind == "invalidates" and e.from_id == stage_id:
            out.add(e.to_id)
        if e.kind == "requires" and e.to_id == stage_id:
            out.add(e.from_id)
        if e.kind == "produces" and e.from_id == stage_id:
            for cons, paths in ARTIFACTS_REGISTRY.items():
                if e.artifact_path in paths:
                    out.add(cons)
    contract = load_contract(stage_id)
    if contract is not None:
        out.update(c for c in contract.consumers if c)
        out.update(t for t in contract.propagation if t)
    out.discard(stage_id)
    return tuple(sorted(out))


def declared_upstream(stage_id: str) -> tuple[str, ...]:
    """Every stage whose own declarations name ``stage_id`` as depending on it.

    The reverse view of `declared_downstream()`, and the only *corroborating*
    evidence there is: it comes from contracts other than ``stage_id``'s own. A
    stage nobody upstream has ever heard of has an unwitnessed inbound edge set —
    its `inputs` list may be complete, or may simply never have been written, and
    from inside that stage the two look identical.
    """
    return _declared_upstream_map(contract_requires_enabled()).get(stage_id, ())


@lru_cache(maxsize=2)
def _declared_upstream_map(requires_from_contracts: bool) -> dict[str, tuple[str, ...]]:
    sources: set[str] = set(all_contract_stage_ids())
    for order in _pipeline_orders():
        sources.update(order)
    inverted: dict[str, set[str]] = {}
    for src in sources:
        for tgt in _declared_downstream_cached(src, requires_from_contracts):
            inverted.setdefault(tgt, set()).add(src)
    return {tgt: tuple(sorted(srcs)) for tgt, srcs in inverted.items()}


def declared_terminal(stage_id: str) -> bool:
    """Does this contract explicitly declare it has NO consumers? (`edges.consumers: terminal`)"""
    return _contract_edges(stage_id).get("consumers") == _EDGE_TERMINAL


def _contract_edges(stage_id: str) -> dict[str, str]:
    contract = load_contract(stage_id)
    if contract is None:
        return {}
    block = contract.raw.get(_EDGES_KEY)
    if not isinstance(block, dict):
        return {}
    return {str(k): str(v).strip().lower() for k, v in block.items() if v is not None}


def contract_edges_complete(stage_id: str) -> bool:
    """Is this stage's edge information affirmatively complete, in both directions?

    The fail-safe precondition for dropping a stage (plan §5.4). "No declared
    edges" is a statement about the *contract*, never about the pipeline, so it
    can only ever mean **unknown**. Something has to have said so:

    * **inbound** — an upstream contract names this stage in its `consumers` /
      `propagation` / registry edges (`declared_upstream()`), or this contract
      declares `edges.inputs: complete`.
    * **outbound** — something declares a consumer of this stage
      (`declared_downstream()`), or this contract declares `edges.consumers:
      terminal`, which is the explicit spelling of "genuinely none".

    Absent markers plus absent edges is the one combination that must not read as
    "safe" — that confusion is what strands a stale artifact.
    """
    if load_contract(stage_id) is None:
        return False
    edges = _contract_edges(stage_id)
    inbound = bool(declared_upstream(stage_id)) or edges.get("inputs") == _EDGE_COMPLETE
    outbound = bool(declared_downstream(stage_id)) or edges.get("consumers") in (
        _EDGE_COMPLETE,
        _EDGE_TERMINAL,
    )
    return inbound and outbound


def on_master_path(stage_id: str) -> bool:
    """Does ``stage_id`` sit on the path to `master/master.wav`? Then never drop it.

    Belt and braces, deliberately independent of what any contract declares:
    `audio_touching()` covers everything that writes audio, `master_epoch
    .MASTER_PATH_STAGES` covers the non-audio stages whose re-run rewrites what
    the master is cut from (`edl`, `junction_snip_qa`), and the last clause
    catches anything that reads or writes the master file itself.
    """
    return _on_master_path_cached(stage_id)


@lru_cache(maxsize=256)
def _on_master_path_cached(stage_id: str) -> bool:
    if audio_touching(stage_id):
        return True
    try:
        from interview_mux.master_epoch import MASTER_PATH_STAGES, MASTER_REL
    except Exception:
        return True  # cannot tell ⇒ treat as master path ⇒ stay whole-tail
    if stage_id in MASTER_PATH_STAGES:
        return True
    paths = {STAGE_ARTIFACT_DISK_PATHS.get(stage_id) or ""}
    contract = load_contract(stage_id)
    if contract is not None:
        paths.update(o.path or "" for o in contract.outputs)
        paths.update(i.path or "" for i in contract.inputs)
    return MASTER_REL in paths


def precision_invalidate_enabled() -> bool:
    """Global kill switch for §5.4. Default ON — the *per-stage* gate is the safety."""
    raw = os.environ.get(_ENV_PRECISION)
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def audio_touching(stage_id: str) -> bool:
    """Does this stage write audio? Plan §5.4 rail 1 keeps those whole-tail.

    Wider than `budget.AUDIO_MUTATING` on purpose: any stage whose declared
    outputs include a wav is audio-touching, so `ingest`, `transcript_review_build`
    and `vo_synthesize` are covered without waiting for someone to remember to add
    them to a hand-maintained set.
    """
    return _audio_touching_cached(stage_id)


@lru_cache(maxsize=256)
def _audio_touching_cached(stage_id: str) -> bool:
    try:
        from interview_mux.homunculus.budget import AUDIO_MUTATING as BUDGET_AUDIO
        from interview_mux.homunculus.registry import AUDIO_MUTATING as REGISTRY_AUDIO

        if stage_id in BUDGET_AUDIO or stage_id in REGISTRY_AUDIO:
            return True
    except Exception:
        return True  # cannot tell ⇒ treat as audio ⇒ stay whole-tail
    paths = [STAGE_ARTIFACT_DISK_PATHS.get(stage_id) or ""]
    contract = load_contract(stage_id)
    if contract is not None:
        paths.extend(o.path or "" for o in contract.outputs)
    return any(p.endswith((".wav", ".mp3", ".m4a", "/")) or ".wav" in p for p in paths)


def precision_eligible(stage_id: str) -> bool:
    """May ``stage_id``'s declared edges narrow ITS OWN fan-out? (plan §5.4)

    Six conditions, all required. Failing any one keeps today's whole-tail
    behaviour, because over-invalidation only wastes work while
    under-invalidation ships a master built from stale parts.

    1. The global kill switch is on.
    2. The stage's group is conformance-green — the same `STRICT_GROUPS` ratchet
       that `contract_conformance` uses, not a second gate that could disagree.
    3. A contract exists at all.
    4. Something actually declares a downstream dependency. A hollow contract
       must never read as "nothing downstream cares"; with no declared edges
       there is nothing to be precise *with*.
    5. Every concrete declared output has an ownership catalog row (§4.2). An
       output nobody owns is an output whose writers are unknown, so its
       consumer set is unknown too.
    6. The stage writes no audio (rail 1), unless it is in
       `_AUDIO_PRECISION_PROVEN` — which is empty until a fixture proves the
       precise set is a superset of the observed consumer set.

    This is only half the gate. Whether a *particular* downstream stage may be
    dropped is `precision_droppable`, because that is a claim about the
    downstream stage's inputs, not about this stage's outputs.
    """
    return _precision_eligible_cached(
        stage_id,
        precision_invalidate_enabled(),
        contract_requires_enabled(),
        _strict_groups_key(),
    )


def precision_droppable(stage_id: str) -> bool:
    """May ``stage_id`` be *left out* of somebody else's invalidation set?

    The near-miss that shaped this function: `audio_probe_build` is
    conformance-green and declares four consumers, so a source-side-only gate
    happily dropped `content_context`, `talking_points_compose`,
    `ideal_cuts_propose` and `speaker_roles` from its fan-out. All four really do
    read `transcript/protected_zones.json` — through
    `stage_input_helpers.transcript_quality_for_ctx`, which no contract mentions.
    The source's `consumers` list was simply incomplete, and nothing about the
    source could reveal that.

    So dropping a stage is a claim about **that stage's declared inputs being
    complete**, which only that stage's own conformance can support. It needs a
    green group, declared inputs (hollow inputs can never mean "reads nothing"),
    owned outputs, no audio, edge information that is affirmatively complete
    rather than merely absent (`contract_edges_complete`), and no seat on the
    path to `master.wav` (`on_master_path`).
    """
    return _precision_droppable_cached(
        stage_id,
        precision_invalidate_enabled(),
        contract_requires_enabled(),
        _strict_groups_key(),
    )


@lru_cache(maxsize=512)
def _precision_droppable_cached(
    stage_id: str,
    precision_on: bool,
    requires_from_contracts: bool,
    strict_key: tuple[str, ...],
) -> bool:
    if not precision_on or not stage_id:
        return False
    try:
        from interview_mux.contract_conformance import group_for_stage

        group = group_for_stage(stage_id)
    except Exception:
        return False
    if not group or group not in strict_key:
        return False
    contract = load_contract(stage_id)
    if contract is None or not [i for i in contract.inputs if i.path]:
        return False
    if not _outputs_owned(stage_id):
        return False
    if audio_touching(stage_id) and stage_id not in _AUDIO_PRECISION_PROVEN:
        return False
    if on_master_path(stage_id):
        return False
    if not contract_edges_complete(stage_id):
        return False
    return True


def _input_producers(stage_id: str) -> tuple[frozenset[str] | None, ...]:
    """Permitted writers of each declared input, `None` when unknown.

    One entry per declared input, and each entry is the WHOLE set of stages the
    ownership catalog lets write that artifact — never the single canonical
    producer. Collapsing to one producer under-invalidates: `gap_report_sanitize`
    declares `understanding/gap_report.json` with `producer: gap_framing_compose`,
    but the artifact has five permitted writers, so a redo of
    `nugget_layup_compose` looked like it touched nothing `gap_report_sanitize`
    reads and dropped it — sanitizing a gap report against a pre-rewrite state.

    An unknown writer set is an unknown dependency, so it makes the consumer
    un-droppable — the caller must not read a missing edge as an absent one.
    """
    contract = load_contract(stage_id)
    if contract is None:
        return ()
    out: list[frozenset[str] | None] = []
    for inp in contract.inputs:
        if not inp.path:
            continue
        out.append(_permitted_writers(inp.path, inp.producer or ""))
    return tuple(out)


@lru_cache(maxsize=512)
def _permitted_writers(rel: str, declared_producer: str = "") -> frozenset[str] | None:
    """Every stage permitted to write ``rel``; `None` when the writers are unknown.

    The ownership catalog is the SSOT for "permitted writer" (§4.2): the artifact
    row's `producers`, plus every ALLOW row that names a stage, whatever role it
    writes under — `air_contract_sanitize` writes `understanding/gap_report.json`
    as `sanitize` and is a real writer of it.

    Catalog rows can still under-report — `transcript/protected_zones.json` names
    only `transcribe`, while `audio_probe_build` mints it and
    `vernacular_segment_sanitize` rewrites it — so any stage that declares the
    path as a contract output counts too, as does the input's own declared
    `producer`.

    Only ever a union, never a difference. DENY rows are deliberately not applied:
    most are epoch-scoped, this call has no run to read an epoch from, and
    subtracting a writer is the under-invalidating direction. A path the catalog
    has no row for has *unknown* writers and answers `None` rather than falling
    back to whichever stage happens to own the disk path.
    """
    try:
        # `_path_matches` is the catalog's own glob matcher; re-implementing it
        # here would let the two drift apart on exactly the glob rows
        # (`vo_pickup/*.wav`) where a missed match under-invalidates.
        from interview_mux.artifact_ownership import (
            ALLOW,
            _norm_path,
            _path_matches,
            row_for_path,
        )
    except Exception:
        return None
    row = row_for_path(rel)
    if row is None:
        return None
    norm = _norm_path(rel)
    writers = {p for p in row.producers if p}
    writers.update(
        a.stage for a in ALLOW if a.stage and a.verb == "persist" and _path_matches(a.path, norm)
    )
    writers.update(_declared_output_writers().get(norm, ()))
    if declared_producer:
        writers.add(declared_producer)
    canonical = _producer_of_path(rel)
    if canonical:
        writers.add(canonical)
    return frozenset(writers) or None


@lru_cache(maxsize=1)
def _declared_output_writers() -> dict[str, frozenset[str]]:
    """Path -> stages whose contract declares it as an output."""
    out: dict[str, set[str]] = {}
    for sid in all_contract_stage_ids():
        contract = load_contract(sid)
        if contract is None:
            continue
        for o in contract.outputs:
            if o.path:
                out.setdefault(o.path, set()).add(sid)
    return {p: frozenset(s) for p, s in out.items()}


@lru_cache(maxsize=512)
def _producer_of_path(rel: str) -> str:
    for stage, path in STAGE_ARTIFACT_DISK_PATHS.items():
        if path == rel:
            return stage
    return ""


def _strict_groups_key() -> tuple[str, ...]:
    try:
        from interview_mux.contract_conformance import strict_groups

        return tuple(sorted(strict_groups()))
    except Exception:
        return ()


@lru_cache(maxsize=512)
def _precision_eligible_cached(
    stage_id: str,
    precision_on: bool,
    requires_from_contracts: bool,
    strict_key: tuple[str, ...],
) -> bool:
    if not precision_on or not stage_id:
        return False
    try:
        from interview_mux.contract_conformance import group_for_stage

        group = group_for_stage(stage_id)
    except Exception:
        return False
    if not group or group not in strict_key:
        return False
    if load_contract(stage_id) is None:
        return False
    if not _declared_downstream_cached(stage_id, requires_from_contracts):
        return False
    if not _outputs_owned(stage_id):
        return False
    if audio_touching(stage_id) and stage_id not in _AUDIO_PRECISION_PROVEN:
        return False
    return True


@lru_cache(maxsize=256)
def _outputs_owned(stage_id: str) -> bool:
    """Ownership-clean (§4.2): every concrete declared output has a catalog row."""
    try:
        from interview_mux.artifact_ownership import row_for_path
        from interview_mux.stage_contract import is_path_spec

        contract = load_contract(stage_id)
        if contract is None:
            return False
        for out in contract.outputs:
            rel = out.path or ""
            if not rel or is_path_spec(rel):
                continue
            if row_for_path(rel) is None:
                return False
        return True
    except Exception:
        return False


def transitive_invalidate(from_stage: str) -> list[str]:
    """Stages to invalidate because ``from_stage`` changed (plan §5.4).

    Whole-tail by default — one stale artifact reopens everything after it, which
    is the ~49 backward-rewind excess dispatches of §5.1. Precision subtracts from
    that tail, and needs BOTH halves of the gate to agree: the source's contract
    must be trustworthy enough to narrow its own fan-out (`precision_eligible`),
    and each dropped stage's contract must be trustworthy enough to claim it reads
    nothing being re-run (`precision_droppable`).

    Under-invalidation ships a master built from stale parts, so every
    indeterminate answer here resolves to *more* invalidation, not less.
    """
    blanket = _blanket_invalidate(from_stage)
    if not precision_eligible(from_stage):
        return blanket

    declared = set(declared_downstream(from_stage))
    kept = list(blanket)
    # Everything still slated for a re-run. A stage may only leave this set when
    # its own contract proves it reads nothing produced by anything still in it,
    # so removals cascade to a fixpoint and the result is always a *subsequence*
    # of today's list — precision can subtract work, never add it.
    invalidated = set(blanket) | {from_stage}
    shrinking = True
    while shrinking:
        shrinking = False
        for sid in list(kept):
            if sid in declared or not precision_droppable(sid):
                continue
            writers = _input_producers(sid)
            # One entry per declared input, holding every stage permitted to
            # write it. Unknown writers, or any permitted writer still slated for
            # a re-run, and the input may be about to change under `sid`.
            if not writers or any(w is None or (w & invalidated) for w in writers):
                continue
            kept.remove(sid)
            invalidated.discard(sid)
            shrinking = True
    return kept


def _blanket_invalidate(from_stage: str) -> list[str]:
    """Today's behaviour: the whole pipeline tail plus the `invalidates` closure."""
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
    "audio_touching",
    "build_graph",
    "contract_edges_complete",
    "contract_requires_enabled",
    "declared_downstream",
    "declared_terminal",
    "declared_upstream",
    "downstream_consumers",
    "on_master_path",
    "precision_droppable",
    "precision_eligible",
    "precision_invalidate_enabled",
    "propagation_map",
    "root_cause_stage",
    "transitive_invalidate",
    "upstream_closure",
]
