"""Per-run soundscape policy — merge SAP + sonic + delivery brief; cue slots; resolve API."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from interview_mux.acoustic_profile import (
    PACE_CLASS_VALUES,
    UNDERSCORE_POLICY_VALUES,
    load_profile,
    mix_contract as sap_mix_contract,
)
from interview_mux.config import merged_config
from interview_mux.delivery_brief import load_delivery_brief
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context

POLICY_PATH = "understanding/soundscape_policy.json"
REPORT_PATH = "sound_design/soundscape_report.json"

_BED_ROLES = frozenset({"theme_underscore", "ambient_bed", "era_music_bed"})
_PUNCTUATOR_ROLES = frozenset(
    {
        "theme_cold_open",
        "theme_emphasis",
        "theme_chapter_resolve",
        "theme_outro",
        "theme_transition",
        # Legacy — creative delivery should not plan these; kept for read compatibility.
        "chapter_stinger",
        "transition_stinger",
        "cold_open",
        "outro",
        "vo_bridge",
        "rhetorical_punctuator",
    }
)
_FOLEY_ROLES = frozenset({"accent_foley", "environmental_foley", "transition_whoosh"})

_MIN_BED_SEGMENT_MS = 12_000
_MIN_BED_SEGMENT_MS_FINE = 6_000
_DEFAULT_BED_LEVEL = -12.0


def _min_bed_segment_ms(cfg: dict[str, Any] | None = None) -> int:
    from interview_mux.segment_timeline_standard import is_fine_granularity, segmentation_cfg

    sc = segmentation_cfg(cfg)
    if is_fine_granularity(cfg):
        return int(sc.get("min_bed_segment_ms_fine") or _MIN_BED_SEGMENT_MS_FINE)
    return _MIN_BED_SEGMENT_MS


def soundscape_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    c = cfg if cfg is not None else merged_config()
    return c.get("soundscape") or {}


def soundscape_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(soundscape_cfg(cfg).get("enabled", True))


def strict_slots(cfg: dict[str, Any] | None = None) -> bool:
    return bool(soundscape_cfg(cfg).get("strict_slots", True))


def fail_closed(cfg: dict[str, Any] | None = None) -> bool:
    sc = soundscape_cfg(cfg)
    if "fail_closed" in sc:
        return bool(sc["fail_closed"])
    journey = (cfg or merged_config()).get("journey_ui") or {}
    if bool(journey.get("first_try_mode", True)):
        return False
    return bool(sc.get("fail_closed_default", False))


def max_regen_per_asset(cfg: dict[str, Any] | None = None) -> int:
    rem = soundscape_cfg(cfg).get("remediation") or {}
    return int(rem.get("max_regen_per_asset", 1))


def max_remux_cycles(cfg: dict[str, Any] | None = None) -> int:
    rem = soundscape_cfg(cfg).get("remediation") or {}
    return int(rem.get("max_remux_cycles", 1))


def _norm_underscore(raw: str | None) -> str:
    v = str(raw or "normal").strip()
    if v == "sparse_or_skip":
        return "sparse_or_skip"
    if v not in UNDERSCORE_POLICY_VALUES:
        return "normal"
    return v


def _norm_pace(raw: str | None) -> str:
    v = str(raw or "conversational").strip()
    return v if v in PACE_CLASS_VALUES else "conversational"


def _policy_hash(doc: dict[str, Any]) -> str:
    payload = {k: v for k, v in doc.items() if k != "policy_hash"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _density_from_sources(
    *,
    brief: dict[str, Any] | None,
    sonic: dict[str, Any] | None,
    underscore: str,
) -> dict[str, int]:
    dens: dict[str, int] = {"max_beds": 2, "max_punctuators": 2, "max_foley": 1}
    if isinstance(brief, dict):
        bd = brief.get("sfx_density") if isinstance(brief.get("sfx_density"), dict) else {}
        for k in dens:
            if bd.get(k) is not None:
                dens[k] = int(bd[k])
    mix = (sonic or {}).get("mix_policy") if isinstance((sonic or {}).get("mix_policy"), dict) else {}
    adaptive = mix.get("adaptive_max_assets_flow1")
    if adaptive is not None:
        cap = max(0, int(adaptive))
        total = dens["max_beds"] + dens["max_punctuators"] + dens["max_foley"]
        if total > cap and total > 0:
            scale = cap / total
            dens = {k: max(0, int(v * scale)) for k, v in dens.items()}
            # Ensure sum <= cap by trimming foley then punctuators
            while sum(dens.values()) > cap:
                if dens["max_foley"] > 0:
                    dens["max_foley"] -= 1
                elif dens["max_punctuators"] > 0:
                    dens["max_punctuators"] -= 1
                elif dens["max_beds"] > 0:
                    dens["max_beds"] -= 1
                else:
                    break
    if underscore in {"skip", "sparse_or_skip"}:
        dens["max_beds"] = 0
    elif underscore == "sparse":
        from interview_mux.creative_delivery import creative_delivery_required

        # Creative delivery still wants more frequent undersores than a hard single-bed clamp.
        dens["max_beds"] = min(dens["max_beds"], 2 if creative_delivery_required() else 1)
    return dens


def _standards_for_pace(pace: str, underscore: str) -> dict[str, Any]:
    min_rel = 12.0
    if pace in {"brisk", "dense"}:
        min_rel = 14.0
    if underscore in {"skip", "sparse_or_skip"}:
        min_rel = 10.0
    # Soft ceiling for beds under speech — Shape band ~0.40–0.85 (not the old 0.55 cap).
    coverage = 0.85
    if underscore == "sparse":
        coverage = 0.55
    if underscore in {"skip", "sparse_or_skip"}:
        coverage = 0.0
    elif pace == "dense":
        # Creative delivery still wants audible beds under dense talk.
        coverage = 0.85
    return {
        "min_speech_relative_db": min_rel,
        "max_midrange_overlap_score": 0.35,
        "require_intelligibility_pass": True,
        "max_bed_coverage_ratio": coverage,
    }


# Invent gate is SDP-owned; operator overrides must never carry invent_* authority keys.
_INVENT_OVERRIDE_DENY = frozenset(
    {
        "invent_gate",
        "invent_obligation",
        "invent_gate_reason",
        "invent_waived",
        "musical_direction_complete",
    }
)


def _strip_invent_override_keys(overrides: dict[str, Any]) -> dict[str, Any]:
    """Drop invent_* / musical_direction keys from operator override payloads."""
    out: dict[str, Any] = {}
    for key, val in overrides.items():
        k = str(key)
        if k in _INVENT_OVERRIDE_DENY or k.startswith("invent_"):
            continue
        out[k] = val
    return out


def _apply_operator_overrides(policy: dict[str, Any]) -> dict[str, Any]:
    overrides = policy.get("operator_overrides")
    if not isinstance(overrides, dict) or not overrides:
        return policy
    out = dict(policy)
    overrides = _strip_invent_override_keys(overrides)
    out["operator_overrides"] = overrides
    if overrides.get("underscore_policy"):
        out["underscore_policy"] = _norm_underscore(str(overrides["underscore_policy"]))
        mix = dict(out.get("mix_contract") or {})
        mix["underscore_policy"] = out["underscore_policy"]
        out["mix_contract"] = mix
    if overrides.get("pace_class"):
        out["pace_class"] = _norm_pace(str(overrides["pace_class"]))
    dens_ov = overrides.get("sfx_density")
    if isinstance(dens_ov, dict):
        dens = dict(out.get("sfx_density") or {})
        for k in ("max_beds", "max_punctuators", "max_foley"):
            if dens_ov.get(k) is not None:
                dens[k] = int(dens_ov[k])
        out["sfx_density"] = dens
    mix_ov = overrides.get("mix_contract")
    if isinstance(mix_ov, dict):
        mix = dict(out.get("mix_contract") or {})
        mix.update(mix_ov)
        out["mix_contract"] = mix
    return out


def _clamp_density_after_overrides(policy: dict[str, Any]) -> dict[str, Any]:
    """Desired dens clamps from underscore (before invent gate)."""
    out = dict(policy)
    underscore = str(out.get("underscore_policy") or "normal")
    dens = dict(out.get("sfx_density") or {})
    if underscore in {"skip", "sparse_or_skip"}:
        dens["max_beds"] = 0
        out["sfx_density"] = dens
        mc = dict(out.get("mix_contract") or {})
        mc["max_bed_coverage_ratio"] = 0.0
        mc["underscore_policy"] = "skip" if underscore == "skip" else mc.get("underscore_policy", underscore)
        out["mix_contract"] = mc
        standards = dict(out.get("standards") or {})
        standards["max_bed_coverage_ratio"] = 0.0
        out["standards"] = standards
    elif underscore == "sparse":
        dens["max_beds"] = min(int(dens.get("max_beds") or 1), 1)
        out["sfx_density"] = dens
    return out


def beds_hard_zero(policy: dict[str, Any] | None) -> bool:
    """True when policy forbids beds (skip underscore or max_beds≤0)."""
    if not isinstance(policy, dict):
        return False
    underscore = str(policy.get("underscore_policy") or "")
    if underscore in {"skip", "sparse_or_skip"}:
        return True
    dens = policy.get("sfx_density") if isinstance(policy.get("sfx_density"), dict) else {}
    if dens.get("max_beds") is not None and int(dens.get("max_beds") or 0) <= 0:
        return True
    return False


def musical_invent_blocked(policy: dict[str, Any] | None) -> bool:
    """True when invent gate is blocked or beds are hard-zero."""
    if not isinstance(policy, dict):
        return False
    if str(policy.get("invent_gate") or "") == "blocked":
        return True
    return beds_hard_zero(policy)


def _finalize_policy(
    ctx: RunContext,
    policy: dict[str, Any],
    *,
    refresh_slots: bool,
) -> dict[str, Any]:
    """Apply desired sources → dens clamps → optional slots → invent gate LAST → hash.

    Operator dens/underscore prefs are desired-only; invent_obligation always wins.
    """
    out = dict(policy)
    ov = out.get("operator_overrides")
    if isinstance(ov, dict):
        out["operator_overrides"] = _strip_invent_override_keys(ov)
    else:
        out["operator_overrides"] = {}
    out = _apply_operator_overrides(out)
    out = _clamp_density_after_overrides(out)
    if refresh_slots:
        # Sole cue_slots writer (SSOT) — dens ∪ planned ∪ inject path.
        out = build_cue_slots_ssot(ctx, out, rescore=True)
    else:
        invent_status = invent_obligation_status(ctx)
        out = _apply_invent_obligation_gate(
            out,
            status=invent_status,
            rationale=list(out.get("rationale") or []),
        )
    out["policy_hash"] = _policy_hash({k: v for k, v in out.items() if k != "policy_hash"})
    return out


def score_cue_slots(
    ctx: RunContext,
    *,
    underscore: str,
    pace: str,
    dens: dict[str, int],
    mix_contract: dict[str, Any],
    selected_segment_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic cue opportunities constrained by policy."""
    sonic = load_sonic_context(ctx) or {}
    flags = sonic.get("segment_flags") if isinstance(sonic.get("segment_flags"), dict) else {}
    overlap_high = {str(x) for x in (flags.get("overlap_high") or [])}
    sap = load_profile(ctx) or {}
    music_risk = str(sap.get("source_music_risk") or "low")
    bed_range = mix_contract.get("bed_level_db_range") or [-16.0, -12.0]
    bed_level = float(bed_range[0] + bed_range[-1]) / 2.0 if isinstance(bed_range, list) and len(bed_range) == 2 else _DEFAULT_BED_LEVEL
    if pace in {"brisk", "dense"}:
        # Prefer the quiet end of the constant bed band under dense dialogue.
        lo = float(bed_range[0]) if isinstance(bed_range, list) and bed_range else -16.0
        hi = float(bed_range[-1]) if isinstance(bed_range, list) and len(bed_range) > 1 else lo
        if lo > hi:
            lo, hi = hi, lo
        bed_level = min(bed_level, lo)

    sdp = {}
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        raw = ctx.read_json("understanding/sound_design_plan.json")
        sdp = raw if isinstance(raw, dict) else {}
    palettes = [p for p in (sdp.get("palettes") or []) if isinstance(p, dict)]
    theme_segs: set[str] = set()
    for p in palettes:
        for sid in p.get("segment_ids") or []:
            theme_segs.add(str(sid))

    manifest = {}
    if ctx.artifact_exists("segments/manifest.json"):
        raw = ctx.read_json("segments/manifest.json")
        manifest = raw if isinstance(raw, dict) else {}
    segments = [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]
    min_bed_ms = _min_bed_segment_ms()

    narrative = {}
    if ctx.artifact_exists("master/narrative_plan.json"):
        raw = ctx.read_json("master/narrative_plan.json")
        narrative = raw if isinstance(raw, dict) else {}
    chapter_ends: set[str] = set()
    for ch in narrative.get("chapters") or []:
        if isinstance(ch, dict) and ch.get("end_segment_id"):
            chapter_ends.add(str(ch["end_segment_id"]))

    selection_ids = selected_segment_ids
    if selection_ids is None and ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            ordered = sel.get("ordered_segment_ids") or []
            if isinstance(ordered, list) and ordered:
                selection_ids = {str(x) for x in ordered}
            else:
                clips = sel.get("clips") or sel.get("segments") or []
                selection_ids = {str(c.get("segment_id") or c.get("id")) for c in clips if isinstance(c, dict)}

    allow_beds = dens.get("max_beds", 0) > 0 and underscore not in {"skip", "sparse_or_skip"} and music_risk != "high"
    slots: list[dict[str, Any]] = []
    beds_budget = dens.get("max_beds", 0)
    sting_budget = dens.get("max_punctuators", 0)

    for seg in segments:
        sid = str(seg.get("segment_id") or seg.get("id") or "")
        if not sid:
            continue
        if selection_ids is not None and sid not in selection_ids:
            continue
        start = int(seg.get("start_ms") or 0)
        end = int(seg.get("end_ms") or 0)
        dur = max(0, end - start)
        if allow_beds and beds_budget > 0 and dur >= min_bed_ms and sid not in overlap_high:
            theme_bonus = 0.25 if sid in theme_segs else 0.0
            priority = min(1.0, 0.45 + theme_bonus + min(0.2, dur / 120_000))
            if pace == "dense":
                priority *= 0.85
            if priority >= 0.4:
                slots.append(
                    {
                        "slot_id": f"bed_{sid}",
                        "segment_id": sid,
                        "placement": "under_segment",
                        "allowed_roles": ["theme_underscore", "ambient_bed"],
                        "priority": round(priority, 3),
                        "max_level_db": bed_level,
                        "reason": "duration_ok"
                        + ("+theme_match" if sid in theme_segs else "")
                        + ("+pause_ok" if dur >= min_bed_ms else ""),
                    }
                )
                beds_budget -= 1

        if sting_budget > 0 and sid in chapter_ends and pace != "dense":
            slots.append(
                {
                    "slot_id": f"sting_{sid}",
                    "segment_id": sid,
                    "placement": "after_segment",
                    "allowed_roles": ["theme_chapter_resolve", "theme_transition", "chapter_stinger"],
                    "priority": 0.75,
                    "max_level_db": -14.0,
                    "reason": "chapter_boundary",
                }
            )
            sting_budget -= 1

    # Cap slots by priority if over budget after scoring
    bed_slots = [
        s
        for s in slots
        if "theme_underscore" in s.get("allowed_roles", []) or "ambient_bed" in s.get("allowed_roles", [])
    ]
    other = [s for s in slots if s not in bed_slots]
    bed_slots.sort(key=lambda s: float(s.get("priority") or 0), reverse=True)
    bed_slots = bed_slots[: dens.get("max_beds", 0)]
    other = other[: dens.get("max_punctuators", 0) + dens.get("max_foley", 0)]
    # Planned under_segment beds in SDP must keep cue_slots even when dens
    # max_beds is tight — otherwise refresh at sound_design_plan start wipes
    # coverage seeds and strict_slots post-commit thrash (exec_13167).
    return _merge_planned_bed_slots(ctx, bed_slots + other, bed_level=bed_level)


