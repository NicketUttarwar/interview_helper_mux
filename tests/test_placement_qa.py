from __future__ import annotations

from interview_mux.placement_qa import (
    OUTPUT_PATH,
    apply_placement_adjustments,
    maybe_run_placement_qa,
    run_placement_qa,
)
from run_fixtures import (
    MINIMAL_WAV_BYTES,
    isolated_run_ctx,
    minimal_manifest,
    patch_merged_config,
    seed_flow1_sound_spend_ready,
)

def test_run_placement_qa_writes_missing_wav_adjustment(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pq_write")
    seed_flow1_sound_spend_ready(ctx)
    (ctx.path("sound_design", "assets") / "theme_underscore_01.wav").unlink()
    doc = run_placement_qa(ctx)
    assert doc["adjustments"]
    assert ctx.artifact_exists(OUTPUT_PATH)
    assert any(a.get("reason") == "missing_wav" for a in doc["adjustments"])

def test_apply_placement_adjustments_shifts_level_db(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pq_apply")
    ctx.write_json(
        OUTPUT_PATH,
        {"version": 1, "adjustments": [{"asset_id": "bed_01", "suggested_level_db_delta": -3.0}]},
        skip_handoff=True,
    )
    cues = [{"asset_id": "bed_01", "level_db": -20.0}]
    adjusted = apply_placement_adjustments(ctx, cues)
    assert adjusted[0]["level_db"] == -23.0

def test_maybe_run_placement_qa_after_sfx_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"sound_design": {"placement_qa_enabled": True}})
    ctx = isolated_run_ctx(tmp_path, "pq_maybe")
    seed_flow1_sound_spend_ready(ctx)
    maybe_run_placement_qa(ctx)
    assert ctx.artifact_exists(OUTPUT_PATH)
    log_text = ctx.path("gui_log.jsonl").read_text(encoding="utf-8")
    assert "placement_qa" in log_text

def test_mix_overlay_applies_placement_adjustments(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pq_mix")
    seed_flow1_sound_spend_ready(ctx)
    ctx.write_json(
        OUTPUT_PATH,
        {
            "version": 1,
            "adjustments": [
                {"asset_id": "theme_underscore_01", "suggested_level_db_delta": -5.0}
            ],
        },
        skip_handoff=True,
    )
    from interview_mux import placement_qa, sound_design

    adjusted_levels: list[float] = []
    real_apply = placement_qa.apply_placement_adjustments

    def wrap_apply(ctx_, cues):
        out = real_apply(ctx_, cues)
        adjusted_levels.extend(float(c.get("level_db", 0)) for c in out if isinstance(c, dict))
        return out

    monkeypatch.setattr(placement_qa, "apply_placement_adjustments", wrap_apply)

    class FakeAudio:
        def __len__(self):
            # organic_fade_* no-ops when duration is empty
            return 0

        def apply_gain(self, *_a, **_k):
            return self

        def fade_in(self, *_a, **_k):
            return self

        def fade_out(self, *_a, **_k):
            return self

        def __getitem__(self, _k):
            return self

        def __add__(self, _other):
            return self

        def overlay(self, *_a, **_k):
            return self

    monkeypatch.setattr(sound_design, "load_audio", lambda _p: FakeAudio())
    monkeypatch.setattr(sound_design, "loop_to_duration", lambda audio, _d: audio)
    monkeypatch.setattr(sound_design, "placeholder_audio", lambda *_a, **_k: FakeAudio())

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"]},
        skip_handoff=True,
    )
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), skip_handoff=True)
    overlays = sound_design.flow1_overlays_from_sdp(ctx, segment_timing={"seg_001": (0, 5000)})
    # Music-only theme underscore cue should overlay; bed fixtures no longer apply.
    if overlays:
        assert adjusted_levels == [-29.0]
    else:
        assert adjusted_levels == []

