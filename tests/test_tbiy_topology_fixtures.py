"""TBIY topology fixture validation and listen-QC checklist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "tbiy"

TOPOLOGY_PROFILES = (
    "one_on_one_asymmetric",
    "one_on_one_balanced",
    "multi_idea_sparse_host",
    "monologue_heavy",
)


@pytest.mark.parametrize("profile", TOPOLOGY_PROFILES)
def test_tbiy_topology_fixture_pair(profile: str) -> None:
    root = FIXTURE_ROOT / profile
    topo = json.loads((root / "topology.json").read_text(encoding="utf-8"))
    adapt = json.loads((root / "flow_adaptation.json").read_text(encoding="utf-8"))
    assert topo["topology_class"] == profile
    assert adapt["topology_class"] == profile
    assert topo["pickup_eligible_speaker_id"] == topo["least_spoken_speaker_id"]
    assert adapt["pickup_eligible_speaker_id"] == topo["pickup_eligible_speaker_id"]
    assert adapt["production_style"] == "tbiy_narrative"
    assert "segmentation_policy" in adapt
    assert "sfx_density" in adapt


def test_tbiy_qc_checklist_documents_all_profiles() -> None:
    checklist = (
        Path(__file__).resolve().parents[1]
        / "CURSOR_EXECUTE"
        / "flow1-gui-e2e"
        / "fixtures"
        / "tbiy"
        / "qc-checklist.md"
    )
    text = checklist.read_text(encoding="utf-8")
    for profile in TOPOLOGY_PROFILES:
        assert profile in text
