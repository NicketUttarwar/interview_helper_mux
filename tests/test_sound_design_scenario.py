"""Scenario-aware sound design mix behavior (panel overlap, trauma caps, disabled path)."""

from __future__ import annotations

from interview_mux import sound_design
from interview_mux.stages import sound_design_stages
from run_fixtures import (
    MINIMAL_WAV_BYTES,
    isolated_run_ctx,
    patch_merged_config,
    seed_flow1_sound_spend_ready,
    seed_from_sonic_fixture,
    sound_design_plan_with,
)


class _FakeAudio:
    def apply_gain(self, *_a, **_k):
        return self

    def fade_in(self, *_a, **_k):
        return self

    def fade_out(self, *_a, **_k):
        return self

    def __getitem__(self, _k):
        return self


def _stub_overlay_deps(monkeypatch) -> None:
    monkeypatch.setattr(sound_design, "load_audio", lambda _p: _FakeAudio())
    monkeypatch.setattr(sound_design, "loop_to_duration", lambda audio, _d: audio)
    monkeypatch.setattr(sound_design, "placeholder_audio", lambda *_a, **_k: _FakeAudio())


def test_panel_overlap_high_skips_bed_overlay(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "scenario_panel_overlap")
    seed_flow1_sound_spend_ready(ctx)
    seed_from_sonic_fixture(ctx, "panel", seed_base=False)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "bed_01",
                    "role": "ambient_bed",
                    "palette_id": "p1",
                    "description": "Sparse panel bed",
                    "duration_seconds": 6.0,
                }
            ],
            flow_plans={
                "podcast": {
                    "cues": [
                        {
                            "cue_id": "c1",
                            "asset_id": "bed_01",
                            "placement": "under_segment",
                            "segment_id": "seg_006",
                        }
                    ]
                }
            },
        ),
        skip_handoff=True,
    )
    _stub_overlay_deps(monkeypatch)

    overlays = sound_design.flow1_overlays_from_sdp(
        ctx,
        segment_timing={"seg_006": (0, 5000)},
    )
    assert overlays == []


def test_trauma_adjacent_stinger_cap_skips_stinger_overlay(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "scenario_trauma_stinger")
    seed_flow1_sound_spend_ready(ctx)
    seed_from_sonic_fixture(ctx, "trauma_adjacent", seed_base=False)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "stinger_01",
                    "role": "chapter_stinger",
                    "palette_id": "p1",
                    "description": "Soft closure",
                    "duration_seconds": 1.5,
                }
            ],
            flow_plans={
                "podcast": {
                    "cues": [
                        {
                            "cue_id": "s1",
                            "asset_id": "stinger_01",
                            "placement": "after_segment",
                            "segment_id": "seg_001",
                        }
                    ]
                }
            },
        ),
        skip_handoff=True,
    )
    assets_dir = ctx.path("sound_design", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "stinger_01.wav").write_bytes(MINIMAL_WAV_BYTES)
    _stub_overlay_deps(monkeypatch)
    monkeypatch.setattr(
        sound_design,
        "_align_stinger_to_pause_tail",
        lambda *_a, **_k: 4500,
    )

    overlays = sound_design.flow1_overlays_from_sdp(
        ctx,
        segment_timing={"seg_001": (0, 5000)},
        contract={"stinger_max_per_minute": 0, "duck_under_speech_db": 16.0, "underscore_policy": "normal"},
    )
    assert overlays == []


def test_sound_design_disabled_skips_palettes_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"sound_design": {"enabled": False}})
    ctx = isolated_run_ctx(tmp_path, "scenario_sd_off")
    from run_fixtures import seed_analysis_ready_artifacts

    seed_analysis_ready_artifacts(ctx)
    sound_design_stages.run_sound_design_palettes(ctx)
    assert ctx.is_done("sound_design_palettes")
