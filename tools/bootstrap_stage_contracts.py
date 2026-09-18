#!/usr/bin/env python3
"""Bootstrap docs/cross-cutting/stage-contracts/*.yaml from code registries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from contract_dependency_data import deps_for  # noqa: E402
from interview_mux.artifact_ownership import write_permitted  # noqa: E402
from interview_mux.v2.config import ALL_LLM_STAGES  # noqa: E402
from interview_mux.web.stages import STAGE_BY_ID  # noqa: E402
from interview_mux.artifact_dependency_graph import _PROPAGATION_SEEDS  # noqa: E402
from interview_mux.context_resolver import ARTIFACTS_REGISTRY  # noqa: E402
from interview_mux.llm_flow_hardening import LLM_UPSTREAM_STAGE  # noqa: E402
from interview_mux.null_field_policy import CRITICAL_FIELDS, NULLABLE_FIELDS  # noqa: E402
from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER  # noqa: E402
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS, STAGE_ARTIFACT_DISK_PATHS  # noqa: E402
from interview_mux.stage_contract import is_path_spec  # noqa: E402
from interview_mux.stage_contract import PIPELINE_TIERS as _PIPELINE_TIERS  # noqa: E402

OUT = ROOT / "docs" / "cross-cutting" / "stage-contracts"

# Per-stage sufficiency enrichment (LLM-Full)
_SUFFICIENCY: dict[str, list[dict]] = {
    "speaker_roles": [
        {"path": "speakers", "rule": "min_rows", "min_count": 1, "blocking": "progression"},
        {"path": "speakers", "rule": "speakers_not_all_unknown", "blocking": "progression"},
    ],
    "content_context": [
        {"path": "thesis", "rule": "non_empty_string", "min_length": 8, "blocking": "progression"},
        {"path": "topics", "rule": "min_rows", "min_count": 1, "blocking": "progression"},
        {"path": "key_claims[]", "rule": "evidence_anchor", "blocking": "advisory"},
    ],
    "content_brief_reanchor": [
        {"path": "thesis", "rule": "non_empty_string", "min_length": 8, "blocking": "progression"},
        {"path": "topics", "rule": "min_rows", "min_count": 1, "blocking": "progression"},
    ],
    "talking_points_compose": [
        {"path": "strategy_summary", "rule": "non_empty_string", "min_length": 8, "blocking": "progression"},
        {"path": "talking_points", "rule": "min_rows", "min_count": 1, "blocking": "progression"},
    ],
    "ideal_cuts_propose": [
        {"path": "cuts", "rule": "min_rows", "min_count": 1, "blocking": "progression"},
    ],
    "boundary_detection": [
        {"path": "boundaries", "rule": "min_rows", "min_count": 1, "blocking": "progression"},
    ],
    "boundary_topic_resplit": [
        {"path": "boundaries", "rule": "min_rows", "min_count": 1, "blocking": "progression"},
    ],
    "segment_classification": [
        {"path": "segments", "rule": "min_rows", "min_count": 1, "blocking": "progression"},
    ],
}

_PROCESS_SUFFICIENCY: dict[str, list[dict]] = {
    "delivery_brief_build": [
        {
            "path": "version",
            "rule": "required_fields",
            "fields": ["version", "target_duration_sec", "question_budget", "chapter_budget"],
        },
    ],
    "soundscape_policy_build": [
        {
            "path": "version",
            "rule": "required_fields",
            "fields": [
                "version",
                "underscore_policy",
                "pace_class",
                "sfx_density",
                "mix_contract",
                "standards",
                "cue_slots",
            ],
        },
    ],
    "mmaudio_sfx": [{"path": "assets", "rule": "min_rows", "min_count": 0}],
    # Both of these are in `STAGE_ARTIFACT_SCHEMAS` with an empty sufficiency
    # block, which is what `verify_stage_contracts` goes red on. The rule below
    # is the one thing about each artifact that can be defended without
    # inventing a threshold: its own JSON schema's `required` list.
    #
    # Neither stage can carry a row-count rule. `junction_snip_qa` on a clean
    # master has zero `findings` and zero `applied` — that is the *good* outcome
    # — and `sound_design_vo_finalize` answers `{"skipped": true}` whenever
    # sound design or VO is off, with `missing` and `errors` both empty. A
    # `min_rows >= 1` there would fail exactly the runs that went well.
    "junction_snip_qa": [
        {"path": "version", "rule": "required_fields", "fields": ["version", "generated_at"]},
    ],
    "sound_design_vo_finalize": [
        {"path": "skipped", "rule": "required_fields", "fields": ["skipped", "refused"]},
    ],
    "chapter_close_hitch": [
        {"path": "status", "rule": "non_empty_string", "min_length": 1},
    ],
    # HPUB-3 / clinic B1: empty cues refuse ship-complete; contract docs min≥1.
    # JSON schema still allows cue_count 0 so hollow packs can be written then refused.
    "master_transcript_build": [{"path": "cues", "rule": "min_rows", "min_count": 1}],
}

_LLM_DEFAULT_SUFFICIENCY: dict[str, list[dict]] = {
    # Defaults: early_palettes_llm=false → deferred empty palettes OK (SDP invents).
    # Completeness SSOT: artifact_completeness._gaps_sound_design_plan (SDP-B1).
    "sound_design_palettes": [
        {
            "path": "palettes",
            "rule": "min_rows",
            "min_count": 1,
            "when": {"early_palettes_llm": True},
        }
    ],
    "missing_framing": [{"path": "evaluations", "rule": "min_rows", "min_count": 1}],
    # Skip stubs (`ensure_gap_fill_skipped`) legitimately write `gaps: []`.
    # min_count 1 conflicted with that empty-ok path (clinic B3 / CODE_DOC_CONFLICT).
    "gap_framing_compose": [{"path": "gaps", "rule": "min_rows", "min_count": 0}],
    "topic_coverage_audit": [{"path": "topics", "rule": "min_rows", "min_count": 1}],
    "narrative_arc_plan": [{"path": "chapters", "rule": "min_rows", "min_count": 1}],
    "full_master_ranking": [{"path": "ranked_segments", "rule": "min_rows", "min_count": 1}],
    "edl_narrative_audit": [{"path": "findings", "rule": "min_rows", "min_count": 0}],
    "transitions": [{"path": "transitions", "rule": "min_rows", "min_count": 0}],
    "synthetic_framing_plan": [{"path": "lines", "rule": "min_rows", "min_count": 1}],
    "sound_design_plan": [{"path": "assets", "rule": "min_rows", "min_count": 1}],
    "sfx_prompt_craft": [{"path": "prompts", "rule": "min_rows", "min_count": 1}],
    "sfx_prompt_refine": [{"path": "prompts", "rule": "min_rows", "min_count": 1}],
    "music_palette_compose": [{"path": "cues", "rule": "min_rows", "min_count": 1}],
    # Lay-up mining/composing may legitimately return zero rows (no recoverable
    # nuggets), so the rule is presence of the collection, not a row floor.
    "nugget_corpus_mine": [{"path": "nuggets", "rule": "min_rows", "min_count": 1}],
    "nugget_layup_compose": [{"path": "layups", "rule": "min_rows", "min_count": 0}],
    "framing_posture_decide": [
        {"path": "recommended_framing", "rule": "non_empty_string", "blocking": "progression"},
        {"path": "posture_hint", "rule": "non_empty_string", "blocking": "progression"},
    ],
    "vo_line_adjudicate": [{"path": "lines", "rule": "min_rows", "min_count": 0}],
    "air_script_compose": [{"path": "air_script.beats", "rule": "min_rows", "min_count": 0}],
    "air_script_seams": [{"path": "air_script.beats", "rule": "min_rows", "min_count": 0}],
    "episode_meta_build": [{"path": "title", "rule": "non_empty_string", "min_length": 1}],
    "episode_cover_prompt_craft": [
        {"path": "prompt", "rule": "non_empty_string", "min_length": 1}
    ],
}

_GATES = {
    "transcript_review": {"tier": "gate", "gate_id": "G0"},
    "g1_vo_pickup": {"tier": "gate", "gate_id": "G1"},
}

# Contract files that are NOT dispatchable pipeline stages (plan §8.4).
# `process` / `llm_full` / `deterministic` is reserved for the 72 stages in
# ANALYSIS_ORDER + DELIVERY_ORDER; everything else is `gate` (operator must act)
# or `meta` (sub-stage volley, adjudicator, brief, init helper, retired).
# tests/test_contract_tier_partition.py pins the partition.
_NON_STAGE_TIERS: dict[str, str] = {
    # operator-action entries
    "transcript_review": "gate",
    "g1_vo_pickup": "gate",
    "vo_ingest": "gate",
    # meta — not dispatchable by the driver walk
    "_arbiter": "meta",
    "ranking_refine": "meta",
    "transitions_refine": "meta",
    "narrative_arc_refine": "meta",
    "sdp_intent_refine": "meta",
    "sfx_prompt_refine": "meta",
    "edl_narrative_refine": "meta",
    "connector_seam_adjudicate": "meta",
    "island_cluster_structure_adjudicate": "meta",
    "junction_thought_complete": "meta",
    "junction_feel_audit": "meta",
    "sfx_brief": "meta",
    "podcast_sfx_brief": "meta",
    "sound_design_plan_init": "meta",
    "synthetic_framing_plan": "meta",
    "optimal_questions": "meta",
}

_OUTPUT_PATH_OVERRIDES = {
    # These flagship publish stages are validated by their own runtime builders
    # rather than the analysis-envelope schema registry.
    "episode_meta_build": "publish/episode_meta.json",
    "episode_cover_prompt_craft": "publish/cover_prompt.json",
}
_OUTPUT_SCHEMA_OVERRIDES = {
    "chapter_close_hitch": "chapter_close_hitch.schema.json",
    # SOS-B1: co-writer of master/selection.json — same schema as full_master_ranking.
    "selection_order_sanitize": "master_selection_artifact.schema.json",
}

_CONSUMER_OVERRIDES = {
    "episode_meta_build": [
        "episode_cover_prompt_craft",
        "episode_cover_generate",
        "podcast_publish",
    ],
    "episode_cover_prompt_craft": ["episode_cover_generate"],
    "nugget_corpus_mine": ["nugget_layup_compose"],
    "nugget_layup_compose": ["gap_framing_recompose", "edl", "g1_vo_pickup"],
    "air_script_compose": ["air_script_seams", "edl"],
    "air_script_seams": ["transitions", "music_palette_compose", "edl"],
    "mmaudio_sfx": ["mix"],
    "chapter_close_hitch": [
        "connector_fuse_pass_pre_ranking",
        "full_master_ranking",
    ],
    "master_transcript_build": ["podcast_publish"],
}

# Stages whose contract hard inputs are fully owned by dependency_data (do not
# inject LLM_UPSTREAM_STAGE primary as hard). Runtime flow-hardening upstream
# resolution is unchanged.
_SKIP_LLM_UPSTREAM_HARD: frozenset[str] = frozenset(
    {
        # FMR-B1: hard = narrative+manifest+gap per `_check_full_master_ranking`;
        # fuse rounds stay soft enrichment.
        "full_master_ranking",
        # NCM-B3: air_script mastering_plan stays soft; selection hard via
        # _EXTRA_INPUTS (body never refuses on plan).
        "nugget_corpus_mine",
        # NLC-B3: IP audit soft (shadow/budget enrichment); hard = selection+corpus
        # via _EXTRA_INPUTS (body soft-admits missing audit).
        "nugget_layup_compose",
        # ENA-B2: hard = brief+coverage+narrative+selection (build_input /
        # preflight); SDP is optional soft — do not inject LLM_UPSTREAM SDP hard.
        "edl_narrative_audit",
        # ECPC-B2: episode_meta soft-harvest only; hard:[] via dependency_data.
        "episode_cover_prompt_craft",
    }
)

# Extra declared inputs for stages whose reads are not derivable from
# LLM_UPSTREAM_STAGE alone.
_EXTRA_INPUTS: dict[str, dict[str, list[dict]]] = {
    "nugget_corpus_mine": {
        "hard": [{"path": "master/selection.json", "producer": "full_master_ranking"}],
        "soft": [
            {"path": "segments/manifest.json", "producer": "segment_classification"},
            {"path": "understanding/talking_points.json", "producer": "talking_points_compose"},
            {"path": "understanding/ideal_cuts.json", "producer": "ideal_cuts_propose"},
        ],
    },
    "nugget_layup_compose": {
        "hard": [
            {"path": "master/selection.json", "producer": "full_master_ranking"},
            {"path": "understanding/nugget_corpus.json", "producer": "nugget_corpus_mine"},
        ],
        "soft": [
            {"path": "segments/manifest.json", "producer": "segment_classification"},
            {"path": "understanding/talking_points.json", "producer": "talking_points_compose"},
        ],
    },
    "mmaudio_sfx": {
        "hard": [
            {"path": "understanding/sound_design_plan.json", "producer": "sound_design_plan"},
            {"path": "sound_design/sfx_prompts.json", "producer": "sfx_prompt_craft"},
        ],
        "soft": [],
    },
    "chapter_close_hitch": {
        "hard": [{"path": "master/narrative_plan.json", "producer": "narrative_arc_plan"}],
        "soft": [
            {"path": "segments/manifest.json", "producer": "segment_classification"},
            {"path": "transcript/full.json", "producer": "transcribe"},
        ],
    },
    "master_transcript_build": {
        "hard": [
            {"path": "master/master.wav", "producer": "master_finalize"},
            {"path": "master/edl.json", "producer": "edl"},
        ],
        "soft": [{"path": "transcripts/index.json"}],
    },
    "air_script_compose": {
        "hard": [{"path": "master/selection.json", "producer": "full_master_ranking"}],
        "soft": [{"path": "mastering/mastering_plan.json", "producer": "mastering_plan_synthesize"}],
    },
    "air_script_seams": {
        "hard": [{"path": "mastering/mastering_plan.json", "producer": "air_script_compose"}],
        "soft": [
            {"path": "understanding/nugget_layup_plan.json", "producer": "nugget_layup_compose"},
            {"path": "understanding/gap_report.json", "producer": "nugget_layup_compose"},
        ],
    },
}

# Secondary artifacts a stage also writes (beyond its registered envelope path).
_EXTRA_OUTPUTS: dict[str, list[dict]] = {
    "nugget_layup_compose": [
        {
            "path": "understanding/gap_report.json",
            "schema": "gap_report.schema.json",
            "staging": True,
        }
    ],
    "chapter_close_hitch": [
        {
            "path": "mastering/chapter_close_hitch/intent_plan.json",
            "schema": "narrative_plan_artifact.schema.json",
            "staging": True,
        },
        {
            "path": "mastering/chapter_close_hitch/remap.json",
            "staging": True,
        },
    ],
    "master_transcript_build": [
        {"path": "master/transcript.vtt"},
        {"path": "master/transcript.txt"},
    ],
}

_PROCESS_STAGES = [
    "audio_preclean",
    "ingest",
    "transcribe",
    "transcript_review_build",
    "vo_ingest",
    "assembly_preview",
    "edl",
    "mmaudio_sfx",
    "mix",
    "master_finalize",
    "sound_design_plan_init",
    "delivery_brief_build",
    "soundscape_policy_build",
    "source_topology_build",
    "chapter_close_hitch",
    # Deterministic Pass A (ASC-B1) — not in ALL_LLM_STAGES; schema alone
    # previously forced llm_full via STAGE_ARTIFACT_SCHEMAS.
    "air_script_compose",
    # Deterministic Pass B (ASS-B1) — same schema landmine as Pass A.
    "air_script_seams",
    "master_transcript_build",
    "_arbiter",
]

_DETERMINISTIC = [
    "source_acoustic_profile",
    "interview_spine_build",
    "sonic_context_build",
    "sound_design_vo_finalize",
    # Refinement Pass (docs/cross-cutting/refinement-passes.md) — deterministic
    # L0 agenda + recompose/refine runners, gated by refinement_gate.decide_pass.
    # No LLM calls.
    "refinement_agenda",
    "gap_framing_recompose",
    "selection_framing_apply",
    "ranking_refine",
    "narrative_arc_refine",
    "transitions_refine",
    "sdp_intent_refine",
    "edl_narrative_refine",
]

def _registry_outputs(stage_id: str, primary_rel: str | None) -> list[dict]:
    """Secondary outputs from the runtime promotion allowlist (`STAGE_BY_ID`).

    `flush_stage_writes` promotes exactly `StageInfo.artifacts` +
    `audio_outputs`, so that tuple is the existing runtime truth about what a
    stage writes — not a fourth SSOT invented here.

    Paths the ownership constitution **denies** to this stage are excluded: a
    contract output is a write the stage is permitted to make (plan §2.1 puts
    `write_permitted` in the admissibility rule), and `StageInfo` lists some
    co-producer paths that ownership refuses — e.g. `edl_narrative_audit` ->
    `master/transitions.json` is `narrative_must_not_mint_transitions`.
    """
    info = STAGE_BY_ID.get(stage_id)
    if info is None:
        return []
    rows: list[dict] = []
    seen = {primary_rel} if primary_rel else set()
    for rel in list(info.artifacts) + list(info.audio_outputs):
        if not rel or rel in seen:
            continue
        seen.add(rel)
        if not is_path_spec(rel):
            ok, _reason = write_permitted(None, rel, stage_id)
            if not ok:
                continue
        rows.append({"path": rel, "staging": True})
    return rows


def _merge_declared_deps(stage_id: str, doc: dict) -> None:
    """Fold `tools/contract_dependency_data.py` into the generated contract."""
    declared = deps_for(stage_id)
    if not declared:
        return
    for kind in ("hard", "soft"):
        items = (declared.get("inputs") or {}).get(kind) or []
        known = {i["path"] for i in doc["inputs"][kind]}
        doc["inputs"][kind].extend(i for i in items if i["path"] not in known)
    # Explicit empty hard from dependency data wins over seed-predecessor fill.
    if "hard" in (declared.get("inputs") or {}) and not (declared.get("inputs") or {}).get("hard"):
        doc["inputs"]["hard"] = []
    if declared.get("consumers"):
        doc["consumers"] = list(declared["consumers"])
    if declared.get("propagation"):
        doc["propagation"] = {"invalidates_stages": list(declared["propagation"])}
    for item in declared.get("outputs") or []:
        if item["path"] not in {o["path"] for o in doc["outputs"]}:
            doc["outputs"].append(item)
    if declared.get("remediation"):
        doc["remediation"] = {"strategies": list(declared["remediation"])}
    if declared.get("lifecycle_phases"):
        doc["lifecycle"] = {"phases": list(declared["lifecycle_phases"])}


def _all_stage_ids() -> list[str]:
    seen: list[str] = []
    for batch in (
        ANALYSIS_ORDER,
        DELIVERY_ORDER,
        [
            "vo_ingest",
            "sound_design_plan_init",
            "sfx_prompt_refine",
            "synthetic_framing_plan",
            "_arbiter",
        ],
    ):
        for s in batch:
            if s not in seen:
                seen.append(s)
    return seen

def _contract_for(stage_id: str) -> dict:
    if stage_id in _PROCESS_STAGES:
        tier = "process"
    elif stage_id in _DETERMINISTIC:
        tier = "deterministic"
    elif stage_id in _GATES:
        tier = "gate"
    elif stage_id in STAGE_ARTIFACT_SCHEMAS or stage_id in ALL_LLM_STAGES:
        tier = "llm_full"
    else:
        tier = "process"

    # Staging still follows LLM-ness even when the tier is reclassified below.
    stages_output = tier == "llm_full"
    tier = _NON_STAGE_TIERS.get(stage_id, tier)

    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_id) or _OUTPUT_PATH_OVERRIDES.get(stage_id)
    schema_file = STAGE_ARTIFACT_SCHEMAS.get(stage_id) or _OUTPUT_SCHEMA_OVERRIDES.get(stage_id)

    doc: dict = {
        "stage_id": stage_id,
        "tier": tier,
        "lifecycle": {
            "phases": [
                "prestage",
                "pre_call",
                "llm_execute",
                "staged_validate",
                "committed",
                "post_commit_validate",
            ]
        },
        "outputs": [],
        "inputs": {"hard": [], "soft": []},
        "sufficiency": _SUFFICIENCY.get(
            stage_id,
            _LLM_DEFAULT_SUFFICIENCY.get(stage_id, _PROCESS_SUFFICIENCY.get(stage_id, [])),
        ),
        "propagation": {"invalidates_stages": list(_PROPAGATION_SEEDS.get(stage_id, ()))},
        "consumers": _CONSUMER_OVERRIDES.get(
            stage_id,
            [c for c, paths in ARTIFACTS_REGISTRY.items() if rel in paths],
        ),
        "remediation": {"strategies": ["volley_retry", "full_stage_rerun"]},
    }

    if rel:
        doc["outputs"] = [
            {
                "path": rel,
                "schema": schema_file,
                "staging": stages_output,
            }
        ]
    doc["outputs"].extend(_EXTRA_OUTPUTS.get(stage_id, []))
    known_outputs = {o["path"] for o in doc["outputs"]}
    doc["outputs"].extend(
        row for row in _registry_outputs(stage_id, rel) if row["path"] not in known_outputs
    )

    upstream = None if stage_id in _SKIP_LLM_UPSTREAM_HARD else LLM_UPSTREAM_STAGE.get(stage_id)
    if upstream:
        up_rel = STAGE_ARTIFACT_DISK_PATHS.get(upstream) or _OUTPUT_PATH_OVERRIDES.get(
            upstream
        )
        if up_rel:
            doc["inputs"]["hard"].append({"path": up_rel, "producer": upstream})

    for kind, items in _EXTRA_INPUTS.get(stage_id, {}).items():
        known = {i["path"] for i in doc["inputs"][kind]}
        doc["inputs"][kind].extend(i for i in items if i["path"] not in known)

    if stage_id in _GATES:
        doc.update(_GATES[stage_id])

    crit = sorted(CRITICAL_FIELDS.get(stage_id, frozenset()))
    if crit:
        doc["critical_fields"] = crit
    null = sorted(NULLABLE_FIELDS.get(stage_id, frozenset()))
    if null:
        doc["nullable_fields"] = null

    _merge_declared_deps(stage_id, doc)

    return doc

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for sid in _all_stage_ids():
        path = OUT / f"{sid}.yaml"
        doc = _contract_for(sid)
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        print(f"wrote {path.name}")

    rows = []
    for p in sorted(OUT.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        raw = yaml.safe_load(p.read_text())
        rows.append(
            {
                "stage": p.stem,
                "tier": raw.get("tier"),
                "outputs": [o.get("path") for o in raw.get("outputs") or []],
            }
        )
    index = OUT / "00-INDEX.md"
    pipeline_tiers = sorted(_PIPELINE_TIERS)
    lines = [
        "# Stage contracts index\n",
        "<!-- generated by tools/bootstrap_stage_contracts.py — do not hand-edit -->\n",
        "## Tier convention\n",
        "`tier` partitions contract files into dispatchable pipeline stages and",
        "everything else. There are more contract files than pipeline stages, so the",
        "partition is load-bearing: a solver that walks contracts must never offer a",
        "non-stage. `tests/test_contract_tier_partition.py` pins it.\n",
        "| Tier | Meaning | Membership |",
        "|------|---------|------------|",
        "| `process` | Deterministic stage body, no LLM volley | pipeline stage |",
        "| `deterministic` | Stage body derived wholly from upstream artifacts | pipeline stage |",
        "| `llm_full` | Stage body whose artifact content comes from an LLM volley | pipeline stage |",
        "| `gate` | Operator must act; never auto-dispatched | non-stage |",
        "| `meta` | Sub-stage LLM volley, adjudicator, brief, init helper, arbiter, retired | non-stage |",
        "",
        f"**Invariant:** the set of contracts whose tier is in {{{', '.join(f'`{t}`' for t in pipeline_tiers)}}}",
        "equals exactly the 72 stages of `ANALYSIS_ORDER` + `DELIVERY_ORDER`",
        "(`src/interview_mux/v2/config.py`). `gate` / `meta` contracts exist so those",
        "non-stages can still declare inputs, outputs and ownership — they are not",
        "pipeline steps and carry no seed-order position.\n",
        "**Path SSOT:** `STAGE_ARTIFACT_DISK_PATHS` (`src/interview_mux/prompt_validation.py`)",
        "is the declared direction of truth for a stage's primary artifact path; the",
        "`artifact_ownership.py` catalog and contract `outputs` follow it, and",
        "`tests/test_path_ssot_drift.py` fails on drift. See",
        "[contract-migration-test-policy.md](../contract-migration-test-policy.md).\n",
        "## Where the dependency data lives\n",
        "These files are **generated** — `tools/bootstrap_stage_contracts.py`",
        "rewrites every one of them, and it is step 1 of",
        "`scripts/verify_artifact_contract.sh`. A hand edit is reverted on the next",
        "verify run. Populate `tools/contract_dependency_data.py` instead; it is",
        "organised by operator phase because plan §3.3 populates upstream-first.\n",
        "Secondary `outputs` are derived from `web/stages.py::StageInfo.artifacts` +",
        "`audio_outputs` — the tuple `flush_stage_writes` actually promotes — minus",
        "any path the ownership constitution denies that stage. A contract output is",
        "a write the stage is *permitted* to make.\n",
        "## Flags\n",
        "| Flag | Default | Effect |",
        "|------|---------|--------|",
        "| `MUX_CONTRACT_RECORD` | `0` | Record real reads/writes to"
        " `operator/contract_observed.json` at the `write_staging` path resolvers"
        " (`interview_mux.contract_conformance`). Report-only at runtime: a"
        " mismatch warns and never gates a stage. |",
        "| `MUX_CONTRACT_STRICT_GROUPS` | unset | Override"
        " `contract_conformance.STRICT_GROUPS`, the groups whose conformance"
        " findings *fail* `tests/test_contract_conformance.py` instead of warning"
        " (plan §8.10). |",
        "| `MUX_CONTRACT_REQUIRES` | `0` | Consume contract-derived `requires` edges"
        " in `artifact_dependency_graph`. Off means the graph emits the frozen"
        " `_BASELINE_REQUIRES_EDGES`, so populating `inputs[].producer` cannot"
        " change heal routing for brain 0.1.0 / 0.2.0. |",
        "| `MUX_CONTRACT_HARD_INPUT_STRICT` | `0` | Make an **absent** declared hard"
        " input fatal again at `PRESTAGE` (`artifact_lifecycle.hard_input_strict`)."
        " Off — the default — records the absence as a `missing_hard_input` defect"
        " plus a resilience event and refuses the stage without raising, so a"
        " declaration on a conditionally produced artifact cannot crash a live run."
        " Set `=1` in CI and forensics runs that want to fail loudly. |\n",
        "**`inputs` are not inert.** `artifact_lifecycle.run_phase_checks` gates",
        "`PRESTAGE` on every **hard** input, so a wrongly-hard dep still stops a live",
        "stage — as a recorded refusal by default (above), or fatally under",
        "`MUX_CONTRACT_HARD_INPUT_STRICT=1`. A **stale** hard input is fatal either",
        "way: produced-then-invalidated is an ordering bug. During population a dep is",
        "hard only where the stage body already refuses without it; every other real",
        "dep is `soft`, which nothing live consumes.\n",
        "**`sufficiency` is inert.** `sufficiency_engine.sufficiency_enabled()` is a",
        "hardcoded `False` that no flag or config key reaches, so these rules are",
        "documentation — see `tests/test_sufficiency_engine_disabled.py`, which also",
        "records what has to be defused before switching them on.\n",
        "## Contracts\n",
        "| Stage | Tier | Outputs |",
        "|-------|------|---------|",
    ]
    for r in rows:
        outs = ", ".join(r["outputs"] or []) or "—"
        lines.append(f"| `{r['stage']}` | {r['tier']} | {outs} |")
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {index.name} ({len(rows)} stages)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
