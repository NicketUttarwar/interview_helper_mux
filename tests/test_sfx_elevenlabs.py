from __future__ import annotations

from interview_mux.run_context import RunContext
from interview_mux.stages import sfx_elevenlabs


def test_collect_generation_items_uses_unique_plan_asset_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_301", create=True)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "coherence": {"sonic_identity": "", "primary_mood": "", "density": ""},
            "palettes": [],
            "assets": [
                {
                    "asset_id": "bed_a",
                    "role": "ambient_bed",
                    "description": "Ambient bed A",
                    "duration_seconds": 6.0,
                },
                {
                    "asset_id": "sting_b",
                    "role": "chapter_stinger",
                    "description": "Stinger B",
                    "duration_seconds": 1.4,
                },
            ],
            "flow_plans": {
                "flow1": {
                    "profile": "podcast",
                    "cues": [
                        {"cue_id": "c1", "asset_id": "bed_a", "placement": "under_segment"},
                        {"cue_id": "c2", "asset_id": "bed_a", "placement": "under_segment"},
                        {"cue_id": "c3", "asset_id": "sting_b", "placement": "after_segment"},
                    ],
                },
                "flow2": {"profile": "montage", "cues": []},
            },
            "generated": {},
        },
    )

    items = sfx_elevenlabs._collect_generation_items(
        ctx=ctx,
        profile="podcast",
        fallback_cues=[{"asset_id": "fallback"}],
    )
    assert [row["asset_id"] for row in items] == ["bed_a", "sting_b"]


def test_resolve_generation_params_prefers_plan_duration_when_crafted_missing_duration():
    text, duration, influence = sfx_elevenlabs._resolve_generation_params(
        {"role": "ambient_bed", "description": "Bed", "duration_seconds": 7.0},
        {"elevenlabs_prompt": "crafted", "negative_prompt": "no vocals"},
    )
    assert text.endswith("Avoid: no vocals")
    assert duration == 7.0
    assert influence == sfx_elevenlabs._ROLE_INFLUENCE["ambient_bed"]
