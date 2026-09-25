"""LLM stage: place fixed music palette assets into the master cue timeline."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.config import merged_config
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
_BED_SLOT_ROLES = frozenset({"theme_underscore", "underscore_loop", "optional_loop", "ambient_bed"})
_SDP_ANCHOR_KEYS = (
    "segment_id",
    "before_segment_id",
    "after_segment_id",
    "under_segment_id",
)


def _sdp_has_off_selection_anchors(ctx: RunContext, selection_set: set[str]) -> bool:
    """True when on-disk SDP still has cue/palette anchors outside ranked selection."""
    if not selection_set or not ctx.artifact_exists(_SOUND_DESIGN_PLAN_REL):
        return False
    try:
        doc = ctx.read_json(_SOUND_DESIGN_PLAN_REL)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    for pal in doc.get("palettes") or []:
        if not isinstance(pal, dict):
            continue
        for sid in pal.get("segment_ids") or []:
            if str(sid) and str(sid) not in selection_set:
                return True
    flow = doc.get("flow_plans") if isinstance(doc.get("flow_plans"), dict) else {}
    podcast = flow.get("podcast") if isinstance(flow.get("podcast"), dict) else {}
    for cue in podcast.get("cues") or []:
        if not isinstance(cue, dict):
            continue
        for key in _SDP_ANCHOR_KEYS:
            sid = str(cue.get(key) or "")
            if sid and sid not in selection_set:
                return True
    return False


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
    plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic compose when LLM fails or returns empty cues."""
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict)]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for a in assets:
        kind = str(a.get("palette_kind") or "") or palette_kind_for_role(
            str(a.get("role") or ""), energy=str(a.get("energy") or "") or None
        )
        by_kind.setdefault(kind, []).append(a)

    if isinstance(plan, dict) and (plan.get("sonic_opportunities") or plan.get("sonic_scenes")):
        from interview_mux.air_script import cues_from_sonic_plan

        hunted = cues_from_sonic_plan(plan, assets_by_kind=by_kind)
        if hunted:
            return hunted

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
                "level_db": -26,
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

    from interview_mux.music_lane import pick_theme_outro_asset

    close_bed = pick_theme_outro_asset(by_kind.get("full_bed") or []) or pick_theme_outro_asset(
        assets
    )
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


def _arrangement_config() -> dict[str, int]:
    """Read underbed scene controls from the canonical mix config block."""
    cfg = merged_config()
    mix = cfg.get("mix") if isinstance(cfg.get("mix"), dict) else {}
    arrangement = (
        mix.get("underbed_arrangement")
        if isinstance(mix.get("underbed_arrangement"), dict)
        else {}
    )
    try:
        max_scene_segments = max(1, int(arrangement.get("max_scene_segments", 4)))
    except (TypeError, ValueError):
        max_scene_segments = 4
    try:
        dry_break_chapters = max(0, int(arrangement.get("dry_break_chapters", 1)))
    except (TypeError, ValueError):
        dry_break_chapters = 1
    try:
        scene_crossfade_ms = max(1500, int(arrangement.get("scene_crossfade_ms", 1800)))
    except (TypeError, ValueError):
        scene_crossfade_ms = 1800
    return {
        "max_scene_segments": max_scene_segments,
        "dry_break_chapters": dry_break_chapters,
        "scene_crossfade_ms": scene_crossfade_ms,
    }


def _is_bed_slot(slot: dict[str, Any]) -> bool:
    if str(slot.get("placement") or "") not in {"", "under_segment"}:
        return False
    allowed = {str(role) for role in (slot.get("allowed_roles") or [])}
    return bool(allowed & _BED_SLOT_ROLES)


def _contiguous_runs(segment_ids: list[str], ordered_index: dict[str, int]) -> list[list[str]]:
    runs: list[list[str]] = []
    for sid in segment_ids:
        if not runs or ordered_index[sid] != ordered_index[runs[-1][-1]] + 1:
            runs.append([sid])
        else:
            runs[-1].append(sid)
    return runs


