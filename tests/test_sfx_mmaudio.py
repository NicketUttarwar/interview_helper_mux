from __future__ import annotations

import json

from interview_mux.run_context import RunContext
from interview_mux.stages import sfx_mmaudio
from run_fixtures import confirm_test_pickup_speaker, write_fixture_json, write_fixture_theme_wav


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
                    "asset_id": "theme_underscore_a",
                    "role": "theme_underscore",
                    "description": "Warm guitar piano bass underscore",
                    "duration_seconds": 6.0,
                },
                {
                    "asset_id": "theme_chapter_resolve_b",
                    "role": "theme_chapter_resolve",
                    "description": "Cadential resolve motif",
                    "duration_seconds": 1.4,
                },
            ],
            "flow_plans": {
                "podcast": {
                    "profile": "podcast",
                    "cues": [
                        {"cue_id": "c1", "asset_id": "theme_underscore_a", "placement": "under_segment"},
                        {"cue_id": "c2", "asset_id": "theme_underscore_a", "placement": "under_segment"},
                        {"cue_id": "c3", "asset_id": "theme_chapter_resolve_b", "placement": "after_segment"},
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
    assert [row["asset_id"] for row in items] == ["theme_underscore_a", "theme_chapter_resolve_b"]


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
    confirm_test_pickup_speaker(ctx)
    write_fixture_theme_wav(ctx, "master/assembly_preview.wav")
    write_fixture_theme_wav(ctx, "master/assembly.wav")
    write_fixture_json(ctx, "master/edl.json", {"clips": []})
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    epoch = dict(meta.get("delivery_epoch") or {})
    epoch["mix_junction_seat"] = {**dict(epoch.get("mix_junction_seat") or {}), "preview_music": True}
    meta["delivery_epoch"] = epoch
    write_fixture_json(ctx, "run_meta.json", meta)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "coherence": {"sonic_identity": "", "primary_mood": "", "density": ""},
            "palettes": [],
            "assets": [
                {
                    "asset_id": "theme_emphasis_a",
                    "role": "theme_emphasis",
                    "description": "Melodic emphasis swell guitar piano",
                    "duration_seconds": 1.6,
                }
            ],
            "flow_plans": {
                "podcast": {
                    "profile": "podcast",
                    "cues": [{"cue_id": "c1", "asset_id": "theme_emphasis_a", "placement": "after_segment"}],
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
                    "asset_id": "theme_emphasis_a",
                    "sfx_prompt": "Warm melodic emphasis with guitar and piano, no vocals.",
                    "duration_seconds": 9.0,
                    "negative_prompt": "no vocals",
                }
            ]
        },
    )

    calls: list[float] = []

    def fake_music(**kwargs):
        calls.append(kwargs["duration_sec"])
        out = kwargs["out_wav"]
        out.write_bytes(b"RIFF" + b"\x00" * 32)
        return {"backend": "musicgen", "duration_sec": kwargs["duration_sec"]}

    monkeypatch.setattr(sfx_mmaudio, "generate_music_clip", fake_music)
    monkeypatch.setattr(sfx_mmaudio, "musicgen_enabled", lambda: True)
    def fake_qa(c):
        doc = {
            "version": 1,
            "assets": [{"asset_id": "theme_emphasis_a", "verdict": "pass"}],
        }
        c.write_json("sound_design/mmaudio_qa.json", doc, skip_handoff=True, stage_key="mmaudio_sfx")
        return doc

    monkeypatch.setattr(sfx_mmaudio, "run_mmaudio_asset_qa", fake_qa)
    monkeypatch.setattr(sfx_mmaudio, "maybe_auto_refine", lambda *a, **k: None)
    monkeypatch.setattr(sfx_mmaudio, "execute_fitness_remediation", lambda *a, **k: None)
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
    monkeypatch.setattr(
        "interview_mux.musicgen_runner.best_of_n_for_role",
        lambda *_a, **_k: 1,
    )

    sfx_mmaudio.run_sfx_generation(ctx, profile="podcast")

    asset_wav = ctx.path("sound_design", "assets", "theme_emphasis_a.wav")
    flow_wav = ctx.path("master", "sfx", "theme_emphasis_a.wav")
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


def test_score_musicgen_underscore_rejects_weak_seam():
    strong = sfx_mmaudio.score_musicgen_candidate(
        role="theme_underscore",
        qa={
            "verdict": "pass",
            "loop_seam_score": 0.8,
            "musicality": {
                "pulse_clarity": 0.7,
                "tonal_center_score": 0.8,
                "speech_band_roughness": 0.1,
            },
        },
    )
    weak = sfx_mmaudio.score_musicgen_candidate(
        role="theme_underscore",
        qa={
            "verdict": "pass",
            "loop_seam_score": 0.4,
            "musicality": {
                "pulse_clarity": 0.7,
                "tonal_center_score": 0.8,
                "speech_band_roughness": 0.1,
            },
        },
    )

    assert strong["rejected"] is False
    assert weak["rejected"] is True
    assert weak["rejection_reasons"] == ["loop_seam_below_threshold"]
    assert strong["score"] > weak["score"]
    assert weak["score_components"]["weak_loop_seam_penalty"] == -20.0


def test_musicgen_selection_chooses_best_actual_candidate_when_all_rejected():
    selected = sfx_mmaudio._select_musicgen_candidate(
        [
            {"index": 0, "score": -12.0, "rejected": True},
            {"index": 1, "score": -4.0, "rejected": True},
            {"index": 2, "score": -8.0, "rejected": True},
        ]
    )
    assert selected["index"] == 1


def test_musicgen_best_of_n_persists_candidates_and_selected_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_candidates", create=True)
    out = ctx.path("sound_design", "assets", "theme_underscore_a.wav")
    out.parent.mkdir(parents=True, exist_ok=True)

    def fake_music(**kwargs):
        candidate = kwargs["out_wav"]
        candidate.parent.mkdir(parents=True, exist_ok=True)
        index = int(candidate.stem.split("_")[-1])
        candidate.write_bytes(f"candidate-{index}".encode())
        meta = {
            "backend": "musicgen",
            "seed": kwargs["seed"],
            "prompt_hash": "prompt-123",
            "model_id": "fake-musicgen",
        }
        candidate.with_suffix(".gen.json").write_text(json.dumps(meta), encoding="utf-8")
        return meta

    qa_by_index = {
        0: (0.40, 1.0, 1.0, 0.0),
        1: (0.90, 0.8, 0.8, 0.1),
        2: (0.70, 0.3, 0.3, 0.5),
    }

    def fake_analyze(*, path, **_kwargs):
        index = int(path.stem.split("_")[-1])
        seam, pulse, tonal, roughness = qa_by_index[index]
        return {
            "verdict": "pass",
            "loop_seam_score": seam,
            "musicality": {
                "fail_reasons": [],
                "warn_reasons": [],
                "pulse_clarity": pulse,
                "tonal_center_score": tonal,
                "speech_band_roughness": roughness,
            },
        }

    monkeypatch.setattr(sfx_mmaudio, "generate_music_clip", fake_music)
    monkeypatch.setattr(sfx_mmaudio, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(
        "interview_mux.musicgen_runner.best_of_n_for_role",
        lambda _role: 3,
    )
    monkeypatch.setattr(
        "interview_mux.musicgen_runner.musicgen_cfg",
        lambda: {"max_best_of_n": 3},
    )
    monkeypatch.setattr(
        "interview_mux.mmaudio_asset_qa.analyze_asset_wav",
        fake_analyze,
    )
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"musicgen": {"keep_candidates": False}},
    )

    meta = sfx_mmaudio._generate_with_retry(
        ctx=ctx,
        stage="mmaudio_sfx",
        asset_id="theme_underscore_a",
        params={
            "prompt": "warm guitar pulse",
            "negative_prompt": "no vocals",
            "duration_seconds": 6.0,
            "role": "theme_underscore",
            "seed": 100,
        },
        out_file=out,
    )

    assert meta["best_of_n_index"] == 1
    assert out.read_bytes() == b"candidate-1"
    assert json.loads(out.with_suffix(".gen.json").read_text())["seed"] == 100 + 9973
    candidate_dir = out.parent / "_candidates" / "theme_underscore_a"
    assert len(list(candidate_dir.glob("cand_*.wav"))) == 3
    artifact = ctx.read_json("sound_design/musicgen_candidates.json")
    record = artifact["assets"][0]
    assert record["selected_index"] == 1
    assert record["canonical_path"] == "sound_design/assets/theme_underscore_a.wav"
    assert record["candidates"][0]["rejected"] is True
    assert record["candidates"][1]["qa"]["loop_seam_score"] == 0.9


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
    monkeypatch.setattr(sfx_mmaudio, "musicgen_enabled", lambda: False)
    meta = sfx_mmaudio._generate_with_retry(
        ctx=ctx,
        stage="mmaudio_sfx",
        asset_id="bed_a",
        params={"prompt": "x", "negative_prompt": "", "duration_seconds": 2.0, "role": "ambient_bed"},
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
