from __future__ import annotations

from interview_mux.run_context import RunContext
from interview_mux.stages import sfx_mmaudio


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
                "podcast": {
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

    items = sfx_mmaudio._collect_generation_items(
        ctx=ctx,
        profile="podcast",
        fallback_cues=[{"asset_id": "fallback"}],
    )
    assert [row["asset_id"] for row in items] == ["bed_a", "sting_b"]


def test_resolve_generation_params_uses_plan_duration_not_crafted():
    params = sfx_mmaudio._resolve_generation_params(
        {"role": "ambient_bed", "description": "Bed", "duration_seconds": 7.0},
        {
            "sfx_prompt": "crafted",
            "negative_prompt": "no vocals",
            "duration_seconds": 3.0,
        },
    )
    assert params["prompt"] == "crafted"
    assert "Avoid:" not in params["prompt"]
    assert params["negative_prompt"] == "no vocals"
    assert params["duration_seconds"] == 7.0
    assert params["prompt_influence"] == sfx_mmaudio._ROLE_INFLUENCE["ambient_bed"]


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
                "podcast": {
                    "profile": "podcast",
                    "cues": [{"cue_id": "c1", "asset_id": "sting_a", "placement": "after_segment"}],
                },
                "flow2": {"profile": "montage", "cues": []},
            },
            "generated": {},
        },
    )
    ctx.write_json(
        "sound_design/sfx_prompts.json",
        {
            "prompts": [
                {
                    "asset_id": "sting_a",
                    "sfx_prompt": "Warm stinger, no vocals.",
                    "duration_seconds": 9.0,
                    "negative_prompt": "no vocals",
                }
            ]
        },
    )

    calls: list[float] = []

    def fake_generate(**kwargs):
        calls.append(kwargs["duration_seconds"])
        out = kwargs["output_wav"]
        out.write_bytes(b"RIFF" + b"\x00" * 32)
        return {"duration_seconds": kwargs["duration_seconds"]}

    monkeypatch.setattr(sfx_mmaudio, "generate_text_to_audio", fake_generate)
    monkeypatch.setattr(sfx_mmaudio, "run_mmaudio_asset_qa", lambda ctx: {"assets": []})
    monkeypatch.setattr(sfx_mmaudio, "maybe_auto_refine", lambda *a, **k: None)
    monkeypatch.setattr(
        sfx_mmaudio,
        "_trim_wav_to_duration",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.sfx_prompt_review.g15_required",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        sfx_mmaudio,
        "_should_skip_generation",
        lambda *_a, **_k: False,
    )

    sfx_mmaudio.run_sfx_generation(ctx, profile="podcast")

    asset_wav = ctx.path("sound_design", "assets", "sting_a.wav")
    flow_wav = ctx.path("master", "sfx", "sting_a.wav")
    assert asset_wav.is_file()
    assert flow_wav.is_file()
    assert calls == [1.6]
    assert ctx.is_done("mmaudio_sfx")


def test_hash_generation_plan_changes_with_sonic_context_hash():
    item = {"asset_id": "bed_a", "role": "ambient_bed", "duration_seconds": 6.0}
    prompt_row = {"sfx_prompt": "warm pad", "negative_prompt": "no vocals"}
    params = {
        "duration_seconds": 6.0,
        "prompt": "warm pad",
        "negative_prompt": "no vocals",
        "prompt_influence": 0.3,
        "cfg_strength": None,
        "num_steps": None,
        "seed": None,
        "variant": None,
        "role": "ambient_bed",
    }
    h1 = sfx_mmaudio._hash_generation_plan(item, prompt_row, params, sonic_context_hash="abc")
    h2 = sfx_mmaudio._hash_generation_plan(item, prompt_row, params, sonic_context_hash="def")
    assert h1 != h2


