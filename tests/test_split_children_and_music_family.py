"""Family sweep after ISSUES 164/165: positions by family or duration, roles kept apart (ISSUES 166)."""

from __future__ import annotations

from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx

INTRO = [f"seg_001{c}" for c in "defghijk"]
STORY = ["seg_014", "seg_015", "seg_016", "seg_017", "seg_019", "seg_020"]


def test_family_positions_count_a_split_intro_once() -> None:
    from interview_mux.air_order_integrity import family_air_positions

    pos = family_air_positions(INTRO + STORY)
    assert {pos[s] for s in INTRO} == {0}
    assert pos["seg_014"] == 1 and pos["seg_020"] == 6


def test_duration_spread_skips_short_children() -> None:
    from interview_mux.artifact_repairs import _duration_spread_ids

    durs = {s: 4000 for s in INTRO}
    durs.update({"seg_014": 90000, "seg_015": 60000, "seg_016": 80000, "seg_017": 70000, "seg_019": 50000, "seg_020": 85000})
    picks = _duration_spread_ids(INTRO + STORY, durs, 4)
    assert picks and not set(picks) & set(INTRO)


def test_density_budget_keeps_a_slot_per_role() -> None:
    from interview_mux.soundscape_policy import _density_from_sources as d

    def at(cap: int) -> dict:
        return d(brief=None, sonic={"mix_policy": {"adaptive_max_assets_flow1": cap}}, underscore="")

    assert sum(at(2).values()) == 2
    assert at(3) == {"max_beds": 1, "max_punctuators": 1, "max_foley": 1}
    assert sum(at(4).values()) == 4


def test_legacy_bookend_names_are_not_duplicates() -> None:
    from interview_mux.music_lane import collapse_duplicate_music_cues

    assets = {"m": {"asset_id": "m", "role": "motif"}, "f": {"asset_id": "f", "role": "full_bed"}}
    cues = [
        {"cue_id": "a", "asset_id": "m", "placement": "after_segment", "segment_id": "seg_9"},
        {"cue_id": "b", "asset_id": "f", "placement": "after_segment", "segment_id": "seg_9"},
    ]
    out, _ = collapse_duplicate_music_cues(cues, assets)
    assert [c["cue_id"] for c in out] == ["a", "b"]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    import json

    c = isolated_run_ctx(tmp_path, "exec_family_sweep")
    sel = c.run_dir / "master" / "selection.json"
    sel.parent.mkdir(parents=True, exist_ok=True)
    sel.write_text(json.dumps({"ordered_segment_ids": INTRO + STORY}))
    return c


def test_hydrate_anchors_bookends_by_role(ctx) -> None:
    from interview_mux.creative_delivery import hydrate_flow_cue_segments

    sdp = {
        "assets": [
            {"asset_id": "motif", "role": "theme_cold_open"},
            {"asset_id": "close", "role": "theme_outro"},
        ],
        "flow_plans": {
            "podcast": {
                "cues": [
                    {"cue_id": "open", "asset_id": "motif", "placement": "after_segment"},
                    {"cue_id": "close", "asset_id": "close", "placement": "after_segment"},
                ]
            }
        },
    }
    hydrate_flow_cue_segments(ctx, sdp)
    open_cue, close_cue = sdp["flow_plans"]["podcast"]["cues"]
    assert open_cue["placement"] == "before_segment" and open_cue["segment_id"] == INTRO[0]
    assert close_cue["after_segment_id"] == STORY[-1]


def test_host_vo_coverage_counts_families(ctx) -> None:
    from interview_mux.listenability_guards import host_vo_coverage_ratio

    clips = [{"type": "vo_pickup", "timeline_start_ms": 0, "duration_ms": 1000}]
    t = 1000
    for sid in INTRO + STORY:
        clips.append({"type": "speech", "segment_id": sid, "timeline_start_ms": t, "duration_ms": 5000})
        t += 5000
        if sid == "seg_016":
            clips.append({"type": "vo_pickup", "timeline_start_ms": t, "duration_ms": 1000})
            t += 1000
    ratio = host_vo_coverage_ratio(ctx, {"clips": clips})
    assert ratio == pytest.approx(2 / 7)
