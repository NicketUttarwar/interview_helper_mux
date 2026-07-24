"""Loader for the mastering quality eval corpus.

Corpus spec: docs/cross-cutting/mastering-eval-corpus.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_mux.mastering_feasibility import FeasibilityInputs
from interview_mux.mastering_semantic_integrity import IntegrityInputs

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "mastering_quality"

TAXONOMY: dict[str, tuple[str, ...]] = {
    "topology": ("monologue", "balanced_1on1", "guest_heavy", "panel", "sparse_host"),
    "acoustics": ("clean", "noisy"),
    "duration": ("short", "long"),
    "theme": ("technical", "emotional", "historical", "comedy", "business"),
    "vo_reference": ("none", "excellent"),
    "sfx_assets": ("sparse", "rich"),
    "integrity_risk": ("clean", "landmined"),
}


def fixture_ids() -> list[str]:
    return sorted(p.name for p in CORPUS_DIR.iterdir() if (p / "fixture.json").is_file())


def load_fixture(fixture_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    base = CORPUS_DIR / fixture_id
    fixture = json.loads((base / "fixture.json").read_text(encoding="utf-8"))
    expectations = json.loads((base / "expectations.json").read_text(encoding="utf-8"))
    return fixture, expectations


def feasibility_inputs(fixture: dict[str, Any]) -> FeasibilityInputs:
    topology = fixture.get("topology") or {}
    return FeasibilityInputs(
        segments=fixture.get("segments") or {},
        vo_lines=fixture.get("vo_lines") or {},
        sfx_cues=set(fixture.get("sfx_cues") or []),
        locked_volleys=[list(v) for v in (fixture.get("locked_volleys") or [])],
        pickup_speaker_id=topology.get("pickup_eligible_speaker_id"),
        clone_authorized=bool(fixture.get("clone_authorized")),
        synthesis_available=bool(fixture.get("synthesis_available", True)),
        source_duration_ms=fixture.get("source_duration_ms"),
    )


def integrity_inputs(fixture: dict[str, Any]) -> IntegrityInputs:
    segments = fixture.get("segments") or {}
    return IntegrityInputs(
        segments=segments,
        turn_index={sid: int(seg["turn_index"]) for sid, seg in segments.items() if "turn_index" in seg},
        reaction_segment_ids=set(fixture.get("reaction_segment_ids") or []),
        vo_lines=fixture.get("vo_lines") or {},
        claims=fixture.get("claims") or [],
    )


def candidates(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return list(fixture.get("candidates") or [])
