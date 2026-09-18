from __future__ import annotations

import math
import wave
from pathlib import Path

import pytest

from interview_mux.analysis_memory import default_analysis_state, default_sound_design_plan
from interview_mux.pipeline import ANALYSIS_ORDER
from interview_mux.prompt_validation import validate_sound_design_plan
from interview_mux.run_context import RunContext
from interview_mux.stages import sound_design_stages, understanding
from run_fixtures import (
    mark_done_raw,
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


def test_sound_design_plan_persists_assets_and_cues(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_sdp_persist_cues", create=True)
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
        mark_done_raw(_ctx, "sound_design_plan")
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)

    sound_design_stages.run_sound_design_plan(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    # Music-only harden replaces legacy chapter_stinger with motif inventory.
    asset_ids = {str(a.get("asset_id") or "") for a in (sdp.get("assets") or []) if isinstance(a, dict)}
    assert asset_ids
    assert any(aid.startswith("show_theme") or "theme" in aid for aid in asset_ids)
    cues = (((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
    assert cues
    assert str(cues[0].get("asset_id") or "") in asset_ids
    assert ctx.is_done("sound_design_plan")


def test_sound_design_plan_rejects_unknown_cue_asset(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_sdp_reject_cue", create=True)
    _seed_flow1_inputs(ctx)

    def fake_run_flow_llm_stage(_ctx, _stage_key, _prompt_rel, _build_input, persist):
        persist(
            _ctx,
            {
                "assets": [
                    {
                        "asset_id": "show_theme_v1_motif",
                        "role": "theme_cold_open",
                        "description": "Show motif seed phrase with clear pulse.",
                        "duration_seconds": 4.0,
                        "palette_kind": "motif",
                    }
                ],
                "flow_plans": {
                    "podcast": {
                        "profile": "podcast",
                        "cues": [
                            {
                                "cue_id": "bad",
                                "asset_id": "missing_asset_xyz",
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

    # Music-only harden remaps/drops unknown cue assets onto the motif inventory.
    sound_design_stages.run_sound_design_plan(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    asset_ids = {str(a.get("asset_id") or "") for a in (sdp.get("assets") or []) if isinstance(a, dict)}
    cues = (((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
    assert "missing_asset_xyz" not in {
        str(c.get("asset_id") or "") for c in cues if isinstance(c, dict)
    }
    assert all(str(c.get("asset_id") or "") in asset_ids for c in cues if isinstance(c, dict))


def test_sfx_prompt_craft_refuses_default_sdp_empty_assets(tmp_path, monkeypatch):
    """SPC-B3: default/empty SDP must not reach LLM craft."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_sfx_craft_empty_sdp", create=True)
    ctx._one_writer_raw = True
    ctx.write_json("understanding/sound_design_plan.json", default_sound_design_plan())

    def fail_llm(*_a, **_k):
        raise AssertionError("LLM must not run on empty SDP")

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fail_llm)
    with pytest.raises(RuntimeError, match="SDP assets\\[\\] empty"):
        sound_design_stages.run_sfx_prompt_craft(ctx)


def test_sfx_prompt_craft_contract_consumers_mmaudio_sfx() -> None:
    """SPC-B1: primary consumer is mmaudio_sfx, not self."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract("sfx_prompt_craft")
    assert contract is not None
    assert "mmaudio_sfx" in (contract.consumers or [])
    assert "sfx_prompt_craft" not in (contract.consumers or [])


def test_mmaudio_sfx_contract_lifecycle_is_non_llm() -> None:
    """MSFX-B1: MusicGen-first host — contract must not claim llm_execute."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract("mmaudio_sfx")
    assert contract is not None
    assert contract.tier == "process"
    assert "llm_execute" not in contract.lifecycle_phases
    assert "execute" in contract.lifecycle_phases


def test_mmaudio_sfx_stageinfo_musicgen_first() -> None:
    """MSFX-B3: GUI StageInfo must label MusicGen-first, not MMAudio-only."""
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID["mmaudio_sfx"]
    assert "MusicGen" in info.description
    assert "MMAudio text-to-audio" not in info.description


def test_sfx_prompt_craft_writes_prompts_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_sdp_persist_assets", create=True)
    plan = default_sound_design_plan()
    plan["assets"] = [
        {
            "asset_id": "show_theme_v1_motif",
            "role": "theme_cold_open",
            "description": "Warm documentary motif seed",
            "duration_seconds": 4.0,
            "palette_kind": "motif",
        }
    ]
    ctx._one_writer_raw = True
    ctx.write_json("understanding/sound_design_plan.json", plan)
    state = default_analysis_state(ctx.run_id)
    state["style"]["sound_design_notes"] = "Keep subtle."
    ctx.write_json("understanding/analysis_state.json", state)
    _seed_source_acoustic_profile(ctx)

    def fake_run_flow_llm_stage(_ctx, _stage_key, _prompt_rel, build_input, persist):
        payload = build_input(_ctx)
        assert payload["assets"][0]["asset_id"] == "show_theme_v1_motif"
        assert payload["operator_style_sound_design_notes"] == "Keep subtle."
        assert payload["source_acoustic_profile"]["pacing"]["pace_class"]
        persist(
            _ctx,
            {
                "prompts": [
                    {
                        "asset_id": "show_theme_v1_motif",
                        "sfx_prompt": "Warm, short motif phrase with clear pulse.",
                        "duration_seconds": 4.0,
                        "negative_prompt": "no vocals, no speech",
                    }
                ]
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)
    sound_design_stages.run_sfx_prompt_craft(ctx)
    artifact = ctx.read_json("sound_design/sfx_prompts.json")
    assert artifact["prompts"][0]["asset_id"] == "show_theme_v1_motif"
    assert float(artifact["prompts"][0]["duration_seconds"]) > 0
    mark_done_raw(ctx, "sfx_prompt_craft")
    assert ctx.is_done("sfx_prompt_craft")


def test_sfx_prompt_craft_requires_all_plan_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_sdp_persist_b", create=True)
    plan = default_sound_design_plan()
    plan["assets"] = [
        {
            "asset_id": "show_theme_v1_motif",
            "role": "theme_cold_open",
            "description": "Motif seed",
            "duration_seconds": 4.0,
            "palette_kind": "motif",
        },
        {
            "asset_id": "show_theme_v1_underscore",
            "role": "theme_underscore",
            "description": "Underscore loop",
            "duration_seconds": 12.0,
            "palette_kind": "underscore_loop",
        },
    ]
    ctx._one_writer_raw = True
    ctx.write_json("understanding/sound_design_plan.json", plan)

    def fake_run_flow_llm_stage(_ctx, _stage_key, _prompt_rel, build_input, persist):
        # Intentionally omit underscore prompt — craft auto-fills remaining theme assets.
        persist(
            _ctx,
            {
                "prompts": [
                    {
                        "asset_id": "show_theme_v1_motif",
                        "sfx_prompt": "Short motif prompt with enough words for validation.",
                        "duration_seconds": 4.0,
                        "negative_prompt": "no vocals, no speech",
                    }
                ]
            },
        )
        return {"status": "complete"}

    monkeypatch.setattr(sound_design_stages, "run_flow_llm_stage", fake_run_flow_llm_stage)

    sound_design_stages.run_sfx_prompt_craft(ctx)
    artifact = ctx.read_json("sound_design/sfx_prompts.json")
    prompt_ids = {
        str(p.get("asset_id") or "") for p in (artifact.get("prompts") or []) if isinstance(p, dict)
    }
    assert "show_theme_v1_motif" in prompt_ids
    assert "show_theme_v1_underscore" in prompt_ids


def test_analysis_order_places_sonic_context_and_palettes_after_content_brief_reanchor():
    reanchor_idx = ANALYSIS_ORDER.index("content_brief_reanchor")
    framing_idx = ANALYSIS_ORDER.index("framing_posture_decide")
    resplit_idx = ANALYSIS_ORDER.index("boundary_topic_resplit")
    vernacular_idx = ANALYSIS_ORDER.index("vernacular_segment_sanitize")
    low_conf_idx = ANALYSIS_ORDER.index("low_conf_island_scan")
    fuse_idx = ANALYSIS_ORDER.index("connector_fuse_pass")
    sonic_idx = ANALYSIS_ORDER.index("sonic_context_build")
    pal_idx = ANALYSIS_ORDER.index("sound_design_palettes")
    assert framing_idx == reanchor_idx + 1
    assert resplit_idx == framing_idx + 1
    assert vernacular_idx == resplit_idx + 1
    assert low_conf_idx == vernacular_idx + 1
    assert fuse_idx == low_conf_idx + 1
    assert sonic_idx == fuse_idx + 1
    assert pal_idx == sonic_idx + 1


def test_sound_design_palettes_reads_source_acoustic_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("INTERVIEW_MUX_SOUND_DESIGN_EARLY_PALETTES_LLM", "1")
    ctx = RunContext("exec_sdp_205", create=True)
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(thesis="Test thesis"))
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_1",
                text="Founder story about early risk and the first team.",
                start_ms=0,
                end_ms=9000,
            )
        ),
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
        mark_done_raw(_ctx, "sound_design_palettes")
        return {"status": "complete"}

    # Force early-palettes LLM path (default is deferred to sound_design_plan).
    monkeypatch.setattr(
        "interview_mux.stages.sound_design_stages.merged_config",
        lambda: {"sound_design": {"early_palettes_llm": True, "enabled": True}},
    )
    monkeypatch.setattr(sound_design_stages, "run_analysis_llm_stage", fake_run_analysis_llm_stage)
    sound_design_stages.run_sound_design_palettes(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    assert sdp["coherence"]["sonic_identity"].startswith("Warm documentary")
    assert sdp["palettes"][0]["palette_id"] == "origin_story"
    assert validate_sound_design_plan(sdp) == []
    assert ctx.is_done("sound_design_palettes")


def test_sound_design_palettes_defaults_defer_empty_palettes(tmp_path, monkeypatch):
    """Shipped default early_palettes_llm=false heals without early LLM (SDP-B1)."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_sdp_deferred", create=True)
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(thesis="Test thesis"))
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_1", text="hello", start_ms=0, end_ms=2000)
        ),
    )
    ctx.write_json("understanding/analysis_state.json", default_analysis_state(ctx.run_id))
    ctx.write_json("understanding/sound_design_plan.json", default_sound_design_plan())
    _seed_source_acoustic_profile(ctx)

    monkeypatch.setattr(
        "interview_mux.stages.sound_design_stages.merged_config",
        lambda: {"sound_design": {"early_palettes_llm": False, "enabled": True}},
    )
    sound_design_stages.run_sound_design_palettes(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    assert sdp.get("coherence", {}).get("deferred_early_palettes") is True
    assert ctx.is_done("sound_design_palettes")

    from interview_mux.artifact_completeness import _gaps_sound_design_plan

    # Completeness treats deferred plans as OK even if repair seeded a placeholder palette.
    assert "palettes" not in _gaps_sound_design_plan(
        {
            "coherence": {"sonic_identity": "x", "deferred_early_palettes": True},
            "palettes": [],
        }
    )
    assert "palettes" not in _gaps_sound_design_plan(sdp)


def test_sound_design_palettes_sufficiency_gated_on_early_llm() -> None:
    """Contract does not claim blocking palettes≥1 unconditionally (SDP-B1)."""
    from interview_mux.stage_contract import evaluate_when, load_contract

    contract = load_contract("sound_design_palettes")
    assert contract is not None
    rules = [r for r in contract.sufficiency if r.path == "palettes"]
    assert len(rules) == 1
    assert rules[0].min_count == 1
    assert rules[0].when.get("early_palettes_llm") is True
    assert evaluate_when(rules[0].when, None) is False
