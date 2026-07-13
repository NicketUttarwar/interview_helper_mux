from __future__ import annotations

import math
import wave
from pathlib import Path

import pytest

from interview_mux.analysis_memory import default_analysis_state, default_sound_design_plan
from interview_mux.context_volley import _shape_stage_input
from interview_mux.pipeline import ANALYSIS_ORDER
from interview_mux.prompt_validation import validate_sound_design_plan
from interview_mux.run_context import RunContext
from interview_mux.stages import sound_design_stages, understanding
from run_fixtures import (
    minimal_content_brief,
    minimal_gap_report,
    minimal_manifest,
    minimal_manifest_segment,
    minimal_master_selection,
    minimal_narrative_plan,
)


def _write_test_wav(path: Path, *, sample_rate: int = 16000, duration_seconds: float = 1.0) -> None:
    n = int(sample_rate * duration_seconds)
    amp = 8000
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n):
            sample = int(amp * math.sin(2.0 * math.pi * 220.0 * (i / sample_rate)))
            frames += int(sample).to_bytes(2, byteorder="little", signed=True)
        wf.writeframes(bytes(frames))


def _seed_source_acoustic_profile(ctx: RunContext) -> None:
    wav = ctx.path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    _write_test_wav(wav)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "hello world",
            "words": [
                {"text": "hello", "start_ms": 0, "end_ms": 220, "speaker_id": "spk_0"},
                {"text": "world", "start_ms": 260, "end_ms": 450, "speaker_id": "spk_0"},
            ],
        },
    )
    understanding.run_source_acoustic_profile(ctx)


def _seed_flow1_inputs(ctx: RunContext) -> None:
    ctx.write_json("master/selection.json", minimal_master_selection())
    ctx.write_json("master/narrative_plan.json", minimal_narrative_plan())
    ctx.write_json("master/transitions.json", {"transitions": []})
    ctx.write_json("understanding/gap_report.json", minimal_gap_report())
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001", start_ms=0, end_ms=2000, text="hello")),
    )
    ctx.write_json("understanding/sound_design_plan.json", default_sound_design_plan())


def test_sound_design_plan_volley_includes_sound_design_plan():
    raw = {
        "sound_design_plan": {
            "version": 1,
            "coherence": {"sonic_identity": "Warm doc", "primary_mood": "warm", "density": "sparse"},
            "palettes": [{"palette_id": "origin", "theme_label": "Origin", "segment_ids": ["seg_001"]}],
            "assets": [{"asset_id": "old_asset", "role": "chapter_stinger"}],
            "flow_plans": {"podcast": {"profile": "podcast", "cues": []}},
        },
        "selection": {"ordered_segment_ids": ["seg_001"], "chapters": []},
        "narrative_plan": {"arc_summary": "Test"},
        "transitions": {"transitions": []},
        "gap_report": {"interviewer_lines": []},
        "segments": {"segments": [{"segment_id": "seg_001", "text": "hi"}]},
    }
    shaped = _shape_stage_input("sound_design_plan", raw)
    sdp = shaped["sound_design_plan"]
    assert sdp["coherence"]["sonic_identity"] == "Warm doc"
    assert sdp["palettes"][0]["palette_id"] == "origin"
    assert "assets" not in sdp
    assert "flow_plans" not in sdp


