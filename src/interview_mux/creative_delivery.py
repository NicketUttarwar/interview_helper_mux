"""Creative delivery policy — audible SFX/music and editorial shaping on every run."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

_CUE_SEG_RE = re.compile(r"(seg_\d{3})", re.IGNORECASE)
_CHAPTER_CUE_RE = re.compile(r"stinger_ch_(\d+)", re.IGNORECASE)


def creative_delivery_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = (cfg or merged_config()).get("creative_delivery") or {}
    return raw if isinstance(raw, dict) else {}


def creative_delivery_required(cfg: dict[str, Any] | None = None) -> bool:
    return bool(creative_delivery_cfg(cfg).get("required", True))


def min_density_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    scape = (cfg or merged_config()).get("soundscape") or {}
    raw = scape.get("min_density") if isinstance(scape.get("min_density"), dict) else {}
    creative = creative_delivery_cfg(cfg)
    merged = dict(raw)
    for key in (
        "min_assets",
        "min_beds",
        "min_stingers",
        "min_foley",
        "min_bed_coverage_ratio",
        "min_audible_bed_level_db",
        "max_audible_bed_level_db",
        "min_audible_stinger_level_db",
        "min_audible_cold_open_level_db",
        "max_audible_cold_open_level_db",
        "min_audible_emphasis_level_db",
        "max_audible_emphasis_level_db",
    ):
        if creative.get(key) is not None:
            merged[key] = creative[key]
    # Production profile can override bed/bookend audibility bands.
    try:
        from interview_mux.production_profile import get_profile

        profile = get_profile()
        ov = profile.get("soundscape_min_density_overrides")
        if isinstance(ov, dict):
            merged.update({k: v for k, v in ov.items() if v is not None})
    except Exception:
        pass
    return merged


def apply_creative_mix_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Speech-first mix: audible beds under dialogue with hard duck; bookends hotter."""
    if not creative_delivery_required():
        return contract
    out = dict(contract)
    underscore = str(out.get("underscore_policy") or "normal")
    if underscore in {"skip", "sparse_or_skip", "sparse"}:
        out["underscore_policy"] = "normal"
    mins = min_density_cfg()
    quiet_lo = float(mins.get("min_audible_bed_level_db", -26.0))
    quiet_hi = float(mins.get("max_audible_bed_level_db", -22.0))
    if quiet_lo > quiet_hi:
        quiet_lo, quiet_hi = quiet_hi, quiet_lo
    # Force beds into the configured audible band (speech-first documentary ≈ −26…−22).
    out["bed_level_db_range"] = [quiet_lo, quiet_hi]
    duck = float(out.get("duck_under_speech_db") or 16.0)
    # Harder duck so conversation stays on top (plan: ≥18).
    out["duck_under_speech_db"] = max(duck, 18.0)
    return out


