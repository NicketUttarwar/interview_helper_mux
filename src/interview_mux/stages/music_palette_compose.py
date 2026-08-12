"""LLM stage: place fixed music palette assets into the master cue timeline."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.music_motif import (
    analysis_palette_counts,
    harden_palette_inventory,
    palette_kind_for_role,
)
from interview_mux.operator_trace import logged_step
from interview_mux.production_profile import prompt_variant
from interview_mux.run_context import RunContext
from interview_mux.source_topology import attach_adaptation_to_payload
from interview_mux.stage_input_helpers import attach_disfluency_context
from interview_mux.stages.analysis_stage import run_flow_llm_stage

_SOUND_DESIGN_PLAN_REL = "understanding/sound_design_plan.json"
_COMPOSE_REL = "sound_design/music_palette_compose.json"


def _optional_json(ctx: RunContext, rel_path: str) -> dict[str, Any]:
    return ctx.read_json(rel_path) if ctx.artifact_exists(rel_path) else {}


def _assets_by_id(sdp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for a in sdp.get("assets") or []:
        if isinstance(a, dict) and a.get("asset_id"):
            out[str(a["asset_id"])] = a
    return out


def _default_cues(
    sdp: dict[str, Any],
    *,
    ordered: list[str],
    chapters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deterministic compose when LLM fails or returns empty cues."""
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict)]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for a in assets:
        kind = str(a.get("palette_kind") or "") or palette_kind_for_role(
            str(a.get("role") or ""), energy=str(a.get("energy") or "") or None
        )
        by_kind.setdefault(kind, []).append(a)

    cues: list[dict[str, Any]] = []
    first = ordered[0] if ordered else None
    last = ordered[-1] if ordered else None

    open_bed = None
    for a in by_kind.get("full_bed") or []:
        if str(a.get("placement_hint") or "") == "close":
            continue
        open_bed = a
        break
    if open_bed is None:
        open_bed = (by_kind.get("motif") or [None])[0]
    if open_bed and first:
        cues.append(
            {
                "cue_id": "compose_open_bed",
                "asset_id": str(open_bed["asset_id"]),
                "role": str(open_bed.get("role") or "theme_cold_open"),
                "placement": "before_segment",
                "before_segment_id": first,
                "level_db": -10,
            }
        )

    motif = (by_kind.get("motif") or [None])[0]
    if motif and first and (not open_bed or str(motif.get("asset_id")) != str(open_bed.get("asset_id"))):
        cues.append(
            {
                "cue_id": "compose_motif_presence",
                "asset_id": str(motif["asset_id"]),
                "role": str(motif.get("role") or "theme_cold_open"),
                "placement": "before_segment",
                "before_segment_id": first,
                "level_db": -12,
            }
        )

    unders = (by_kind.get("underscore_loop") or [None])[0]
    optional = (by_kind.get("optional_loop") or [None])[0]
    bed_targets = ordered[:: max(1, len(ordered) // 4)][:4] if ordered else []
    if not bed_targets and first:
        bed_targets = [first]
    for i, sid in enumerate(bed_targets):
        use_opt = bool(optional) and i % 2 == 1
        bed = optional if use_opt else unders
        if not bed:
            continue
        cues.append(
            {
                "cue_id": f"compose_bed_{i+1:02d}",
                "asset_id": str(bed["asset_id"]),
                "role": str(bed.get("role") or "theme_underscore"),
                "placement": "under_segment",
                "under_segment_id": sid,
                "segment_id": sid,
                "level_db": -22,
                "crossfade_ms": 1500,
            }
        )

    stingers = by_kind.get("stinger") or []
    hinge_ids: list[str] = []
    for ch in chapters:
        segs = [str(s) for s in (ch.get("segment_ids") or ch.get("segments") or []) if s]
        if segs:
            hinge_ids.append(segs[-1])
    if not hinge_ids and len(ordered) >= 2:
        hinge_ids = ordered[len(ordered) // 3 :: max(1, len(ordered) // 3)][: len(stingers) or 2]
    for i, sid in enumerate(hinge_ids[: max(1, len(stingers))]):
        st = stingers[i % len(stingers)] if stingers else None
        if not st:
            break
        cues.append(
            {
                "cue_id": f"compose_stinger_{i+1:02d}",
                "asset_id": str(st["asset_id"]),
                "role": str(st.get("role") or "theme_emphasis"),
                "placement": "after_segment",
                "after_segment_id": sid,
                "level_db": -14,
            }
        )

    close_bed = None
    for a in by_kind.get("full_bed") or []:
        if str(a.get("placement_hint") or "") == "close" or str(a.get("role")) == "theme_outro":
            close_bed = a
            break
    if close_bed and last:
        cues.append(
            {
                "cue_id": "compose_close_bed",
                "asset_id": str(close_bed["asset_id"]),
                "role": str(close_bed.get("role") or "theme_outro"),
                "placement": "after_segment",
                "after_segment_id": last,
                "level_db": -10,
            }
        )
    return cues


def _apply_cues(sdp: dict[str, Any], cues: list[dict[str, Any]]) -> dict[str, Any]:
    """Rewrite podcast cues to reuse palette asset_ids only."""
    out = dict(sdp)
    known = _assets_by_id(out)
    cleaned: list[dict[str, Any]] = []
    for i, cue in enumerate(cues):
        if not isinstance(cue, dict):
            continue
        aid = str(cue.get("asset_id") or "")
        if not aid or aid not in known:
            continue
        asset = known[aid]
        row = dict(cue)
        row["asset_id"] = aid
        row.setdefault("role", asset.get("role") or "theme_underscore")
        row.setdefault("cue_id", f"compose_cue_{i+1:02d}")
        if str(row.get("placement") or "") == "under_segment":
            row["crossfade_ms"] = max(1500, int(row.get("crossfade_ms") or 0))
        cleaned.append(row)
    flow = dict(out.get("flow_plans") or {}) if isinstance(out.get("flow_plans"), dict) else {}
    podcast = dict(flow.get("podcast") or {}) if isinstance(flow.get("podcast"), dict) else {}
    podcast["cues"] = cleaned
    podcast["compose_deferred"] = False
    podcast["composed_by"] = "music_palette_compose"
    flow["podcast"] = podcast
    out["flow_plans"] = flow
    return out


def run_music_palette_compose(ctx: RunContext) -> None:
    """Place existing palette WAVs into the master shape — no new stems."""

    def build_input(c: RunContext) -> dict[str, Any]:
        sdp = _optional_json(c, _SOUND_DESIGN_PLAN_REL)
        brief = _optional_json(c, "understanding/music_brief.json")
        counts = analysis_palette_counts(c)
        # Ensure inventory is exact before compose.
        if isinstance(sdp, dict) and brief:
            sdp = harden_palette_inventory(sdp, brief, counts=counts)
        assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict)]
        palette = [
            {
                "asset_id": a.get("asset_id"),
                "role": a.get("role"),
                "palette_kind": a.get("palette_kind")
                or palette_kind_for_role(
                    str(a.get("role") or ""), energy=str(a.get("energy") or "") or None
                ),
                "energy": a.get("energy"),
                "duration_seconds": a.get("duration_seconds"),
                "description": str(a.get("description") or "")[:160],
                "placement_hint": a.get("placement_hint"),
            }
            for a in assets
        ]
        selection = _optional_json(c, "master/selection.json")
        ordered = [str(x) for x in (selection.get("ordered_segment_ids") or []) if x]
        narrative = _optional_json(c, "master/narrative_plan.json")
        delight = _optional_json(c, "mastering/listen_delight_audit.json")
        policy = _optional_json(c, "understanding/soundscape_policy.json")
        payload: dict[str, Any] = {
            "palette_counts": counts,
            "palette_assets": palette,
            "ordered_segment_ids": ordered[:48],
            "narrative_plan": {
                "arc_summary": str(narrative.get("arc_summary") or "")[:300],
                "chapters": [
                    {
                        "chapter_id": ch.get("chapter_id") or ch.get("id"),
                        "title": ch.get("title") or ch.get("label"),
                        "segment_ids": (ch.get("segment_ids") or ch.get("segments") or [])[:12],
                    }
                    for ch in (narrative.get("chapters") or [])
                    if isinstance(ch, dict)
                ][:12],
            },
            "edl_landmarks": _compact_edl(c),
            "assembly_preview_meta": _optional_json(c, "master/assembly_preview_meta.json"),
            "cue_slots": (policy.get("cue_slots") or [])[:24] if isinstance(policy, dict) else [],
            "listen_delight_hints": {
                "score": delight.get("score") or delight.get("overall_score"),
                "notes": str(delight.get("summary") or delight.get("notes") or "")[:400],
                "issues": (delight.get("issues") or delight.get("findings") or [])[:8],
            },
            "delivery_brief": _optional_json(c, "understanding/delivery_brief.json"),
            "mastering_plan": _optional_json(c, "mastering/mastering_plan.json"),
            "constraints": {
                "reuse_asset_ids_only": True,
                "no_new_wavs": True,
                "alternate_underscore_and_optional_loop": True,
                "full_beds_at_open_and_optional_close": True,
                "stingers_at_chapter_hinges": True,
                "motif_is_dna_and_open_presence": True,
                "bed_coverage_via_looping": True,
            },
        }
        from interview_mux.delivery_brief import attach_delivery_brief_to_payload

        return attach_disfluency_context(
            attach_delivery_brief_to_payload(c, attach_adaptation_to_payload(c, payload)),
            c,
        )

    def persist(c: RunContext, artifacts: dict) -> None:
        sdp = (
            c.read_json(_SOUND_DESIGN_PLAN_REL)
            if c.artifact_exists(_SOUND_DESIGN_PLAN_REL)
            else {}
        )
        if not isinstance(sdp, dict):
            sdp = {}
        brief = (
            c.read_json("understanding/music_brief.json")
            if c.artifact_exists("understanding/music_brief.json")
            else {}
        )
        counts = analysis_palette_counts(c)
        if isinstance(brief, dict):
            sdp = harden_palette_inventory(sdp, brief, counts=counts)

        selection = (
            c.read_json("master/selection.json")
            if c.artifact_exists("master/selection.json")
            else {}
        )
        ordered = [
            str(x)
            for x in ((selection.get("ordered_segment_ids") or []) if isinstance(selection, dict) else [])
            if x
        ]
        narrative = (
            c.read_json("master/narrative_plan.json")
            if c.artifact_exists("master/narrative_plan.json")
            else {}
        )
        chapters = [
            ch
            for ch in ((narrative.get("chapters") or []) if isinstance(narrative, dict) else [])
            if isinstance(ch, dict)
        ]

        raw_cues = artifacts.get("cues")
        if not isinstance(raw_cues, list):
            raw_cues = ((artifacts.get("flow_plans") or {}) if isinstance(artifacts.get("flow_plans"), dict) else {}).get(
                "podcast", {}
            )
            if isinstance(raw_cues, dict):
                raw_cues = raw_cues.get("cues")
        if not isinstance(raw_cues, list) or not raw_cues:
            raw_cues = _default_cues(sdp, ordered=ordered, chapters=chapters)

        sdp = _apply_cues(sdp, [c for c in raw_cues if isinstance(c, dict)])
        # If LLM returned only invalid asset_ids, fall back.
        podcast = ((sdp.get("flow_plans") or {}).get("podcast") or {}) if isinstance(sdp.get("flow_plans"), dict) else {}
        if not (podcast.get("cues") or []):
            sdp = _apply_cues(
                sdp, _default_cues(sdp, ordered=ordered, chapters=chapters)
            )

        write_validated_artifact(
            c, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="sound_design_plan"
        )
        compose_out = {
            "version": 1,
            "palette_counts": counts,
            "cue_count": len(
                (((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
            ),
            "asset_ids_used": sorted(
                {
                    str(cu.get("asset_id"))
                    for cu in (((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
                    if isinstance(cu, dict) and cu.get("asset_id")
                }
            ),
            "notes": artifacts.get("notes") or artifacts.get("rationale") or "",
        }
        c.write_json(_COMPOSE_REL, compose_out)
        c.log(
            f"music_palette_compose: {compose_out['cue_count']} cues using "
            f"{len(compose_out['asset_ids_used'])} palette assets",
            level="info",
            stage="music_palette_compose",
        )

    with logged_step("music_palette_compose/llm_stage", ctx=ctx, stage="music_palette_compose"):
        run_flow_llm_stage(
            ctx,
            "music_palette_compose",
            prompt_variant("sound_design/music-palette-compose.system.txt", ctx),
            build_input,
            persist,
        )


def _compact_edl(ctx: RunContext) -> dict[str, Any]:
    edl = _optional_json(ctx, "master/edl.json")
    events = [e for e in (edl.get("events") or edl.get("items") or []) if isinstance(e, dict)]
    landmarks: list[dict[str, Any]] = []
    for e in events[:40]:
        landmarks.append(
            {
                "segment_id": e.get("segment_id") or e.get("id"),
                "kind": e.get("kind") or e.get("type") or e.get("event_type"),
                "start_ms": e.get("start_ms") or e.get("t0_ms"),
                "end_ms": e.get("end_ms") or e.get("t1_ms"),
            }
        )
    return {"event_count": len(events), "landmarks": landmarks}
