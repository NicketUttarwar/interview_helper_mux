"""Production style profiles — documentary vs TBIY narrative compass."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root
from interview_mux.prompt_examples import prompt_path
from interview_mux.run_context import RunContext

DEFAULT_STYLE = "documentary_interview"
TBIY_STYLE = "tbiy_narrative"


def get_production_style(ctx: RunContext | None = None) -> str:
    if ctx is not None:
        if ctx.artifact_exists("understanding/analysis_state.json"):
            try:
                st = ctx.read_json("understanding/analysis_state.json")
                meta = st.get("meta") if isinstance(st, dict) else {}
                if isinstance(meta, dict) and meta.get("production_style"):
                    return str(meta["production_style"])
            except Exception:
                pass
        if ctx.artifact_exists("understanding/flow_adaptation.json"):
            try:
                adapt = ctx.read_json("understanding/flow_adaptation.json")
                if isinstance(adapt, dict) and adapt.get("production_style"):
                    return str(adapt["production_style"])
            except Exception:
                pass
        if ctx.artifact_exists("run_meta.json"):
            try:
                meta = ctx.read_json("run_meta.json")
                if isinstance(meta, dict) and meta.get("production_style"):
                    return str(meta["production_style"])
            except Exception:
                pass
    return str(merged_config().get("production_style", DEFAULT_STYLE))


def is_tbiy(ctx: RunContext | None = None) -> bool:
    return get_production_style(ctx) == TBIY_STYLE


def get_profile(ctx: RunContext | None = None) -> dict[str, Any]:
    style = get_production_style(ctx)
    profiles = merged_config().get("production_profiles") or {}
    base = profiles.get(DEFAULT_STYLE) or {}
    specific = profiles.get(style) or {}
    out = dict(base)
    out.update(specific)
    out["production_style"] = style
    return out


def prompt_variant(rel_path: str, ctx: RunContext | None = None) -> str:
    """Return tbiy prompt path when profile is tbiy and variant exists."""
    if not is_tbiy(ctx):
        return rel_path
    if ".tbiy." in rel_path:
        return rel_path
    tbiy = rel_path.replace(".system.txt", ".tbiy.system.txt")
    p = prompt_path(*tbiy.split("/"))
    if p.is_file():
        return tbiy
    return rel_path


def mix_rules(ctx: RunContext | None = None) -> dict[str, Any]:
    cfg = merged_config()
    mix = dict(cfg.get("mix") or {})
    if is_tbiy(ctx):
        tbiy_mix = mix.get("tbiy_narrative") or {}
        mix = {**mix, **tbiy_mix}
    profile = get_profile(ctx)
    mix.update(profile.get("mix_overrides") or {})
    return mix


def sfx_caps(ctx: RunContext | None = None) -> dict[str, int]:
    profile = get_profile(ctx)
    sd = merged_config().get("sound_design") or {}
    caps = {
        "max_assets_flow1": int(profile.get("max_assets_flow1") or sd.get("max_assets_flow1", 6)),
        "max_punctuators": int(profile.get("max_punctuators", 4)),
        "max_beds": int(profile.get("max_beds", 2)),
        "max_foley": int(profile.get("max_foley", 2)),
    }
    return caps


def adaptation_defaults(ctx: RunContext | None = None) -> dict[str, Any]:
    profile = get_profile(ctx)
    return dict(profile.get("adaptation_defaults") or {})


def punctuators_enabled(ctx: RunContext | None = None) -> bool:
    profile = get_profile(ctx)
    return bool(profile.get("punctuators_enabled", is_tbiy(ctx)))