def apply_creative_sfx_density(dens: dict[str, Any]) -> dict[str, Any]:
    """Raise editorial SFX budgets using soft guidance — not hard reject ceilings."""
    if not creative_delivery_required():
        return dens
    from interview_mux.listenability_guards import soft_unique_asset_guidance

    mins = min_density_cfg()
    out = dict(dens)
    soft = soft_unique_asset_guidance(0)
    out["max_beds"] = max(int(out.get("max_beds") or 0), int(mins.get("min_beds") or 1), soft)
    out["max_punctuators"] = max(
        int(out.get("max_punctuators") or 0), int(mins.get("min_stingers") or 1), soft
    )
    out["max_foley"] = max(int(out.get("max_foley") or 0), int(mins.get("min_foley") or 1), soft // 2)
    return out


def _selection_chapter_end_ids(ctx: RunContext) -> list[str]:
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            ends: list[str] = []
            for ch in sel.get("chapters") or []:
                if not isinstance(ch, dict):
                    continue
                seg_ids = [str(x) for x in (ch.get("segment_ids") or []) if x]
                if seg_ids:
                    ends.append(seg_ids[-1])
            if ends:
                return ends
    if ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json")
        if isinstance(plan, dict):
            ends = []
            for ch in plan.get("chapters") or []:
                if isinstance(ch, dict) and ch.get("end_segment_id"):
                    ends.append(str(ch["end_segment_id"]))
            if ends:
                return ends
    if ctx.artifact_exists("master/transitions.json"):
        trans = ctx.read_json("master/transitions.json")
        rows = trans.get("transitions") if isinstance(trans, dict) else []
        return [str(t["after_segment_id"]) for t in rows if isinstance(t, dict) and t.get("after_segment_id")]
    return []


def _segment_from_cue_id(cue_id: str) -> str | None:
    match = _CUE_SEG_RE.search(str(cue_id or ""))
    return match.group(1).lower() if match else None


def hydrate_flow_cue_segments(ctx: RunContext, sdp: dict[str, Any]) -> list[str]:
    """Fill missing segment anchors on podcast flow cues (in-place). Returns action log."""
    actions: list[str] = []
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    if not flow and isinstance(flow_plans.get("flow1"), dict):
        flow = flow_plans["flow1"]
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    if not cues:
        return actions

    chapter_ends = _selection_chapter_end_ids(ctx)
    transition_after: list[str] = []
    if ctx.artifact_exists("master/transitions.json"):
        trans = ctx.read_json("master/transitions.json")
        rows = trans.get("transitions") if isinstance(trans, dict) else []
        transition_after = [
            str(t["after_segment_id"]) for t in rows if isinstance(t, dict) and t.get("after_segment_id")
        ]

    stinger_idx = 0
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        cue_id = str(cue.get("cue_id") or "")
        placement = str(cue.get("placement") or "")
        seg_from_id = _segment_from_cue_id(cue_id)

        if placement == "under_segment" and not cue.get("segment_id"):
            if seg_from_id:
                cue["segment_id"] = seg_from_id
                actions.append(f"hydrate:{cue_id}:segment_id={seg_from_id}")

        if placement == "before_segment" and not (
            cue.get("segment_id") or cue.get("before_segment_id")
        ):
            if seg_from_id:
                cue["segment_id"] = seg_from_id
                actions.append(f"hydrate:{cue_id}:segment_id={seg_from_id}")

        if placement == "after_segment" and not cue.get("after_segment_id"):
            ch_match = _CHAPTER_CUE_RE.search(cue_id)
            if ch_match:
                idx = int(ch_match.group(1)) - 1
                if 0 <= idx < len(chapter_ends):
                    cue["after_segment_id"] = chapter_ends[idx]
                    actions.append(f"hydrate:{cue_id}:after_segment_id={chapter_ends[idx]}")
                    continue
            if seg_from_id:
                cue["after_segment_id"] = seg_from_id
                actions.append(f"hydrate:{cue_id}:after_segment_id={seg_from_id}")
                continue
            if stinger_idx < len(transition_after):
                cue["after_segment_id"] = transition_after[stinger_idx]
                actions.append(f"hydrate:{cue_id}:after_segment_id={transition_after[stinger_idx]}")
            elif stinger_idx < len(chapter_ends):
                cue["after_segment_id"] = chapter_ends[stinger_idx]
                actions.append(f"hydrate:{cue_id}:after_segment_id={chapter_ends[stinger_idx]}")
            stinger_idx += 1

    if actions:
        flow["cues"] = cues
        if isinstance(flow_plans.get("podcast"), dict):
            flow_plans["podcast"] = flow
        elif isinstance(flow_plans.get("flow1"), dict):
            flow_plans["flow1"] = flow
        sdp["flow_plans"] = flow_plans
    return actions


def validate_cue_segment_anchors(cues: list[dict[str, Any]], selection_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not creative_delivery_required():
        return errors
    for cue in cues:
        if not isinstance(cue, dict) or cue.get("skip"):
            continue
        cid = str(cue.get("cue_id") or "?")
        placement = str(cue.get("placement") or "")
        if placement == "under_segment" and not cue.get("segment_id"):
            errors.append(f"cue {cid}: under_segment missing segment_id")
        elif placement == "before_segment" and not (cue.get("segment_id") or cue.get("before_segment_id")):
            errors.append(f"cue {cid}: before_segment missing segment anchor")
        elif placement == "after_segment" and not (cue.get("after_segment_id") or cue.get("segment_id")):
            errors.append(f"cue {cid}: after_segment missing after_segment_id")
        for key in ("segment_id", "after_segment_id", "before_segment_id"):
            sid = cue.get(key)
            if sid and selection_ids and str(sid) not in selection_ids:
                errors.append(f"cue {cid}: {key}={sid} not in selection")
    return errors


def validate_creative_density(ctx: RunContext, sdp: dict[str, Any]) -> list[str]:
    """Validate role presence (coverage ratios enforced at soundscape/listenability verify)."""
    errors: list[str] = []
    if not creative_delivery_required():
        return errors
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict)]
    if len(assets) < 3:
        errors.append(f"creative delivery requires role-diverse SDP assets (have {len(assets)})")

    roles = {str(a.get("role") or "") for a in assets}
    if "era_music_bed" in roles or "ambient_bed" in roles:
        roles.add("theme_underscore")
    if "cold_open" in roles:
        roles.add("theme_cold_open")
    if "chapter_stinger" in roles or "transition_stinger" in roles:
        roles.add("theme_chapter_resolve")
    need = {"theme_underscore", "theme_cold_open"}
    miss = sorted(need - roles)
    accent_family = {
        "theme_emphasis",
        "theme_chapter_resolve",
        "theme_transition",
        "theme_outro",
    }
    if not (roles & accent_family):
        miss.append("theme_emphasis_or_resolve")
    for m in miss:
        errors.append(f"creative delivery missing music role:{m}")

    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    cues = [c for c in (flow.get("cues") or []) if isinstance(c, dict) and not c.get("skip")]
    beds = sum(1 for c in cues if c.get("placement") == "under_segment")
    if beds < 1:
        errors.append("creative delivery requires at least one under_segment bed cue")

    from interview_mux.soundscape_policy import resolve_mix_contract

    contract = apply_creative_mix_contract(resolve_mix_contract(ctx))
    underscore = str(contract.get("underscore_policy") or "normal")
    if underscore in {"skip", "sparse_or_skip"}:
        errors.append(f"creative delivery forbids underscore_policy={underscore}")
    return errors


