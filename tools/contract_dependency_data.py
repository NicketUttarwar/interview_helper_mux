"""Hand-derived stage dependency data, merged into contracts by the generator.

`tools/bootstrap_stage_contracts.py` **overwrites** every
`docs/cross-cutting/stage-contracts/*.yaml` on each run, and it runs as step 1 of
`scripts/verify_artifact_contract.sh`. Anything hand-edited into a contract file
is therefore reverted on the next verify. So the dependency data of plan §4.3
lives here, in the generator's input, and the YAML stays generated.

Organised by operator phase (`interview_mux.v2.phases`) because plan §3.3
populates upstream-first, one group at a time.

## Safety rule for `hard` vs `soft`

Contract `inputs` are **not** inert, contrary to plan §3.4 which claims
`inputs[].producer` is the only live lever. `artifact_lifecycle.run_phase_checks`
walks `contract.inputs`, and for every **hard** dep whose `when` holds it emits
`missing input <path> for <stage>` at `PRESTAGE` and runs `read_stale_guard`
against it. A wrongly-hard dep therefore gates a live stage — the same hazard as
`sufficiency`.

So while contracts are being populated:

* a dep is **hard** only when the stage body already refuses without it
  (`ctx.artifact_exists_required(...)`, or an unconditional read that raises);
* every other real dep is **soft**, which nothing live consumes;
* `producer` is set on both, and the `requires` edges it mints are gated by
  `MUX_CONTRACT_REQUIRES` (`artifact_dependency_graph`).

A soft row may additionally carry `correctness: true`. That marker is read by
`ship_reachability` alone — everything on the dispatch path filters on `hard` —
and it means the master would be *wrong* without the artifact even though the
stage body does not refuse. Justify one the same way hardness is justified: name
the code that degrades silently in its absence.

Evidence for each entry: `tools/extract_stage_artifact_touches.py` over the
stage's entrypoint module, cross-checked against `web/stages.py::STAGE_BY_ID`
(the promotion allowlist `flush_stage_writes` uses) and the guardrail tables in
`artifact_dependency_graph._PROPAGATION_SEEDS` / `stage_completion`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

# ---------------------------------------------------------------------------
# Producer resolution
# ---------------------------------------------------------------------------
# `inputs[].producer` is what mints a `requires` edge, so a guessed producer
# routes a heal to a stage that can only be denied — the inverse of the
# i12–i54 `authority_denied` class, and pinned by
# `tests/test_contract_ownership_xcheck.py::test_declared_producer_is_a_permitted_writer_of_the_input_path`.
#
# So it is derived, never typed by hand:
#
#   1. `STAGE_ARTIFACT_DISK_PATHS` — the declared path SSOT (plan §8.7). Where
#      several stages claim one path the FIRST is the canonical minter and the
#      rest are mutators (`master/selection.json` is minted by
#      `full_master_ranking`, then re-ordered by `selection_order_sanitize`).
#   2. Otherwise the ownership catalog, when it names exactly one pipeline
#      stage — covers sidecars with no SSOT row (`preclean/lineage.json`).
#   3. Otherwise none: the artifact is operator-, GUI- or ops-supplied and has
#      no stage that could heal it.


# Paths with no `STAGE_ARTIFACT_DISK_PATHS` row that several stages may write,
# so rule 2 cannot choose. Each is resolved by reading the writer.
PRODUCER_OVERRIDES: dict[str, str] = {
    # `stages/transcript_review.py` mints and rewrites it across the G0 loop;
    # `transcribe` holds a write row only to seed an empty corrections map.
    "transcript/corrections.json": "transcript_review_build",
    # Minted alongside `master/selection.json` in the ranking pass; the later
    # owners (`selection_order_sanitize`, `transitions`) re-order in place.
    "mastering/media_ip_cta.json": "full_master_ranking",
    "understanding/reorder_bridges.json": "full_master_ranking",
    "understanding/speaker_delivery_plan.json": "full_master_ranking",
    # Minted by the interviewer-script volley; `gap_framing_recompose` and
    # `air_script_seams` rewrite it during refinement.
    "understanding/gap_framing_plan.json": "gap_framing_compose",
    # Minted by the air-script omit pass; `air_contract_sanitize` re-sanitises.
    "understanding/omit_ledger.json": "air_script_compose",
}


@lru_cache(maxsize=1)
def _producer_index() -> dict[str, str]:
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    stages = set(ANALYSIS_ORDER) | set(DELIVERY_ORDER)
    index: dict[str, str] = {}
    for stage_id, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        if rel not in index and stage_id in stages:
            index[rel] = stage_id
    return index


def producer_for(path: str) -> str | None:
    """Canonical producing stage for an artifact path, or None if operator-supplied."""
    from interview_mux.artifact_ownership import owners_of
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    hit = PRODUCER_OVERRIDES.get(path) or _producer_index().get(path)
    if hit:
        return hit
    stages = set(ANALYSIS_ORDER) | set(DELIVERY_ORDER)
    owners = [o for o in owners_of(path) if o in stages]
    return owners[0] if len(owners) == 1 else None


def dep(path: str, **extra: Any) -> dict[str, Any]:
    """One `InputDep` row with its producer resolved from the path SSOT.

    Pass ``producer=None`` for a read-modify-write of the stage's own artifact:
    a self-edge is not a dependency and would make the stage its own blocker.
    """
    row: dict[str, Any] = {"path": path}
    producer = extra.pop("producer", producer_for(path))
    if producer:
        row["producer"] = producer
    row.update(extra)
    return row


# Declaring a hard input is not free. `artifact_lifecycle.run_phase_checks` is
# called from `pipeline.run_single_stage` at PRESTAGE and *raises* when a
# declared hard input is missing or stale, and `ship_reachability` reads the
# same list — a hard input on a conditionally-produced artifact turns a run that
# would have degraded gracefully into a hard failure, or a "reachable" verdict
# into a proven HALT. `when` predicates are honoured (`evaluate_when`), so a
# gated dependency is safe as long as the predicate matches the gate the stage
# itself checks.
#
# Every hard input below therefore rests on one of exactly three bases:
#
#   REFUSES   the stage body calls `artifact_exists_required` /
#             `read_artifact_path` / raises on absence itself, so hard adds no
#             failure mode that the code does not already have.
#   PREFLIGHT `llm_preflight._PREFLIGHT_CHECKERS` registers a checker for the
#             stage that errors on absence of this exact path.
#   ALWAYS    the artifact is unconditionally present before dispatch in every
#             posture and branch. Only `_TRANSCRIPT_ALWAYS_PRESENT` qualifies.
#
# Anything else is soft. When in doubt, soft.
_TRANSCRIPT_ALWAYS_PRESENT = """transcript/full.json — `run_transcribe` either
writes it or raises (no branch completes without it), it sits at ANALYSIS_ORDER
position 2 ahead of every consumer, and nothing gates transcription: no posture,
operator choice or framing decision skips it. Two earlier stages
(`transcript_review_build`, `audio_probe_build`) already hard-require it through
`artifact_exists_required`, so a run missing it has failed long before here."""


def deps(*paths: str) -> list[dict[str, Any]]:
    return [dep(p) for p in paths]


def back(*paths: str) -> list[dict[str, Any]]:
    """Reads of an artifact whose only producer is *downstream* of this stage.

    Real and recorded — a re-entered stage sees artifacts a later stage already
    wrote — but the producer is deliberately omitted. A `requires` edge pointing
    forward in seed order is a phantom blocker by construction
    (`tests/test_contract_generator_roundtrip.py::test_hard_inputs_are_produced_by_an_earlier_seed_position`).
    """
    return [dep(p, producer=None) for p in paths]


# `stage_input_helpers.transcript_quality_for_ctx` reads these three and folds
# them into `payload["transcript_quality"]` for every stage that calls it. It is
# the read that `tests/test_precision_invalidation.py` pins as the near-miss:
# undeclared, cross-module, and invisible to a call-depth-0 scan of the stage
# body. Declared here so the callers' `inputs` are complete at the depth the
# precision gate reasons about.
def transcript_quality_reads() -> list[dict[str, Any]]:
    return [
        *deps("transcript/review_queue.json", "analysis/run_golden_facts.json"),
        # `audio_probes.py:100` is the writer; the catalog row names `transcribe`,
        # so pin the producer the way `vernacular_segment_sanitize` already does.
        dep("transcript/protected_zones.json", producer="audio_probe_build"),
    ]


def rmw(*paths: str) -> list[dict[str, Any]]:
    """Artifacts this stage both reads and writes.

    The producer is omitted for the same reason as `back()`: the canonical minter
    is the declaring stage itself, and a `requires` edge from a stage to itself is
    never satisfiable. The pre-state is still a real input — it decides the
    outcome — so it must stay declared, which is also what keeps `dispatch_delta`
    from stripping it as the stage's own product.
    """
    return [dep(p, producer=None) for p in paths]


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------
# audio_preclean's real source is `ctx.input_audio()` — outside the run dir, so
# not an artifact. `normalized_rebuild` scope re-cleans ingest output instead,
# hence the conditional soft dep.
_PREPARE: dict[str, dict[str, Any]] = {
    "audio_preclean": {
        "inputs": {
            "soft": [
                {"path": "ingest/normalized.wav", "producer": "ingest"},
            ]
        },
        # The self-skip marker (§8.1) is a real committed write —
        # `stages/audio_preclean.py:33` resolves it through `ctx.final_path` and
        # the catalog names `audio_preclean` its owner — so it belongs in
        # `outputs`, not just in `artifact_lifecycle`'s prose.
        "outputs": [{"path": "preclean/skip.json"}],
        "consumers": ["ingest", "vo_ingest", "vo_synthesize"],
    },
    "ingest": {
        "inputs": {
            "soft": [
                {"path": "preclean/isolated.wav", "producer": "audio_preclean"},
            ]
        },
        "consumers": [
            "transcribe",
            "audio_probe_build",
            "transcript_review_build",
            "source_acoustic_profile",
            "source_topology_build",
            "mix",
            "master_finalize",
        ],
    },
    "transcribe": {
        # `run_transcribe` resolves ingest/normalized.wav and raises when absent.
        "inputs": {
            "hard": [
                {"path": "ingest/normalized.wav", "producer": "ingest"},
            ]
        },
        "consumers": [
            "audio_probe_build",
            "transcript_review_build",
            "source_acoustic_profile",
            "interview_spine_build",
            "speaker_roles",
            "content_context",
            "segment_classification",
        ],
    },
    "transcript_review_build": {
        "inputs": {
            "hard": [
                {"path": "transcript/full.json", "producer": "transcribe"},
            ],
            "soft": [
                {"path": "transcript/speakers.json", "producer": "transcribe"},
                {"path": "ingest/normalized.wav", "producer": "ingest"},
            ],
        },
        "consumers": ["transcript_review"],
    },
    "audio_probe_build": {
        # ctx.artifact_exists_required("transcript/full.json") — hard by the body.
        # The source WAV read is wrapped in try/except and fails open.
        #
        # The four backward reads are from a recorded run (`MUX_CONTRACT_RECORD=1`
        # over the stage suite): on re-entry the probe sees delivery artifacts a
        # later stage already wrote. They were undeclared, which made `prepare`
        # non-conformant despite already being a strict group.
        "inputs": {
            "hard": [
                {"path": "transcript/full.json", "producer": "transcribe"},
            ],
            "soft": [
                {"path": "ingest/normalized.wav", "producer": "ingest"},
                *back(
                    "master/edl.json",
                    "understanding/flow_adaptation.json",
                    "understanding/gap_fill_skip.json",
                    "understanding/source_topology.json",
                ),
            ],
        },
        "consumers": [
            "vernacular_segment_sanitize",
            "low_conf_island_scan",
            "boundary_detection",
            "segment_classification",
        ],
    },
}

# ---------------------------------------------------------------------------
# understand-a — transcript -> segments
# ---------------------------------------------------------------------------
# Hardness here is read straight out of the imperative encodings:
# `llm_preflight._PREFLIGHT_CHECKERS` (which artifacts a stage refuses without)
# and the stage bodies' own `raise` sites. Anything guarded by a *config* flag
# stays soft, because `InputDep.when` has no config predicate and a hard dep
# would gate the stage even on the disabled branch — `ideal_cuts_materialize`
# is exactly that case (`analysis.ideal_cuts.enable=false` returns before the
# `understanding/ideal_cuts.json` requirement).
_UNDERSTAND_A: dict[str, dict[str, Any]] = {
    "source_acoustic_profile": {
        # `read_artifact_path("ingest/normalized.wav")` goes through
        # `artifact_exists_required`, so the stage already refuses without it.
        #
        # `transcript/full.json` is hard on the `_TRANSCRIPT_ALWAYS_PRESENT`
        # basis below rather than on a refusal in this body.
        "inputs": {
            "hard": [
                {"path": "ingest/normalized.wav", "producer": "ingest"},
                {"path": "transcript/full.json", "producer": "transcribe"},
            ],
            "soft": [
                {"path": "preclean/isolated.wav", "producer": "audio_preclean"},
                *back("understanding/interview_spine.json"),
            ],
        },
        "outputs": [{"path": "understanding/source_readiness.json"}],
        "consumers": [
            "interview_spine_build",
            "boundary_detection",
            "sonic_context_build",
            "sound_design_palettes",
            "mastering_plan_synthesize",
        ],
    },
    "interview_spine_build": {
        # Both requirements live behind `if not spine_enabled(): return`.
        "inputs": {
            "hard": [
                {
                    "path": "transcript/full.json",
                    "producer": "transcribe",
                    "when": {"spine_enabled": True},
                },
                {
                    "path": "understanding/source_acoustic_profile.json",
                    "producer": "source_acoustic_profile",
                    "when": {"spine_enabled": True},
                },
            ],
            "soft": [
                {"path": "ingest/normalized.wav", "producer": "ingest"},
                {"path": "preclean/isolated.wav", "producer": "audio_preclean"},
            ],
        },
        "consumers": ["speaker_roles", "content_context", "boundary_detection"],
    },
    "speaker_roles": {
        # `_preflight_speaker_roles` + `_spine_preflight`.
        "inputs": {
            "hard": [
                {"path": "transcript/full.json", "producer": "transcribe"},
                {
                    "path": "understanding/interview_spine.json",
                    "producer": "interview_spine_build",
                    "when": {"spine_enabled": True},
                },
            ],
            "soft": [
                {"path": "transcript/speakers.json", "producer": "transcribe"},
                dep("transcript/diarization_repairs.json"),
            ],
        },
        "consumers": [
            "content_context",
            "boundary_detection",
            "segment_classification",
            "source_topology_build",
        ],
    },
    "source_topology_build": {
        # No raise site: the topology builder degrades rather than refusing.
        "inputs": {
            "soft": [
                {"path": "understanding/speakers.json", "producer": "speaker_roles"},
                {"path": "transcript/full.json", "producer": "transcribe"},
                {"path": "ingest/normalized.wav", "producer": "ingest"},
            ]
        },
        "consumers": [
            "content_context",
            "boundary_detection",
            "segment_classification",
            "boundary_topic_resplit",
            "missing_framing",
            "narrative_arc_plan",
            "full_master_ranking",
            "sound_design_plan",
        ],
    },
    "content_context": {
        # `_preflight_content_context` refuses on both.
        "inputs": {
            "hard": [
                {"path": "transcript/full.json", "producer": "transcribe"},
            ],
            "soft": [
                {"path": "understanding/source_topology.json", "producer": "source_topology_build"},
                {"path": "ingest/normalized.wav", "producer": "ingest"},
                {"path": "transcript/review_queue.json", "producer": "transcript_review_build"},
                *back("segments/manifest.json"),
                *transcript_quality_reads(),
            ],
        },
        "consumers": [
            "talking_points_compose",
            "ideal_cuts_propose",
            "boundary_detection",
            "segment_classification",
            "content_brief_reanchor",
            "narrative_arc_plan",
            "full_master_ranking",
            "topic_coverage_audit",
        ],
    },
    "talking_points_compose": {
        # Transcript hard on the `_TRANSCRIPT_ALWAYS_PRESENT` basis; speakers
        # soft because no preflight is registered for this stage.
        "inputs": {
            "hard": [
                {"path": "transcript/full.json", "producer": "transcribe"},
            ],
            "soft": [
                {"path": "understanding/speakers.json", "producer": "speaker_roles"},
                # `_talking_points_base_payload` folds the brief in when it
                # exists (`stages/understanding.py:125`).
                {"path": "understanding/content_brief.json", "producer": "content_context"},
                *transcript_quality_reads(),
            ],
        },
        "consumers": [
            "ideal_cuts_propose",
            "ideal_cuts_materialize",
            "mastering_shape_agenda",
            "nugget_corpus_mine",
            "nugget_layup_compose",
        ],
    },
    "ideal_cuts_propose": {
        # Same as `talking_points_compose`.
        "inputs": {
            "hard": [
                {"path": "transcript/full.json", "producer": "transcribe"},
            ],
            "soft": [
                {"path": "understanding/speakers.json", "producer": "speaker_roles"},
                {
                    "path": "understanding/talking_points.json",
                    "producer": "talking_points_compose",
                },
                # `build_input` folds the brief in when it exists
                # (`stages/understanding.py:404`).
                {"path": "understanding/content_brief.json", "producer": "content_context"},
                *transcript_quality_reads(),
            ],
        },
        "consumers": ["ideal_cuts_materialize", "boundary_detection", "nugget_corpus_mine"],
    },
    "ideal_cuts_materialize": {
        # `understanding/ideal_cuts.json` is required only on the enabled branch
        # (`analysis.ideal_cuts.enable`), so it stays soft — see the note above.
        "inputs": {
            "soft": [
                {"path": "understanding/ideal_cuts.json", "producer": "ideal_cuts_propose"},
                {"path": "transcript/full.json", "producer": "transcribe"},
                {"path": "ingest/normalized.wav", "producer": "ingest"},
                # `refresh_selection_seed_from_boundaries` / `run_ideal_cuts_
                # materialize` read the boundaries back (`ideal_cuts.py:1001`,
                # `:1121`). Every writer of that path is downstream in seed
                # order, so `back()` omits the producer.
                *back("segments/boundaries.json"),
            ]
        },
        # Read-modify-write, and the write is the stage body's own, not a
        # helper's: `run_ideal_cuts_materialize` rewrites the boundaries it
        # materialised cuts against, and the catalog names this stage a producer
        # of the path. Undeclared it was the one blocking finding in
        # `understand-a` under `--entrypoint-only --call-depth 0`.
        "outputs": [{"path": "segments/boundaries.json"}],
        "consumers": [
            "boundary_detection",
            "segment_classification",
            "mastering_shape_agenda",
            "full_master_ranking",
        ],
    },
    "boundary_detection": {
        # `_preflight_boundary_detection` refuses without speakers.json; the
        # content_brief hard dep is already minted from LLM_UPSTREAM_STAGE.
        "inputs": {
            "hard": [
                {"path": "understanding/speakers.json", "producer": "speaker_roles"},
            ],
            "soft": [
                {"path": "transcript/full.json", "producer": "transcribe"},
                {
                    "path": "understanding/talking_points.json",
                    "producer": "talking_points_compose",
                },
                {
                    "path": "understanding/ideal_cuts_materialized.json",
                    "producer": "ideal_cuts_materialize",
                },
                # The proposal itself, not only the materialised form —
                # `build_input` passes both (`stages/segmentation.py:124`).
                {"path": "understanding/ideal_cuts.json", "producer": "ideal_cuts_propose"},
                {
                    "path": "understanding/source_acoustic_profile.json",
                    "producer": "source_acoustic_profile",
                },
                *transcript_quality_reads(),
            ],
        },
        "consumers": [
            "segment_classification",
            "content_brief_reanchor",
            "sonic_context_build",
            "sound_design_palettes",
            "missing_framing",
        ],
    },
    "segment_classification": {
        # boundaries.json arrives as the LLM_UPSTREAM_STAGE hard dep.
        "inputs": {
            "soft": [
                {"path": "transcript/full.json", "producer": "transcribe"},
                {"path": "understanding/speakers.json", "producer": "speaker_roles"},
                {
                    "path": "understanding/talking_points.json",
                    "producer": "talking_points_compose",
                },
                # `build_classification_payload` passes `bundle.content_brief`
                # (`segmentation_input_resolver.py:226`).
                {"path": "understanding/content_brief.json", "producer": "content_context"},
                *back("master/edl.json"),
                *transcript_quality_reads(),
            ]
        },
        "consumers": [
            "content_brief_reanchor",
            "vernacular_segment_sanitize",
            "low_conf_island_scan",
            "connector_fuse_pass",
            "sonic_context_build",
            "sound_design_palettes",
            "missing_framing",
        ],
    },
}

# ---------------------------------------------------------------------------
# understand-b — segment refinement
# ---------------------------------------------------------------------------
# Four of the six stages here short-circuit rather than refuse:
# `framing_posture_decide` returns a stub when the homunculus feature or the
# posture flag is off, `vernacular_segment_sanitize` writes a skip report when
# zones or the manifest are absent, and `low_conf_island_scan` /
# `connector_fuse_pass` return on `analysis.*.enabled=false`. None of their deps
# may be hard.
_UNDERSTAND_B: dict[str, dict[str, Any]] = {
    "content_brief_reanchor": {
        # `_preflight_content_brief_reanchor` refuses without the prior brief;
        # segments/manifest.json is the LLM_UPSTREAM_STAGE hard dep already.
        "inputs": {
            "hard": [
                {"path": "understanding/content_brief.json", "producer": "content_context"},
            ],
            "soft": [
                {"path": "segments/boundaries.json", "producer": "boundary_detection"},
                {"path": "understanding/speakers.json", "producer": "speaker_roles"},
            ],
        },
        "consumers": [
            "boundary_topic_resplit",
            "sonic_context_build",
            "sound_design_palettes",
            "missing_framing",
        ],
    },
    "framing_posture_decide": {
        "inputs": {
            "soft": [
                {"path": "understanding/speakers.json", "producer": "speaker_roles"},
                {
                    "path": "understanding/source_topology.json",
                    "producer": "source_topology_build",
                },
                {
                    "path": "understanding/flow_adaptation.json",
                    "producer": "source_topology_build",
                },
            ]
        },
        "consumers": ["missing_framing", "gap_framing_compose", "transitions", "vo_synthesize"],
    },
    "boundary_topic_resplit": {
        # content_brief.json arrives from LLM_UPSTREAM_STAGE=content_brief_reanchor.
        "inputs": {
            "soft": [
                {"path": "segments/boundaries.json", "producer": "boundary_detection"},
                {"path": "segments/manifest.json", "producer": "segment_classification"},
                {"path": "transcript/full.json", "producer": "transcribe"},
                {"path": "understanding/speakers.json", "producer": "speaker_roles"},
                {
                    "path": "understanding/flow_adaptation.json",
                    "producer": "source_topology_build",
                },
                # Cross-module helper reads, invisible to a call-depth-0 scan of
                # the stage body: `interview_spine.compact.attach_spine_to_payload`
                # and `source_topology.attach_adaptation_to_payload` on the LLM
                # path, `split_plan.propose_split_plan` on the way out.
                *deps(
                    "understanding/interview_spine.json",
                    "understanding/source_topology.json",
                    "understanding/ideal_cuts_materialized.json",
                ),
                # `full_master_ranking` is the only writer and sits downstream.
                *back("understanding/speaker_delivery_plan.json"),
                # Operator NLE edits — `ops`-written, no stage produces it.
                *back("segments/nle_edits.json"),
                # Own artifact: `propose_split_plan` reads the prior plan back.
                *rmw("segments/split_plan.json"),
            ]
        },
        "consumers": [
            "segment_classification",
            "vernacular_segment_sanitize",
            "low_conf_island_scan",
            "connector_fuse_pass",
            "sonic_context_build",
            "sound_design_palettes",
            "missing_framing",
        ],
    },
    "vernacular_segment_sanitize": {
        "inputs": {
            "soft": [
                {
                    "path": "transcript/protected_zones.json",
                    "producer": "audio_probe_build",
                },
                {"path": "segments/manifest.json", "producer": "segment_classification"},
                # `enforcement_mode_for_ctx` / `load_must_keep_segment_ids` read
                # the golden facts (`stages/audio_probes.py:38`, `:53`), and the
                # resplit reads the flows and the audio tags (`:287`, `:289`).
                *deps("analysis/run_golden_facts.json", "transcript/speaker_flows.json"),
                # Own artifact, read for its pre-state.
                *rmw("vernacular/audio_tags_by_flow.json"),
            ]
        },
        # The resplit rewrites the protected zones it just read
        # (`stages/audio_probes.py:420`) — read-modify-write, so the path is both
        # a declared input and a declared output.
        "outputs": [{"path": "transcript/protected_zones.json"}],
        "consumers": ["low_conf_island_scan", "connector_fuse_pass", "full_master_ranking"],
    },
    "low_conf_island_scan": {
        "inputs": {
            "soft": [
                {"path": "segments/manifest.json", "producer": "segment_classification"},
                {"path": "transcript/full.json", "producer": "transcribe"},
                {
                    "path": "analysis/vernacular_must_keep.json",
                    "producer": "vernacular_segment_sanitize",
                },
            ]
        },
        "consumers": ["connector_fuse_pass", "full_master_ranking"],
    },
    "connector_fuse_pass": {
        "inputs": {
            "soft": [
                {"path": "segments/manifest.json", "producer": "segment_classification"},
                {"path": "transcript/full.json", "producer": "transcribe"},
                {
                    "path": "analysis/low_conf_islands.json",
                    "producer": "low_conf_island_scan",
                },
                {
                    "path": "analysis/low_conf_must_keep.json",
                    "producer": "low_conf_island_scan",
                },
            ]
        },
        "consumers": [
            "connector_fuse_pass_pre_ranking",
            "topic_coverage_audit",
            "narrative_arc_plan",
            "full_master_ranking",
            "nugget_corpus_mine",
            "nugget_layup_compose",
            "transitions",
            "edl",
        ],
    },
}

# ---------------------------------------------------------------------------
# understand-c — sonic context, mastering research, Shape
# ---------------------------------------------------------------------------
# **Nothing in this group is hard.** Every one of the eight stages degrades
# rather than refusing, and the degradation is the documented design:
#
# * `sonic_context_build` reads everything through `sonic_context._read_if_dict`,
#   which returns `None` on a missing artifact; the stage's own `built_from`
#   list is literally the set of artifacts it found.
# * the three `mastering_research_*` stages are a presence scan — `_probe` walks
#   `FIELD_PROBES` with `ctx.artifact_exists` and writes `status:
#   skipped_or_thin` for whatever is absent. Missing upstream is the expected
#   state at Shape time (W4–W8 are thin by construction, per `SHAPE_CORE_WAVES`).
# * the three Shape stages short-circuit on `soft_gate_enabled()` and fall
#   through a heuristic ladder ending in `forced_sparse_plan`; the `except`
#   arms still write a schema-valid artifact.
#
# So a hard dep here would gate a stage that is built never to be gated —
# `artifact_lifecycle.run_phase_checks` would refuse PRESTAGE on a tape where
# the stage is designed to produce a thin-but-valid artifact.
#
# The research probe set is derived from `mastering_research.FIELD_PROBES`
# rather than transcribed, so the contract cannot rot when a probe is added.
_RESEARCH_PROBE_EXCLUDE = frozenset(
    {
        # Recorder infrastructure, not artifacts (`contract_conformance.is_ignored`).
        "run_meta.json",
        "understanding/analysis_state.json",
        ".stage_done",
        "llm_audit.jsonl",
    }
)


def research_probe_paths() -> list[str]:
    """Every artifact the research waves probe, in `FIELD_PROBES` order."""
    from interview_mux.mastering_research import FIELD_PROBES

    seen: list[str] = []
    for probes in FIELD_PROBES.values():
        for rel in probes:
            if rel not in seen and rel not in _RESEARCH_PROBE_EXCLUDE:
                seen.append(rel)
    return seen


def _research_probe_inputs() -> list[dict[str, Any]]:
    return [dep(rel) for rel in sorted(research_probe_paths())]


# Readers of `understanding/sonic_context.json` and `understanding/sound_design_plan.json`
# — both are read by the whole sound/build/ship tail, so the consumer lists are
# long by nature rather than by over-reporting.
_SONIC_CONSUMERS = [
    "sound_design_palettes",
    "soundscape_policy_build",
    "episode_structure_compose",
    "sound_design_plan",
    "edl_narrative_audit",
    "music_palette_compose",
    "sfx_prompt_craft",
    "mix",
    "junction_snip_qa",
    "master_finalize",
]

_UNDERSTAND_C: dict[str, dict[str, Any]] = {
    "sonic_context_build": {
        # `build_sonic_context` + `classify_atlas_bucket` / `build_tag_registry`
        # / `build_cue_opportunities` / `build_segment_flags` / `build_avoid_hard`
        # / `compute_mix_policy`, all via `_read_if_dict`.
        "inputs": {
            "soft": deps(
                "understanding/content_brief.json",
                "understanding/source_acoustic_profile.json",
                "understanding/speakers.json",
                "understanding/value_features.json",
                "understanding/gap_report.json",
                "segments/manifest.json",
                "transcript/full.json",
                "transcript/disfluencies.json",
                "master/narrative_plan.json",
            )
        },
        "consumers": list(_SONIC_CONSUMERS),
    },
    "sound_design_palettes": {
        # Read-modify-write: `_load_sound_design_plan` reads the plan, the stage
        # folds palettes / coherence into it and writes it back. It MUST be
        # declared as an input as well as an output or the no-delta guard strips
        # it as "the stage's own product" and refuses a legitimate re-run
        # (tests/test_contract_input_declaration_safety.py). `producer=None`
        # because the canonical producer of that path is this stage itself.
        "inputs": {
            "soft": [
                dep("understanding/sound_design_plan.json", producer=None),
                *deps(
                    "understanding/sonic_context.json",
                    "understanding/content_brief.json",
                    "understanding/source_acoustic_profile.json",
                    "understanding/value_features.json",
                    "understanding/flow_adaptation.json",
                    "understanding/source_topology.json",
                    "segments/manifest.json",
                ),
            ]
        },
        "consumers": [c for c in _SONIC_CONSUMERS if c != "sound_design_palettes"]
        + ["delivery_brief_build"],
    },
    "mastering_research_routing": {
        # `_routing_user_payload` runs only when `mastering.research.llm.enabled`
        # (default false), and it probes the whole catalog via
        # `_probe_presence_map`. Config-gated, so soft — `InputDep.when` has no
        # config predicate and a hard dep would gate the disabled branch too.
        "inputs": {"soft": _research_probe_inputs()},
        # Nothing reads `mastering/research/routing.json`: `run_research_rollup`
        # re-runs the routing rather than reading its artifact.
        "consumers": [],
    },
    "mastering_research_waves": {
        # `_probe` is unconditional here — every field report records which of
        # its `FIELD_PROBES` exist.
        "inputs": {"soft": _research_probe_inputs()},
        "consumers": ["mastering_research_rollup"],
    },
    "mastering_research_rollup": {
        # `run_research_rollup` calls routing and every wave itself, then reads
        # the per-field reports back out of `mastering/research/`.
        "inputs": {"soft": _research_probe_inputs()},
        "consumers": [
            "mastering_shape_agenda",
            "mastering_shape_candidates",
            "mastering_plan_synthesize",
            "mastering_plan_confirm",
        ],
        "outputs": [
            {"path": "glob:mastering/research/*.json"},
            {"path": "mastering/research/routing.json"},
        ],
    },
    "mastering_shape_agenda": {
        # `_style_hints` + `_talking_points_bound` + `_shape_llm_user_payload`
        # + `compile_shape_evidence`.
        "inputs": {
            "soft": deps(
                "mastering/research_dossier.json",
                "understanding/content_brief.json",
                "understanding/source_topology.json",
                "understanding/talking_points.json",
                "understanding/ideal_cuts_materialized.json",
                "understanding/gap_evaluations.json",
                "understanding/gap_report.json",
                "master/selection.json",
                "segments/manifest.json",
                "mastering/mastering_plan.json",
                "mastering/shape/candidates.json",
            )
        },
        "consumers": ["mastering_shape_candidates"],
        "outputs": [
            {"path": "mastering/shape/eval_rubric.json"},
            {"path": "glob:mastering/evidence_packets/*.json"},
        ],
    },
    "mastering_shape_candidates": {
        "inputs": {
            "soft": deps(
                "mastering/shape/agenda.json",
                "mastering/research_dossier.json",
                "understanding/content_brief.json",
                "understanding/source_topology.json",
                "understanding/gap_evaluations.json",
                "understanding/gap_report.json",
                "master/selection.json",
                "segments/manifest.json",
                "mastering/mastering_plan.json",
            )
        },
        "consumers": ["mastering_plan_synthesize"],
        "outputs": [
            # `mastering.shape.soft_gate.skip_diversity` defaults true, so this
            # is written only on the diversity branch.
            {"path": "mastering/shape/diversity_report.json"},
            {"path": "glob:mastering/evidence_packets/*.json"},
        ],
    },
    "mastering_plan_synthesize": {
        # `_shape_llm_user_payload` + `compile_shape_evidence` +
        # `shape_order_emit.attach_shape_order`.
        "inputs": {
            "soft": deps(
                "mastering/shape/candidates.json",
                "mastering/shape/agenda.json",
                "mastering/research_dossier.json",
                "understanding/content_brief.json",
                "understanding/source_topology.json",
                "understanding/gap_evaluations.json",
                "understanding/gap_report.json",
                "understanding/episode_structure.json",
                "master/selection.json",
                "master/narrative_plan.json",
                "segments/manifest.json",
            )
        },
        # Every downstream stage that binds narrative_mode / montage grammar.
        "consumers": [
            "missing_framing",
            "mastering_plan_confirm",
            "gap_framing_compose",
            "delivery_brief_build",
            "soundscape_policy_build",
            "episode_structure_compose",
            "narrative_arc_plan",
            "chapter_close_hitch",
            "full_master_ranking",
            "air_script_compose",
            "nugget_corpus_mine",
            "information_package_plan",
            "nugget_layup_compose",
            "refinement_agenda",
            "gap_framing_recompose",
            "selection_framing_apply",
            "air_script_seams",
            "air_contract_sanitize",
            "transitions",
            "sound_design_plan",
            "vo_synthesize",
            "edl_narrative_audit",
            "edl",
            "listen_delight_audit",
            "music_palette_compose",
            "mix",
            "junction_snip_qa",
            "master_finalize",
        ],
        "outputs": [{"path": "glob:mastering/evidence_packets/*.json"}],
    },
}

# ---------------------------------------------------------------------------
# fill_gaps — gap evaluation, framing script, delivery/soundscape/episode briefs
# ---------------------------------------------------------------------------
# Hardness comes from `llm_preflight._PREFLIGHT_CHECKERS` /
# `_FLOW_UPSTREAM_ARTIFACTS` — the table that decides which artifacts a stage
# refuses without. Only `missing_framing` has an entry in this group.
#
# Four of the six stages read their own artifact and write it back, which is the
# trap that stranded `speaker_roles` and `vernacular_segment_sanitize`: declaring
# the artifact as an output alone lets the no-delta guard strip it as the
# stage's own product and then refuse a legitimate re-run. Each is declared as
# BOTH, with `producer=None` where this stage is the canonical minter.
#
# `mastering/mastering_plan.json` is consumed by essentially the whole delivery
# tail, so `mastering_plan_confirm` shares `_PLAN_CONSUMERS` with
# `mastering_plan_synthesize`.
_PLAN_CONSUMERS = list(_UNDERSTAND_C["mastering_plan_synthesize"]["consumers"])

_FILL_GAPS: dict[str, dict[str, Any]] = {
    "missing_framing": {
        # `_preflight_missing_framing` refuses on both, and on an empty manifest.
        # `segments/boundaries.json` already arrives as the LLM_UPSTREAM_STAGE dep.
        "inputs": {
            "hard": deps(
                "understanding/content_brief.json",
                "segments/manifest.json",
            ),
            "soft": [
                dep("understanding/gap_evaluations.json", producer=None),
                *deps(
                    "transcript/full.json",
                    "understanding/speakers.json",
                    "understanding/source_topology.json",
                    "understanding/talking_points.json",
                    "understanding/flow_adaptation.json",
                    "understanding/value_features.json",
                    "understanding/gap_report.json",
                    "understanding/speaker_delivery_plan.json",
                    "mastering/mastering_plan.json",
                    "master/selection.json",
                    "master/narrative_plan.json",
                ),
            ],
        },
        "consumers": [
            "mastering_plan_confirm",
            "gap_framing_compose",
            "air_script_compose",
            "nugget_layup_compose",
            "refinement_agenda",
            "gap_framing_recompose",
            "air_script_seams",
            "edl",
        ],
    },
    "mastering_plan_confirm": {
        # Pass2 of the Shape soft gate: re-reads the provisional plan it is about
        # to overwrite, re-scores it against the gap evidence, writes it back.
        "inputs": {
            "soft": [
                dep("mastering/mastering_plan.json", producer="mastering_plan_synthesize"),
                *deps(
                    "mastering/research_dossier.json",
                    "understanding/gap_evaluations.json",
                    "understanding/gap_report.json",
                    "understanding/content_brief.json",
                    "understanding/source_topology.json",
                    "understanding/episode_structure.json",
                    "master/selection.json",
                    "master/narrative_plan.json",
                    "segments/manifest.json",
                ),
            ]
        },
        "consumers": [c for c in _PLAN_CONSUMERS if c != "mastering_plan_confirm"],
        "outputs": [
            {"path": "mastering/shadow_diff.json"},
            {"path": "glob:mastering/evidence_packets/*.json"},
        ],
    },
    "gap_framing_compose": {
        # No preflight entry: the stage no-ops under layup authority or a seat
        # freeze rather than refusing, so nothing beyond the LLM_UPSTREAM dep on
        # `understanding/gap_evaluations.json` is hard.
        "inputs": {
            "soft": [
                dep("understanding/gap_report.json", producer=None),
                *deps(
                    "understanding/nugget_layup_plan.json",
                    "understanding/nugget_corpus.json",
                    "understanding/content_brief.json",
                    "understanding/delivery_brief.json",
                    "understanding/episode_structure.json",
                    "understanding/speakers.json",
                    "understanding/source_topology.json",
                    "understanding/talking_points.json",
                    "understanding/flow_adaptation.json",
                    "understanding/value_features.json",
                    "understanding/reorder_bridges.json",
                    "understanding/speaker_delivery_plan.json",
                    "segments/manifest.json",
                    "segments/boundaries.json",
                    "master/selection.json",
                    "master/narrative_plan.json",
                    "mastering/mastering_plan.json",
                ),
            ]
        },
        "consumers": [
            "mastering_plan_confirm",
            "delivery_brief_build",
            "chapter_close_hitch",
            "full_master_ranking",
            "nugget_corpus_mine",
            "nugget_layup_compose",
            "gap_report_sanitize",
            "gap_framing_recompose",
            "selection_framing_apply",
            "air_script_seams",
            "air_contract_sanitize",
            "transitions",
            "sound_design_plan",
            "vo_line_adjudicate",
            "vo_synthesize",
            "sound_design_vo_finalize",
            "edl",
            "assembly_preview",
            "listen_delight_audit",
            "mix",
            "junction_snip_qa",
            "master_finalize",
            "master_transcript_build",
            "podcast_publish",
        ],
        "outputs": [
            {"path": "understanding/gap_framing_plan.json"},
            {"path": "understanding/gap_vo_context_audit.json"},
            {"path": "understanding/speaker_delivery_plan.json"},
        ],
    },
    "delivery_brief_build": {
        "inputs": {
            "soft": [
                dep("understanding/delivery_brief.json", producer=None),
                *deps(
                    "understanding/content_brief.json",
                    "understanding/speakers.json",
                    "understanding/source_topology.json",
                    "understanding/flow_adaptation.json",
                    "understanding/sound_design_plan.json",
                    "mastering/mastering_plan.json",
                    "master/selection.json",
                    "segments/manifest.json",
                    "transcript/full.json",
                    "ingest/checksums.json",
                ),
            ]
        },
        "consumers": [
            "gap_framing_compose",
            "soundscape_policy_build",
            "full_master_ranking",
            "transitions",
            "sound_design_plan",
            "listen_delight_audit",
            "music_palette_compose",
            "mix",
        ],
    },
    "soundscape_policy_build": {
        "inputs": {
            "soft": [
                dep("understanding/soundscape_policy.json", producer=None),
                *deps(
                    "understanding/sonic_context.json",
                    "understanding/sound_design_plan.json",
                    "understanding/delivery_brief.json",
                    "understanding/source_acoustic_profile.json",
                    "mastering/mastering_plan.json",
                    "master/selection.json",
                    "master/narrative_plan.json",
                    "segments/manifest.json",
                ),
            ]
        },
        "consumers": ["sound_design_plan", "music_palette_compose", "sfx_prompt_craft"],
    },
    "episode_structure_compose": {
        # The last three are a cross-module helper read no stage-body scan can
        # see: `run_episode_structure_compose` calls
        # `analysis_memory.update_completion_from_analysis`, which walks
        # `llm_flow_hardening.ANALYSIS_READY_ARTIFACT_PATHS` through
        # `artifact_completeness.artifact_status` — a content read that parses
        # and schema-validates each one, not an existence probe.
        "inputs": {
            "soft": deps(
                "understanding/content_brief.json",
                "understanding/speakers.json",
                "understanding/sonic_context.json",
                "understanding/sound_design_plan.json",
                "understanding/source_acoustic_profile.json",
                "mastering/mastering_plan.json",
                "master/selection.json",
                "segments/manifest.json",
                "segments/boundaries.json",
                "transcript/full.json",
                "understanding/gap_evaluations.json",
                "understanding/gap_report.json",
                "understanding/delivery_brief.json",
            )
        },
        "outputs": [{"path": "understanding/episode_structure_compact.txt"}],
        "consumers": [
            "mastering_plan_synthesize",
            "mastering_plan_confirm",
            "gap_framing_compose",
            "narrative_arc_plan",
            "chapter_close_hitch",
            "full_master_ranking",
            "gap_framing_recompose",
            "selection_framing_apply",
            "air_script_seams",
            "transitions",
            "sound_design_plan",
            "edl",
            "mix",
            "junction_snip_qa",
        ],
    },
}

# ---------------------------------------------------------------------------
# plan_rank — coverage, narrative, ranking, layups, air contract, transitions
# ---------------------------------------------------------------------------
# Hardness is `llm_preflight._check_upstream_artifacts` only:
#
#   narrative_arc_plan   <- master/coverage_audit.json
#   full_master_ranking  <- master/narrative_plan.json, master/coverage_audit.json
#   transitions          <- master/selection.json
#
# `topic_coverage_audit` runs `_preflight_pre_delivery`, which asserts every
# `ANALYSIS_READY_ARTIFACT_PATHS` entry is `complete` — a *status* test, not an
# existence test. A hard contract dep is an existence test that additionally
# arms `artifact_lifecycle.read_stale_guard`, so promoting those to hard would
# add a refusal the stage does not have today. They stay soft.
#
# This group is where read-modify-write is the norm rather than the exception:
# `master/selection.json` is minted by `full_master_ranking` and then rewritten
# by `selection_order_sanitize`, `mastering/mastering_plan.json` by four air
# stages, `understanding/gap_report.json` by three, and
# `connector_fuse_pass_pre_ranking` re-fuses `segments/manifest.json` in place.
# Every one of those is declared as input AND output; see the module docstring
# of `tests/test_contract_input_declaration_safety.py` for why omitting the
# input strands the stage.
_SELECTION_CONSUMERS = [
    "missing_framing",
    "mastering_plan_confirm",
    "gap_framing_compose",
    "delivery_brief_build",
    "soundscape_policy_build",
    "episode_structure_compose",
    "chapter_close_hitch",
    "selection_order_sanitize",
    "air_script_compose",
    "nugget_corpus_mine",
    "information_package_plan",
    "nugget_layup_compose",
    "gap_report_sanitize",
    "gap_framing_recompose",
    "selection_framing_apply",
    "air_script_seams",
    "air_contract_sanitize",
    "transitions",
    "sound_design_plan",
    "sound_design_vo_finalize",
    "edl_narrative_audit",
    "edl",
    "listen_delight_audit",
    "music_palette_compose",
    "sfx_prompt_craft",
    "mix",
    "junction_snip_qa",
    "master_finalize",
    "podcast_publish",
]

_PLAN_RANK: dict[str, dict[str, Any]] = {
    "topic_coverage_audit": {
        "inputs": {
            "soft": [
                dep("master/coverage_audit.json", producer=None),
                *deps(
                    "understanding/content_brief.json",
                    "understanding/source_topology.json",
                    "understanding/flow_adaptation.json",
                    "understanding/value_features.json",
                    "understanding/speakers.json",
                    "understanding/gap_evaluations.json",
                    "understanding/gap_report.json",
                    "understanding/interview_spine.json",
                    "understanding/sound_design_plan.json",
                    "segments/manifest.json",
                    "segments/boundaries.json",
                    "transcript/full.json",
                    "transcript/review_queue.json",
                ),
                # Recorded (`MUX_CONTRACT_RECORD=1`): skip flags and the ranking
                # sidecar, neither of which has an upstream producer here.
                *back(
                    "analysis_complete.json",
                    "understanding/gap_fill_skip.json",
                    "understanding/speaker_delivery_plan.json",
                ),
            ]
        },
        "consumers": [
            "narrative_arc_plan",
            "full_master_ranking",
            "refinement_agenda",
            "gap_framing_recompose",
            "selection_framing_apply",
            "transitions",
            "edl_narrative_audit",
            "junction_snip_qa",
        ],
    },
    "narrative_arc_plan": {
        # `master/coverage_audit.json` arrives hard via LLM_UPSTREAM_STAGE, which
        # is exactly `_preflight_narrative_arc_plan`'s requirement.
        "inputs": {
            "soft": [
                dep("master/narrative_plan.json", producer=None),
                *deps(
                    "mastering/mastering_plan.json",
                    "understanding/content_brief.json",
                    "understanding/episode_structure.json",
                    "understanding/source_topology.json",
                    "understanding/flow_adaptation.json",
                    "understanding/value_features.json",
                    "segments/manifest.json",
                    "segments/boundaries.json",
                ),
            ]
        },
        "consumers": [
            "mastering_plan_synthesize",
            "mastering_plan_confirm",
            "missing_framing",
            "gap_framing_compose",
            "soundscape_policy_build",
            "chapter_close_hitch",
            "full_master_ranking",
            "air_script_compose",
            "gap_framing_recompose",
            "transitions",
            "sound_design_plan",
            "edl_narrative_audit",
            "edl",
            "music_palette_compose",
            "sfx_prompt_craft",
            "mix",
            "junction_snip_qa",
            "master_finalize",
            "podcast_publish",
        ],
    },
    "chapter_close_hitch": {
        # narrative_plan / manifest / transcript are already hard from _EXTRA_INPUTS.
        "inputs": {
            "soft": [
                dep("mastering/chapter_close_hitch.json", producer=None),
                *deps(
                    "master/selection.json",
                    "mastering/mastering_plan.json",
                    "understanding/content_brief.json",
                    "understanding/episode_structure.json",
                    "understanding/flow_adaptation.json",
                    "understanding/gap_report.json",
                    "understanding/ideal_cuts_materialized.json",
                    "understanding/nugget_corpus.json",
                    "understanding/nugget_layup_plan.json",
                    "understanding/omit_ledger.json",
                    "understanding/source_topology.json",
                    "understanding/speaker_delivery_plan.json",
                    "understanding/speakers.json",
                    "understanding/talking_points.json",
                    "segments/boundaries.json",
                    # `resolve_keeper_air_bounds` measures the source audio
                    # (`chapter_close_hitch.py:1755`).
                    "ingest/normalized.wav",
                ),
            ]
        },
        "outputs": [
            {"path": "mastering/chapter_close_hitch/hitch_keepers.json"},
            {"path": "mastering/chapter_close_hitch/pre_keepers.json"},
            {"path": "mastering/chapter_close_hitch/omit_ledger.json"},
            {"path": "mastering/chapter_close_hitch/vo_snapshot.json"},
            {"path": "master/narrative_plan.qc.json"},
            {"path": "understanding/episode_structure_compact.txt"},
            {"path": "segments/boundaries.json"},
        ],
    },
    "connector_fuse_pass_pre_ranking": {
        # Second connector fuse, run against the ranked manifest: reads it,
        # re-fuses, writes it back.
        "inputs": {
            "soft": [
                dep("segments/manifest.json", producer="segment_classification"),
                *deps(
                    "transcript/full.json",
                    "analysis/low_conf_islands.json",
                    "analysis/connector_fuse_audit.json",
                    "mastering/chapter_close_hitch.json",
                ),
            ]
        },
        "consumers": ["full_master_ranking"],
    },
    "full_master_ranking": {
        # `_preflight_full_master_ranking` refuses without both.
        "inputs": {
            "hard": deps("master/narrative_plan.json", "master/coverage_audit.json"),
            "soft": [
                dep("master/selection.json", producer=None),
                dep("understanding/reorder_bridges.json", producer=None),
                dep("understanding/speaker_delivery_plan.json", producer=None),
                *deps(
                    "analysis/run_golden_facts.json",
                    "master/transitions.json",
                    "mastering/mastering_plan.json",
                    "mastering/media_ip_cta.json",
                    "segments/manifest.json",
                    "segments/boundaries.json",
                    "segments/nle_edits.json",
                    "transcript/full.json",
                    "transcript/review_queue.json",
                    "understanding/content_brief.json",
                    "understanding/delivery_brief.json",
                    "understanding/episode_structure.json",
                    "understanding/flow_adaptation.json",
                    "understanding/gap_framing_plan.json",
                    "understanding/gap_report.json",
                    "understanding/ideal_cuts.json",
                    "understanding/interview_spine.json",
                    "understanding/nugget_corpus.json",
                    "understanding/nugget_layup_plan.json",
                    "understanding/source_acoustic_profile.json",
                    "understanding/source_topology.json",
                    "understanding/speakers.json",
                    "understanding/talking_points.json",
                    # `build_input` boosts the ranking with the high-value speech
                    # scan when it exists (`stages/selection.py:360`, `:367`).
                    "analysis/high_value_speech_boosts.json",
                    "analysis/high_value_speech_islands.json",
                ),
            ],
        },
        "consumers": list(_SELECTION_CONSUMERS),
        "outputs": [
            {"path": "master/rank_candidates.json"},
            {"path": "master/order_reconcile.json"},
            {"path": "master/story_health.json"},
            {"path": "mastering/media_ip_cta.json"},
            {"path": "understanding/reorder_bridges.json"},
            {"path": "understanding/speaker_delivery_plan.json"},
            {"path": "analysis/stt_lexicon_islands.json"},
        ],
    },
    "selection_order_sanitize": {
        "inputs": {
            "soft": [
                dep("master/selection.json", producer="full_master_ranking"),
                *deps(
                    "mastering/media_ip_cta.json",
                    "segments/manifest.json",
                    "segments/nle_edits.json",
                    "understanding/ideal_cuts.json",
                    "understanding/reorder_bridges.json",
                    "understanding/talking_points.json",
                ),
            ]
        },
        "consumers": [c for c in _SELECTION_CONSUMERS if c != "selection_order_sanitize"],
    },
    "air_script_compose": {
        # selection + mastering_plan already hard from _EXTRA_INPUTS.
        "inputs": {
            "soft": deps(
                "analysis/high_value_speech_islands.json",
                "master/narrative_plan.json",
                "segments/manifest.json",
                "segments/nle_edits.json",
                "understanding/gap_evaluations.json",
                "understanding/gap_fill_skip.json",
                "understanding/ideal_cuts.json",
                "understanding/source_acoustic_profile.json",
                "understanding/source_topology.json",
                "understanding/talking_points.json",
            )
        },
        "outputs": [{"path": "understanding/omit_ledger.json"}],
    },
    "nugget_corpus_mine": {
        "inputs": {
            "soft": [
                dep("understanding/nugget_corpus.json", producer=None),
                *deps(
                    "mastering/media_ip_cta.json",
                    "understanding/flow_adaptation.json",
                    "understanding/gap_report.json",
                    "understanding/native_comprehension_masks.json",
                    "understanding/nugget_layup_plan.json",
                    "understanding/source_topology.json",
                    "understanding/speakers.json",
                ),
            ]
        },
        "outputs": [{"path": "understanding/nugget_layup_qc.json"}],
    },
    "information_package_plan": {
        # Folds information packages into the mastering plan in place.
        "inputs": {
            "soft": [
                dep("mastering/mastering_plan.json", producer="mastering_plan_synthesize"),
                *deps("master/selection.json", "segments/manifest.json"),
            ]
        },
        "consumers": ["nugget_layup_compose", "air_script_seams", "edl"],
    },
    "nugget_layup_compose": {
        # selection / nugget_corpus already hard from _EXTRA_INPUTS.
        "inputs": {
            "soft": [
                dep("understanding/nugget_layup_plan.json", producer=None),
                dep("understanding/gap_report.json", producer="gap_framing_compose"),
                dep("mastering/mastering_plan.json", producer="mastering_plan_synthesize"),
                *deps(
                    "analysis/low_conf_must_keep.json",
                    "mastering/media_ip_cta.json",
                    "transcript/full.json",
                    "understanding/content_brief.json",
                    "understanding/episode_structure.json",
                    "understanding/flow_adaptation.json",
                    "understanding/gap_evaluations.json",
                    "understanding/ideal_cuts.json",
                    "understanding/interview_spine.json",
                    "understanding/native_comprehension_masks.json",
                    "understanding/source_topology.json",
                    "understanding/speakers.json",
                    "understanding/value_features.json",
                ),
            ]
        },
        "outputs": [
            {"path": "mastering/mastering_plan.json"},
            {"path": "understanding/native_comprehension_masks.json"},
            {"path": "understanding/nugget_comprehension_index.json"},
            {"path": "understanding/nugget_layup_qc.json"},
        ],
    },
    "gap_report_sanitize": {
        "inputs": {
            "soft": [
                dep("understanding/gap_report.json", producer="gap_framing_compose"),
                *deps("master/selection.json"),
            ]
        },
        "consumers": [
            "nugget_layup_compose",
            "gap_framing_recompose",
            "selection_framing_apply",
            "air_script_seams",
            "air_contract_sanitize",
            "transitions",
            "vo_line_adjudicate",
            "vo_synthesize",
            "edl",
            "mix",
            "master_finalize",
        ],
    },
    "refinement_agenda": {
        "inputs": {
            "soft": deps(
                "master/coverage_audit.json",
                "mastering/mastering_plan.json",
                "understanding/gap_evaluations.json",
                "understanding/source_acoustic_profile.json",
                "understanding/source_topology.json",
            )
        },
        "consumers": [
            "gap_framing_recompose",
            "selection_framing_apply",
        ],
    },
    "gap_framing_recompose": {
        "inputs": {
            "soft": [
                dep("understanding/gap_report.json", producer="gap_framing_compose"),
                dep("understanding/gap_framing_plan.json", producer="gap_framing_compose"),
                dep("understanding/nugget_layup_plan.json", producer="nugget_layup_compose"),
                *deps(
                    "master/coverage_audit.json",
                    "master/narrative_plan.json",
                    "master/selection.json",
                    "mastering/mastering_plan.json",
                    "segments/manifest.json",
                    "understanding/comprehension_risks.json",
                    "understanding/content_brief.json",
                    "understanding/episode_structure.json",
                    "understanding/gap_evaluations.json",
                    "understanding/nugget_corpus.json",
                    "understanding/refinement_agenda.json",
                ),
            ]
        },
        "outputs": [
            {"path": "understanding/gap_framing_plan.json"},
            {"path": "understanding/gap_report.draft.json"},
            {"path": "understanding/gap_vo_context_audit.json"},
            {"path": "understanding/nugget_layup_plan.json"},
            {"path": "understanding/cold_open_audition.json"},
            {"path": "understanding/listener_outcome_trajectory.json"},
            {"path": "understanding/refinement_plan.json"},
            {"path": "understanding/refinement_skip_copy.json"},
        ],
    },
    "selection_framing_apply": {
        "inputs": {
            "soft": [
                dep("understanding/gap_report.json", producer="gap_framing_compose"),
                *deps(
                    "master/coverage_audit.json",
                    "master/selection.json",
                    "mastering/mastering_plan.json",
                    "segments/manifest.json",
                    "understanding/content_brief.json",
                    "understanding/episode_structure.json",
                    "understanding/flow_adaptation.json",
                    "understanding/gap_framing_plan.json",
                    "understanding/nugget_corpus.json",
                    "understanding/nugget_layup_plan.json",
                    "understanding/refinement_agenda.json",
                    "understanding/source_topology.json",
                    "understanding/speaker_delivery_plan.json",
                    "understanding/speakers.json",
                ),
            ]
        },
        "outputs": [
            {"path": "understanding/gap_report.json"},
            {"path": "understanding/gap_report.draft.json"},
            {"path": "understanding/refinement_plan.json"},
            {"path": "understanding/refinement_skip_copy.json"},
        ],
    },
    "air_script_seams": {
        # mastering_plan / gap_report / nugget_layup_plan already hard.
        "inputs": {
            "soft": deps(
                "analysis/high_value_speech_islands.json",
                "master/selection.json",
                "segments/manifest.json",
                "segments/nle_edits.json",
                "transcript/full.json",
                "understanding/episode_structure.json",
                "understanding/gap_evaluations.json",
                "understanding/gap_fill_skip.json",
                "understanding/source_acoustic_profile.json",
                "understanding/source_topology.json",
            )
        },
        "outputs": [{"path": "understanding/gap_framing_plan.json"}],
    },
    "air_contract_sanitize": {
        "inputs": {
            "soft": [
                dep("mastering/mastering_plan.json", producer="air_script_seams"),
                dep("understanding/omit_ledger.json", producer="air_script_compose"),
                dep("understanding/gap_report.json", producer="gap_framing_compose"),
                *deps(
                    "master/selection.json",
                    "segments/manifest.json",
                    "understanding/gap_fill_skip.json",
                    "understanding/source_topology.json",
                ),
            ]
        },
        "consumers": [
            "transitions",
            "vo_synthesize",
            "edl",
            "mix",
            "junction_snip_qa",
            "master_finalize",
        ],
        "outputs": [{"path": "understanding/omit_ledger.json"}],
    },
    "transitions": {
        # `_preflight_transitions` refuses without the selection.
        "inputs": {
            "hard": deps("master/selection.json"),
            "soft": [
                dep("master/transitions.json", producer=None),
                dep("understanding/synthetic_framing_plan.json", producer=None),
                dep("understanding/reorder_bridges.json", producer="full_master_ranking"),
                dep(
                    "understanding/speaker_delivery_plan.json",
                    producer="full_master_ranking",
                ),
                *deps(
                    "master/coverage_audit.json",
                    "master/narrative_plan.json",
                    "master/transitions_pair_freeze.json",
                    "mastering/mastering_plan.json",
                    "mastering/media_ip_cta.json",
                    "segments/manifest.json",
                    "segments/boundaries.json",
                    "segments/nle_edits.json",
                    "understanding/content_brief.json",
                    "understanding/delivery_brief.json",
                    "understanding/episode_structure.json",
                    "understanding/flow_adaptation.json",
                    "understanding/gap_report.json",
                    "understanding/ideal_cuts.json",
                    "understanding/interview_spine.json",
                    "understanding/nugget_corpus.json",
                    "understanding/nugget_layup_plan.json",
                    "understanding/source_topology.json",
                    "understanding/speakers.json",
                    "understanding/talking_points.json",
                ),
            ],
        },
        "consumers": [
            "full_master_ranking",
            "sound_design_plan",
            "vo_synthesize",
            "edl",
            "mix",
            "junction_snip_qa",
            "master_finalize",
            "master_transcript_build",
            "podcast_publish",
        ],
        "outputs": [
            {"path": "master/deferred_transition_pairs.json"},
            {"path": "master/transitions_pair_freeze.json"},
            {"path": "master/order_reconcile.json"},
            {"path": "master/rank_candidates.json"},
            {"path": "master/story_health.json"},
            {"path": "understanding/reorder_bridges.json"},
            {"path": "understanding/speaker_delivery_plan.json"},
        ],
    },
}

# ---------------------------------------------------------------------------
# sound
# ---------------------------------------------------------------------------
# Two stages, and the recorded run (`MUX_CONTRACT_RECORD=1`) covers the big one:
# `sound_design_plan` showed 13 undeclared reads, every one of which is visible
# in `run_sound_design_plan`'s `build_input`.

_SOUND: dict[str, dict[str, Any]] = {
    "sound_design_plan": {
        # `build_input` reads the whole delivery picture, but each read is either
        # `read_json` (empty dict when absent) or a `load_*` helper that returns
        # falsey and is then skipped by an `if`. Nothing here gates the stage, so
        # nothing here is hard. `master/transitions.json` stays hard because the
        # registry already declared it and the stage is seeded after `transitions`.
        #
        # `order_reconcile` and the `refresh_*` helpers run first and pull in the
        # EDL, the mastering plan and the structure/policy artifacts — all three
        # wrapped in try/except with an explicit fail-open log.
        "inputs": {
            "soft": [
                *deps(
                    "segments/manifest.json",
                    "master/selection.json",
                    "master/narrative_plan.json",
                    "understanding/gap_report.json",
                    "understanding/content_brief.json",
                    "understanding/content_brief_reanchor.json",
                    "understanding/delivery_brief.json",
                    "understanding/episode_structure.json",
                    "understanding/sonic_context.json",
                    "understanding/soundscape_policy.json",
                    "understanding/source_acoustic_profile.json",
                    "understanding/speakers.json",
                    "understanding/analysis_state.json",
                    "mastering/mastering_plan.json",
                ),
                *back("master/edl.json"),
            ],
        },
        # `persist` calls `_load_sound_design_plan(c)` and merges into it, so the
        # plan is a read-modify-write — declared as an output already, which
        # `evaluate` counts as readable.
        "outputs": [
            {"path": "understanding/music_brief.json"},
            {"path": "understanding/episode_structure_compact.txt"},
        ],
        "consumers": ["sound_design_palettes", "mmaudio_sfx", "music_palette_compose"],
    },
    "vo_line_adjudicate": {
        # Homunculus-0.1.0-only and config-gated on
        # `analysis.gap_vo.adjudicate_before_synth`; both off-paths persist a skip
        # stub and mark done. Every read is `artifact_exists`-guarded, so the
        # stage has no hard input at all — it degrades to a stub, not a refusal.
        "inputs": {
            "soft": deps(
                "understanding/nugget_layup_plan.json",
                "understanding/nugget_corpus.json",
                "understanding/omit_ledger.json",
                "understanding/native_comprehension_masks.json",
                "understanding/content_brief.json",
            ),
        },
        # `_allocate` writes the allocation plan alongside the adjudication doc;
        # `stamp_gap_report_omit_skips` writes the gap report back under this
        # stage's key, which is why the gap report is already a declared output.
        "outputs": [{"path": "understanding/nugget_allocation_plan.json"}],
        "consumers": ["vo_synthesize"],
    },
}

# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
# Four of these are AUDIO_MUTATING (`edl`, `mix`, `junction_snip_qa`, and
# `master_finalize` in `ship`), so the hard-input bar is at its strictest here:
# a wrong hard input does not degrade a mix, it refuses one.
#
# `FALLBACK_HARD_INPUTS` in `dispatch_delta` is *not* a safe source of hard
# inputs. It feeds the no-delta guard, which merely tolerates a missing path,
# whereas `run_phase_checks` raises on one. It lists `master/assembly.wav` for
# `junction_snip_qa` — see the note on that stage for why declaring that as a
# contract hard input would re-create an exec_11871 halt.

_BUILD: dict[str, dict[str, Any]] = {
    "edl": {
        # REFUSES: `check_narrative_qc(ctx, stage="edl", require_selection=True)`
        # raises SystemExit for a missing content brief, coverage audit or
        # selection, and `narrative_qc.strict` is true in the shipped config.
        # `validate_flow1_narrative` returns early on the brief, so the order of
        # these three is the order the gate reports them in.
        "inputs": {
            "hard": [
                {"path": "understanding/content_brief.json", "producer": "content_context"},
                {"path": "master/coverage_audit.json", "producer": "topic_coverage_audit"},
                {"path": "master/selection.json", "producer": "full_master_ranking"},
            ],
            "soft": [
                # `run_edl` substitutes `{"transitions": []}` when the file is
                # absent, so the EDL is built with no seam grammar at all rather
                # than refusing — soft for dispatch, required for correctness.
                dep("master/transitions.json", correctness=True),
                *deps(
                    "master/narrative_plan.json",
                    "master/edl_narrative_audit.json",
                    "segments/manifest.json",
                    "understanding/gap_report.json",
                    "understanding/omit_ledger.json",
                    "understanding/nugget_layup_plan.json",
                    "understanding/sound_design_plan.json",
                    "mastering/mastering_plan.json",
                    "mastering/media_ip_cta.json",
                ),
            ],
        },
        "consumers": [
            "assembly_preview",
            "mix",
            "junction_snip_qa",
            "master_finalize",
            "master_transcript_build",
            "podcast_publish",
        ],
    },
    "assembly_preview": {
        # `run_preview` reads the EDL with `read_json` and iterates `clips`, so an
        # absent EDL yields an empty preview rather than a refusal. Soft.
        "inputs": {
            "soft": deps(
                "master/edl.json",
                "ingest/normalized.wav",
                "master/selection.json",
            ),
        },
        "consumers": ["junction_snip_qa", "mix"],
    },
    "junction_snip_qa": {
        # NO hard inputs, deliberately.
        #
        # `FALLBACK_HARD_INPUTS` lists `master/assembly.wav` here, but
        # `junction_recut_precedes_mix` exists precisely because this stage must
        # be able to run *before* the first mix: "The ladder needs only
        # master/edl.json — the remaster it drives is what mints assembly.wav."
        # Declaring the assembly hard would refuse the stage at PRESTAGE in exactly
        # the pre-mix recut posture it was added to serve, re-creating the
        # exec_11871 mix <-> junction_snip_qa ping-pong as a hard stop.
        #
        # The EDL is read with `read_json`, so it is soft too.
        "inputs": {
            "soft": [
                # Ownership makes `junction_snip_qa` authoritative for the air
                # order, the assembly ledger and the render ledger: it reads each
                # one and promotes it back, so they are read-modify-write.
                *rmw(
                    "master/assembly_ledger.json",
                    "master/air_order.json",
                    "master/render_ledger.json",
                ),
                # `assert_consumer` returns early without selection or the EDL,
                # so their absence is precisely when the T0-3 order this stage
                # adjudicates goes unchecked. Correctness-marked, still soft.
                dep("master/edl.json", correctness=True),
                dep("master/selection.json", correctness=True),
                *deps(
                "master/assembly.wav",
                "segments/manifest.json",
                "understanding/gap_report.json",
                "understanding/sonic_context.json",
                "understanding/source_acoustic_profile.json",
                "understanding/sound_design_plan.json",
                "mastering/media_ip_cta.json",
                ),
            ],
        },
        "consumers": ["mix", "master_finalize"],
    },
    "mix": {
        # REFUSES: the speech bed is `load_audio(ctx.read_path("ingest",
        # "normalized.wav"))`, which raises on a missing file — there is no mix
        # without a source tape in any posture.
        #
        # The EDL is soft: `mix` reads it with `read_json` and sanitises it, and
        # `assert_consumer` returns early when it is absent rather than refusing.
        # It stays soft — a contract hard input would fire at PRESTAGE, upstream
        # of `assert_consumer`'s `pre_mix_recut` exemption, and the
        # `junction_recut_precedes_mix` posture needs a mix that can run without
        # a settled EDL. `correctness` says the master would be wrong without it
        # while leaving that flexibility intact: nothing on the dispatch path
        # reads the marker.
        "inputs": {
            "hard": [
                {"path": "ingest/normalized.wav", "producer": "ingest"},
            ],
            "soft": [
                dep("master/edl.json", correctness=True),
                dep("master/selection.json", correctness=True),
                *deps(
                    "master/transitions.json",
                    "master/junction_snip_qa.json",
                    "master/seam_autopsy.json",
                    "understanding/sound_design_plan.json",
                    "understanding/omit_ledger.json",
                    "understanding/gap_report.json",
                    "sound_design/mmaudio_qa.json",
                ),
            ],
        },
        "consumers": ["junction_snip_qa", "master_finalize", "listen_delight_audit"],
    },
    "listen_delight_audit": {
        # Audit over whatever the master chain has produced; every read is
        # existence-guarded and the stage reports rather than refuses.
        "inputs": {
            "soft": deps(
                "master/assembly.wav",
                "master/edl.json",
                "master/selection.json",
                "understanding/sound_design_plan.json",
                "understanding/delivery_brief.json",
            ),
        },
        "consumers": ["master_finalize"],
    },
    "music_palette_compose": {
        # Owns cue placement on the SDP after the EDL exists (the `sound_design_plan`
        # note says so explicitly), so the plan is a read-modify-write: already a
        # declared output, and declared as an input here too.
        "inputs": {
            "soft": deps(
                "understanding/sound_design_plan.json",
                "understanding/music_brief.json",
                "master/edl.json",
                "master/selection.json",
                "understanding/episode_structure.json",
            ),
        },
        "consumers": ["mmaudio_sfx", "mix"],
    },
}

# ---------------------------------------------------------------------------
# ship
# ---------------------------------------------------------------------------

_SHIP: dict[str, dict[str, Any]] = {
    "master_finalize": {
        # REFUSES: `master_wav(ctx, "master/assembly.wav", "master/master.wav")`
        # opens the assembly and raises `FileNotFoundError(assembly)` when it is
        # not a file. There is no branch of this stage that produces a master
        # without one, and unlike `junction_snip_qa` there is no pre-mix posture —
        # `master_finalize` is seeded at DELIVERY_ORDER 30, after `mix` at 28.
        #
        # This is the declaration `ship_reachability` needs: the master is
        # reachable exactly when the assembly is.
        "inputs": {
            "hard": [
                {"path": "master/assembly.wav", "producer": "mix"},
            ],
            "soft": [
                # `master/seam_autopsy.json` is a declared output of this stage as
                # well: `verify_commitment` reads the prior autopsy and
                # `master_finalize` rewrites it. The render ledger is minted by
                # `junction_snip_qa` upstream.
                *rmw("master/seam_autopsy.json"),
                # Not correctness-marked: `render_ledger_exists` sits in
                # `RUBRIC_PMQ_CHECKS`, i.e. advisory under the default
                # aspirational policy, so by the project's own contract a
                # missing render ledger does not block publish.
                {"path": "master/render_ledger.json", "producer": "junction_snip_qa"},
                dep("master/edl.json", correctness=True),
                dep("master/selection.json", correctness=True),
                *deps(
                    "master/junction_snip_qa.json",
                    "master/transitions.json",
                    "understanding/omit_ledger.json",
                    "understanding/gap_report.json",
                    "understanding/sound_design_plan.json",
                    "mastering/mastering_plan.json",
                    "mastering/listen_delight_audit.json",
                    "mastering/chapter_close_hitch.json",
                ),
            ],
        },
        "consumers": ["master_transcript_build", "podcast_encode_mp3", "podcast_publish"],
    },
    "podcast_encode_mp3": {
        # REFUSES, and says so in the message it raises:
        # `raise FileNotFoundError("master/master.wav missing — run master_finalize first")`.
        "inputs": {
            "hard": [
                {"path": "master/master.wav", "producer": "master_finalize"},
            ],
        },
        "consumers": ["podcast_publish"],
    },
    "episode_cover_generate": {
        # Every read is `artifact_exists`-guarded and the stage returns early when
        # the prompt is absent, so nothing is hard.
        "inputs": {
            "soft": deps(
                "publish/cover_prompt.json",
                "publish/episode_meta.json",
                "understanding/content_brief.json",
                "understanding/speakers.json",
                "master/selection.json",
            ),
        },
        "consumers": ["podcast_publish"],
    },
    "podcast_publish": {
        # The optional G-Publish gate: `run_podcast_publish_skip` marks it skipped
        # and writes `{"skipped": true}` without packaging anything, so by rule 1
        # (presence must not depend on a gate outcome) nothing here can be hard.
        "inputs": {
            "soft": deps(
                "master/master.wav",
                "master/edl.json",
                "master/transcript.json",
                "master/transcript.vtt",
                "master/selection.json",
                "master/narrative_plan.json",
                "publish/episode_meta.json",
                "publish/cover_meta.json",
                "publish/audio.mp3",
                "segments/manifest.json",
                "understanding/gap_report.json",
                "understanding/speakers.json",
            ),
        },
        "consumers": [],
    },
}

GROUP_DEPS: dict[str, dict[str, dict[str, Any]]] = {
    "prepare": _PREPARE,
    "understand-a": _UNDERSTAND_A,
    "understand-b": _UNDERSTAND_B,
    "understand-c": _UNDERSTAND_C,
    "fill_gaps": _FILL_GAPS,
    "plan_rank": _PLAN_RANK,
    "sound": _SOUND,
    "build": _BUILD,
    "ship": _SHIP,
}


def deps_for(stage_id: str) -> dict[str, Any]:
    for group in GROUP_DEPS.values():
        if stage_id in group:
            return group[stage_id]
    return {}


def populated_stage_ids() -> list[str]:
    return sorted({sid for group in GROUP_DEPS.values() for sid in group})


def populated_groups() -> list[str]:
    return sorted(GROUP_DEPS)


__all__ = ["GROUP_DEPS", "deps_for", "populated_groups", "populated_stage_ids"]
