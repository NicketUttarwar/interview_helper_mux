"""Tape character detection and policy packs for refinement."""

from __future__ import annotations

from typing import Any

from interview_mux.refinement_catalog import ELIGIBLE_CLASS_VOCAB, refinement_cfg
from interview_mux.run_context import RunContext

POLICY_PACKS: dict[str, dict[str, Any]] = {
    "short_clean": {
        "eligible_class_defaults": [],
        "simple_tape_override": True,
        "kill_dull_aggression": "low",
        "sfx_restraint": "high",
        "midpass_shard_threshold_sec": 99999,
    },
    "asymmetric_technical": {
        "eligible_class_defaults": ["gap_vo", "transitions", "cold_open", "sdp_intent"],
        "simple_tape_override": False,
        "kill_dull_aggression": "high",
        "sfx_restraint": "med",
        "midpass_shard_threshold_sec": 1800,
        "interviewer_summary_max_words": 80,
    },
    "panel_multi_guest": {
        "eligible_class_defaults": ["gap_vo", "ranking", "transitions"],
        "simple_tape_override": False,
        "kill_dull_aggression": "med",
        "sfx_restraint": "med",
        "midpass_shard_threshold_sec": 2400,
    },
    "long_meander": {
        "eligible_class_defaults": ["gap_vo", "narrative", "ranking", "transitions", "edl_narrative"],
        "simple_tape_override": False,
        "kill_dull_aggression": "high",
        "sfx_restraint": "high",
        "midpass_shard_threshold_sec": 900,
    },
    "default": {
        "eligible_class_defaults": ["gap_vo", "transitions", "sdp_intent"],
        "simple_tape_override": False,
        "kill_dull_aggression": "med",
        "sfx_restraint": "med",
        "midpass_shard_threshold_sec": 1800,
    },
}


def detect_tape_character(ctx: RunContext) -> list[str]:
    chars: list[str] = []
    topology: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/source_topology.json"):
        raw = ctx.read_json("understanding/source_topology.json")
        if isinstance(raw, dict):
            topology = raw
    tclass = str(topology.get("topology_class") or topology.get("class") or "")
    if "asymmetric" in tclass:
        chars.append("asymmetric_host_light")
    if "monologue" in tclass:
        chars.append("monologue_heavy")
    if "panel" in tclass or "multi" in tclass:
        chars.append("panel_multi_guest")

    high_gaps = 0
    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        ge = ctx.read_json("understanding/gap_evaluations.json")
        evals = (ge or {}).get("evaluations") if isinstance(ge, dict) else []
        for ev in evals or []:
            if isinstance(ev, dict) and str(ev.get("severity") or "").lower() == "high":
                high_gaps += 1
            gt = str((ev or {}).get("gap_type") or "")
            if "definition" in gt:
                if "technical_jargon" not in chars:
                    chars.append("technical_jargon")
    duration = 0.0
    if ctx.artifact_exists("understanding/source_acoustic_profile.json"):
        sap = ctx.read_json("understanding/source_acoustic_profile.json")
        if isinstance(sap, dict):
            duration = float(sap.get("duration_sec") or sap.get("duration") or 0)
    if duration and duration < 600 and high_gaps <= 1:
        chars.append("short_clean")
    if duration and duration > 3600:
        chars.append("long_meander")
    if not chars:
        chars.append("default_balanced")
    return chars


def resolve_policy_pack(ctx: RunContext, characters: list[str] | None = None) -> dict[str, Any]:
    chars = characters if characters is not None else detect_tape_character(ctx)
    cfg_packs = (refinement_cfg().get("policy_packs") or {}) if isinstance(refinement_cfg(), dict) else {}
    packs = {**POLICY_PACKS, **(cfg_packs if isinstance(cfg_packs, dict) else {})}

    if "short_clean" in chars and "asymmetric_host_light" not in chars:
        pack_id = "short_clean"
    elif "long_meander" in chars:
        pack_id = "long_meander"
    elif "panel_multi_guest" in chars:
        pack_id = "panel_multi_guest"
    elif "asymmetric_host_light" in chars or "technical_jargon" in chars:
        pack_id = "asymmetric_technical"
    else:
        pack_id = "default"

    base = dict(packs.get(pack_id) or packs["default"])
    base["pack_id"] = pack_id
    base["tape_character"] = list(chars)
    # Clamp eligible to vocab
    elig = [c for c in (base.get("eligible_class_defaults") or []) if c in ELIGIBLE_CLASS_VOCAB]
    base["eligible_class_defaults"] = elig
    return base


def is_simple_tape(ctx: RunContext) -> bool:
    pack = resolve_policy_pack(ctx)
    return bool(pack.get("simple_tape_override"))
