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
    """Speech-first mix: audible beds under dialogue with hard duck; bookends hotter.

    Do not rewrite skip-underscore when source_music_risk is high or dry_beds is set.
    Default posture is abundant (skip/sparse → normal) otherwise.
    """
    if not creative_delivery_required():
        return contract
    out = dict(contract)
    underscore = str(out.get("underscore_policy") or "normal")
    risk = str(out.get("source_music_risk") or out.get("source_music_risk_level") or "").lower()
    keep_dry = bool(out.get("dry_beds")) or risk in {"high", "true", "1"}
    if underscore in {"sparse", "sparse_or_skip"} and not keep_dry:
        out["underscore_policy"] = "normal"
    mins = min_density_cfg()
    quiet_lo = float(mins.get("min_audible_bed_level_db", -16.0))
    quiet_hi = float(mins.get("max_audible_bed_level_db", -12.0))
    if quiet_lo > quiet_hi:
        quiet_lo, quiet_hi = quiet_hi, quiet_lo
    # Constant underbed band (speech-first ≈ −16…−12). Mix does not duck beds.
    out["bed_level_db_range"] = [quiet_lo, quiet_hi]
    duck = float(out.get("duck_under_speech_db") or 12.0)
    # Accents / overlapping bookends still sidechain; underbeds ignore this.
    out["duck_under_speech_db"] = max(duck, 12.0)
    return out


def _bed_level_band(mix_contract: dict[str, Any] | None = None) -> tuple[float, float]:
    """Return (quiet_lo, quiet_hi) for speech-first beds, quieter first (more negative)."""
    mins = min_density_cfg()
    lo = float(mins.get("min_audible_bed_level_db", -16.0))
    hi = float(mins.get("max_audible_bed_level_db", -12.0))
    rng = (mix_contract or {}).get("bed_level_db_range") if isinstance(mix_contract, dict) else None
    if isinstance(rng, list) and len(rng) == 2:
        try:
            lo, hi = float(rng[0]), float(rng[1])
        except (TypeError, ValueError):
            pass
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def audible_bed_level_db(mix_contract: dict[str, Any] | None = None) -> float:
    """High end of the audible bed band (speech-first, typically −12 dB)."""
    _lo, hi = _bed_level_band(mix_contract)
    return hi


def clamp_bed_level_db(level: float, mix_contract: dict[str, Any] | None = None) -> float:
    lo, hi = _bed_level_band(mix_contract)
    return min(max(float(level), lo), hi)


def alternate_contiguous_loop_assets(
    cues: list[dict[str, Any]],
    *,
    ordered: list[str],
    primary_id: str,
    optional_id: str | None,
    max_run: int = 4,
) -> int:
    """Reassign under-segment loops so a contiguous run switches assets every max_run.

    Matches music_palette_compose scene splitting: optional_loop exists to break
    avoidable same-loop spans, not to leave one underscore on 30+ clips.
    """
    if not optional_id or optional_id == primary_id or max_run < 1 or not primary_id:
        return 0
    by_seg: dict[str, list[dict[str, Any]]] = {}
    for cue in cues:
        if not isinstance(cue, dict) or cue.get("skip"):
            continue
        if str(cue.get("placement") or "") != "under_segment":
            continue
        sid = str(cue.get("under_segment_id") or cue.get("segment_id") or "")
        if sid:
            by_seg.setdefault(sid, []).append(cue)
    changed = 0
    scene = 0
    run_len = 0
    in_run = False
    for sid in ordered:
        rows = by_seg.get(sid) or []
        if not rows:
            if in_run:
                scene += 1
                in_run = False
                run_len = 0
            continue
        if not in_run:
            in_run = True
            run_len = 0
        elif run_len >= max_run:
            scene += 1
            run_len = 0
        asset = optional_id if scene % 2 else primary_id
        for cue in rows:
            if str(cue.get("asset_id") or "") != asset:
                cue["asset_id"] = asset
                changed += 1
        run_len += 1
    return changed


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


def _first_selected_segment_id(ctx: RunContext) -> str | None:
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            for sid in sel.get("ordered_segment_ids") or []:
                if sid:
                    return str(sid)
    return None


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
            sid = str(cue.get("under_segment_id") or "") or seg_from_id
            if not sid:
                sid = _first_selected_segment_id(ctx) or ""
            if sid:
                cue["segment_id"] = sid
                actions.append(f"hydrate:{cue_id}:segment_id={sid}")

        if placement == "before_segment" and not (
            cue.get("segment_id") or cue.get("before_segment_id")
        ):
            sid = str(cue.get("before_segment_id") or cue.get("under_segment_id") or "") or seg_from_id
            if not sid:
                sid = _first_selected_segment_id(ctx) or ""
            if sid:
                cue["segment_id"] = sid
                actions.append(f"hydrate:{cue_id}:segment_id={sid}")

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


