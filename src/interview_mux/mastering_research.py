"""Eight-wave mastering research runtime → research_dossier.json.

Canon: docs/cross-cutting/mastering-process.md, mastering-research-fields.md
Fail-open: missing upstream → status=skipped_or_thin field reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_context_compiler import compile_packet, content_hash, make_item, write_packet
from interview_mux.mastering_plan_loader import research_llm_enabled
from interview_mux.run_context import RunContext

RESEARCH_DIR = "mastering/research"
DOSSIER_REL = "mastering/research_dossier.json"
ROLLUP_REL = "mastering/research/rollup.json"
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

# A-01: Pass1 Shape readiness — Waves 1–3 only (W4–W8 expected thin at Shape time).
SHAPE_CORE_WAVES: frozenset[int] = frozenset({1, 2, 3})
SHAPE_CORE_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "thesis_claims",
        "source_topology",
        "g0_transcript_fidelity",
        "speaker_roles",
    }
)

# Artifact probes per field (first existing wins for thin evidence)
FIELD_PROBES: dict[str, tuple[str, ...]] = {
    "preclean_lineage": ("preclean/lineage.json",),
    "ingest_normalization": ("ingest/normalized.wav", "ingest/source_meta.json"),
    "source_acoustic_profile": ("understanding/source_acoustic_profile.json",),
    "source_readiness_band": ("run_meta.json",),
    # Canon paths (G0 / roles / spine) — legacy aliases kept as fallbacks.
    "g0_transcript_fidelity": (
        "transcript/review_queue.json",
        "transcript/full.json",
        "transcript/corrections.json",
        "transcript/review.json",
        "transcript/words.json",
    ),
    "speaker_roles": (
        "understanding/speakers.json",
        "understanding/speaker_roles.json",
    ),
    "source_topology": ("understanding/source_topology.json",),
    "speaker_volleys": (
        "understanding/interview_spine.json",
        "understanding/episode_structure.json",
    ),
    "pickup_speaker_voice": ("understanding/source_topology.json",),
    "interview_spine_windows": (
        "understanding/interview_spine.json",
        "understanding/interview_spine/windows.json",
    ),
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


def _field_catalog() -> list[dict[str, Any]]:
    return [
        {"field_id": fid, "wave": wave}
        for wave, fields in sorted(WAVE_FIELDS.items())
        for fid in fields
    ]


def _probe_presence_map(ctx: RunContext) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fid, probes in FIELD_PROBES.items():
        present: list[str] = []
        for rel in probes:
            if rel == ".stage_done":
                if ctx.path(rel).exists():
                    present.append(rel)
            elif ctx.artifact_exists(rel):
                present.append(rel)
        out[fid] = {
            "present_artifacts": present,
            "status": "present" if present else "absent",
        }
    return out


def _routing_user_payload(ctx: RunContext) -> dict[str, Any]:
    """Tape-leaning packet for research-router (fail-open if lint rejects)."""
    payload: dict[str, Any] = {
        "goal": (
            "Route mastering research fields for this source; allocate attention only — "
            "emit dispositions per field from the catalog and presence map."
        ),
        "field_catalog": _field_catalog(),
        "probe_presence_map": _probe_presence_map(ctx),
        "waves": sorted(WAVE_FIELDS.keys()),
    }
    # Prefer real tape slices when present so volley lint accepts the packet.
    for rel, key in (
        ("understanding/content_brief.json", "content_brief"),
        ("understanding/source_topology.json", "source_topology"),
        ("segments/manifest.json", "manifest"),
    ):
        if ctx.artifact_exists(rel):
            try:
                doc = ctx.read_json(rel)
            except Exception:
                continue
            if isinstance(doc, dict) and doc:
                payload[key] = doc
    return payload


def _routing_from_llm_artifacts(arts: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(arts, dict):
        return None
    candidate = arts
    nested = arts.get("routing") or arts.get("mastering_research_routing")
    if isinstance(nested, dict):
        candidate = nested
    fields = candidate.get("fields")
    if not isinstance(fields, list) or not fields:
        return None
    out = dict(candidate)
    out.setdefault("version", 1)
    if out.get("mode") not in {"off", "advisory", "authoritative"}:
        out["mode"] = "advisory"
    out["source"] = "llm"
    out.setdefault("generated_at", _now())
    return out


def _sequential_stub_routing(*, llm_failed: bool = False) -> dict[str, Any]:
    """HM-1 2A: schema-valid skip stub (mode off/advisory, fields: [])."""
    routing: dict[str, Any] = {
        "version": 1,
        "mode": "advisory" if llm_failed else "off",
        "fields": [],
        "source": "stub",
        "skipped": "llm_failed" if llm_failed else "research_llm_disabled",
        "llm_failed": bool(llm_failed),
        "waves": sorted(WAVE_FIELDS.keys()),
        "field_count": sum(len(v) for v in WAVE_FIELDS.values()),
        "generated_at": _now(),
    }
    if llm_failed:
        routing["notes"] = ["llm_failed"]
        # Explicit non-authoritative: empty fields + advisory mode (MRR-B2).
        routing["authoritative"] = False
    return routing


def run_research_routing(ctx: RunContext) -> None:
    if research_llm_enabled():
        fail_reason = "invalid_or_empty_llm_artifacts"
        try:
            from interview_mux.mastering_llm import invoke_mastering_prompt

            arts = invoke_mastering_prompt(
                ctx,
                "mastering_research_routing",
                "mastering/research-router.system.txt",
                _routing_user_payload(ctx),
                max_attempts=2,
            )
            routing = _routing_from_llm_artifacts(arts)
            if routing is not None:
                ctx.write_json(ROUTING_REL, routing)
                _heal_research_stage(ctx, "mastering_research_routing")
                return
        except Exception as exc:
            fail_reason = f"invoke_exception:{type(exc).__name__}"
            ctx.log(
                f"mastering_research_routing: LLM invoke failed — {exc}",
                level="warning",
                stage="mastering_research_routing",
                action_id="mastering_research_routing.llm_failed",
                detail={"reason": fail_reason, "error": str(exc)[:240]},
            )
        else:
            ctx.log(
                "mastering_research_routing: LLM returned unusable routing artifacts",
                level="warning",
                stage="mastering_research_routing",
                action_id="mastering_research_routing.llm_failed",
                detail={"reason": fail_reason},
            )
        # CSP-05 / MRR: write diagnostic stub but do NOT heal-done after LLM fail/hollow.
        stub = _sequential_stub_routing(llm_failed=True)
        stub["fail_reason"] = fail_reason
        ctx.write_json(ROUTING_REL, stub)
        from interview_mux.openai_primary_honesty import raise_hollow_openai_primary

        raise_hollow_openai_primary("mastering_research_routing", fail_reason)
    ctx.write_json(ROUTING_REL, _sequential_stub_routing(llm_failed=False))
    _heal_research_stage(ctx, "mastering_research_routing")


def run_research_rollup(ctx: RunContext) -> dict[str, Any]:
    """Ensure all wave fields exist, then write dossier rollup.

    Intentionally re-probes every wave via ``run_research_wave`` even when
    ``mastering_research_waves`` already wrote ``waves.json`` (MRW-B2). Seed
    order may skip or stale the waves stage; rollup is the fail-open gather
    step that refreshes field reports before Shape. Do not treat the duplicate
    walk as accidental thrash — share the same ``run_research_wave`` helper.
    """
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
        "field_reports": [
            {
                "field_id": fid,
                "wave": wave,
                "status": str((fields_out.get(fid) or {}).get("status") or "skipped_or_thin")
                if isinstance(fields_out.get(fid), dict)
                else "skipped_or_thin",
                "path": f"{RESEARCH_DIR}/{fid}.json",
            }
            for wave, fids in sorted(WAVE_FIELDS.items())
            for fid in fids
        ],
        "salience_map": {},
        "complete_fields": [k for k, v in fields_out.items() if v.get("status") == "complete"],
        "thin_fields": [k for k, v in fields_out.items() if v.get("status") != "complete"],
        "shape_core": _shape_core_status_from_fields(fields_out),
        "generated_at": _now(),
    }
    _persist_research_dossier(ctx, dossier)
    _heal_research_stage(ctx, "mastering_research_rollup")
    return dossier


def _persist_research_dossier(ctx: RunContext, dossier: dict[str, Any]) -> None:
    """Write the same dossier payload to both SSOT paths (MRRoll-B3).

    ``mastering/research_dossier.json`` and ``mastering/research/rollup.json``
    must stay byte-equivalent content; callers must not write one without the other.
    """
    ctx.write_json(DOSSIER_REL, dossier)
    ctx.write_json(ROLLUP_REL, dossier)


def load_dossier(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(DOSSIER_REL):
        return None
    doc = ctx.read_json(DOSSIER_REL)
    return doc if isinstance(doc, dict) else None


def shape_core_field_ids() -> frozenset[str]:
    """Field ids in Waves 1–3 (Pass1 Shape readiness floor)."""
    ids: set[str] = set()
    for wave in SHAPE_CORE_WAVES:
        ids.update(WAVE_FIELDS.get(wave) or ())
    return frozenset(ids)


def _shape_core_status_from_fields(fields: dict[str, Any] | None) -> dict[str, Any]:
    fields = fields if isinstance(fields, dict) else {}
    core_ids = shape_core_field_ids()
    thin: list[str] = []
    complete: list[str] = []
    for fid in sorted(core_ids):
        doc = fields.get(fid)
        status = str(doc.get("status") or "") if isinstance(doc, dict) else ""
        if status == "complete":
            complete.append(fid)
        else:
            thin.append(fid)
    missing_required: list[str] = []
    for fid in sorted(SHAPE_CORE_REQUIRED_FIELDS):
        doc = fields.get(fid)
        if not isinstance(doc, dict) or str(doc.get("status") or "") != "complete":
            missing_required.append(fid)
    majority_thin = len(thin) >= max(1, (len(core_ids) + 1) // 2)
    ready = (not majority_thin) and (not missing_required)
    return {
        "thin": thin,
        "complete": complete,
        "missing_required": missing_required,
        "majority_thin": majority_thin,
        "ready": ready,
    }


def research_shape_core_status(ctx: RunContext) -> dict[str, Any]:
    """W1–3 readiness: majority thin or any hard-required missing ⇒ not ready."""
    dossier = load_dossier(ctx)
    fields = dossier.get("fields") if isinstance(dossier, dict) else None
    return _shape_core_status_from_fields(fields if isinstance(fields, dict) else None)


def research_shape_core_thin(ctx: RunContext) -> bool:
    """True when Waves 1–3 are not ready for Shape/gap consumers (A-01)."""
    return not bool(research_shape_core_status(ctx).get("ready"))


def live_shape_core_status(ctx: RunContext) -> dict[str, Any]:
    """W1–3 readiness re-probed from the run directory as it stands right now.

    ``research_shape_core_status`` reports what the rollup saw when it ran. The
    same probes against today's disk say whether that record still describes the
    run: core evidence that landed afterwards is invisible to the dossier.
    """
    fields = {
        fid: {"field_id": fid, "status": _probe(ctx, fid)[0]} for fid in shape_core_field_ids()
    }
    return _shape_core_status_from_fields(fields)


def research_dossier_shape_core_stale(ctx: RunContext) -> bool:
    """True when the dossier records a thin shape-core the run has since outgrown.

    A stale record is what turns the A-01 refusal into a latch: the rollup has
    completed, so it never re-probes, and consumers pinned to it can never be
    released. Staleness clears the moment the rollup re-runs.
    """
    if not isinstance(load_dossier(ctx), dict):
        return False
    if not research_shape_core_thin(ctx):
        return False
    return bool(live_shape_core_status(ctx).get("ready"))


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


def _heal_research_stage(ctx: RunContext, stage: str) -> None:
    from interview_mux.stage_completion import heal_or_refuse_mark

    heal_or_refuse_mark(ctx, stage, force=True)


# Stage entry points

def run_mastering_research_routing(ctx: RunContext) -> None:
    run_research_routing(ctx)


def run_mastering_research_waves(ctx: RunContext) -> None:
    """Probe WAVE_FIELDS and persist ``waves.json``.

    Does not read ``mastering/research/routing.json`` — contract hard:[]
    (MRW-B1; probes are soft-presence only). ``run_research_rollup`` will
    re-run the same ``run_research_wave`` helpers later — intentional dual-run
    (MRW-B2), not a bug; waves stage still owns the seed-order primary for
    early Shape thinness.
    """
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
    _heal_research_stage(ctx, "mastering_research_waves")


def run_mastering_research_rollup(ctx: RunContext) -> None:
    run_research_rollup(ctx)
