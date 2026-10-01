"""The sound design plan's asset cap, and the deterministic clamp to it.

One cap, read by the lint and applied by the sanitizer (ISSUES 114): the model
is told the cap and still returns one asset too many often enough that the
pre-flush barrier refused the plan on count while the lint called it a
non-blocking warning. The sanitizer now trims the plan to the cap, assets
referenced by cues first, so the plan on disk never exceeds it.
"""

from __future__ import annotations

from typing import Any


def sound_design_asset_cap(ctx: Any) -> int:
    """Config cap, narrowed by the delivery brief's density budget when present."""
    from interview_mux.config import merged_config

    cfg = merged_config()
    sd = cfg.get("sound_design") or {}
    cap = int(sd.get("max_assets", sd.get("max_assets_flow1", 6)))
    try:
        if ctx is not None and ctx.artifact_exists("understanding/delivery_brief.json"):
            brief = ctx.read_json("understanding/delivery_brief.json")
            dens = brief.get("sfx_density") if isinstance(brief, dict) else {}
            if isinstance(dens, dict):
                brief_cap = sum(int(dens.get(k) or 0) for k in ("max_beds", "max_punctuators", "max_foley"))
                if brief_cap > 0:
                    cap = min(cap, brief_cap)
    except Exception:
        pass
    return max(1, cap)


def _cue_asset_ids(doc: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    flows = doc.get("flow_plans") if isinstance(doc.get("flow_plans"), dict) else {}
    for flow in flows.values():
        if not isinstance(flow, dict):
            continue
        for cue in flow.get("cues") or []:
            if not isinstance(cue, dict):
                continue
            aid = str(cue.get("asset_id") or "").strip()
            if aid and aid not in seen:
                seen.append(aid)
    return seen


#: Roles the creative delivery check requires on the plan (one asset each),
#: and the roles that stand in for them. An unreferenced outro theme was the
#: first thing the clamp dropped in exec_095, and the barrier then refused the
#: plan for "missing music role:theme_outro" (ISSUES 119).
PROTECTED_ROLES: frozenset[str] = frozenset(
    {
        "theme_underscore",
        "theme_cold_open",
        "theme_outro",
        "theme_emphasis",
        "theme_chapter_resolve",
        "theme_transition",
        "era_music_bed",
        "ambient_bed",
        "cold_open",
        "chapter_stinger",
        "transition_stinger",
    }
)


def dedupe_assets(doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Keep the first row of each asset id. Pure; note or None (ISSUES 122)."""
    assets = doc.get("assets")
    if not isinstance(assets, list):
        return doc, None
    seen: set[str] = set()
    kept: list[Any] = []
    dropped: list[str] = []
    for a in assets:
        aid = str(a.get("asset_id") or "").strip() if isinstance(a, dict) else ""
        if aid and aid in seen:
            dropped.append(aid)
            continue
        if aid:
            seen.add(aid)
        kept.append(a)
    if not dropped:
        return doc, None
    out = dict(doc)
    out["assets"] = kept
    return out, {"action": "dedupe_assets", "dropped_duplicates": dropped}


def clamp_assets_to_cap(doc: dict[str, Any], cap: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Trim ``assets`` to ``cap`` distinct ids and drop cues that used the rest.

    Keeps plan order. The first asset of each protected role outranks the
    rest, then assets referenced by cues, then the others. Pure; returns the
    (possibly same) document and an action note or None.
    """
    assets = doc.get("assets")
    if not isinstance(assets, list) or cap <= 0:
        return doc, None
    rows = [a for a in assets if isinstance(a, dict) and a.get("asset_id")]
    ids: list[str] = []
    for a in rows:
        aid = str(a.get("asset_id"))
        if aid not in ids:
            ids.append(aid)
    if len(ids) <= cap:
        return doc, None
    used = set(_cue_asset_ids(doc))
    role_of: dict[str, str] = {}
    for a in rows:
        aid = str(a.get("asset_id"))
        role_of.setdefault(aid, str(a.get("role") or "").strip())
    protected: list[str] = []
    seen_roles: set[str] = set()
    for aid in ids:
        role = role_of.get(aid, "")
        if role in PROTECTED_ROLES and role not in seen_roles:
            protected.append(aid)
            seen_roles.add(role)
    ranked = (
        protected
        + [i for i in ids if i in used and i not in protected]
        + [i for i in ids if i not in used and i not in protected]
    )
    keep = set(ranked[:cap])
    dropped = [i for i in ids if i not in keep]
    out = dict(doc)
    out["assets"] = [a for a in assets if not (isinstance(a, dict) and str(a.get("asset_id") or "") in dropped)]
    flows = out.get("flow_plans")
    cues_dropped = 0
    if isinstance(flows, dict):
        flows = dict(flows)
        for name, flow in list(flows.items()):
            if not isinstance(flow, dict) or not isinstance(flow.get("cues"), list):
                continue
            kept = [
                c
                for c in flow["cues"]
                if not (isinstance(c, dict) and str(c.get("asset_id") or "") in dropped)
            ]
            if len(kept) != len(flow["cues"]):
                cues_dropped += len(flow["cues"]) - len(kept)
                flow = dict(flow)
                flow["cues"] = kept
                flows[name] = flow
        out["flow_plans"] = flows
    return out, {
        "action": "clamp_assets_to_cap",
        "cap": cap,
        "dropped_assets": dropped,
        "dropped_cues": cues_dropped,
    }