def test_apply_placement_adjustments_sets_crossfade_ms(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pq_cf")
    ctx.write_json(
        OUTPUT_PATH,
        {"version": 1, "adjustments": [{"asset_id": "stinger_01", "suggested_crossfade_ms": 180}]},
        skip_handoff=True,
    )
    cues = [{"asset_id": "stinger_01", "level_db": -18.0}]
    adjusted = apply_placement_adjustments(ctx, cues)
    assert adjusted[0]["crossfade_ms"] == 180


def test_placement_qa_preserves_junction_crossfade_across_rerun(tmp_path, monkeypatch):
    """MUX_FORENSICS=0 cascade: remaster mix must not wipe junction fade floors.

    exec_13161: adjust_music_fade → placement_qa regenerate → effective XF=0 →
    oscillation_halt residual blocked PMQ.
    """
    import json
    import os

    os.environ["MUX_FORENSICS"] = "0"
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pq_preserve_xf")
    sdp_path = ctx.path("understanding", "sound_design_plan.json")
    sdp_path.parent.mkdir(parents=True, exist_ok=True)
    sdp_path.write_text(
        json.dumps(
            {
                "version": 1,
                "assets": [{"asset_id": "theme_a", "role": "theme_emphasis"}],
                "flow_plans": {
                    "podcast": {
                        "profile": "podcast",
                        "cues": [
                            {
                                "cue_id": "c_theme_a",
                                "asset_id": "theme_a",
                                "role": "theme_emphasis",
                                "placement": "after_segment",
                                "crossfade_ms": None,
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assets_dir = ctx.path("sound_design", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "theme_a.wav").write_bytes(MINIMAL_WAV_BYTES)
    ctx.write_json(
        OUTPUT_PATH,
        {
            "version": 1,
            "adjustments": [
                {
                    "asset_id": "theme_a",
                    "action": "adjust_crossfade",
                    "suggested_crossfade_ms": 180,
                    "reason": "junction_snip_qa:music_hard_transition",
                    "provenance": {
                        "rule_id": "junction_snip_qa",
                        "source_artifact": "master/junction_snip_qa.json",
                    },
                }
            ],
        },
        skip_handoff=True,
    )
    doc = run_placement_qa(ctx)
    row = next((a for a in doc["adjustments"] if a.get("asset_id") == "theme_a"), None)
    assert row is not None
    assert int(row.get("suggested_crossfade_ms") or 0) >= 180


def test_placement_qa_theme_bookend_gets_soft_crossfade(tmp_path, monkeypatch):
    """MUX_FORENSICS=0: theme bookend/stinger cues get soft XF even under mmaudio rows."""
    import json
    import os

    os.environ["MUX_FORENSICS"] = "0"
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pq_theme_xf")
    sdp_path = ctx.path("understanding", "sound_design_plan.json")
    sdp_path.parent.mkdir(parents=True, exist_ok=True)
    sdp_path.write_text(
        json.dumps(
            {
                "version": 1,
                "assets": [{"asset_id": "show_theme_v1_stinger_01", "role": "theme_emphasis"}],
                "flow_plans": {
                    "podcast": {
                        "profile": "podcast",
                        "cues": [
                            {
                                "cue_id": "c_stinger",
                                "asset_id": "show_theme_v1_stinger_01",
                                "role": "theme_emphasis",
                                "placement": "after_segment",
                                "crossfade_ms": None,
                                "segment_id": "seg_001",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assets_dir = ctx.path("sound_design", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "show_theme_v1_stinger_01.wav").write_bytes(MINIMAL_WAV_BYTES)
    ctx.write_json(
        "sound_design/mmaudio_qa.json",
        {
            "version": 1,
            "assets": [
                {
                    "asset_id": "show_theme_v1_stinger_01",
                    "role": "theme_emphasis",
                    "verdict": "warn",
                    "reasons": ["hot_tail"],
                }
            ],
        },
        skip_handoff=True,
    )
    doc = run_placement_qa(ctx)
    row = next(
        (a for a in doc["adjustments"] if a.get("asset_id") == "show_theme_v1_stinger_01"),
        None,
    )
    assert row is not None
    assert int(row.get("suggested_crossfade_ms") or 0) >= 180
