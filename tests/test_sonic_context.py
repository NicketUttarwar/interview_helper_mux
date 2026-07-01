from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.analysis_memory import default_analysis_state
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import build_sonic_context
from run_fixtures import (
    isolated_run_ctx,
    minimal_manifest_segment,
    minimal_source_acoustic_profile,
    seed_from_sonic_fixture,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sonic_context"
SONIC_FIXTURE_NAMES = sorted(p.stem for p in FIXTURE_DIR.glob("*.json"))


def _seed_base(ctx: RunContext) -> None:
    state = default_analysis_state(ctx.run_id)
    state["style"]["format_class"] = "one_on_one"
    state["style"]["tone_class"] = "journalistic"
    ctx.write_json("understanding/analysis_state.json", state, skip_handoff=True)
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Interview on execution quality.",
            "topics": [{"name": "Product strategy", "summary": "Roadmap and delivery.", "segment_ids": ["seg_001"]}],
            "emotional_beats": [{"label": "measured confidence", "segment_ids": ["seg_001"]}],
        },
        skip_handoff=True,
    )
    ctx.write_json("understanding/source_acoustic_profile.json", minimal_source_acoustic_profile(), skip_handoff=True)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                minimal_manifest_segment("seg_001", start_ms=0, end_ms=6000, speaker_id="host", speaker_role="interviewer"),
                minimal_manifest_segment(
                    "seg_002",
                    start_ms=6200,
                    end_ms=12000,
                    speaker_id="guest_a",
                    speaker_role="interviewee",
                    topic_tags=["execution", "tradeoffs"],
                ),
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "flow_1_master/narrative_plan.json",
        {"chapters": [], "arc_summary": "test", "ordering_constraints": []},
        skip_handoff=True,
    )
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []}, skip_handoff=True)
    ctx.write_json("understanding/value_features.json", {"profiles": {}}, skip_handoff=True)


@pytest.mark.parametrize("fixture_name", SONIC_FIXTURE_NAMES)
def test_sonic_fixture_atlas_and_mix_policy(tmp_path, monkeypatch, fixture_name: str):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, f"sonic_{fixture_name}")
    expected = seed_from_sonic_fixture(ctx, fixture_name, seed_base=False)

    doc = ctx.read_json("understanding/sonic_context.json")
    scenario = expected.get("scenario") if isinstance(expected.get("scenario"), dict) else {}
    mix = expected.get("mix_policy") if isinstance(expected.get("mix_policy"), dict) else {}
    flags = expected.get("segment_flags") if isinstance(expected.get("segment_flags"), dict) else {}

    assert doc["scenario"]["atlas_bucket"] == scenario.get("atlas_bucket")
    assert doc["mix_policy"]["adaptive_max_assets_flow1"] == mix.get("adaptive_max_assets_flow1")
    assert doc["mix_policy"]["adaptive_max_assets_flow2"] == mix.get("adaptive_max_assets_flow2")
    if flags:
        for key in ("overlap_high", "trauma_adjacent", "jargon_dense"):
            if key in flags:
                assert doc["segment_flags"].get(key) == flags.get(key)


def test_build_sonic_context_panel_bucket(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "sonic_panel")
    _seed_base(ctx)
    manifest = ctx.read_json("segments/manifest.json")
    manifest["segments"].append(
        minimal_manifest_segment(
            "seg_003",
            start_ms=12200,
            end_ms=17000,
            speaker_id="guest_b",
            speaker_role="interviewee",
            topic_tags=["coordination"],
        )
    )
    manifest["segments"].append(
        minimal_manifest_segment(
            "seg_004",
            start_ms=17200,
            end_ms=22000,
            speaker_id="guest_c",
            speaker_role="interviewee",
            topic_tags=["ops"],
        )
    )
    ctx.write_json("segments/manifest.json", manifest, skip_handoff=True)

    doc = build_sonic_context(ctx)
    assert doc["scenario"]["atlas_bucket"] == "panel"


def test_build_sonic_context_trauma_adjacent_bucket(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "sonic_trauma")
    _seed_base(ctx)
    brief = ctx.read_json("understanding/content_brief.json")
    brief["emotional_beats"] = [{"label": "grief and loss", "segment_ids": ["seg_002"]}]
    brief["topics"].append({"name": "trauma response", "summary": "coping and support", "segment_ids": ["seg_002"]})
    ctx.write_json("understanding/content_brief.json", brief, skip_handoff=True)

    doc = build_sonic_context(ctx)
    assert doc["scenario"]["atlas_bucket"] == "trauma_adjacent"
    assert "no playful/comedic motifs" in doc["avoid_hard"]


def test_build_sonic_context_dense_jargon_bucket(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "sonic_jargon")
    _seed_base(ctx)
    manifest = ctx.read_json("segments/manifest.json")
    manifest["segments"][1]["topic_tags"] = ["api", "sdk", "latency", "throughput", "schema"]
    ctx.write_json("segments/manifest.json", manifest, skip_handoff=True)

    doc = build_sonic_context(ctx)
    assert doc["scenario"]["atlas_bucket"] == "dense_jargon"
    assert doc["mix_policy"]["adaptive_max_assets_flow1"] <= 3
