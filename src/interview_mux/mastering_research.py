"""Eight-wave mastering research runtime → research_dossier.json.

Canon: docs/cross-cutting/mastering-process.md, mastering-research-fields.md
Fail-open: missing upstream → status=skipped_or_thin field reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_context_compiler import compile_packet, content_hash, make_item, write_packet
from interview_mux.run_context import RunContext

RESEARCH_DIR = "mastering/research"
DOSSIER_REL = "mastering/research_dossier.json"
ROUTING_REL = "mastering/research/routing.json"

WAVE_FIELDS: dict[int, tuple[str, ...]] = {
    1: ("preclean_lineage", "ingest_normalization", "source_acoustic_profile", "source_readiness_band"),
    2: (
        "g0_transcript_fidelity",
        "speaker_roles",
        "source_topology",
        "speaker_volleys",
        "pickup_speaker_voice",
        "interview_spine_windows",
    ),
    3: (
        "thesis_claims",
        "value_features",
        "coherence_risks",
        "topic_coverage",
        "narrative_arc_candidates",
        "transition_bridge_inventory",
    ),
    4: (
        "boundaries_segments",
        "delivery_brief_budgets",
        "episode_structure_pack",
        "nle_operator_edits",
        "master_ranking_exclusions",
        "edl_speech_timeline",
    ),
    5: ("gap_framing_plan", "gap_vo_synthesis", "framing_coverage_guard"),
    6: (
        "sonic_context_cues",
        "sound_design_palettes",
        "soundscape_policy_slots",
        "sdp_plan_and_prompts",
        "mmaudio_assets_qa",
        "house_chain_levels",
        "production_style_profile",
    ),
    7: (
        "journey_gates",
        "story_board_steering",
        "conversation_studio",
        "stage_reuse_and_hash",
        "llm_volley_audit",
    ),
    8: (
        "deterministic_lint",
        "edl_narrative_qc",
        "artifact_completeness",
        "mix_completeness",
        "master_verify",
        "local_audio_runtimes",
        "llm_routing_tiers",
    ),
}

# Artifact probes per field (first existing wins for thin evidence)
FIELD_PROBES: dict[str, tuple[str, ...]] = {
    "preclean_lineage": ("preclean/lineage.json",),
    "ingest_normalization": ("ingest/normalized.wav", "ingest/source_meta.json"),
    "source_acoustic_profile": ("understanding/source_acoustic_profile.json",),
    "source_readiness_band": ("run_meta.json",),
    "g0_transcript_fidelity": ("transcript/review.json", "transcript/words.json"),
    "speaker_roles": ("understanding/speaker_roles.json",),
    "source_topology": ("understanding/source_topology.json",),
    "speaker_volleys": ("understanding/episode_structure.json",),
    "pickup_speaker_voice": ("understanding/source_topology.json",),
    "interview_spine_windows": ("understanding/interview_spine/windows.json",),
    "thesis_claims": ("understanding/content_brief.json",),
    "value_features": ("understanding/value_features.json", "understanding/content_brief.json"),
    "coherence_risks": ("understanding/coherence_report.json",),
    "topic_coverage": ("master/coverage_audit.json", "understanding/content_brief.json"),
    "narrative_arc_candidates": ("master/narrative_plan.json", "understanding/content_brief.json"),
    "transition_bridge_inventory": ("master/transitions.json",),
    "boundaries_segments": ("segments/manifest.json",),
    "delivery_brief_budgets": ("understanding/delivery_brief.json",),
    "episode_structure_pack": ("understanding/episode_structure.json",),
    "nle_operator_edits": ("segments/nle_edits.json",),
    "master_ranking_exclusions": ("master/selection.json",),
    "edl_speech_timeline": ("master/edl.json",),
    "gap_framing_plan": ("understanding/gap_framing_plan.json", "understanding/gap_report.json"),
    "gap_vo_synthesis": ("vo_pickup/synthesis_report.json",),
    "framing_coverage_guard": ("master/selection.json",),
    "sonic_context_cues": ("understanding/sonic_context.json",),
    "sound_design_palettes": ("sound_design/palettes.json",),
    "soundscape_policy_slots": ("understanding/soundscape_policy.json",),
    "sdp_plan_and_prompts": ("sound_design/plan.json",),
    "mmaudio_assets_qa": ("sound_design/mmaudio_qa.json",),
    "house_chain_levels": ("master/mix_report.json",),
    "production_style_profile": ("understanding/analysis_state.json", "run_meta.json"),
    "journey_gates": ("run_meta.json",),
    "story_board_steering": ("understanding/analysis_state.json",),
    "conversation_studio": ("understanding/gap_report.json",),
    "stage_reuse_and_hash": (".stage_done",),
    "llm_volley_audit": ("llm_audit.jsonl",),
    "deterministic_lint": ("run_meta.json",),
    "edl_narrative_qc": ("master/edl_narrative_audit.json",),
    "artifact_completeness": ("run_meta.json",),
    "mix_completeness": ("master/mix_report.json",),
    "master_verify": ("master/master.wav",),
    "local_audio_runtimes": ("run_meta.json",),
    "llm_routing_tiers": ("run_meta.json",),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _probe(ctx: RunContext, field_id: str) -> tuple[str, list[str]]:
    found: list[str] = []
    for rel in FIELD_PROBES.get(field_id, ()):
        if rel == ".stage_done":
            p = ctx.path(rel)
            if p.exists():
                found.append(rel)
            continue
        if ctx.artifact_exists(rel):
            found.append(rel)
    if found:
        return "complete", found
    return "skipped_or_thin", []


def write_field_report(ctx: RunContext, field_id: str, wave: int) -> dict[str, Any]:
    status, refs = _probe(ctx, field_id)
    report = {
        "version": 1,
        "field_id": field_id,
        "wave": wave,
        "status": status,
        "evidence_refs": refs,
        "summary": f"{field_id}: {status}",
        "confidence": 0.8 if status == "complete" else 0.2,
        "generated_at": _now(),
    }
    ctx.write_json(f"{RESEARCH_DIR}/{field_id}.json", report)
    return report


def run_research_wave(ctx: RunContext, wave: int) -> dict[str, Any]:
    fields = WAVE_FIELDS.get(wave) or ()
    reports = [write_field_report(ctx, fid, wave) for fid in fields]
    return {
        "wave": wave,
        "field_ids": list(fields),
        "complete_count": sum(1 for r in reports if r.get("status") == "complete"),
        "thin_count": sum(1 for r in reports if r.get("status") != "complete"),
        "generated_at": _now(),
    }


def run_research_routing(ctx: RunContext) -> None:
    routing = {
        "version": 1,
        "mode": "sequential_waves",
        "waves": sorted(WAVE_FIELDS.keys()),
        "field_count": sum(len(v) for v in WAVE_FIELDS.values()),
        "generated_at": _now(),
    }
    ctx.write_json(ROUTING_REL, routing)


def run_research_rollup(ctx: RunContext) -> dict[str, Any]:
    """Ensure all wave fields exist, then write dossier rollup."""
    run_research_routing(ctx)
    wave_summaries = []
    fields_out: dict[str, Any] = {}
    for wave in sorted(WAVE_FIELDS.keys()):
        wave_summaries.append(run_research_wave(ctx, wave))
        for fid in WAVE_FIELDS[wave]:
            rel = f"{RESEARCH_DIR}/{fid}.json"
            if ctx.artifact_exists(rel):
                doc = ctx.read_json(rel)
                if isinstance(doc, dict):
                    fields_out[fid] = doc
    dossier = {
        "version": 1,
        "waves": wave_summaries,
        "fields": fields_out,
        "complete_fields": [k for k, v in fields_out.items() if v.get("status") == "complete"],
        "thin_fields": [k for k, v in fields_out.items() if v.get("status") != "complete"],
        "generated_at": _now(),
    }
    ctx.write_json(DOSSIER_REL, dossier)
    ctx.write_json("mastering/research/rollup.json", dossier)
    return dossier


def load_dossier(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(DOSSIER_REL):
        return None
    doc = ctx.read_json(DOSSIER_REL)
    return doc if isinstance(doc, dict) else None


def compile_shape_evidence(ctx: RunContext, *, consumer_id: str, pass_name: str) -> dict[str, Any]:
    """Compile evidence packet from dossier + key artifacts; fail-open thin."""
    items = []
    dossier = load_dossier(ctx)
    if isinstance(dossier, dict):
        items.append(
            make_item(
                ref=DOSSIER_REL,
                kind="research_dossier",
                salience=1.0,
                inline={
                    "complete_fields": dossier.get("complete_fields"),
                    "thin_fields": dossier.get("thin_fields"),
                    "pass": pass_name,
                },
                sha256=content_hash(dossier),
            )
        )
    for rel, salience in (
        ("understanding/content_brief.json", 0.95),
        ("understanding/source_topology.json", 0.9),
        ("understanding/gap_evaluations.json", 0.85),
        ("understanding/gap_report.json", 0.8),
        ("master/selection.json", 0.75),
        ("understanding/analysis_state.json", 0.7),
        ("segments/manifest.json", 0.65),
    ):
        if ctx.artifact_exists(rel):
            try:
                doc = ctx.read_json(rel) if rel.endswith(".json") else {"path": rel}
            except Exception:
                doc = {"path": rel, "status": "unreadable"}
            items.append(
                make_item(
                    ref=rel,
                    kind="artifact",
                    salience=salience,
                    inline=doc if isinstance(doc, dict) else {"value": doc},
                    sha256=content_hash(doc),
                )
            )
    packet = compile_packet(consumer_id=consumer_id, items=items, consumer_kind="shape")
    write_packet(ctx, packet)
    return packet


# Stage entry points

def run_mastering_research_routing(ctx: RunContext) -> None:
    run_research_routing(ctx)


def run_mastering_research_waves(ctx: RunContext) -> None:
    summaries = [run_research_wave(ctx, wave) for wave in sorted(WAVE_FIELDS.keys())]
    ctx.write_json(
        "mastering/research/waves.json",
        {
            "version": 1,
            "waves": summaries,
            "field_count": sum(len(v) for v in WAVE_FIELDS.values()),
            "generated_at": _now(),
        },
    )


def run_mastering_research_rollup(ctx: RunContext) -> None:
    run_research_rollup(ctx)