def _planned_under_segment_bed_ids(ctx: RunContext) -> set[str]:
    """Segment ids that already carry a non-skipped under_segment bed in SDP."""
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return set()
    try:
        sdp = ctx.read_json("understanding/sound_design_plan.json")
    except Exception:
        return set()
    if not isinstance(sdp, dict):
        return set()
    assets_by_id = {
        str(a.get("asset_id")): a
        for a in (sdp.get("assets") or [])
        if isinstance(a, dict) and a.get("asset_id")
    }
    out: set[str] = set()
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    for key in ("podcast", "flow1"):
        flow = flow_plans.get(key) if isinstance(flow_plans.get(key), dict) else {}
        for cue in flow.get("cues") or []:
            if not isinstance(cue, dict) or cue.get("skip"):
                continue
            if str(cue.get("placement") or "") != "under_segment":
                continue
            aid = str(cue.get("asset_id") or "")
            role = str(
                (assets_by_id.get(aid) or {}).get("role") or cue.get("role") or "theme_underscore"
            )
            if role not in _BED_ROLES and role != "theme_underscore":
                continue
            sid = str(cue.get("segment_id") or "")
            if sid:
                out.add(sid)
    return out


def _merge_planned_bed_slots(
    ctx: RunContext,
    slots: list[dict[str, Any]],
    *,
    bed_level: float,
) -> list[dict[str, Any]]:
    """Union SDP-planned bed segments into scored cue_slots (beyond dens cap)."""
    planned = _planned_under_segment_bed_ids(ctx)
    if not planned:
        return slots
    have = {
        str(s.get("segment_id") or "")
        for s in slots
        if isinstance(s, dict)
        and (
            "theme_underscore" in (s.get("allowed_roles") or [])
            or "ambient_bed" in (s.get("allowed_roles") or [])
        )
        and s.get("segment_id")
    }
    out = list(slots)
    for sid in sorted(planned):
        if sid in have:
            continue
        out.append(
            {
                "slot_id": f"bed_{sid}",
                "segment_id": sid,
                "placement": "under_segment",
                "allowed_roles": ["theme_underscore"],
                "priority": 0.55,
                "max_level_db": bed_level,
                "reason": "planned_sdp_bed",
                "origin": "planned",
            }
        )
        have.add(sid)
    return out


