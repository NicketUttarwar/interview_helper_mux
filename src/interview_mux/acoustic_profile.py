"""Shared helpers for understanding/source_acoustic_profile.json."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

SAP_PATH = "understanding/source_acoustic_profile.json"

_DEFAULT_MIX_CONTRACT: dict[str, Any] = {
    "duck_under_speech_db": 16.0,
    "underscore_policy": "normal",
    "stinger_max_per_minute": 4,
}


def load_profile(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(SAP_PATH):
        return None
    data = ctx.read_json(SAP_PATH)
    return data if isinstance(data, dict) else None


def mix_contract(ctx: RunContext) -> dict[str, Any]:
    profile = load_profile(ctx)
    if not profile:
        return dict(_DEFAULT_MIX_CONTRACT)
    raw = profile.get("mix_contract")
    if not isinstance(raw, dict):
        return dict(_DEFAULT_MIX_CONTRACT)
    out = dict(_DEFAULT_MIX_CONTRACT)
    if raw.get("duck_under_speech_db") is not None:
        out["duck_under_speech_db"] = float(raw["duck_under_speech_db"])
    if raw.get("underscore_policy"):
        out["underscore_policy"] = str(raw["underscore_policy"])
    if raw.get("stinger_max_per_minute") is not None:
        out["stinger_max_per_minute"] = int(raw["stinger_max_per_minute"])
    return out


def placement_hints(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    hints = profile.get("placement_hints")
    return hints if isinstance(hints, dict) else {}


def pacing_one_liner(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    pacing = profile.get("pacing") if isinstance(profile.get("pacing"), dict) else {}
    pace = pacing.get("pace_class", "unknown")
    wpm = pacing.get("global_wpm", "?")
    pause = pacing.get("pause_p50_ms", "?")
    return f"pace={pace} wpm={wpm} pause_p50={pause}ms"


def compact_for_volley(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    out: dict[str, Any] = {}
    pacing = profile.get("pacing") if isinstance(profile.get("pacing"), dict) else {}
    if pacing.get("pace_class"):
        out["pace_class"] = pacing["pace_class"]
    if pacing.get("global_wpm") is not None:
        out["global_wpm"] = pacing["global_wpm"]
    mix = profile.get("mix_contract") if isinstance(profile.get("mix_contract"), dict) else {}
    if mix:
        out["mix_contract"] = {
            k: mix[k]
            for k in ("underscore_policy", "duck_under_speech_db", "stinger_max_per_minute")
            if k in mix
        }
    hints = placement_hints(profile)
    if hints:
        out["placement_hints"] = hints
    return out
