"""Deterministic delivery brief — adaptive soft targets for one recording → master."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.config import merged_config
from interview_mux.coverage_limits import (
    delivery_output_ideal_ratio,
    delivery_output_min_ratio,
)
from interview_mux.run_context import RunContext
from interview_mux.run_context import RunContext

DELIVERY_BRIEF_PATH = "understanding/delivery_brief.json"
HIGH_SEVERITY = frozenset({"high", "critical", "blocking"})


def delivery_brief_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = cfg or merged_config()
    return (resolved.get("analysis") or {}).get("delivery_brief") or {}


def delivery_brief_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(delivery_brief_cfg(cfg).get("enabled", True))


def load_delivery_brief(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(DELIVERY_BRIEF_PATH):
        return None
    doc = ctx.read_json(DELIVERY_BRIEF_PATH)
    return doc if isinstance(doc, dict) else None


def _source_duration_ms(ctx: RunContext) -> int:
    if ctx.artifact_exists("transcript/full.json"):
        doc = ctx.read_json("transcript/full.json")
        if isinstance(doc, dict):
            for key in ("duration_ms", "audio_duration_ms"):
                val = doc.get(key)
                if isinstance(val, (int, float)) and val > 0:
                    return int(val)
            items = doc.get("items") or []
            if items and isinstance(items[-1], dict):
                end = items[-1].get("end_ms") or items[-1].get("end")
                if isinstance(end, (int, float)):
                    return int(end)
    if ctx.artifact_exists("ingest/checksums.json"):
        meta = ctx.read_json("ingest/checksums.json")
        if isinstance(meta, dict):
            dur = meta.get("duration_ms") or meta.get("duration_sec")
            if isinstance(dur, (int, float)):
                return int(dur if dur > 10000 else dur * 1000)
    return 0


def _count_record_gaps(ctx: RunContext) -> tuple[int, int]:
    """Return (blocking_severity_record_count, all_record_count)."""
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return 0, 0
    from interview_mux.gates import _line_requires_vo

    rep = ctx.read_json("understanding/gap_report.json")
    lines = []
    if isinstance(rep, dict):
        lines = rep.get("interviewer_lines") or rep.get("lines") or rep.get("gaps") or []
    high = 0
    all_rec = 0
    for row in lines:
        if not isinstance(row, dict):
            continue
        delivery = str(row.get("delivery") or "").lower()
        if delivery and delivery != "record":
            continue
        all_rec += 1
        if _line_requires_vo(row):
            high += 1
    return high, all_rec


def _segment_count(ctx: RunContext) -> int:
    if not ctx.artifact_exists("segments/manifest.json"):
        return 0
    man = ctx.read_json("segments/manifest.json")
    segs = man.get("segments") or [] if isinstance(man, dict) else []
    return len([s for s in segs if isinstance(s, dict)])


def _flow_adaptation(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("understanding/flow_adaptation.json"):
        return {}
    doc = ctx.read_json("understanding/flow_adaptation.json")
    return doc if isinstance(doc, dict) else {}


def build_delivery_brief(ctx: RunContext, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derive soft targets from analysis artifacts + config (+ operator overrides)."""
    cfg = merged_config()
    db_cfg = delivery_brief_cfg(cfg)
    thresholds = (cfg.get("analysis") or {}).get("prompt_thresholds") or {}
    sound = cfg.get("sound_design") or {}
    max_chapters = int(thresholds.get("max_chapters", 8))
    question_max = int(db_cfg.get("question_budget_max", 6))
    ideal_frac = float(db_cfg.get("ideal_fraction_of_source", delivery_output_ideal_ratio()))
    min_ratio = float(db_cfg.get("min_ratio_of_source", delivery_output_min_ratio()))
    max_ratio = float(db_cfg.get("max_ratio_of_source", 1.0))
    min_sec = int(db_cfg.get("min_duration_sec", 600))
    max_sec = int(db_cfg.get("max_duration_sec", 7200))

    source_ms = _source_duration_ms(ctx)
    source_sec = max(0, source_ms // 1000)
    ideal = int(round(source_sec * ideal_frac)) if source_sec else min_sec
    ideal = max(int(source_sec * min_ratio) if source_sec else min_sec, min(max_sec, ideal))
    target_min = max(int(source_sec * min_ratio) if source_sec else min_sec // 2, int(ideal * 0.7))
    target_max = min(max_sec, max(int(source_sec * max_ratio) if source_sec else max_sec, int(ideal * 1.25) if ideal else max_sec))

    high_gaps, all_gaps = _count_record_gaps(ctx)
    q_ideal = min(question_max, high_gaps if high_gaps else all_gaps)
    q_max = min(question_max, max(q_ideal, all_gaps))
    q_min = 0 if q_ideal == 0 else max(0, min(1, q_ideal))

    segs = _segment_count(ctx)
    if segs <= 8:
        ch_ideal = max(1, min(max_chapters, max(2, segs // 2)))
    elif segs <= 24:
        ch_ideal = max(3, min(max_chapters, 5))
    else:
        ch_ideal = max(4, min(max_chapters, 8))
    ch_min = 1
    ch_max = max_chapters

    adapt = _flow_adaptation(ctx)
    sfx = adapt.get("sfx_density") if isinstance(adapt.get("sfx_density"), dict) else {}
    max_assets = int(sound.get("max_assets", sound.get("max_assets_flow1", 6)))
    dens = {
        "max_beds": int(sfx.get("max_beds") or max(1, max_assets // 3)),
        "max_punctuators": int(sfx.get("max_punctuators") or max(1, max_assets // 3)),
        "max_foley": int(sfx.get("max_foley") or max(0, max_assets // 4)),
    }
    weights = adapt.get("ranking_weights") if isinstance(adapt.get("ranking_weights"), dict) else {}

    # Refresh TBIY conformance against brief/gaps when style is tbiy_narrative
    conf_compact: dict[str, Any] | None = None
    five_act_mode = str(adapt.get("five_act_mode") or "soft")
    moat_mode = str(adapt.get("moat_mode") or "soft")
    vo_bridge_priority = str(adapt.get("vo_bridge_priority") or "normal")
    from interview_mux.production_profile import is_tbiy

    if is_tbiy(ctx):
        from interview_mux.tbiy_conformance import compact_conformance_for_volley, refresh_conformance

        plan = refresh_conformance(ctx)
        conf_compact = compact_conformance_for_volley(plan)
        if isinstance(plan, dict):
            modes = plan.get("modes") if isinstance(plan.get("modes"), dict) else {}
            five_act_mode = str(modes.get("five_act_mode") or five_act_mode)
            moat_mode = str(modes.get("moat_mode") or moat_mode)
            vo_bridge_priority = str(modes.get("vo_bridge_priority") or vo_bridge_priority)
            # Re-read adaptation after refresh (weights/sfx may have shifted)
            adapt = _flow_adaptation(ctx)
            if isinstance(adapt.get("sfx_density"), dict):
                sfx = adapt["sfx_density"]
                dens = {
                    "max_beds": int(sfx.get("max_beds") or dens["max_beds"]),
                    "max_punctuators": int(sfx.get("max_punctuators") or dens["max_punctuators"]),
                    "max_foley": int(sfx.get("max_foley") or dens["max_foley"]),
                }
            if isinstance(adapt.get("ranking_weights"), dict):
                weights = adapt["ranking_weights"]
        # High VO-bridge need → nudge question budget toward more short frame lines
        if vo_bridge_priority == "high" and q_ideal < question_max:
            q_ideal = min(question_max, max(q_ideal, high_gaps + 1, 2))
            q_max = min(question_max, max(q_max, q_ideal))
        if five_act_mode == "collapsed":
            ch_ideal = max(ch_min, min(ch_ideal, 4))

    rationale = [
        f"source_duration_ms={source_ms}",
        f"delivery_compression_ratio={round(ideal / source_sec, 3) if source_sec else 0}",
        f"high_severity_record_gaps={high_gaps}",
        f"segment_count={segs}",
        f"topology_style={adapt.get('production_style') or 'unknown'}",
    ]
    if conf_compact:
        score = conf_compact.get("score") if isinstance(conf_compact.get("score"), dict) else {}
        rationale.append(f"tbiy_conformance_ratio={score.get('ratio')}")
        rationale.append(f"five_act_mode={five_act_mode}")
        rationale.append(f"moat_mode={moat_mode}")
        rationale.append(f"vo_bridge_priority={vo_bridge_priority}")

    brief: dict[str, Any] = {
        "version": 1,
        "source_duration_ms": source_ms,
        "target_duration_sec": {"min": target_min, "ideal": ideal, "max": target_max},
        "question_budget": {"min": q_min, "ideal": q_ideal, "max": q_max},
        "chapter_budget": {"min": ch_min, "ideal": ch_ideal, "max": ch_max},
        "selection_mode": "coverage_first",
        "sfx_density": dens,
        # Soft hint: prefer intact speaker volleys (conversation units) over max isolated clips.
        # See docs/cross-cutting/volley-glossary.md — not an LLM message-packet setting.
        "speaker_volley_density": {
            "prefer_intact": True,
            "min_volleys": 0,
            "soft": True,
        },
        "ranking_weights": dict(weights) if weights else {},
        "rationale": rationale,
        "operator_overrides": {},
        "generated": {
            "at": datetime.now(timezone.utc).isoformat(),
            "by": "delivery_brief_build",
        },
    }
    if conf_compact:
        brief["tbiy_conformance"] = conf_compact
        brief["five_act_mode"] = five_act_mode
        brief["moat_mode"] = moat_mode
        brief["vo_bridge_priority"] = vo_bridge_priority

    existing_overrides: dict[str, Any] = {}
    if ctx.artifact_exists(DELIVERY_BRIEF_PATH):
        prev = ctx.read_json(DELIVERY_BRIEF_PATH)
        if isinstance(prev, dict) and isinstance(prev.get("operator_overrides"), dict):
            existing_overrides = dict(prev["operator_overrides"])

    merged_overrides = {**existing_overrides, **(overrides or {})}
    if merged_overrides:
        brief["operator_overrides"] = merged_overrides
        brief = _apply_overrides(brief, merged_overrides)
        brief["rationale"].append("operator_overrides_applied")

    return brief


def _apply_overrides(brief: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    out = dict(brief)
    if isinstance(overrides.get("target_duration_sec"), dict):
        base = dict(out.get("target_duration_sec") or {})
        base.update({k: int(v) for k, v in overrides["target_duration_sec"].items() if v is not None})
        out["target_duration_sec"] = base
    if isinstance(overrides.get("question_budget"), dict):
        base = dict(out.get("question_budget") or {})
        base.update({k: int(v) for k, v in overrides["question_budget"].items() if v is not None})
        out["question_budget"] = base
    if isinstance(overrides.get("chapter_budget"), dict):
        base = dict(out.get("chapter_budget") or {})
        base.update({k: int(v) for k, v in overrides["chapter_budget"].items() if v is not None})
        out["chapter_budget"] = base
    if overrides.get("selection_mode"):
        out["selection_mode"] = str(overrides["selection_mode"])
    if isinstance(overrides.get("sfx_density"), dict):
        dens = dict(out.get("sfx_density") or {})
        dens.update(overrides["sfx_density"])
        out["sfx_density"] = dens
    return out


def apply_delivery_brief_patch(ctx: RunContext, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge operator overrides and rebuild brief."""
    overrides = patch.get("operator_overrides") if isinstance(patch.get("operator_overrides"), dict) else patch
    brief = build_delivery_brief(ctx, overrides=overrides if isinstance(overrides, dict) else {})
    ctx.write_json(DELIVERY_BRIEF_PATH, brief)
    ctx.log("delivery_brief updated (operator patch)", level="info", stage="delivery_brief_build")
    return brief


def rebuild_delivery_brief(ctx: RunContext, *, reason: str = "rebuild") -> dict[str, Any] | None:
    """Rebuild brief preserving operator_overrides when enabled."""
    if not delivery_brief_enabled():
        return load_delivery_brief(ctx)
    brief = build_delivery_brief(ctx)
    ctx.write_json(DELIVERY_BRIEF_PATH, brief, stage_key="delivery_brief_build")
    ctx.log(f"delivery_brief rebuilt ({reason})", level="info", stage="delivery_brief_build")
    return brief


def run_delivery_brief_build(ctx: RunContext) -> None:
    """Pipeline stage: write understanding/delivery_brief.json."""
    if not delivery_brief_enabled():
        ctx.log("delivery_brief disabled; writing minimal stub", level="warning", stage="delivery_brief_build")
        stub = {
            "version": 1,
            "source_duration_ms": _source_duration_ms(ctx),
            "target_duration_sec": {"min": 0, "ideal": 0, "max": 0},
            "question_budget": {"min": 0, "ideal": 0, "max": 0},
            "chapter_budget": {"min": 1, "ideal": 4, "max": 8},
            "selection_mode": "coverage_first",
            "sfx_density": {},
            "ranking_weights": {},
            "rationale": ["disabled"],
            "operator_overrides": {},
            "generated": {"at": datetime.now(timezone.utc).isoformat(), "by": "delivery_brief_build"},
        }
        ctx.write_json(DELIVERY_BRIEF_PATH, stub, stage_key="delivery_brief_build")
        return
    brief = build_delivery_brief(ctx)
    ctx.write_json(DELIVERY_BRIEF_PATH, brief, stage_key="delivery_brief_build")
    ideal = (brief.get("target_duration_sec") or {}).get("ideal")
    q = (brief.get("question_budget") or {}).get("ideal")
    ctx.log(
        f"delivery_brief ready: ideal_duration={ideal}s question_budget={q}",
        level="success",
        stage="delivery_brief_build",
    )
    try:
        from interview_mux.analysis_memory import maybe_auto_verify_profile, update_completion_from_analysis

        update_completion_from_analysis(ctx)
        maybe_auto_verify_profile(ctx)
    except Exception as exc:  # noqa: BLE001
        ctx.log(f"profile auto-verify skipped: {exc}", level="warning", stage="delivery_brief_build")


def estimated_selection_duration_sec(ctx: RunContext) -> float | None:
    """Sum ranked segment durations (+ VO lines when timing present)."""
    if not ctx.artifact_exists("master/selection.json") or not ctx.artifact_exists("segments/manifest.json"):
        return None
    sel = ctx.read_json("master/selection.json")
    man = ctx.read_json("segments/manifest.json")
    if not isinstance(sel, dict) or not isinstance(man, dict):
        return None
    by_id: dict[str, dict[str, Any]] = {}
    for s in man.get("segments") or []:
        if isinstance(s, dict) and s.get("segment_id"):
            by_id[str(s["segment_id"])] = s
    total_ms = 0
    for sid in sel.get("ordered_segment_ids") or []:
        seg = by_id.get(str(sid))
        if not seg:
            continue
        start = seg.get("start_ms")
        end = seg.get("end_ms")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            total_ms += max(0, int(end) - int(start))
            continue
        dur = seg.get("duration_ms") or seg.get("duration_sec")
        if isinstance(dur, (int, float)):
            total_ms += int(dur if dur > 1000 else dur * 1000)
    return total_ms / 1000.0 if total_ms else 0.0


def compact_delivery_brief_for_volley(brief: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compact delivery brief for an LLM volley (message packet). See volley-glossary.md."""
    if not isinstance(brief, dict):
        return None
    out: dict[str, Any] = {
        "target_duration_sec": brief.get("target_duration_sec"),
        "question_budget": brief.get("question_budget"),
        "chapter_budget": brief.get("chapter_budget"),
        "selection_mode": brief.get("selection_mode"),
        "sfx_density": brief.get("sfx_density"),
        "speaker_volley_density": brief.get("speaker_volley_density"),
        "ranking_weights": brief.get("ranking_weights"),
    }
    if brief.get("five_act_mode"):
        out["five_act_mode"] = brief.get("five_act_mode")
    if brief.get("moat_mode"):
        out["moat_mode"] = brief.get("moat_mode")
    if brief.get("vo_bridge_priority"):
        out["vo_bridge_priority"] = brief.get("vo_bridge_priority")
    if isinstance(brief.get("tbiy_conformance"), dict):
        out["tbiy_conformance"] = brief["tbiy_conformance"]
    return out


compact_delivery_brief_for_llm_volley = compact_delivery_brief_for_volley


def attach_delivery_brief_to_payload(ctx: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    brief = load_delivery_brief(ctx)
    compact = compact_delivery_brief_for_volley(brief)
    if compact:
        payload = dict(payload)
        payload["delivery_brief"] = compact
    return payload


__all__ = [
    "DELIVERY_BRIEF_PATH",
    "apply_delivery_brief_patch",
    "attach_delivery_brief_to_payload",
    "build_delivery_brief",
    "compact_delivery_brief_for_volley",
    "delivery_brief_cfg",
    "delivery_brief_enabled",
    "estimated_selection_duration_sec",
    "load_delivery_brief",
    "rebuild_delivery_brief",
    "run_delivery_brief_build",
]