# --- Cue-slot SSOT (Partial Zero DP-SOUND-SDP-CUE custom A+) -----------------
# One writer: dens score ∪ planned ∪ inject → normalize → dedupe → invent soft-block.

_ORIGIN_RANK = {"planned": 3, "inject": 2, "dens": 1}
_CUE_SLOT_REQUIRED = (
    "slot_id",
    "segment_id",
    "placement",
    "allowed_roles",
    "priority",
    "max_level_db",
    "reason",
    "origin",
)


def _bed_level_from_mix(mix_contract: dict[str, Any] | None) -> float:
    bed_range = (mix_contract or {}).get("bed_level_db_range") or [-16.0, -12.0]
    if isinstance(bed_range, list) and len(bed_range) == 2:
        try:
            return float(bed_range[0] + bed_range[-1]) / 2.0
        except (TypeError, ValueError):
            return _DEFAULT_BED_LEVEL
    return _DEFAULT_BED_LEVEL


def infer_cue_slot_origin(slot: dict[str, Any]) -> str:
    """Map existing reason/origin strings onto dens|planned|inject."""
    raw = str(slot.get("origin") or "").strip().lower()
    if raw in _ORIGIN_RANK:
        return raw
    reason = str(slot.get("reason") or "").lower()
    if "planned_sdp" in reason:
        return "planned"
    if (
        "theme_underscore" in reason
        or reason.startswith("inject")
        or "palette_bed" in reason
        or "quartile_spread" in reason
    ):
        return "inject"
    return "dens"


