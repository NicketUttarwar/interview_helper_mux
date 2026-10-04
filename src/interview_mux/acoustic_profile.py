"""Shared helpers for understanding/source_acoustic_profile.json."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

SAP_PATH = "understanding/source_acoustic_profile.json"

PACE_CLASS_VALUES = frozenset({"calm", "conversational", "brisk", "dense"})
UNDERSCORE_POLICY_VALUES = frozenset({"normal", "sparse", "skip"})

_DEFAULT_MIX_CONTRACT: dict[str, Any] = {
    "duck_under_speech_db": 12.0,
    "underscore_policy": "normal",
    "stinger_max_per_minute": 4,
}


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(dict(out[key]), val)
        else:
            out[key] = val
    return out


def normalize_operator_overrides(overrides: dict[str, Any]) -> dict[str, Any]:
    """Normalize GUI/flat keys into nested pacing + mix_contract override shape."""
    out: dict[str, Any] = {}
    pacing = overrides.get("pacing")
    if isinstance(pacing, dict) and pacing.get("pace_class"):
        out.setdefault("pacing", {})["pace_class"] = str(pacing["pace_class"])
    elif overrides.get("pace_class"):
        out.setdefault("pacing", {})["pace_class"] = str(overrides["pace_class"])

    mix = overrides.get("mix_contract")
    if isinstance(mix, dict) and mix.get("underscore_policy"):
        out.setdefault("mix_contract", {})["underscore_policy"] = str(mix["underscore_policy"])
    elif overrides.get("underscore_policy"):
        out.setdefault("mix_contract", {})["underscore_policy"] = str(overrides["underscore_policy"])
    return out


def validate_operator_overrides(overrides: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pacing = overrides.get("pacing")
    if isinstance(pacing, dict) and pacing.get("pace_class"):
        pace = str(pacing["pace_class"])
        if pace not in PACE_CLASS_VALUES:
            errors.append(f"operator_overrides.pacing.pace_class must be one of {sorted(PACE_CLASS_VALUES)}")
    mix = overrides.get("mix_contract")
    if isinstance(mix, dict) and mix.get("underscore_policy"):
        policy = str(mix["underscore_policy"])
        if policy not in UNDERSCORE_POLICY_VALUES:
            errors.append(
                f"operator_overrides.mix_contract.underscore_policy must be one of {sorted(UNDERSCORE_POLICY_VALUES)}"
            )
    return errors


def apply_operator_overrides(profile: dict[str, Any]) -> dict[str, Any]:
    """Return profile with operator_overrides deep-merged into derived sections."""
    overrides = profile.get("operator_overrides")
    if not isinstance(overrides, dict) or not overrides:
        return dict(profile)
    merged = dict(profile)
    for key, val in overrides.items():
        if key == "operator_overrides":
            continue
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(dict(merged[key]), val)
        else:
            merged[key] = val
    merged["operator_overrides"] = overrides
    return merged


def load_profile(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(SAP_PATH):
        return None
    data = ctx.read_json(SAP_PATH)
    if not isinstance(data, dict):
        return None
    return apply_operator_overrides(data)


def save_operator_overrides(ctx: RunContext, overrides: dict[str, Any]) -> dict[str, Any]:
    """Persist operator_overrides without re-running DSP. Returns merged profile view."""
    if not ctx.artifact_exists(SAP_PATH):
        raise FileNotFoundError(SAP_PATH)
    raw = ctx.read_json(SAP_PATH)
    if not isinstance(raw, dict):
        raise ValueError("source_acoustic_profile is not a JSON object")
    normalized = normalize_operator_overrides(overrides if isinstance(overrides, dict) else {})
    errors = validate_operator_overrides(normalized)
    if errors:
        raise ValueError("; ".join(errors))
    raw["operator_overrides"] = normalized
    ctx.write_json(SAP_PATH, raw)
    from interview_mux.operator_snapshots import persist_operator_acoustic_overrides

    persist_operator_acoustic_overrides(ctx, normalized, source="acoustic_override_save")
    return apply_operator_overrides(raw)


def mix_contract(ctx: RunContext) -> dict[str, Any]:
    """Prefer unified soundscape policy when present; else SAP mix_contract."""
    try:
        from interview_mux.soundscape_policy import load_policy, resolve_mix_contract

        if load_policy(ctx) is not None:
            return resolve_mix_contract(ctx)
    except Exception:
        pass
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
        # A rate, not a count: int() turned 0.4/min into 0 (ISSUES 165).
        out["stinger_max_per_minute"] = float(raw["stinger_max_per_minute"])
    if raw.get("bed_level_db_range") is not None:
        out["bed_level_db_range"] = raw["bed_level_db_range"]
    if raw.get("midrange_policy") is not None:
        out["midrange_policy"] = raw["midrange_policy"]
    if raw.get("max_bed_coverage_ratio") is not None:
        out["max_bed_coverage_ratio"] = float(raw["max_bed_coverage_ratio"])
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