def _estimate_bed_coverage_ratio(ctx: RunContext, cues: list[dict[str, Any]]) -> float:
    """Estimate under_segment bed coverage vs selection speech duration (MU5 preflight)."""
    bed_cues = [c for c in cues if str(c.get("placement") or "") == "under_segment"]
    if not bed_cues:
        return 0.0
    speech_ms = 0.0
    try:
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            for row in (sel.get("segments") or []) if isinstance(sel, dict) else []:
                if not isinstance(row, dict):
                    continue
                start = float(row.get("start_ms") or row.get("start") or 0)
                end = float(row.get("end_ms") or row.get("end") or 0)
                if end > start:
                    speech_ms += end - start
    except Exception:
        speech_ms = 0.0
    if speech_ms <= 0:
        # No selection clock yet — require at least one bed (presence already checked).
        return 1.0 if bed_cues else 0.0
    covered: set[str] = set()
    for cue in bed_cues:
        sid = str(
            cue.get("segment_id")
            or cue.get("under_segment_id")
            or cue.get("targets_segment_id")
            or ""
        ).strip()
        if sid:
            covered.add(sid)
    # Approximate: each unique under_segment bed covers that segment's share equally.
    try:
        sel = (
            ctx.read_json("master/selection.json")
            if ctx.artifact_exists("master/selection.json")
            else {}
        )
        segs = [r for r in (sel.get("segments") or []) if isinstance(r, dict)]
        covered_ms = 0.0
        for row in segs:
            sid = str(row.get("segment_id") or row.get("id") or "")
            if sid not in covered:
                continue
            start = float(row.get("start_ms") or row.get("start") or 0)
            end = float(row.get("end_ms") or row.get("end") or 0)
            if end > start:
                covered_ms += end - start
        return max(0.0, min(1.0, covered_ms / speech_ms))
    except Exception:
        return max(0.0, min(1.0, len(covered) / max(1, len(bed_cues))))


def validate_creative_density(ctx: RunContext, sdp: dict[str, Any]) -> list[str]:
    """MU5: role presence + referenced bed coverage before MusicGen GPU."""
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
    try:
        from interview_mux.information_packages import information_packages_cfg

        if bool((information_packages_cfg().get("episode_close") or {}).get("require_music", True)):
            need.add("theme_outro")
    except Exception:
        need.add("theme_outro")
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

    min_cov = float(min_density_cfg().get("min_bed_coverage_ratio") or 0.40)
    est = _estimate_bed_coverage_ratio(ctx, cues)
    if beds >= 1 and est + 1e-9 < min_cov:
        errors.append(
            f"creative density preflight: estimated bed coverage {est:.2f} "
            f"< min_bed_coverage_ratio {min_cov:.2f} — repair compose before MusicGen"
        )

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
        lo = float(mins.get("min_audible_bed_level_db", -16.0))
        hi = float(mins.get("max_audible_bed_level_db", -12.0))
        if lo > hi:
            lo, hi = hi, lo
        return max(lo, min(hi, float(default)))
    if role_s in {"theme_cold_open", "theme_outro", "cold_open"}:
        lo = float(mins.get("min_audible_cold_open_level_db", -9.0))
        hi = float(mins.get("max_audible_cold_open_level_db", -5.0))
        if lo > hi:
            lo, hi = hi, lo
        return max(lo, min(hi, max(float(default), lo)))
    if role_s in {"theme_emphasis", "theme_chapter_resolve", "theme_transition"}:
        lo = float(mins.get("min_audible_emphasis_level_db", -15.0))
        hi = float(mins.get("max_audible_emphasis_level_db", -11.0))
        if lo > hi:
            lo, hi = hi, lo
        return max(lo, min(hi, max(float(default), lo)))
    # Generic stinger floor
    return max(default, float(mins.get("min_audible_stinger_level_db", -15.0)))


def enforce_creative_selection_edit(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    stage: str = "full_master_ranking",
) -> dict[str, Any]:
    """Editorial soft-pack toward the brief's ``trim_target`` (default: ideal).

    Prefer landing at or under ideal (concise). The brief max (1.5× source)
    is a ceiling, not a target to fill. Single pack pass — no forced
    minimum-trim on top of an already-tight selection. Shares the
    volley-intact drop preference with
    ``selection_auto_pack.auto_pack_selection_to_brief`` via
    ``pack_selection_to_duration``.
    """
    if not creative_delivery_required():
        return selection
    cfg = creative_delivery_cfg()
    from interview_mux.delivery_brief import load_delivery_brief
    from interview_mux.selection_auto_pack import pack_selection_to_duration

    brief = load_delivery_brief(ctx)
    if not brief:
        return selection
    target_key = str(cfg.get("trim_target", "ideal"))
    budget = brief.get("target_duration_sec") if isinstance(brief.get("target_duration_sec"), dict) else {}
    target = budget.get(target_key)
    try:
        target_sec = float(target) if target is not None else None
    except (TypeError, ValueError):
        target_sec = None
    if target_sec is None or target_sec <= 0:
        return selection

    return pack_selection_to_duration(
        ctx,
        selection,
        target_sec=target_sec,
        stage=stage,
        meta_key="creative_pack",
        action_id="pipeline.selection.creative_pack",
        log_label=f"Creative pack to {target_key}",
    )