def normalize_cue_slot(
    raw: Any,
    *,
    bed_level: float | None = None,
    origin: str | None = None,
) -> dict[str, Any] | None:
    """Coerce any writer-shaped dict into the canonical cue_slot schema.

    Returns None when the candidate cannot become a valid slot (missing segment).
    """
    if not isinstance(raw, dict):
        return None
    sid = str(raw.get("segment_id") or "").strip()
    if not sid:
        return None
    placement = str(raw.get("placement") or "under_segment").strip() or "under_segment"
    roles_raw = raw.get("allowed_roles") or []
    if isinstance(roles_raw, str):
        roles = [roles_raw.strip()] if roles_raw.strip() else []
    elif isinstance(roles_raw, list):
        roles = [str(r).strip() for r in roles_raw if str(r).strip()]
    else:
        roles = []
    if not roles:
        roles = ["theme_underscore"]
    try:
        priority = float(raw.get("priority") if raw.get("priority") is not None else 0.5)
    except (TypeError, ValueError):
        priority = 0.5
    level = bed_level if bed_level is not None else _DEFAULT_BED_LEVEL
    if raw.get("max_level_db") is not None:
        try:
            level = float(raw.get("max_level_db"))
        except (TypeError, ValueError):
            pass
    reason = str(raw.get("reason") or "cue_slot").strip() or "cue_slot"
    orig = str(origin or "").strip().lower()
    if orig not in _ORIGIN_RANK:
        orig = infer_cue_slot_origin({**raw, "reason": reason})
    slot_id = str(raw.get("slot_id") or "").strip() or f"bed_{sid}"
    out: dict[str, Any] = {
        "slot_id": slot_id,
        "segment_id": sid,
        "placement": placement,
        "allowed_roles": roles,
        "priority": round(priority, 3),
        "max_level_db": level,
        "reason": reason,
        "origin": orig,
    }
    # Preserve optional bind metadata when already present (volley annotate).
    for opt in ("speaker_volley_id", "hinge", "hinge_kind"):
        if raw.get(opt) is not None:
            out[opt] = raw.get(opt)
    return out


def cue_slot_identity(slot: dict[str, Any]) -> tuple[str, str, str]:
    """Stable merge key: placement + segment + primary role."""
    placement = str(slot.get("placement") or "under_segment")
    sid = str(slot.get("segment_id") or "")
    roles = [str(r) for r in (slot.get("allowed_roles") or []) if str(r).strip()]
    primary = "theme_underscore"
    for cand in ("theme_underscore", "ambient_bed", "era_music_bed"):
        if cand in roles:
            primary = cand
            break
    if roles and primary not in roles:
        primary = roles[0]
    return (placement, sid, primary)


