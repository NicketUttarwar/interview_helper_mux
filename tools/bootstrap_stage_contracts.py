#!/usr/bin/env python3
"""Bootstrap docs/cross-cutting/stage-contracts/*.yaml from code registries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from interview_mux.v2.config import ALL_LLM_STAGES  # noqa: E402
from interview_mux.artifact_dependency_graph import _PROPAGATION_SEEDS  # noqa: E402
from interview_mux.context_resolver import ARTIFACTS_REGISTRY  # noqa: E402
from interview_mux.llm_flow_hardening import LLM_UPSTREAM_STAGE  # noqa: E402
from interview_mux.null_field_policy import CRITICAL_FIELDS, NULLABLE_FIELDS  # noqa: E402
from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER  # noqa: E402
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS, STAGE_ARTIFACT_DISK_PATHS  # noqa: E402

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
    "chapter_close_hitch": [
        {"path": "status", "rule": "non_empty_string", "min_length": 1},
    ],
    "master_transcript_build": [{"path": "cues", "rule": "min_rows", "min_count": 0}],
}

_LLM_DEFAULT_SUFFICIENCY: dict[str, list[dict]] = {
    "sound_design_palettes": [{"path": "palettes", "rule": "min_rows", "min_count": 1}],
    "missing_framing": [{"path": "evaluations", "rule": "min_rows", "min_count": 1}],
    "gap_framing_compose": [{"path": "gaps", "rule": "min_rows", "min_count": 1}],
    "topic_coverage_audit": [{"path": "topics", "rule": "min_rows", "min_count": 1}],
    "narrative_arc_plan": [{"path": "chapters", "rule": "min_rows", "min_count": 1}],
    "full_master_ranking": [{"path": "ranked_segments", "rule": "min_rows", "min_count": 1}],
    "edl_narrative_audit": [{"path": "findings", "rule": "min_rows", "min_count": 1}],
    "transitions": [{"path": "transitions", "rule": "min_rows", "min_count": 1}],
    "synthetic_framing_plan": [{"path": "lines", "rule": "min_rows", "min_count": 1}],
    "sound_design_plan": [{"path": "assets", "rule": "min_rows", "min_count": 1}],
    "sfx_prompt_craft": [{"path": "prompts", "rule": "min_rows", "min_count": 1}],
    "sfx_prompt_refine": [{"path": "prompts", "rule": "min_rows", "min_count": 1}],
    "music_palette_compose": [{"path": "cues", "rule": "min_rows", "min_count": 1}],
    # Lay-up mining/composing may legitimately return zero rows (no recoverable
    # nuggets), so the rule is presence of the collection, not a row floor.
    "nugget_corpus_mine": [{"path": "nuggets", "rule": "min_rows", "min_count": 0}],
    "nugget_layup_compose": [{"path": "layups", "rule": "min_rows", "min_count": 0}],
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

_OUTPUT_PATH_OVERRIDES = {
    # These flagship publish stages are validated by their own runtime builders
    # rather than the analysis-envelope schema registry.
    "episode_meta_build": "publish/episode_meta.json",
    "episode_cover_prompt_craft": "publish/cover_prompt.json",
}
_OUTPUT_SCHEMA_OVERRIDES = {
    "chapter_close_hitch": "chapter_close_hitch.schema.json",
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
                "staging": tier == "llm_full",
            }
        ]
    doc["outputs"].extend(_EXTRA_OUTPUTS.get(stage_id, []))

    upstream = LLM_UPSTREAM_STAGE.get(stage_id)
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
    lines = ["# Stage contracts index\n", "| Stage | Tier | Outputs |", "|-------|------|---------|"]
    for r in rows:
        outs = ", ".join(r["outputs"] or []) or "—"
        lines.append(f"| `{r['stage']}` | {r['tier']} | {outs} |")
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {index.name} ({len(rows)} stages)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
