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


def test_resolve_generation_params_uses_plan_duration_not_crafted():
    text, duration, influence = sfx_elevenlabs._resolve_generation_params(
        {"role": "ambient_bed", "description": "Bed", "duration_seconds": 7.0},
        {
            "elevenlabs_prompt": "crafted",
            "negative_prompt": "no vocals",
            "duration_seconds": 3.0,
        },
    )
    assert text.endswith("Avoid: no vocals")
    assert duration == 7.0
    assert influence == sfx_elevenlabs._ROLE_INFLUENCE["ambient_bed"]


def test_run_sfx_generation_writes_one_wav_per_asset_id(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_064", create=True)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "coherence": {"sonic_identity": "", "primary_mood": "", "density": ""},
            "palettes": [],
            "assets": [
                {
                    "asset_id": "sting_a",
                    "role": "chapter_stinger",
                    "description": "Stinger",
                    "duration_seconds": 1.6,
                }
            ],
            "flow_plans": {
                "flow1": {
                    "profile": "podcast",
                    "cues": [{"cue_id": "c1", "asset_id": "sting_a", "placement": "after_segment"}],
                },
                "flow2": {"profile": "montage", "cues": []},
            },
            "generated": {},
        },
    )
    ctx.write_json(
        "sound_design/elevenlabs_prompts.json",
        {
            "prompts": [
                {
                    "asset_id": "sting_a",
                    "elevenlabs_prompt": "Warm stinger, no vocals.",
                    "duration_seconds": 9.0,
                    "negative_prompt": "no vocals",
                }
            ]
        },
    )

    calls: list[float] = []

    def fake_generate(*, api_key, text, duration_seconds, prompt_influence=None, max_retries=3):
        calls.append(duration_seconds)
        return b"RIFF" + b"\x00" * 32

    monkeypatch.setattr(sfx_elevenlabs, "require_secret", lambda _k: "test-key")
    monkeypatch.setattr(sfx_elevenlabs, "generate_sound_effect", fake_generate)

    sfx_elevenlabs.run_sfx_generation(ctx, profile="podcast")

    asset_wav = ctx.path("sound_design", "assets", "sting_a.wav")
    flow_wav = ctx.path("flow_1_master", "sfx", "sting_a.wav")
    assert asset_wav.is_file()
    assert flow_wav.is_file()
    assert calls == [1.6]
    assert ctx.is_done("elevenlabs_sfx_flow1")
