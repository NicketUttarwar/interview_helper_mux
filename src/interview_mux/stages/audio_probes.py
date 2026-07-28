"""Pipeline stages for Local Audio Probe Platform + vernacular sanitize."""

from __future__ import annotations

from typing import Any

from interview_mux.audio_probe_orchestrator import build_audio_probe_artifacts
from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.vernacular_sanitize import sanitize_manifest_with_zones


def run_audio_probe_build(ctx: RunContext) -> None:
    """After STT: speaker flows → probes → golden facts → protected zones."""
    ctx.artifact_exists_required(
        "transcript/full.json",
        stage="audio_probe_build",
        label="Transcript from transcribe",
    )
    transcript = ctx.read_json("transcript/full.json")
    if not isinstance(transcript, dict):
        raise RuntimeError("transcript/full.json must be an object")

    with ctx.logged_step("audio_probe_build", "Run audio probe platform"):
        arts = build_audio_probe_artifacts(transcript)
        ctx.write_json("analysis/run_golden_facts.json", arts["golden_facts"])
        ctx.write_json("transcript/protected_zones.json", arts["protected_zones"])
        ctx.write_json("transcript/speaker_flows.json", arts["speaker_flows"])
        ctx.write_json("vernacular/probe_report.json", arts["probe_report"])
        ctx.write_json(
            "vernacular/audio_tags_by_flow.json",
            {"version": 1, "by_flow": arts.get("audio_tags_by_flow") or {}},
        )
        ctx.log(
            f"Audio probes: flows={arts['golden_facts'].get('meta', {}).get('flows')} "
            f"vernacular={arts['golden_facts'].get('run', {}).get('has_in_flow_vernacular')}",
            stage="audio_probe_build",
            action_id="audio_probes.build",
            detail={
                "event": "audio_probe_build",
                "vernacular": arts["golden_facts"].get("run", {}).get("has_in_flow_vernacular"),
                "zones": len((arts["protected_zones"].get("zones") or [])),
            },
        )


def run_vernacular_segment_sanitize(ctx: RunContext) -> None:
    """N-way split segments intersecting protected zones; refresh must_keep ids."""
    if not ctx.artifact_exists("transcript/protected_zones.json"):
        ctx.log(
            "vernacular_segment_sanitize: no protected_zones; skip",
            stage="vernacular_segment_sanitize",
            action_id="vernacular.sanitize.skip",
        )
        return
    if not ctx.artifact_exists("segments/manifest.json"):
        ctx.log(
            "vernacular_segment_sanitize: no manifest yet; skip",
            stage="vernacular_segment_sanitize",
            action_id="vernacular.sanitize.skip",
        )
        return

    zones = ctx.read_json("transcript/protected_zones.json")
    manifest = ctx.read_json("segments/manifest.json")
    if not isinstance(zones, dict) or not isinstance(manifest, dict):
        return
    if not (zones.get("zones") or []):
        ctx.write_json(
            "vernacular/resplit_report.json",
            {"version": 1, "rows": [], "must_keep_segment_ids": [], "skipped": "no_zones"},
        )
        return

    cfg = dict((merged_config().get("audio_probes") or {}).get("sanitize") or {})
    min_child = int(cfg.get("min_child_ms") or 800)

    with ctx.logged_step("vernacular_segment_sanitize", "N-way vernacular resplit"):
        result = sanitize_manifest_with_zones(manifest, zones, min_child_ms=min_child)
        ctx.write_json("segments/manifest.json", result["manifest"])
        ctx.write_json("vernacular/resplit_report.json", result["resplit_report"])

        # Refresh golden facts must_keep list
        if ctx.artifact_exists("analysis/run_golden_facts.json"):
            facts = ctx.read_json("analysis/run_golden_facts.json")
            if isinstance(facts, dict):
                run = dict(facts.get("run") or {})
                run["vernacular_must_keep_segment_ids"] = list(result["must_keep_segment_ids"])
                facts["run"] = run
                # also stamp onto narrative-friendly sidecar
                ctx.write_json("analysis/run_golden_facts.json", facts)
                ctx.write_json(
                    "analysis/vernacular_must_keep.json",
                    {
                        "version": 1,
                        "must_keep_segment_ids": result["must_keep_segment_ids"],
                        "enforcement_mode": run.get("enforcement_mode") or "shadow",
                    },
                )

        # Attach zone segment_ids by overlap
        segs = result["manifest"].get("segments") or []
        updated_zones = []
        for z in zones.get("zones") or []:
            if not isinstance(z, dict):
                continue
            zz = dict(z)
            z0, z1 = int(zz.get("start_ms") or 0), int(zz.get("end_ms") or 0)
            ids = []
            for s in segs:
                if not isinstance(s, dict):
                    continue
                if (s.get("audio_tags") or {}).get("is_special"):
                    try:
                        a, b = int(s.get("start_ms") or 0), int(s.get("end_ms") or 0)
                    except (TypeError, ValueError):
                        continue
                    if min(b, z1) - max(a, z0) > 0:
                        ids.append(str(s.get("segment_id")))
            zz["segment_ids"] = ids
            updated_zones.append(zz)
        zones_out = dict(zones)
        zones_out["zones"] = updated_zones
        ctx.write_json("transcript/protected_zones.json", zones_out)

        ctx.log(
            f"Vernacular sanitize: splits={len(result['resplit_report'].get('rows') or [])} "
            f"must_keep={len(result['must_keep_segment_ids'])}",
            stage="vernacular_segment_sanitize",
            action_id="vernacular.sanitize",
            detail={
                "event": "vernacular_segment_sanitize",
                "must_keep": result["must_keep_segment_ids"][:20],
            },
        )


def vernacular_must_keep_ids(ctx: RunContext) -> set[str]:
    """Segment ids that must not be auto-packed away."""
    ids: set[str] = set()
    if ctx.artifact_exists("analysis/vernacular_must_keep.json"):
        doc = ctx.read_json("analysis/vernacular_must_keep.json")
        if isinstance(doc, dict):
            for sid in doc.get("must_keep_segment_ids") or []:
                if sid:
                    ids.add(str(sid))
    if ctx.artifact_exists("analysis/run_golden_facts.json"):
        doc = ctx.read_json("analysis/run_golden_facts.json")
        if isinstance(doc, dict):
            mode = str((doc.get("run") or {}).get("enforcement_mode") or "shadow")
            if mode == "authoritative":
                for sid in (doc.get("run") or {}).get("vernacular_must_keep_segment_ids") or []:
                    if sid:
                        ids.add(str(sid))
            # Even in shadow, expose ids for soft consumers; auto_pack only hard-blocks authoritative
            elif mode == "shadow":
                pass
    return ids


def authoritative_must_keep_ids(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("analysis/run_golden_facts.json"):
        return set()
    doc = ctx.read_json("analysis/run_golden_facts.json")
    if not isinstance(doc, dict):
        return set()
    if str((doc.get("run") or {}).get("enforcement_mode") or "shadow") != "authoritative":
        return set()
    return {
        str(sid)
        for sid in (doc.get("run") or {}).get("vernacular_must_keep_segment_ids") or []
        if sid
    }
