"""Probe registry for the Local Audio Probe Platform."""

from __future__ import annotations

from typing import Any

# Catalog version bumps invalidate audio_probe_build fingerprints.
PROBE_CATALOG_VERSION = "1"

PROBES: list[dict[str, Any]] = [
    {
        "probe_id": "vprobe.multilingual_or_uncommon",
        "pack": "vernacular",
        "prompt_file": "multilingual_or_uncommon.system.txt",
        "output": "YES_NO",
        "budget_class": "vernacular",
        "prefilter": "vernacular_candidate",
        "gate_class": "hard_must_keep",
        "escalation": ["vprobe.extract_keywords", "vprobe.span_hint"],
    },
    {
        "probe_id": "vprobe.non_english_speech",
        "pack": "vernacular",
        "prompt_file": "non_english_speech.system.txt",
        "output": "YES_NO",
        "budget_class": "vernacular",
        "prefilter": "vernacular_candidate",
        "gate_class": "hard_must_keep",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.uncommon_english",
        "pack": "vernacular",
        "prompt_file": "uncommon_english.system.txt",
        "output": "YES_NO",
        "budget_class": "vernacular",
        "prefilter": "vernacular_candidate",
        "gate_class": "hard_must_keep",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.extract_keywords",
        "pack": "vernacular",
        "prompt_file": "extract_keywords.system.txt",
        "output": "KEYWORDS",
        "budget_class": "vernacular",
        "prefilter": "escalation_only",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.span_hint",
        "pack": "vernacular",
        "prompt_file": "span_hint.system.txt",
        "output": "SPANS",
        "budget_class": "vernacular",
        "prefilter": "escalation_only",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.passion_or_emphasis",
        "pack": "salience",
        "prompt_file": "passion_or_emphasis.system.txt",
        "output": "LEVEL",
        "budget_class": "salience",
        "prefilter": "stress_or_salience",
        "gate_class": "soft_prefer",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.pull_quote",
        "pack": "salience",
        "prompt_file": "pull_quote.system.txt",
        "output": "YES_NO",
        "budget_class": "salience",
        "prefilter": "stress_or_salience",
        "gate_class": "soft_prefer",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.speech_act",
        "pack": "structure",
        "prompt_file": "speech_act.system.txt",
        "output": "ACT",
        "budget_class": "salience",
        "prefilter": "always_sample",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.crosstalk",
        "pack": "defect",
        "prompt_file": "crosstalk.system.txt",
        "output": "YES_NO",
        "budget_class": "defect",
        "prefilter": "low_confidence",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.non_speech_bleed",
        "pack": "defect",
        "prompt_file": "non_speech_bleed.system.txt",
        "output": "YES_NO",
        "budget_class": "defect",
        "prefilter": "low_confidence",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.unintelligible",
        "pack": "defect",
        "prompt_file": "unintelligible.system.txt",
        "output": "YES_NO",
        "budget_class": "defect",
        "prefilter": "low_confidence",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.affect_burst",
        "pack": "salience",
        "prompt_file": "affect_burst.system.txt",
        "output": "YES_NO",
        "budget_class": "salience",
        "prefilter": "stress_or_salience",
        "gate_class": "soft_prefer",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.name_or_title",
        "pack": "entities",
        "prompt_file": "name_or_title.system.txt",
        "output": "KEYWORDS",
        "budget_class": "salience",
        "prefilter": "always_sample",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.sensitive_disclosure",
        "pack": "safety",
        "prompt_file": "sensitive_disclosure.system.txt",
        "output": "YES_NO",
        "budget_class": "safety",
        "prefilter": "long_turn",
        "gate_class": "safety",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.disagreement",
        "pack": "narrative",
        "prompt_file": "disagreement.system.txt",
        "output": "YES_NO",
        "budget_class": "narrative",
        "prefilter": "stress_or_salience",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.nonliteral",
        "pack": "fidelity",
        "prompt_file": "nonliteral.system.txt",
        "output": "YES_NO",
        "budget_class": "narrative",
        "prefilter": "stress_or_salience",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.acoustic_discontinuity",
        "pack": "defect",
        "prompt_file": "acoustic_discontinuity.system.txt",
        "output": "YES_NO",
        "budget_class": "defect",
        "prefilter": "low_confidence",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.retelling",
        "pack": "narrative",
        "prompt_file": "retelling.system.txt",
        "output": "YES_NO",
        "budget_class": "narrative",
        "prefilter": "long_turn",
        "gate_class": "advisory",
        "escalation": [],
    },
    {
        "probe_id": "vprobe.payoff_moment",
        "pack": "narrative",
        "prompt_file": "payoff_moment.system.txt",
        "output": "YES_NO",
        "budget_class": "narrative",
        "prefilter": "stress_or_salience",
        "gate_class": "soft_prefer",
        "escalation": [],
    },
]

_BY_ID = {p["probe_id"]: p for p in PROBES}


def probe_by_id(probe_id: str) -> dict[str, Any] | None:
    return _BY_ID.get(probe_id)


def probes_for_packs(enabled_packs: set[str] | None = None) -> list[dict[str, Any]]:
    if not enabled_packs:
        return list(PROBES)
    return [p for p in PROBES if p.get("pack") in enabled_packs]


def primary_gate_probes() -> list[dict[str, Any]]:
    """Probes that run on candidates (not escalation-only)."""
    return [p for p in PROBES if p.get("prefilter") != "escalation_only"]