def audibility_level_db(*, role: str, default: float) -> float:
    """Clamp mix levels: beds audible under dialogue; speech-free roles hotter."""
    if not creative_delivery_required():
        return default
    mins = min_density_cfg()
    role_s = str(role or "")
    if role_s == "bed" or role_s == "theme_underscore":
        lo = float(mins.get("min_audible_bed_level_db", -26.0))
        hi = float(mins.get("max_audible_bed_level_db", -22.0))
        if lo > hi:
            lo, hi = hi, lo
        return max(lo, min(hi, float(default)))
    if role_s in {"theme_cold_open", "theme_outro", "cold_open"}:
        lo = float(mins.get("min_audible_cold_open_level_db", -12.0))
        hi = float(mins.get("max_audible_cold_open_level_db", -8.0))
        if lo > hi:
            lo, hi = hi, lo
        return max(lo, min(hi, max(float(default), lo)))
    if role_s in {"theme_emphasis", "theme_chapter_resolve", "theme_transition"}:
        lo = float(mins.get("min_audible_emphasis_level_db", -16.0))
        hi = float(mins.get("max_audible_emphasis_level_db", -12.0))
        if lo > hi:
            lo, hi = hi, lo
        return max(lo, min(hi, max(float(default), lo)))
    # Generic stinger floor
    return max(default, float(mins.get("min_audible_stinger_level_db", -16.0)))