def test_sound_design_plan_persists_assets_and_cues(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_202", create=True)
    _seed_flow1_inputs(ctx)

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
                    "podcast": {
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
        _ctx.mark_done("sound_design_plan", force=True)
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)

    sound_design_stages.run_sound_design_plan(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    assert sdp["assets"][0]["asset_id"] == "chapter_stinger_warm"
    assert sdp["flow_plans"]["podcast"]["cues"][0]["asset_id"] == "chapter_stinger_warm"
    assert ctx.is_done("sound_design_plan")


def test_sound_design_plan_rejects_unknown_cue_asset(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_203", create=True)
    _seed_flow1_inputs(ctx)

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
                    "podcast": {
                        "profile": "podcast",
                        "cues": [{"cue_id": "bad", "asset_id": "missing_asset", "placement": "after_segment"}],
                    }
                },
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)

    with pytest.raises(ValueError, match="unknown asset_id"):
        sound_design_stages.run_sound_design_plan(ctx)


def test_sfx_prompt_craft_writes_prompts_artifact(tmp_path, monkeypatch):
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
    state = default_analysis_state(ctx.run_id)
    state["style"]["sound_design_notes"] = "Keep subtle."
    ctx.write_json("understanding/analysis_state.json", state)
    _seed_source_acoustic_profile(ctx)

    def fake_run_flow_llm_stage(_ctx, _stage_key, _prompt_rel, build_input, persist):
        payload = build_input(_ctx)
        assert payload["assets"][0]["asset_id"] == "chapter_stinger_warm"
        assert payload["operator_style_sound_design_notes"] == "Keep subtle."
        assert payload["source_acoustic_profile"]["pacing"]["pace_class"]
        persist(
            _ctx,
            {
                "prompts": [
                    {
                        "asset_id": "chapter_stinger_warm",
                        "sfx_prompt": "Warm, short transition marker.",
                        "duration_seconds": 1.5,
                        "negative_prompt": "no vocals, no speech",
                    }
                ]
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)
    sound_design_stages.run_sfx_prompt_craft(ctx)
    artifact = ctx.read_json("sound_design/sfx_prompts.json")
    assert artifact["prompts"][0]["asset_id"] == "chapter_stinger_warm"
    assert artifact["prompts"][0]["duration_seconds"] == 1.5
    ctx.mark_done("sfx_prompt_craft")
    assert ctx.is_done("sfx_prompt_craft")


def test_sfx_prompt_craft_requires_all_plan_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_204b", create=True)
    plan = default_sound_design_plan()
    plan["assets"] = [
        {"asset_id": "a1", "role": "chapter_stinger", "description": "A", "duration_seconds": 1.5},
        {"asset_id": "a2", "role": "ambient_bed", "description": "B", "duration_seconds": 6.0},
    ]
    ctx.write_json("understanding/sound_design_plan.json", plan)

    def fake_run_flow_llm_stage(_ctx, _stage_key, _prompt_rel, build_input, persist):
        persist(
            _ctx,
            {
                "prompts": [
                    {
                        "asset_id": "a1",
                        "sfx_prompt": "Stinger prompt with enough words for validation.",
                        "duration_seconds": 2.0,
                        "negative_prompt": "no vocals, no speech",
                    }
                ]
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)

    with pytest.raises(ValueError, match="missing crafted prompt"):
        sound_design_stages.run_sfx_prompt_craft(ctx)


def test_analysis_order_places_sonic_context_and_palettes_after_content_brief_reanchor():
    reanchor_idx = ANALYSIS_ORDER.index("content_brief_reanchor")
    sonic_idx = ANALYSIS_ORDER.index("sonic_context_build")
    pal_idx = ANALYSIS_ORDER.index("sound_design_palettes")
    assert sonic_idx == reanchor_idx + 1
    assert pal_idx == sonic_idx + 1


def test_sound_design_palettes_volley_includes_source_acoustic_profile():
    raw = {
        "content_brief": {"thesis": "Test"},
        "segments": {"segments": []},
        "sound_design_plan": default_sound_design_plan(),
        "source_acoustic_profile": {
            "pacing": {"pace_class": "conversational", "speech_active_ratio": 0.7},
            "energy": {"room_timbre_hint": "dry_close_mic"},
            "mix_contract": {"underscore_policy": "sparse", "stinger_max_per_minute": 1},
            "prompt_tokens": {"bed_style": "soft room tone", "avoid": "trailer whoosh"},
        },
    }
    shaped = _shape_stage_input("sound_design_palettes", raw)
    sap = shaped["source_acoustic_profile"]
    assert sap["pace_class"] == "conversational"
    assert sap["room_timbre_hint"] == "dry_close_mic"
    assert sap["mix_contract"]["underscore_policy"] == "sparse"
    assert sap["prompt_tokens"]["bed_style"] == "soft room tone"


def test_sound_design_palettes_reads_source_acoustic_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_205", create=True)
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(thesis="Test thesis"))
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_1", text="hello")),
    )
    ctx.write_json("understanding/analysis_state.json", default_analysis_state(ctx.run_id))
    ctx.write_json("understanding/sound_design_plan.json", default_sound_design_plan())
    _seed_source_acoustic_profile(ctx)

    def fake_run_analysis_llm_stage(_ctx, _stage_key, _prompt_rel, build_input, persist):
        payload = build_input(_ctx)
        assert payload["source_acoustic_profile"]["mix_contract"]["underscore_policy"] in (
            "normal",
            "sparse",
        )
        persist(
            _ctx,
            {
                "coherence": {
                    "sonic_identity": "Warm documentary with speech-first ducking.",
                    "primary_mood": "warm",
                    "density": "sparse",
                },
                "palettes": [
                    {
                        "palette_id": "origin_story",
                        "theme_label": "Origin Story",
                        "keywords": ["founder", "early", "risk"],
                        "segment_ids": ["seg_1"],
                        "ambient_description": "Low intimate room tone with gentle air.",
                        "accent_description": "Rare soft texture between chapters.",
                        "avoid": ["comedy hits", "trailer whooshes", "crowd chants"],
                    }
                ],
            },
        )
        _ctx.mark_done("sound_design_palettes", force=True)
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_analysis_llm_stage", fake_run_analysis_llm_stage)
    sound_design_stages.run_sound_design_palettes(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    assert sdp["coherence"]["sonic_identity"].startswith("Warm documentary")
    assert sdp["palettes"][0]["palette_id"] == "origin_story"
    assert validate_sound_design_plan(sdp) == []
    assert ctx.is_done("sound_design_palettes")
