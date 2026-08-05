"""Percentage-band listenability guards — no numbered hard caps on conversation/SFX.

Budgets and QC use min/max ratios of selection duration, hinge opportunities,
and timeline quartiles. Counts emerge from show length and editorial need.
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

_DEFAULTS: dict[str, float] = {
    "host_vo_coverage_min_ratio": 0.20,
    "host_vo_coverage_max_ratio": 0.85,
    "host_vo_duration_min_ratio": 0.05,
    "host_vo_duration_max_ratio": 0.45,
    "host_vo_quartile_presence_min_ratio": 0.75,
    "bed_coverage_min_ratio": 0.22,
    "bed_coverage_max_ratio": 0.55,
    "bed_quartile_presence_min_ratio": 0.5,
    "hinge_stinger_coverage_min_ratio": 0.5,
    "hinge_stinger_coverage_max_ratio": 1.0,
    "intentional_air_min_ratio": 0.01,
    "intentional_air_max_ratio": 0.12,
    "air_after_vo_fraction": 0.18,
    "air_before_answer_fraction": 0.08,
    "air_at_chapter_hinge_fraction": 0.12,
    "air_pad_floor_ms": 250.0,
    "air_pad_ceil_ms": 1800.0,
    "gap_eval_scored_min_ratio": 0.95,
    "uncovered_high_gap_max_ratio": 0.0,
    "fail_closed": 1.0,
}


def listenability_guards_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg or merged_config()
    creative = root.get("creative_delivery") if isinstance(root.get("creative_delivery"), dict) else {}
    raw = creative.get("listenability_guards") if isinstance(creative.get("listenability_guards"), dict) else {}
    out = dict(_DEFAULTS)
    for key, default in _DEFAULTS.items():
        if key in raw and raw[key] is not None:
            try:
                out[key] = float(raw[key])
            except (TypeError, ValueError):
                out[key] = default
    # Prefer raised bed floor from soundscape when creative delivery is on.
    scape = root.get("soundscape") if isinstance(root.get("soundscape"), dict) else {}
    dens = scape.get("min_density") if isinstance(scape.get("min_density"), dict) else {}
    if dens.get("min_bed_coverage_ratio") is not None:
        try:
            out["bed_coverage_min_ratio"] = max(
                float(out["bed_coverage_min_ratio"]),
                float(dens["min_bed_coverage_ratio"]),
            )
        except (TypeError, ValueError):
            pass
    return out


def _seg_durs(ctx: RunContext) -> dict[str, int]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return {}
    man = ctx.read_json("segments/manifest.json")
    out: dict[str, int] = {}
    for row in (man.get("segments") or []) if isinstance(man, dict) else []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "")
        if not sid:
            continue
        out[sid] = max(0, int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0))
    return out


def _selection_order(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return []
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return []
    return [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]


def selection_duration_ms(ctx: RunContext) -> int:
    durs = _seg_durs(ctx)
    return sum(durs.get(s, 0) for s in _selection_order(ctx))


def quartile_segment_buckets(order: list[str], durs: dict[str, int]) -> list[list[str]]:
    """Split ordered segments into four duration-balanced quartiles."""
    if not order:
        return [[], [], [], []]
    total = sum(durs.get(s, 0) for s in order) or len(order)
    target = total / 4.0
    buckets: list[list[str]] = [[], [], [], []]
    acc = 0
    qi = 0
    for sid in order:
        buckets[min(qi, 3)].append(sid)
        acc += durs.get(sid, 0) or 1
        if qi < 3 and acc >= target * (qi + 1):
            qi += 1
    return buckets


def estimate_bed_coverage_ratio(ctx: RunContext) -> float:
    from interview_mux.soundscape_verify import _estimate_bed_coverage

    return float(_estimate_bed_coverage(ctx))


def bed_quartile_presence(ctx: RunContext) -> float:
    """Fraction of quartiles that have at least one under_segment bed."""
    order = _selection_order(ctx)
    durs = _seg_durs(ctx)
    if not order:
        return 0.0
    bedded: set[str] = set()
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        sdp = ctx.read_json("understanding/sound_design_plan.json")
        if isinstance(sdp, dict):
            flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
            flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
            for c in flow.get("cues") or []:
                if not isinstance(c, dict) or c.get("skip"):
                    continue
                if str(c.get("placement") or "") not in {"under_segment", "under_segment_span"}:
                    continue
                ids = [str(x) for x in (c.get("segment_ids") or []) if x]
                if not ids and c.get("segment_id"):
                    ids = [str(c["segment_id"])]
                bedded.update(ids)
    buckets = quartile_segment_buckets(order, durs)
    present = sum(1 for b in buckets if b and any(s in bedded for s in b))
    nonempty = sum(1 for b in buckets if b)
    return present / nonempty if nonempty else 0.0


def _host_targets_from_gap(ctx: RunContext) -> set[str]:
    targets: set[str] = set()
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return targets
    gr = ctx.read_json("understanding/gap_report.json")
    if not isinstance(gr, dict):
        return targets
    for ln in gr.get("interviewer_lines") or []:
        if not isinstance(ln, dict):
            continue
        if ln.get("skipped_optional"):
            continue
        tid = str(ln.get("targets_segment_id") or ln.get("segment_id") or "")
        if tid:
            targets.add(tid)
    return targets


def host_vo_coverage_ratio(ctx: RunContext, edl: dict[str, Any] | None = None) -> float:
    """Share of selected speech segments preceded by host VO/transition nearby."""
    order = _selection_order(ctx)
    if not order:
        return 0.0
    covered: set[str] = set()
    if edl and isinstance(edl, dict):
        clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
        host_ends: list[int] = []
        for c in clips:
            ctype = str(c.get("type") or "")
            if ctype in {"vo_pickup", "transition", "silence"}:
                if ctype != "silence":
                    start = int(c.get("timeline_start_ms") or 0)
                    dur = int(c.get("duration_ms") or 0)
                    host_ends.append(start + dur)
            elif ctype == "speech":
                sid = str(c.get("segment_id") or "")
                start = int(c.get("timeline_start_ms") or 0)
                # Covered if a host clip ended within 4s before this speech.
                if any(0 <= start - he <= 4000 for he in host_ends):
                    covered.add(sid)
    else:
        covered = _host_targets_from_gap(ctx) & set(order)
        # Also count transition after→before as covering before.
        if ctx.artifact_exists("master/transitions.json"):
            tr = ctx.read_json("master/transitions.json")
            rows = tr.get("transitions") if isinstance(tr, dict) else []
            for t in rows or []:
                if isinstance(t, dict) and t.get("before_segment_id"):
                    covered.add(str(t["before_segment_id"]))
    return len(covered) / len(order)


def host_vo_duration_ratio(ctx: RunContext, edl: dict[str, Any] | None = None) -> float:
    if not edl or not isinstance(edl, dict):
        # Estimate from gap report durations vs selection.
        host_ms = 0
        if ctx.artifact_exists("understanding/gap_report.json"):
            gr = ctx.read_json("understanding/gap_report.json")
            if isinstance(gr, dict):
                for ln in gr.get("interviewer_lines") or []:
                    if not isinstance(ln, dict) or ln.get("skipped_optional"):
                        continue
                    host_ms += int(float(ln.get("estimated_duration_sec") or 6) * 1000)
        total = selection_duration_ms(ctx) + host_ms
        return (host_ms / total) if total else 0.0
    host = speech = 0
    for c in edl.get("clips") or []:
        if not isinstance(c, dict):
            continue
        dur = int(c.get("duration_ms") or 0)
        ctype = str(c.get("type") or "")
        if ctype in {"vo_pickup", "transition"}:
            host += dur
        elif ctype == "speech":
            speech += dur
    denom = host + speech
    return (host / denom) if denom else 0.0


def host_vo_quartile_presence(ctx: RunContext, edl: dict[str, Any] | None = None) -> float:
    order = _selection_order(ctx)
    durs = _seg_durs(ctx)
    if not order:
        return 0.0
    host_near: set[str] = set()
    if edl and isinstance(edl, dict):
        clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
        for i, c in enumerate(clips):
            if str(c.get("type") or "") != "speech":
                continue
            sid = str(c.get("segment_id") or "")
            # Look back up to 3 clips for host.
            for prev in clips[max(0, i - 3) : i]:
                if str(prev.get("type") or "") in {"vo_pickup", "transition"}:
                    host_near.add(sid)
                    break
    else:
        host_near = _host_targets_from_gap(ctx)
    buckets = quartile_segment_buckets(order, durs)
    present = sum(1 for b in buckets if b and any(s in host_near for s in b))
    nonempty = sum(1 for b in buckets if b)
    return present / nonempty if nonempty else 0.0


def hinge_ids(ctx: RunContext) -> list[str]:
    """Chapter/topic hinge segment ids (after which a stinger may land)."""
    ends: list[str] = []
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            for ch in sel.get("chapters") or []:
                if isinstance(ch, dict):
                    segs = [str(x) for x in (ch.get("segment_ids") or []) if x]
                    if segs:
                        ends.append(segs[-1])
    if not ends and ctx.artifact_exists("master/transitions.json"):
        tr = ctx.read_json("master/transitions.json")
        rows = tr.get("transitions") if isinstance(tr, dict) else []
        for t in rows or []:
            if isinstance(t, dict) and t.get("after_segment_id"):
                ends.append(str(t["after_segment_id"]))
    order = _selection_order(ctx)
    if not ends and order:
        # Synthetic hinges every ~quartile boundary.
        durs = _seg_durs(ctx)
        for bucket in quartile_segment_buckets(order, durs):
            if bucket:
                ends.append(bucket[-1])
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for sid in ends:
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def hinge_stinger_coverage_ratio(ctx: RunContext) -> float:
    hinges = hinge_ids(ctx)
    if not hinges:
        return 1.0
    stung: set[str] = set()
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        sdp = ctx.read_json("understanding/sound_design_plan.json")
        if isinstance(sdp, dict):
            flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
            flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
            for c in flow.get("cues") or []:
                if not isinstance(c, dict) or c.get("skip"):
                    continue
                if c.get("placement") not in {"after_segment", "before_segment"}:
                    continue
                for key in ("after_segment_id", "segment_id", "before_segment_id"):
                    if c.get(key):
                        stung.add(str(c[key]))
    hit = sum(1 for h in hinges if h in stung)
    return hit / len(hinges)


def intentional_air_ratio(edl: dict[str, Any] | None) -> float:
    if not edl or not isinstance(edl, dict):
        return 0.0
    air = speechish = 0
    for c in edl.get("clips") or []:
        if not isinstance(c, dict):
            continue
        dur = int(c.get("duration_ms") or 0)
        if str(c.get("type") or "") == "silence":
            air += dur
        else:
            speechish += dur
    total = air + speechish
    return (air / total) if total else 0.0


def air_pad_ms(clip_duration_ms: int, *, kind: str, cfg: dict[str, Any] | None = None) -> int:
    guards = cfg or listenability_guards_cfg()
    frac_key = {
        "after_vo": "air_after_vo_fraction",
        "before_answer": "air_before_answer_fraction",
        "chapter_hinge": "air_at_chapter_hinge_fraction",
    }.get(kind, "air_after_vo_fraction")
    frac = float(guards.get(frac_key) or 0.1)
    floor = int(guards.get("air_pad_floor_ms") or 250)
    ceil = int(guards.get("air_pad_ceil_ms") or 1800)
    raw = int(max(0, clip_duration_ms) * frac)
    return max(floor, min(ceil, raw))


def gap_eval_scored_ratio(ctx: RunContext) -> float:
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return 0.0
    doc = ctx.read_json("understanding/gap_evaluations.json")
    if not isinstance(doc, dict):
        return 0.0
    rows = [r for r in (doc.get("evaluations") or []) if isinstance(r, dict)]
    if not rows:
        return 0.0
    order = set(_selection_order(ctx))
    relevant = [r for r in rows if not order or str(r.get("segment_id") or "") in order]
    if not relevant:
        relevant = rows
    scored = sum(1 for r in relevant if r.get("severity") or r.get("gap_type"))
    return scored / len(relevant)


def uncovered_high_gap_ratio(ctx: RunContext) -> float:
    """Share of *selected* high-severity gaps still lacking host VO coverage.

    Gaps on excluded segments are ignored — selection is air-order authority and
    leftover reinclusion is banned.
    """
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return 0.0
    evals = ctx.read_json("understanding/gap_evaluations.json")
    if not isinstance(evals, dict):
        return 0.0
    selected: set[str] = set()
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            selected = {str(s) for s in (sel.get("ordered_segment_ids") or []) if s}
    highs = [
        str(r.get("segment_id") or "")
        for r in (evals.get("evaluations") or [])
        if isinstance(r, dict)
        and str(r.get("severity") or "").lower() == "high"
        and r.get("segment_id")
        and (not selected or str(r.get("segment_id")) in selected)
    ]
    if not highs:
        return 0.0
    covered = _host_targets_from_gap(ctx)
    # Pair-bound transitions also cover the following selected segment.
    if ctx.artifact_exists("master/transitions.json"):
        tr = ctx.read_json("master/transitions.json")
        for row in (tr.get("transitions") or []) if isinstance(tr, dict) else []:
            if isinstance(row, dict) and row.get("before_segment_id") and str(row.get("text") or "").strip():
                covered.add(str(row["before_segment_id"]))
    missing = [s for s in highs if s not in covered]
    return len(missing) / len(highs)


def required_sfx_roles_present(ctx: RunContext) -> list[str]:
    """Return missing required roles (empty if OK). Music-only creative delivery."""
    required = {"theme_underscore", "theme_cold_open"}
    accent_family = {
        "theme_emphasis",
        "theme_chapter_resolve",
        "theme_transition",
        "theme_outro",
    }
    roles: set[str] = set()
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        sdp = ctx.read_json("understanding/sound_design_plan.json")
        if isinstance(sdp, dict):
            for a in sdp.get("assets") or []:
                if isinstance(a, dict) and a.get("role"):
                    roles.add(str(a["role"]))
            # Legacy aliases map to theme requirements during migration.
            if "era_music_bed" in roles or "ambient_bed" in roles:
                roles.add("theme_underscore")
            if "cold_open" in roles:
                roles.add("theme_cold_open")
            if "chapter_stinger" in roles or "transition_stinger" in roles:
                roles.add("theme_chapter_resolve")
    missing = sorted(required - roles)
    if not (roles & accent_family):
        missing.append("theme_emphasis_or_resolve")
    return missing


def soft_unique_asset_guidance(selection_ms: int) -> int:
    """Soft unique-asset guidance from show length (not a hard reject ceiling)."""
    minutes = max(1.0, selection_ms / 60000.0)
    # ~1 unique role asset per 3 minutes, clamped softly for planning hints only.
    return max(3, min(16, int(round(minutes / 3.0)) + 2))


def evaluate_listenability(
    ctx: RunContext,
    *,
    edl: dict[str, Any] | None = None,
    stage: str = "listenability",
) -> dict[str, Any]:
    """Measure ratios vs bands. Returns report with failures list."""
    from interview_mux.creative_delivery import creative_delivery_required

    guards = listenability_guards_cfg()
    failures: list[str] = []
    metrics: dict[str, Any] = {}

    if not creative_delivery_required():
        return {
            "version": 1,
            "verdict": "pass",
            "failures": [],
            "metrics": {},
            "skipped": "creative_delivery_not_required",
            "stage": stage,
        }

    bed_cov = estimate_bed_coverage_ratio(ctx)
    bed_q = bed_quartile_presence(ctx)
    host_cov = host_vo_coverage_ratio(ctx, edl)
    host_dur = host_vo_duration_ratio(ctx, edl)
    host_q = host_vo_quartile_presence(ctx, edl)
    hinge_c = hinge_stinger_coverage_ratio(ctx)
    air_r = intentional_air_ratio(edl)
    gap_scored = gap_eval_scored_ratio(ctx)
    uncovered = uncovered_high_gap_ratio(ctx)
    missing_roles = required_sfx_roles_present(ctx)

    metrics = {
        "bed_coverage_ratio": round(bed_cov, 4),
        "bed_quartile_presence_ratio": round(bed_q, 4),
        "host_vo_coverage_ratio": round(host_cov, 4),
        "host_vo_duration_ratio": round(host_dur, 4),
        "host_vo_quartile_presence_ratio": round(host_q, 4),
        "hinge_stinger_coverage_ratio": round(hinge_c, 4),
        "intentional_air_ratio": round(air_r, 4),
        "gap_eval_scored_ratio": round(gap_scored, 4),
        "uncovered_high_gap_ratio": round(uncovered, 4),
        "missing_sfx_roles": missing_roles,
        "bands": {k: guards[k] for k in guards},
    }

    def _below(name: str, value: float, key: str) -> None:
        floor = float(guards[key])
        if value + 0.001 < floor:
            failures.append(f"{name} {value:.3f} < min {floor:.3f}")

    def _above(name: str, value: float, key: str) -> None:
        ceil = float(guards[key])
        if value > ceil + 0.001:
            failures.append(f"{name} {value:.3f} > max {ceil:.3f}")

    _below("bed_coverage", bed_cov, "bed_coverage_min_ratio")
    _above("bed_coverage", bed_cov, "bed_coverage_max_ratio")
    _below("bed_quartile_presence", bed_q, "bed_quartile_presence_min_ratio")

    # Host conversation bands — only when gap framing produced (or should produce) VO.
    enforce_host = False
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        enforce_host = bool(gap_framing_enabled(ctx))
    except Exception:
        enforce_host = ctx.artifact_exists("understanding/gap_report.json")
    if enforce_host and ctx.artifact_exists("understanding/gap_report.json"):
        gr = ctx.read_json("understanding/gap_report.json")
        lines = (gr.get("interviewer_lines") or []) if isinstance(gr, dict) else []
        if lines:
            _below("host_vo_coverage", host_cov, "host_vo_coverage_min_ratio")
            _above("host_vo_coverage", host_cov, "host_vo_coverage_max_ratio")
            _below("host_vo_duration", host_dur, "host_vo_duration_min_ratio")
            _above("host_vo_duration", host_dur, "host_vo_duration_max_ratio")
            _below("host_vo_quartile_presence", host_q, "host_vo_quartile_presence_min_ratio")
            if uncovered > float(guards["uncovered_high_gap_max_ratio"]) + 0.001:
                failures.append(f"uncovered_high_gap_ratio {uncovered:.3f} exceeds max")

    _below("hinge_stinger_coverage", hinge_c, "hinge_stinger_coverage_min_ratio")
    _above("hinge_stinger_coverage", hinge_c, "hinge_stinger_coverage_max_ratio")
    if edl is not None:
        _below("intentional_air", air_r, "intentional_air_min_ratio")
        _above("intentional_air", air_r, "intentional_air_max_ratio")
    if gap_scored + 0.001 < float(guards["gap_eval_scored_min_ratio"]) and enforce_host:
        failures.append(
            f"gap_eval_scored {gap_scored:.3f} < min {guards['gap_eval_scored_min_ratio']:.3f}"
        )
    if missing_roles:
        failures.append(f"missing_sfx_roles:{','.join(missing_roles)}")

    return {
        "version": 1,
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
        "metrics": metrics,
        "stage": stage,
        "fail_closed": bool(float(guards.get("fail_closed") or 0) >= 0.5),
    }


def write_listenability_contract(ctx: RunContext, report: dict[str, Any]) -> None:
    ctx.write_json("master/listenability_contract.json", report, stage_key="mix")