def enforce_creative_selection_edit(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    stage: str = "full_master_ranking",
) -> dict[str, Any]:
    """Ensure selection is editorially shaped — trim toward ideal and drop low-value segments."""
    if not creative_delivery_required():
        return selection
    cfg = creative_delivery_cfg()
    out = _pack_selection_to_target(
        ctx,
        selection,
        target_key=str(cfg.get("trim_target", "ideal")),
        stage=stage,
    )
    excluded = list(out.get("excluded_segment_ids") or [])
    ordered = [str(x) for x in (out.get("ordered_segment_ids") or []) if x]
    if excluded:
        return out

    min_trim = int(cfg.get("min_trim_segments", 1))
    min_ratio = float(cfg.get("min_excluded_ratio", 0.05))
    if min_trim <= 0 and min_ratio <= 0:
        return out
    if not ordered:
        return out

    from interview_mux.selection_auto_pack import _arc_critical_ids, estimated_duration_sec

    critical = _arc_critical_ids(ctx)
    ranks = out.get("segment_ranks") or out.get("ranks") or {}
    if not isinstance(ranks, dict):
        ranks = {}

    def rank_of(sid: str) -> float:
        try:
            return float(ranks.get(sid, 9999))
        except (TypeError, ValueError):
            return 9999.0

    droppable = [sid for sid in ordered if sid not in critical]
    # Prefer dropping mid-monologue segments so I↔S turn boundaries survive denser volleys.
    speaker_of: dict[str, str] = {}
    try:
        if ctx.artifact_exists("segments/manifest.json"):
            man = ctx.read_json("segments/manifest.json")
            for row in (man.get("segments") or []) if isinstance(man, dict) else []:
                if isinstance(row, dict) and row.get("segment_id"):
                    speaker_of[str(row["segment_id"])] = str(row.get("speaker_id") or "")
    except Exception:
        speaker_of = {}

    def volley_drop_score(sid: str) -> tuple[float, float]:
        try:
            idx = ordered.index(sid)
        except ValueError:
            return (0.0, rank_of(sid))
        spk = speaker_of.get(sid, "")
        prev = speaker_of.get(ordered[idx - 1], "") if idx > 0 else ""
        nxt = speaker_of.get(ordered[idx + 1], "") if idx + 1 < len(ordered) else ""
        mid_mono = 1.0 if spk and spk == prev == nxt else 0.0
        return (mid_mono, rank_of(sid))

    droppable.sort(key=volley_drop_score, reverse=True)
    dropped: list[str] = []
    remaining = list(ordered)
    total_before = len(ordered)
    while droppable:
        need_more = len(dropped) < min_trim or (len(dropped) / max(1, total_before)) < min_ratio
        if not need_more:
            break
        if len(remaining) <= max(1, len(critical) or 1):
            break
        sid = droppable.pop(0)
        if sid not in remaining:
            continue
        remaining = [x for x in remaining if x != sid]
        dropped.append(sid)

    if not dropped:
        return out

    result = dict(out)
    result["ordered_segment_ids"] = remaining
    ex = list(result.get("excluded_segment_ids") or [])
    for sid in dropped:
        if sid not in ex:
            ex.append(sid)
    result["excluded_segment_ids"] = ex
    meta = dict(result.get("_meta") or {})
    meta["creative_trim"] = {
        "dropped": dropped,
        "min_trim_segments": min_trim,
        "min_excluded_ratio": min_ratio,
    }
    result["_meta"] = meta
    ctx.log(
        f"Creative selection trim: dropped {len(dropped)} low-value segment(s)",
        level="info",
        stage=stage,
        action_id="pipeline.selection.creative_trim",
        detail={"dropped": dropped[:20], "remaining": len(remaining)},
    )
    return result


def _pack_selection_to_target(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    target_key: str,
    stage: str,
) -> dict[str, Any]:
    from interview_mux.delivery_brief import load_delivery_brief
    from interview_mux.selection_auto_pack import _arc_critical_ids, estimated_duration_sec

    brief = load_delivery_brief(ctx)
    if not brief:
        return selection
    budget = brief.get("target_duration_sec") if isinstance(brief.get("target_duration_sec"), dict) else {}
    target = budget.get(target_key)
    try:
        target_sec = float(target) if target is not None else None
    except (TypeError, ValueError):
        target_sec = None
    if target_sec is None or target_sec <= 0:
        return selection

    ordered = [str(x) for x in (selection.get("ordered_segment_ids") or []) if x]
    if not ordered:
        return selection
    est = estimated_duration_sec(ctx, ordered)
    if est <= target_sec:
        return selection

    critical = _arc_critical_ids(ctx)
    ranks = selection.get("segment_ranks") or selection.get("ranks") or {}
    if not isinstance(ranks, dict):
        ranks = {}

    def rank_of(sid: str) -> float:
        try:
            return float(ranks.get(sid, 9999))
        except (TypeError, ValueError):
            return 9999.0

    droppable = [sid for sid in ordered if sid not in critical]
    droppable.sort(key=rank_of, reverse=True)
    dropped: list[str] = []
    remaining = list(ordered)
    for sid in droppable:
        if estimated_duration_sec(ctx, remaining) <= target_sec:
            break
        if len(remaining) <= max(1, len(critical) or 1):
            break
        remaining = [x for x in remaining if x != sid]
        dropped.append(sid)

    if not dropped:
        return selection

    out = dict(selection)
    out["ordered_segment_ids"] = remaining
    excluded = list(out.get("excluded_segment_ids") or [])
    for sid in dropped:
        if sid not in excluded:
            excluded.append(sid)
    out["excluded_segment_ids"] = excluded
    meta = dict(out.get("_meta") or {})
    meta["creative_pack"] = {
        "dropped": dropped,
        "before_sec": round(est, 1),
        "after_sec": round(estimated_duration_sec(ctx, remaining), 1),
        "target_sec": target_sec,
        "target_key": target_key,
    }
    out["_meta"] = meta
    ctx.log(
        f"Creative pack to {target_key} {target_sec:.0f}s: dropped {len(dropped)} segment(s)",
        level="info",
        stage=stage,
        action_id="pipeline.selection.creative_pack",
    )
    return out
