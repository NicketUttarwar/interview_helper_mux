from __future__ import annotations

import pytest

from interview_mux.analysis_memory import default_sound_design_plan
from interview_mux.gates import set_selected_flow
from interview_mux.run_context import RunContext
from interview_mux.stages import sound_design_stages


def _seed_flow1_inputs(ctx: RunContext) -> None:
    ctx.write_json(
        "flow_1_master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "chapters": [{"chapter_id": "ch_01", "segment_ids": ["seg_001"]}]},
    )
    ctx.write_json("flow_1_master/narrative_plan.json", {"arc_summary": "Test arc"})
    ctx.write_json("flow_1_master/transitions.json", {"transitions": []})
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []})
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [{"segment_id": "seg_001", "start_ms": 0, "end_ms": 2000, "text": "hello"}]},
    )
    ctx.write_json("understanding/sound_design_plan.json", default_sound_design_plan())


def test_sound_design_plan_flow1_requires_selected_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_201", create=True)
    _seed_flow1_inputs(ctx)
    set_selected_flow(ctx, "flow2")
    with pytest.raises(SystemExit, match="selected_flow=flow1"):
        sound_design_stages.run_sound_design_plan_flow1(ctx)


def test_sound_design_plan_flow1_persists_assets_and_cues(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_202", create=True)
    _seed_flow1_inputs(ctx)
    set_selected_flow(ctx, "flow1")

    def fake_run_flow_llm_stage(_ctx, _stage_key, _prompt_rel, build_input, persist):
        payload = build_input(_ctx)
        assert "selection" in payload
        assert "sound_design_plan" in payload
        persist(
            _ctx,
            {
                "assets": [
                    {
                        "asset_id": "chapter_stinger_warm",
                        "role": "chapter_stinger",
                        "description": "Soft tonal rise, no vocals.",
                        "duration_seconds": 1.6,
                        "reuse_note": "Reusable chapter boundary marker.",
                    }
                ],
                "flow_plans": {
                    "flow1": {
                        "profile": "podcast",
                        "cues": [
                            {
                                "cue_id": "sting_001",
                                "asset_id": "chapter_stinger_warm",
                                "placement": "after_segment",
                                "after_segment_id": "seg_001",
                            }
                        ],
                    }
                },
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)

    sound_design_stages.run_sound_design_plan_flow1(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    assert sdp["assets"][0]["asset_id"] == "chapter_stinger_warm"
    assert sdp["flow_plans"]["flow1"]["cues"][0]["asset_id"] == "chapter_stinger_warm"
    assert ctx.is_done("sound_design_plan_flow1")


def test_sound_design_plan_flow1_rejects_unknown_cue_asset(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_203", create=True)
    _seed_flow1_inputs(ctx)
    set_selected_flow(ctx, "flow1")

    def fake_run_flow_llm_stage(_ctx, _stage_key, _prompt_rel, _build_input, persist):
        persist(
            _ctx,
            {
                "assets": [
                    {
                        "asset_id": "known_asset",
                        "role": "chapter_stinger",
                        "description": "Soft marker.",
                        "duration_seconds": 1.4,
                    }
                ],
                "flow_plans": {
                    "flow1": {
                        "profile": "podcast",
                        "cues": [{"cue_id": "bad", "asset_id": "missing_asset", "placement": "after_segment"}],
                    }
                },
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)

    with pytest.raises(ValueError, match="unknown asset_id"):
        sound_design_stages.run_sound_design_plan_flow1(ctx)


def test_elevenlabs_prompt_craft_writes_prompts_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_204", create=True)
    plan = default_sound_design_plan()
    plan["assets"] = [
        {
            "asset_id": "chapter_stinger_warm",
            "role": "chapter_stinger",
            "description": "Warm documentary marker",
            "duration_seconds": 1.5,
        }
    ]
    ctx.write_json("understanding/sound_design_plan.json", plan)
    ctx.write_json("understanding/analysis_state.json", {"style": {"sound_design_notes": "Keep subtle."}})
    ctx.write_json("understanding/source_acoustic_profile.json", {"pacing": {"pace_class": "conversational"}})

    def fake_run_flow_llm_stage(_ctx, _stage_key, _prompt_rel, build_input, persist):
        payload = build_input(_ctx)
        assert payload["assets"][0]["asset_id"] == "chapter_stinger_warm"
        assert payload["operator_style_sound_design_notes"] == "Keep subtle."
        assert payload["source_acoustic_profile"]["pacing"]["pace_class"] == "conversational"
        persist(
            _ctx,
            {
                "prompts": [
                    {
                        "asset_id": "chapter_stinger_warm",
                        "elevenlabs_prompt": "Warm, short transition marker.",
                        "duration_seconds": 1.5,
                        "negative_prompt": "no vocals, no speech",
                    }
                ]
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)
    sound_design_stages.run_elevenlabs_prompt_craft(ctx)
    artifact = ctx.read_json("sound_design/elevenlabs_prompts.json")
    assert artifact["prompts"][0]["asset_id"] == "chapter_stinger_warm"
    assert ctx.is_done("elevenlabs_prompt_craft")


def test_sound_design_palettes_reads_source_acoustic_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_205", create=True)
    ctx.write_json("understanding/content_brief.json", {"thesis": "Test thesis"})
    ctx.write_json("segments/manifest.json", {"segments": [{"segment_id": "seg_1", "text": "hello"}]})
    ctx.write_json("understanding/analysis_state.json", {"style": {}})
    ctx.write_json("understanding/sound_design_plan.json", default_sound_design_plan())
    ctx.write_json("understanding/source_acoustic_profile.json", {"mix_contract": {"underscore_policy": "normal"}})

    def fake_run_analysis_llm_stage(_ctx, _stage_key, _prompt_rel, build_input, persist):
        payload = build_input(_ctx)
        assert payload["source_acoustic_profile"]["mix_contract"]["underscore_policy"] == "normal"
        persist(
            _ctx,
            {
                "coherence": {"sonic_identity": "doc", "primary_mood": "warm", "density": "sparse"},
                "palettes": [],
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_analysis_llm_stage", fake_run_analysis_llm_stage)
    sound_design_stages.run_sound_design_palettes(ctx)
    assert ctx.is_done("sound_design_palettes")