def merge_normalized_cue_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe by identity; planned > inject > dens; higher priority on tie."""
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        key = cue_slot_identity(slot)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = slot
            continue
        rank_new = _ORIGIN_RANK.get(str(slot.get("origin") or "dens"), 0)
        rank_old = _ORIGIN_RANK.get(str(prev.get("origin") or "dens"), 0)
        if rank_new > rank_old:
            by_key[key] = slot
        elif rank_new == rank_old:
            try:
                if float(slot.get("priority") or 0) > float(prev.get("priority") or 0):
                    by_key[key] = slot
            except (TypeError, ValueError):
                pass
    return sorted(
        by_key.values(),
        key=lambda s: (-float(s.get("priority") or 0), str(s.get("segment_id") or "")),
    )


def _slot_survives_invent_soft_block(slot: dict[str, Any]) -> bool:
    """Keep planned/inject beds while invent unpaid; drop dens heuristic invent."""
    origin = str(slot.get("origin") or infer_cue_slot_origin(slot))
    if origin in {"planned", "inject"}:
        return True
    reason = str(slot.get("reason") or "").lower()
    if "planned_sdp" in reason or "theme_underscore" in reason:
        return True
    # Keep non-bed punctuators that are not musical invent (chapter stingers etc.)
    roles = [str(r) for r in (slot.get("allowed_roles") or [])]
    if roles and not any(r in _BED_ROLES or r == "theme_underscore" for r in roles):
        return True
    return False


def build_cue_slots_ssot(
    ctx: RunContext,
    policy: dict[str, Any],
    *,
    inject_slots: list[dict[str, Any]] | None = None,
    rescore: bool = True,
) -> dict[str, Any]:
    """Sole cue_slots writer: score ∪ planned ∪ inject → normalize → dedupe → invent gate.

    Repair inject must call this (or ``admit_inject_cue_slots``) — never assign
    ``policy["cue_slots"]`` ad hoc.
    """
    out = dict(policy) if isinstance(policy, dict) else {}
    mix = dict(out.get("mix_contract") or {})
    bed_level = _bed_level_from_mix(mix)
    dens = dict(out.get("sfx_density") or {})
    if rescore:
        scored = score_cue_slots(
            ctx,
            underscore=str(out.get("underscore_policy") or "normal"),
            pace=str(out.get("pace_class") or "conversational"),
            dens=dens,
            mix_contract=mix,
        )
    else:
        scored = [s for s in (out.get("cue_slots") or []) if isinstance(s, dict)]

    normalized: list[dict[str, Any]] = []
    for raw in scored:
        n = normalize_cue_slot(raw, bed_level=bed_level)
        if n:
            normalized.append(n)
    for raw in inject_slots or []:
        n = normalize_cue_slot(raw, bed_level=bed_level, origin="inject")
        if n:
            normalized.append(n)

    out["cue_slots"] = merge_normalized_cue_slots(normalized)
    invent_status = invent_obligation_status(ctx)
    out = _apply_invent_obligation_gate(
        out,
        status=invent_status,
        rationale=list(out.get("rationale") or []),
    )
    return out


def admit_inject_cue_slots(
    ctx: RunContext,
    policy: dict[str, Any] | None,
    *,
    segment_ids: list[str],
    reason: str = "theme_underscore_inject",
    persist: bool = True,
    rescore: bool = False,
) -> dict[str, Any]:
    """Fold repair inject into the SSOT writer (Partial Zero A+)."""
    base = dict(policy) if isinstance(policy, dict) else (load_policy(ctx) or {})
    inject: list[dict[str, Any]] = []
    for sid in segment_ids:
        s = str(sid or "").strip()
        if not s:
            continue
        inject.append(
            {
                "slot_id": f"bed_{s}",
                "segment_id": s,
                "placement": "under_segment",
                "allowed_roles": ["theme_underscore"],
                "priority": 0.55,
                "reason": str(reason or "theme_underscore_inject"),
                "origin": "inject",
            }
        )
    if not inject:
        return base
    out = build_cue_slots_ssot(ctx, base, inject_slots=inject, rescore=rescore)
    out["policy_hash"] = _policy_hash({k: v for k, v in out.items() if k != "policy_hash"})
    if persist:
        try:
            from interview_mux.write_staging import write_committed_json

            write_committed_json(
                ctx, POLICY_PATH, out, stage_key="soundscape_policy_build"
            )
        except Exception:
            try:
                ctx.write_json(POLICY_PATH, out, stage_key="soundscape_policy_build")
            except Exception:
                pass
    return out


def invent_obligation_status(ctx: RunContext) -> dict[str, Any]:
    """F-03: unpaid invent obligation blocks heuristic musical invent.

    Returns keys: unpaid (bool), waived (bool), invent (str), pals (int), cues (int).
    """
    out: dict[str, Any] = {
        "unpaid": False,
        "waived": False,
        "invent": "",
        "pals": 0,
        "cues": 0,
    }
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return out
    try:
        sdp = ctx.read_json("understanding/sound_design_plan.json")
    except Exception:
        return out
    if not isinstance(sdp, dict):
        return out
    coh = sdp.get("coherence") if isinstance(sdp.get("coherence"), dict) else {}
    meta = sdp.get("_meta") if isinstance(sdp.get("_meta"), dict) else {}
    invent = str(coh.get("invent_obligation") or meta.get("invent_obligation") or "").strip()
    waived = bool(coh.get("invent_waived") or meta.get("invent_waived"))
    pals = sdp.get("palettes") if isinstance(sdp.get("palettes"), list) else []
    cues: list[Any] = []
    fp = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    for key in ("podcast", "flow1"):
        flow = fp.get(key) if isinstance(fp.get(key), dict) else {}
        if isinstance(flow.get("cues"), list):
            cues.extend(flow["cues"])
    out.update(
        {
            "invent": invent,
            "waived": waived,
            "pals": len(pals),
            "cues": len(cues),
            "unpaid": bool(invent == "sound_design_plan" and not pals and not cues and not waived),
        }
    )
    return out


def _apply_invent_obligation_gate(
    policy: dict[str, Any],
    *,
    status: dict[str, Any],
    rationale: list[str],
) -> dict[str, Any]:
    """Block heuristic musical invent while invent obligation is unpaid.

    Partial Zero A+: never wipe planned/inject cue_slots — soft-block only.
    Dens heuristic invent beds are dropped; invent_gate stays blocked.
    """
    if not status.get("unpaid"):
        policy["invent_gate"] = "clear" if not status.get("invent") else "satisfied"
        return policy
    dens = dict(policy.get("sfx_density") or {})
    dens["max_beds"] = 0
    dens["max_punctuators"] = min(int(dens.get("max_punctuators") or 0), 0)
    dens["max_foley"] = min(int(dens.get("max_foley") or 0), 0)
    policy["sfx_density"] = dens
    mix = dict(policy.get("mix_contract") or {})
    mix["max_bed_coverage_ratio"] = 0.0
    mix["underscore_policy"] = "skip"
    policy["mix_contract"] = mix
    policy["underscore_policy"] = "skip"
    standards = dict(policy.get("standards") or {})
    standards["max_bed_coverage_ratio"] = 0.0
    policy["standards"] = standards
    # Soft-block: keep planned/inject beds; drop dens heuristic invent only.
    kept: list[dict[str, Any]] = []
    for raw in policy.get("cue_slots") or []:
        if not isinstance(raw, dict):
            continue
        slot = normalize_cue_slot(raw, bed_level=_bed_level_from_mix(mix))
        if slot and _slot_survives_invent_soft_block(slot):
            kept.append(slot)
    policy["cue_slots"] = merge_normalized_cue_slots(kept)
    policy["invent_gate"] = "blocked"
    policy["invent_obligation"] = str(status.get("invent") or "sound_design_plan")
    policy["invent_gate_reason"] = (
        "unpaid_invent_obligation_soft_block_keeps_planned_inject"
    )
    policy["musical_direction_complete"] = False
    rationale.append(
        "invent_gate=blocked:unpaid_soft_block_keeps_planned_inject_beds"
    )
    policy["rationale"] = list(rationale)
    return policy


def build_policy(ctx: RunContext, *, refresh_slots: bool = True) -> dict[str, Any]:
    sap = load_profile(ctx) or {}
    sonic = load_sonic_context(ctx) or {}
    brief = load_delivery_brief(ctx)
    sap_mix = sap.get("mix_contract") if isinstance(sap.get("mix_contract"), dict) else {}
    sonic_mix = sonic.get("mix_policy") if isinstance(sonic.get("mix_policy"), dict) else {}

    underscore = _norm_underscore(str(sonic_mix.get("underscore_policy") or sap_mix.get("underscore_policy") or "normal"))
    from interview_mux.creative_delivery import (
        apply_creative_mix_contract,
        apply_creative_sfx_density,
        creative_delivery_required,
        min_density_cfg,
    )

    music_risk = str(sap.get("source_music_risk") or "low")
    if music_risk == "high" and not creative_delivery_required():
        underscore = "skip"
    # Creative delivery: medium risk becomes normal so dens/coverage are not sparse-clamped.
    # High risk stays restrained (sparse), not upgraded to wallpaper beds.
    if creative_delivery_required():
        if music_risk == "medium" and underscore in {"sparse", "sparse_or_skip"}:
            underscore = "normal"
        elif music_risk == "high":
            underscore = "sparse"
    dens = _density_from_sources(brief=brief, sonic=sonic, underscore=underscore)
    dens = apply_creative_sfx_density(dens)
    pacing = sap.get("pacing") if isinstance(sap.get("pacing"), dict) else {}
    pace = _norm_pace(str(pacing.get("pace_class") or "conversational"))

    duck = float(sap_mix.get("duck_under_speech_db") or 12.0)
    if pace in {"brisk", "dense"}:
        duck = max(duck, 14.0)
    stinger_cap = float(
        sonic_mix.get("stinger_cap_per_minute")
        or sap_mix.get("stinger_max_per_minute")
        or 4
    )
    bed_range = sap_mix.get("bed_level_db_range") or [-16.0, -12.0]
    if not isinstance(bed_range, list) or len(bed_range) != 2:
        bed_range = [-16.0, -12.0]
    # Default ceiling ~85% so compose can fill mid/late show; min floor stays ~40%.
    coverage = 0.85
    if underscore == "sparse":
        coverage = 0.55
    if underscore in {"skip", "sparse_or_skip"}:
        coverage = 0.0
    elif pace == "dense":
        coverage = 0.85

    mix = {
        "bed_level_db_range": [float(bed_range[0]), float(bed_range[1])],
        "duck_under_speech_db": duck,
        "stinger_max_per_minute": stinger_cap,
        "midrange_policy": str(sap_mix.get("midrange_policy") or "carve_speech"),
        "max_bed_coverage_ratio": coverage,
        "rhythmic_presence_default": sap_mix.get("rhythmic_presence_default") or "none",
        "tempo_feel_bpm": sap_mix.get("tempo_feel_bpm"),
        "underscore_policy": underscore if underscore != "sparse_or_skip" else "sparse",
    }
    mix = apply_creative_mix_contract(mix)
    if creative_delivery_required():
        min_cov = float(min_density_cfg().get("min_bed_coverage_ratio") or 0.40)
        coverage = max(coverage, min_cov)
        mix["max_bed_coverage_ratio"] = coverage
        underscore = str(mix.get("underscore_policy") or underscore)
        # Re-assert high-risk restraint after creative upgrade of sparse→normal.
        if music_risk == "high":
            underscore = "sparse"
            mix["underscore_policy"] = "sparse"
            dens = dict(dens)
            dens["max_beds"] = min(max(int(dens.get("max_beds") or 2), 2), 2)
            coverage = max(0.40, min(float(mix.get("max_bed_coverage_ratio") or 0.40), 0.55))
            mix["max_bed_coverage_ratio"] = coverage
    standards = _standards_for_pace(pace, underscore)
    standards["max_bed_coverage_ratio"] = coverage

    rationale: list[str] = [
        f"pace_class={pace}",
        f"underscore={underscore}",
        f"sfx_density={dens}",
    ]
    if music_risk != "low":
        rationale.append(f"source_music_risk={music_risk}")

    # Prefer Shape narrative_mode soft targets when plan is present.
    plan_mode = None
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        try:
            plan = ctx.read_json("mastering/mastering_plan.json")
        except Exception:
            plan = None
        if isinstance(plan, dict):
            from interview_mux.mastering_plan_loader import plan_is_authoritative

            if plan_is_authoritative(plan):
                plan_mode = str(
                    plan.get("confirmed_mode")
                    or plan.get("narrative_mode")
                    or plan.get("provisional_mode")
                    or ""
                ).strip()
                if plan_mode in {"sparse_source", "conversational_host"}:
                    underscore = "sparse"
                    dens = dict(dens)
                    if creative_delivery_required():
                        dens["max_beds"] = min(max(int(dens.get("max_beds") or 2), 2), 2)
                    else:
                        dens["max_beds"] = min(int(dens.get("max_beds") or 1), 1)
                    dens["max_foley"] = 0
                    coverage = min(max(coverage, 0.40), 0.85)
                    mix["max_bed_coverage_ratio"] = coverage
                    mix["underscore_policy"] = underscore
                    standards["max_bed_coverage_ratio"] = coverage
                    rationale.append(f"mastering_plan_mode_overlay={plan_mode}:sparse")
                elif plan_mode in {"guide_summary", "documentary_bridge"}:
                    underscore = "normal" if underscore == "skip" else underscore
                    mix["underscore_policy"] = underscore
                    rationale.append(f"mastering_plan_mode_overlay={plan_mode}:normal")
                elif plan_mode == "hook_montage":
                    dens = dict(dens)
                    dens["max_punctuators"] = max(int(dens.get("max_punctuators") or 2), 3)
                    mix["stinger_max_per_minute"] = max(
                        float(mix.get("stinger_max_per_minute") or 4), 5.0
                    )
                    rationale.append(f"mastering_plan_mode_overlay={plan_mode}:stinger_bias")

    # Preserve prior operator overrides if rebuilding
    prior_overrides: dict[str, Any] = {}
    if ctx.artifact_exists(POLICY_PATH):
        prior = ctx.read_json(POLICY_PATH)
        if isinstance(prior, dict) and isinstance(prior.get("operator_overrides"), dict):
            prior_overrides = dict(prior["operator_overrides"])

    policy: dict[str, Any] = {
        "version": 1,
        "derived_from": {
            "source_acoustic_profile": bool(sap),
            "sonic_context": bool(sonic),
            "delivery_brief": bool(brief),
            "mastering_plan": bool(plan_mode),
            "sonic_context_hash": (sonic or {}).get("sonic_context_hash"),
        },
        "underscore_policy": underscore if underscore != "sparse_or_skip" else "sparse",
        "pace_class": pace,
        "sfx_density": dens,
        "mix_contract": mix,
        "standards": standards,
        "cue_slots": [],
        "operator_overrides": prior_overrides,
        "rationale": rationale,
    }
    if plan_mode:
        policy["narrative_mode_hint"] = plan_mode
        policy["mastering_plan_bound"] = True
    # F-03: invent gate always last via finalize (overrides → dens → slots → invent → hash).
    return _finalize_policy(ctx, policy, refresh_slots=refresh_slots)


def load_policy(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(POLICY_PATH):
        return None
    data = ctx.read_json(POLICY_PATH)
    if not isinstance(data, dict):
        return None
    # Re-gate on every load so corrupt disk (blocked + dens beds) cannot bypass invent.
    return _finalize_policy(ctx, data, refresh_slots=False)


def resolve_mix_contract(ctx: RunContext) -> dict[str, Any]:
    """Single consumer API: prefer soundscape policy; fall back to SAP."""
    policy = load_policy(ctx)
    if policy and isinstance(policy.get("mix_contract"), dict):
        mc = dict(policy["mix_contract"])
        # Ensure required consumer keys
        out = {
            "duck_under_speech_db": float(mc.get("duck_under_speech_db", 16.0)),
            "underscore_policy": str(mc.get("underscore_policy") or policy.get("underscore_policy") or "normal"),
            "stinger_max_per_minute": float(mc.get("stinger_max_per_minute", 4)),
        }
        if mc.get("bed_level_db_range") is not None:
            out["bed_level_db_range"] = mc["bed_level_db_range"]
        if mc.get("midrange_policy") is not None:
            out["midrange_policy"] = mc["midrange_policy"]
        if mc.get("max_bed_coverage_ratio") is not None:
            out["max_bed_coverage_ratio"] = float(mc["max_bed_coverage_ratio"])
        if mc.get("rhythmic_presence_default") is not None:
            out["rhythmic_presence_default"] = mc["rhythmic_presence_default"]
        out["tempo_feel_bpm"] = mc.get("tempo_feel_bpm")
        sap = load_profile(ctx) or {}
        out["source_music_risk"] = sap.get("source_music_risk") or mc.get("source_music_risk")
        try:
            from interview_mux.mastering_plan_loader import load_plan_raw

            plan = load_plan_raw(ctx) or {}
            card = plan.get("circumstance_card") if isinstance(plan.get("circumstance_card"), dict) else {}
            if card.get("dry_beds"):
                out["dry_beds"] = True
                out["source_music_risk"] = out.get("source_music_risk") or "high"
        except Exception:
            pass
        from interview_mux.creative_delivery import apply_creative_mix_contract

        return apply_creative_mix_contract(out)
    base = sap_mix_contract(ctx)
    # Expand with SAP raw fields when available
    sap = load_profile(ctx) or {}
    raw = sap.get("mix_contract") if isinstance(sap.get("mix_contract"), dict) else {}
    if raw.get("bed_level_db_range") is not None:
        base["bed_level_db_range"] = raw["bed_level_db_range"]
    if raw.get("midrange_policy") is not None:
        base["midrange_policy"] = raw["midrange_policy"]
    if raw.get("max_bed_coverage_ratio") is not None:
        base["max_bed_coverage_ratio"] = raw["max_bed_coverage_ratio"]
    base["source_music_risk"] = sap.get("source_music_risk")
    try:
        from interview_mux.mastering_plan_loader import load_plan_raw

        plan = load_plan_raw(ctx) or {}
        card = plan.get("circumstance_card") if isinstance(plan.get("circumstance_card"), dict) else {}
        if card.get("dry_beds"):
            base["dry_beds"] = True
            base["source_music_risk"] = base.get("source_music_risk") or "high"
    except Exception:
        pass
    from interview_mux.creative_delivery import apply_creative_mix_contract

    return apply_creative_mix_contract(base)


def compact_for_volley(policy: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    slots = [s for s in (policy.get("cue_slots") or []) if isinstance(s, dict)]
    return {
        "policy_hash": policy.get("policy_hash"),
        "underscore_policy": policy.get("underscore_policy"),
        "pace_class": policy.get("pace_class"),
        "sfx_density": policy.get("sfx_density"),
        "mix_contract": {
            k: (policy.get("mix_contract") or {}).get(k)
            for k in (
                "underscore_policy",
                "duck_under_speech_db",
                "stinger_max_per_minute",
                "bed_level_db_range",
                "max_bed_coverage_ratio",
                "midrange_policy",
            )
            if (policy.get("mix_contract") or {}).get(k) is not None
        },
        "standards": policy.get("standards"),
        "cue_slot_ids": [str(s.get("slot_id")) for s in slots[:24]],
        "cue_slots": slots[:24],
    }


def refresh_cue_slots(ctx: RunContext) -> dict[str, Any]:
    """Re-score cue slots using ranking selection; persist updated policy.

    Annotates cue slots with speaker_volley_id / hinge metadata when episode
    structure has speaker_volleys (conversation units — see volley-glossary.md).
    """
    policy = load_policy(ctx)
    if not policy:
        policy = build_policy(ctx, refresh_slots=True)
    else:
        # Rescore then invent-last (load_policy already re-gated without rescoring).
        policy = _finalize_policy(ctx, policy, refresh_slots=True)
    policy = _annotate_slots_with_speaker_volleys(ctx, policy)
    # Re-normalize after annotate so volley fields stay on canonical slots;
    # invent soft-block still applies if unpaid.
    invent_status = invent_obligation_status(ctx)
    if invent_status.get("unpaid"):
        policy = _apply_invent_obligation_gate(
            policy,
            status=invent_status,
            rationale=list(policy.get("rationale") or []),
        )
    else:
        mix = dict(policy.get("mix_contract") or {})
        bed_level = _bed_level_from_mix(mix)
        normalized = [
            n
            for raw in (policy.get("cue_slots") or [])
            if (n := normalize_cue_slot(raw, bed_level=bed_level))
        ]
        policy["cue_slots"] = merge_normalized_cue_slots(normalized)
    policy["policy_hash"] = _policy_hash({k: v for k, v in policy.items() if k != "policy_hash"})
    # Commit even when called from sound_design_plan staging — that stage only
    # flushes SDP, so a staged policy write would be discarded on approve.
    # Ownership ALLOW is soundscape_policy_build only; pass that stage_key so
    # soft-freeze assert_write does not AuthorityDeny mid-SDP (exec_13167).
    try:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(
            ctx, POLICY_PATH, policy, stage_key="soundscape_policy_build"
        )
    except Exception:
        ctx.write_json(POLICY_PATH, policy, stage_key="soundscape_policy_build")
    return policy


def _annotate_slots_with_speaker_volleys(ctx: RunContext, policy: dict[str, Any]) -> dict[str, Any]:
    try:
        from interview_mux.episode_structure import load_episode_structure
        from interview_mux.speaker_volley_sfx import bind_cues_to_speaker_volleys, speaker_volleys_from_structure

        doc = load_episode_structure(ctx)
        volleys = speaker_volleys_from_structure(doc)
        if not volleys:
            return policy
        out = dict(policy)
        slots = [s for s in (out.get("cue_slots") or []) if isinstance(s, dict)]
        out["cue_slots"] = bind_cues_to_speaker_volleys(slots, volleys)
        dens = dict(out.get("sfx_density") or {})
        # Soft honor of delivery_brief.speaker_volley_density when present
        try:
            from interview_mux.delivery_brief import load_delivery_brief

            brief = load_delivery_brief(ctx)
            if isinstance(brief, dict) and isinstance(brief.get("speaker_volley_density"), dict):
                dens["speaker_volley_density"] = brief["speaker_volley_density"]
                out["sfx_density"] = dens
        except Exception:
            pass
        return out
    except Exception:
        return policy


def save_operator_overrides(ctx: RunContext, overrides: dict[str, Any]) -> dict[str, Any]:
    policy = load_policy(ctx) or build_policy(ctx, refresh_slots=False)
    merged = dict(policy.get("operator_overrides") or {})
    incoming = _strip_invent_override_keys(overrides if isinstance(overrides, dict) else {})
    merged.update(incoming)
    policy["operator_overrides"] = _strip_invent_override_keys(merged)
    # Desired prefs live in operator_overrides; invent gate applied last in finalize.
    policy = _finalize_policy(ctx, policy, refresh_slots=True)
    ctx.write_json(POLICY_PATH, policy)
    return policy


def role_bucket(role: str) -> str:
    r = str(role or "")
    if r in _BED_ROLES:
        return "beds"
    if r in _FOLEY_ROLES:
        return "foley"
    if r in _PUNCTUATOR_ROLES:
        return "punctuators"
    return "punctuators"


def persist_soundscape_skip_stub(ctx: RunContext) -> dict[str, Any]:
    """HG-2 2A: schema-valid disabled stub (rationale marks skip; extra keys fail schema)."""
    stub: dict[str, Any] = {
        "version": 1,
        "underscore_policy": "skip",
        "pace_class": "conversational",
        "sfx_density": {},
        "mix_contract": {"underscore_policy": "skip"},
        "standards": {},
        "cue_slots": [],
        "operator_overrides": {},
        "rationale": ["disabled"],
    }
    ctx.write_json(POLICY_PATH, stub, stage_key="soundscape_policy_build")
    from interview_mux.stage_completion import heal_or_refuse_mark

    heal_or_refuse_mark(ctx, "soundscape_policy_build", force=True)
    return stub


def run_soundscape_policy_build(ctx: RunContext) -> None:
    from interview_mux.stage_completion import heal_or_refuse_mark

    if not soundscape_enabled():
        ctx.log("soundscape_policy_build skipped (soundscape.enabled=false)", level="info", stage="soundscape_policy_build")
        persist_soundscape_skip_stub(ctx)
        return
    with logged_step("soundscape_policy_build/build", ctx=ctx, stage="soundscape_policy_build"):
        if not ctx.artifact_exists("understanding/delivery_brief.json"):
            raise RuntimeError("soundscape_policy_build requires understanding/delivery_brief.json")
        policy = build_policy(ctx, refresh_slots=True)
        from interview_mux.prompt_validation import validate_soundscape_policy

        errors = validate_soundscape_policy(policy)
        if errors:
            raise ValueError("soundscape_policy invalid: " + "; ".join(errors[:8]))
        ctx.write_json(POLICY_PATH, policy)
        # SSP-B1 (5A): fail_closed + invent blocked → incomplete (no soft heal-done).
        if fail_closed() and str(policy.get("invent_gate") or "") == "blocked":
            ctx.log(
                "soundscape_policy_build incomplete: invent_gate=blocked under fail_closed",
                level="warning",
                stage="soundscape_policy_build",
                detail={"invent_obligation": policy.get("invent_obligation")},
            )
            raise RuntimeError(
                "soundscape_policy_build incomplete: invent_gate=blocked "
                "(unpaid invent obligation) — resume sound_design_plan or waive invent"
            )
        ctx.log(
            f"soundscape_policy: underscore={policy.get('underscore_policy')} "
            f"pace={policy.get('pace_class')} slots={len(policy.get('cue_slots') or [])} "
            f"hash={(policy.get('policy_hash') or '')[:12]}",
            level="success",
            stage="soundscape_policy_build",
            detail={
                "sfx_density": policy.get("sfx_density"),
                "policy_hash": policy.get("policy_hash"),
            },
        )
    heal_or_refuse_mark(ctx, "soundscape_policy_build", force=True)