def test_generate_with_retry_retries_once(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_retry", create=True)
    out = tmp_path / "out.wav"
    attempts = {"n": 0}

    def flaky(**kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise sfx_mmaudio.MMAudioUnavailable("timeout")
        kwargs["output_wav"].write_bytes(b"RIFF")
        return {"ok": True}

    monkeypatch.setattr(sfx_mmaudio, "generate_text_to_audio", flaky)
    meta = sfx_mmaudio._generate_with_retry(
        ctx=ctx,
        stage="mmaudio_sfx",
        asset_id="bed_a",
        params={"prompt": "x", "negative_prompt": "", "duration_seconds": 2.0},
        out_file=out,
    )
    assert meta["ok"] is True
    assert attempts["n"] == 2


def test_maybe_auto_refine_skips_trauma_without_override(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_trauma_refine", create=True)
    ctx.write_json(
        "sound_design/mmaudio_qa.json",
        {"version": 1, "assets": [{"asset_id": "sting_a", "verdict": "fail"}]},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.sonic_context.load_sonic_context",
        lambda _ctx: {"scenario": {"atlas_bucket": "trauma_adjacent"}, "sonic_context_hash": "t1"},
    )
    monkeypatch.setattr(sfx_mmaudio, "mmaudio_cfg", lambda: {"auto_refine_enabled": True, "auto_refine_on_qa_fail": True, "auto_refine_on_trauma": False, "auto_refine_max_attempts_per_asset": 2})
    refined: list[list[str]] = []

    def fake_refine(c, asset_ids=None):
        refined.append(list(asset_ids or []))

    monkeypatch.setattr(
        "interview_mux.stages.sound_design_stages.run_sfx_prompt_refine",
        fake_refine,
    )
    monkeypatch.setattr(sfx_mmaudio, "_refine_attempts", lambda *_a, **_k: 0)
    monkeypatch.setattr(sfx_mmaudio, "_regenerate_assets_after_refine", lambda *_a, **_k: None)
    monkeypatch.setattr(sfx_mmaudio, "_load_crafted_prompts", lambda *_a: {})
    monkeypatch.setattr(sfx_mmaudio, "_collect_generation_items_for_regen", lambda *_a: [])

    sfx_mmaudio.maybe_auto_refine(ctx, "mmaudio_sfx")
    assert refined == []


def test_maybe_auto_refine_runs_trauma_with_auto_on_trauma(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_trauma_auto", create=True)
    ctx.write_json(
        "sound_design/mmaudio_qa.json",
        {"version": 1, "assets": [{"asset_id": "sting_a", "verdict": "fail"}]},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.sonic_context.load_sonic_context",
        lambda _ctx: {"scenario": {"atlas_bucket": "trauma_adjacent"}, "sonic_context_hash": "t1"},
    )
    monkeypatch.setattr(
        sfx_mmaudio,
        "mmaudio_cfg",
        lambda: {
            "auto_refine_enabled": True,
            "auto_refine_on_qa_fail": True,
            "auto_refine_on_trauma": True,
            "auto_refine_max_attempts_per_asset": 2,
        },
    )
    refined: list[list[str]] = []

    def fake_refine(c, asset_ids=None):
        refined.append(list(asset_ids or []))

    monkeypatch.setattr(
        "interview_mux.stages.sound_design_stages.run_sfx_prompt_refine",
        fake_refine,
    )
    monkeypatch.setattr(sfx_mmaudio, "_refine_attempts", lambda *_a, **_k: 0)
    monkeypatch.setattr(sfx_mmaudio, "_regenerate_assets_after_refine", lambda *_a, **_k: None)
    monkeypatch.setattr(sfx_mmaudio, "_load_crafted_prompts", lambda *_a: {})
    monkeypatch.setattr(sfx_mmaudio, "_collect_generation_items_for_regen", lambda *_a: [])

    out = sfx_mmaudio.maybe_auto_refine(ctx, "mmaudio_sfx")
    assert out == ["sting_a"]
    assert refined == [["sting_a"]]
    meta = ctx.read_json("run_meta.json")
    assert meta.get("sfx_auto_refine_override", {}).get("sting_a") is True