def _normalize_arrangement(
    sdp: dict[str, Any],
    cues: list[dict[str, Any]],
    *,
    ordered: list[str],
    chapters: list[dict[str, Any]],
    policy: dict[str, Any] | None = None,
    overlap_high: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Deterministically replace only bed cues with slot-safe contiguous scenes."""
    assets = _assets_by_id(sdp)
    loop_assets: dict[str, dict[str, Any]] = {}
    stingers: list[dict[str, Any]] = []
    for asset in assets.values():
        kind = str(asset.get("palette_kind") or "") or palette_kind_for_role(
            str(asset.get("role") or ""), energy=str(asset.get("energy") or "") or None
        )
        if kind in {"underscore_loop", "optional_loop"} and kind not in loop_assets:
            loop_assets[kind] = asset
        elif kind == "stinger":
            stingers.append(asset)

    non_beds: list[dict[str, Any]] = []
    existing_beds: dict[str, dict[str, Any]] = {}
    for cue in cues:
        aid = str(cue.get("asset_id") or "")
        asset = assets.get(aid) or {}
        kind = str(asset.get("palette_kind") or "") or palette_kind_for_role(
            str(asset.get("role") or cue.get("role") or ""),
            energy=str(asset.get("energy") or "") or None,
        )
        is_bed = str(cue.get("placement") or "") == "under_segment" and kind in {
            "underscore_loop",
            "optional_loop",
        }
        if is_bed:
            sid = str(cue.get("under_segment_id") or cue.get("segment_id") or "")
            if sid:
                existing_beds.setdefault(sid, cue)
        else:
            non_beds.append(dict(cue))

    pol = policy if isinstance(policy, dict) else {}
    from interview_mux.soundscape_policy import beds_hard_zero, musical_invent_blocked

    hard_zero_bed = beds_hard_zero(pol) or musical_invent_blocked(pol)
    primary = loop_assets.get("underscore_loop")
    if hard_zero_bed or not primary or not ordered:
        return non_beds

    slots = [slot for slot in (pol.get("cue_slots") or []) if isinstance(slot, dict)]
    if pol and not slots:
        return non_beds
    slot_by_sid = {
        str(slot.get("segment_id")): slot
        for slot in slots
        if slot.get("segment_id") and _is_bed_slot(slot)
    }
    allowed_ids = set(slot_by_sid) if pol else set(ordered)
    allowed_ids -= set(overlap_high or set())
    ordered_index = {sid: i for i, sid in enumerate(ordered)}

    chapter_rows: list[tuple[int, list[str]]] = []
    for chapter_index, chapter in enumerate(chapters):
        raw_ids = chapter.get("segment_ids") or chapter.get("segments") or []
        chapter_ids = {
            str(sid) for sid in raw_ids if sid and str(sid) in ordered_index
        }
        eligible = [
            sid for sid in ordered if sid in chapter_ids and sid in allowed_ids
        ]
        if eligible:
            chapter_rows.append((chapter_index, eligible))
    if not chapter_rows:
        fallback = [sid for sid in ordered if sid in allowed_ids]
        if fallback:
            chapter_rows = [(0, fallback)]

    optional = loop_assets.get("optional_loop")
    arrangement = _arrangement_config()
    max_scene_segments = arrangement["max_scene_segments"]
    dry_break_chapters = arrangement["dry_break_chapters"]
    scene_crossfade_ms = arrangement["scene_crossfade_ms"]
    scene_rows: list[tuple[int, list[str]]] = []
    next_bed_chapter = 0
    for chapter_index, eligible in chapter_rows:
        if not optional and chapter_index < next_bed_chapter:
            continue
        runs = _contiguous_runs(eligible, ordered_index)
        if optional:
            for run in runs:
                scene_rows.extend(
                    (chapter_index, run[start : start + max_scene_segments])
                    for start in range(0, len(run), max_scene_segments)
                )
        else:
            scene_rows.extend(
                (chapter_index, run[:max_scene_segments])
                for run in runs
                if run[:max_scene_segments]
            )
            next_bed_chapter = chapter_index + dry_break_chapters + 1

    from interview_mux.creative_delivery import audible_bed_level_db, clamp_bed_level_db

    bed_cues: list[dict[str, Any]] = []
    for scene_index, (_, scene) in enumerate(scene_rows):
        asset = optional if optional and scene_index % 2 else primary
        assert asset is not None
        for segment_index, sid in enumerate(scene):
            prior = existing_beds.get(sid) or {}
            slot = slot_by_sid.get(sid) or {}

            level = prior.get("level_db")
            if level is None:
                level = slot.get("max_level_db")
            if level is None:
                level = audible_bed_level_db()
            try:
                level = clamp_bed_level_db(float(level))
            except (TypeError, ValueError):
                level = audible_bed_level_db()
            try:
                crossfade = max(
                    scene_crossfade_ms,
                    int(prior.get("crossfade_ms") or scene_crossfade_ms),
                )
            except (TypeError, ValueError):
                crossfade = scene_crossfade_ms
            bed_cues.append(
                {
                    "cue_id": f"arrange_scene_{scene_index+1:02d}_{segment_index+1:02d}",
                    "asset_id": str(asset["asset_id"]),
                    "role": str(asset.get("role") or "theme_underscore"),
                    "placement": "under_segment",
                    "under_segment_id": sid,
                    "segment_id": sid,
                    "level_db": level,
                    "crossfade_ms": crossfade,
                }
            )

    # With one loop, musical hinges help reset the ear between bedded chapters.
    if not optional and stingers and chapters:
        density = pol.get("density") if isinstance(pol.get("density"), dict) else {}
        max_punctuators = density.get("max_punctuators")
        budget = len(stingers)
        if max_punctuators is not None:
            budget = min(budget, max(0, int(max_punctuators or 0)))
        existing_stingers = [
            cue
            for cue in non_beds
            if palette_kind_for_role(
                str((assets.get(str(cue.get("asset_id") or "")) or {}).get("role") or cue.get("role") or "")
            )
            == "stinger"
        ]
        remaining = max(0, budget - len(existing_stingers))
        occupied = {str(cue.get("after_segment_id") or "") for cue in existing_stingers}
        for chapter_index, chapter in enumerate(chapters[:-1]):
            if remaining <= 0:
                break
            ids = [
                str(sid)
                for sid in (chapter.get("segment_ids") or chapter.get("segments") or [])
                if sid and str(sid) in ordered_index
            ]
            if not ids:
                continue
            hinge = max(ids, key=ordered_index.__getitem__)
            if hinge in occupied:
                continue
            asset = stingers[(budget - remaining) % len(stingers)]
            non_beds.append(
                {
                    "cue_id": f"arrange_hinge_{chapter_index+1:02d}",
                    "asset_id": str(asset["asset_id"]),
                    "role": str(asset.get("role") or "theme_emphasis"),
                    "placement": "after_segment",
                    "after_segment_id": hinge,
                    "level_db": -14,
                }
            )
            occupied.add(hinge)
            remaining -= 1
    return non_beds + bed_cues


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


def _inject_bed_cue_slots_for_composed_cues(ctx: RunContext, sdp: dict[str, Any]) -> list[str]:
    """Align soundscape cue_slots with seated under_segment beds (compose-owned)."""
    from interview_mux.soundscape_policy import (
        admit_inject_cue_slots,
        load_policy,
        soundscape_enabled,
    )

    if not soundscape_enabled():
        return []
    flow = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    podcast = flow.get("podcast") if isinstance(flow.get("podcast"), dict) else {}
    cues = [c for c in (podcast.get("cues") or []) if isinstance(c, dict)]
    bed_segs: list[str] = []
    seen: set[str] = set()
    for cue in cues:
        if str(cue.get("placement") or "") != "under_segment":
            continue
        sid = str(
            cue.get("under_segment_id") or cue.get("segment_id") or ""
        ).strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        bed_segs.append(sid)
    if not bed_segs:
        return []
    try:
        policy = load_policy(ctx) or {}
        admit_inject_cue_slots(
            ctx,
            policy,
            segment_ids=bed_segs,
            reason="theme_underscore_music_palette_compose",
            persist=True,
            rescore=False,
            writer_stage="music_palette_compose",
        )
        return bed_segs
    except Exception as exc:
        ctx.log(
            f"music_palette_compose: bed cue_slot inject skipped: {exc}",
            level="warning",
            stage="music_palette_compose",
        )
        return []


def run_music_palette_compose(ctx: RunContext) -> None:
    """Place existing palette WAVs into the master shape — no new stems."""

    # MPC-B2: contract hard SDP from sound_design_plan — refuse before LLM.
    if not ctx.artifact_exists(_SOUND_DESIGN_PLAN_REL):
        raise RuntimeError("sound_design_plan required before music_palette_compose")

    def build_input(c: RunContext) -> dict[str, Any]:
        if not c.artifact_exists(_SOUND_DESIGN_PLAN_REL):
            raise RuntimeError("sound_design_plan required before music_palette_compose")
        sdp = c.read_json(_SOUND_DESIGN_PLAN_REL)
        if not isinstance(sdp, dict):
            raise RuntimeError("sound_design_plan required before music_palette_compose")
        brief = _optional_json(c, "understanding/music_brief.json")
        counts = analysis_palette_counts(c)
        # Ensure inventory is exact before compose.
        if brief:
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

        plan = (
            c.read_json("mastering/mastering_plan.json")
            if c.artifact_exists("mastering/mastering_plan.json")
            else {}
        )
        plan = plan if isinstance(plan, dict) else {}

        raw_cues = artifacts.get("cues")
        if not isinstance(raw_cues, list):
            raw_cues = ((artifacts.get("flow_plans") or {}) if isinstance(artifacts.get("flow_plans"), dict) else {}).get(
                "podcast", {}
            )
            if isinstance(raw_cues, dict):
                raw_cues = raw_cues.get("cues")
        if not isinstance(raw_cues, list) or not raw_cues:
            raw_cues = _default_cues(sdp, ordered=ordered, chapters=chapters, plan=plan)
        elif plan.get("sonic_opportunities"):
            from interview_mux.air_script import unused_required_opportunities

            if unused_required_opportunities(plan, [c for c in raw_cues if isinstance(c, dict)]):
                hunted = _default_cues(sdp, ordered=ordered, chapters=chapters, plan=plan)
                if hunted:
                    raw_cues = hunted

        policy = (
            c.read_json("understanding/soundscape_policy.json")
            if c.artifact_exists("understanding/soundscape_policy.json")
            else {}
        )
        sonic = (
            c.read_json("understanding/sonic_context.json")
            if c.artifact_exists("understanding/sonic_context.json")
            else {}
        )
        flags = sonic.get("segment_flags") if isinstance(sonic, dict) and isinstance(sonic.get("segment_flags"), dict) else {}
        overlap_high = {str(sid) for sid in (flags.get("overlap_high") or [])}
        normalized = _normalize_arrangement(
            sdp,
            [cue for cue in raw_cues if isinstance(cue, dict)],
            ordered=ordered,
            chapters=chapters,
            policy=policy if isinstance(policy, dict) else {},
            overlap_high=overlap_high,
        )
        sdp = _apply_cues(sdp, normalized)
        # If LLM returned only invalid asset_ids, fall back.
        podcast = ((sdp.get("flow_plans") or {}).get("podcast") or {}) if isinstance(sdp.get("flow_plans"), dict) else {}
        if not (podcast.get("cues") or []):
            fallback = _normalize_arrangement(
                sdp,
                _default_cues(sdp, ordered=ordered, chapters=chapters, plan=plan),
                ordered=ordered,
                chapters=chapters,
                policy=policy if isinstance(policy, dict) else {},
                overlap_high=overlap_high,
            )
            sdp = _apply_cues(
                sdp, fallback
            )

        # S1-C: compose owns bed cue_slot inject (honest writer_stage).
        injected = _inject_bed_cue_slots_for_composed_cues(c, sdp)
        if injected:
            c.log(
                f"music_palette_compose: injected {len(injected)} bed cue_slot(s)",
                level="info",
                stage="music_palette_compose",
                detail={"segment_ids": injected[:12]},
            )

        # R2-A: compose is the sole density/slots authority after deferred clears.
        # One deterministic repair pass, then refuse — no heal↔validate thrash.
        from interview_mux.artifact_repairs import repair_sound_design_plan
        from interview_mux.sdp_cross_validate import validate_post_sound_plan

        sdp, repair_notes = repair_sound_design_plan(c, sdp)
        if repair_notes:
            c.log(
                f"music_palette_compose: density repair applied ({len(repair_notes)} notes)",
                level="info",
                stage="music_palette_compose",
                detail={"actions": [n.get("action") for n in repair_notes[:12] if isinstance(n, dict)]},
            )
        # Ensure compose_deferred is cleared before post-validate (repair may not).
        flow_chk = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
        pod_chk = flow_chk.get("podcast") if isinstance(flow_chk.get("podcast"), dict) else {}
        if isinstance(pod_chk, dict):
            pod_chk = dict(pod_chk)
            pod_chk["compose_deferred"] = False
            pod_chk["composed_by"] = "music_palette_compose"
            flow_chk = dict(flow_chk)
            flow_chk["podcast"] = pod_chk
            sdp["flow_plans"] = flow_chk

        # Validate in-memory before commit — never poison disk with a refused plan.
        density_errs = validate_post_sound_plan(c, doc=sdp)
        if density_errs:
            aspirational = False
            try:
                from interview_mux.floor_progress import (
                    record_floor_advisory,
                    soundscape_density_aspirational,
                )

                aspirational = soundscape_density_aspirational(c)
                if aspirational:
                    record_floor_advisory(
                        c,
                        "soundscape_density",
                        {
                            "errors": density_errs[:8],
                            "source": "music_palette_compose_post_repair",
                        },
                        aspirational_proceeded=True,
                    )
                    c.log(
                        "music_palette_compose: density miss after repair — "
                        "progress_floors advisory continue: "
                        + "; ".join(density_errs[:4]),
                        level="warning",
                        stage="music_palette_compose",
                    )
            except Exception:
                aspirational = False
            if not aspirational:
                raise RuntimeError(
                    "music_palette_compose: post-compose density/slots refuse after one repair — "
                    + "; ".join(density_errs[:6])
                )

        selection_set = {str(s) for s in (ordered or []) if s}
        write_validated_artifact(
            c, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="music_palette_compose"
        )
        # i14b: if ownership/sanitize reintroduced off-selection anchors, force commit.
        if selection_set and _sdp_has_off_selection_anchors(c, selection_set):
            from interview_mux.artifact_sanitize.one_writer import commit_sound_design_plan_doc

            c.log(
                "music_palette_compose: pruned SDP reverted on write — force commit",
                level="warning",
                stage="music_palette_compose",
            )
            commit_sound_design_plan_doc(
                c,
                sdp,
                stage_key="music_palette_compose",
                reason="i14b_prune_persist",
            )
        from interview_mux.artifact_lifecycle import restamp_committed_artifact

        restamp_committed_artifact(
            c, _SOUND_DESIGN_PLAN_REL, producer_stage="sound_design_plan"
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
        # Seed cold_open + outro cues in music epoch (before MusicGen / mix).
        try:
            from interview_mux.theme_slot_integrity import ensure_theme_bookend_cues

            seeded = ensure_theme_bookend_cues(c)
            if seeded:
                c.log(
                    f"music_palette_compose: seeded theme bookend cues via {seeded}",
                    level="info",
                    stage="music_palette_compose",
                )
                # Refresh used-asset list after seed.
                sdp2 = (
                    c.read_json(_SOUND_DESIGN_PLAN_REL)
                    if c.artifact_exists(_SOUND_DESIGN_PLAN_REL)
                    else {}
                )
                if isinstance(sdp2, dict):
                    compose_out["asset_ids_used"] = sorted(
                        {
                            str(cu.get("asset_id"))
                            for cu in (
                                ((sdp2.get("flow_plans") or {}).get("podcast") or {}).get(
                                    "cues"
                                )
                                or []
                            )
                            if isinstance(cu, dict) and cu.get("asset_id")
                        }
                    )
                    compose_out["cue_count"] = len(
                        (((sdp2.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
                    )
                    c.write_json(_COMPOSE_REL, compose_out)
        except Exception as exc:
            c.log(
                f"music_palette_compose: bookend seed skipped: {exc}",
                level="warning",
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
