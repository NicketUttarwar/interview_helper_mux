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
    (ctx.path("sound_design", "assets") / "bed_01.wav").unlink()
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
        {"version": 1, "adjustments": [{"asset_id": "bed_01", "suggested_level_db_delta": -5.0}]},
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
        def apply_gain(self, *_a, **_k):
            return self

        def fade_in(self, *_a, **_k):
            return self

        def fade_out(self, *_a, **_k):
            return self

        def __getitem__(self, _k):
            return self

    monkeypatch.setattr(sound_design, "load_audio", lambda _p: FakeAudio())
    monkeypatch.setattr(sound_design, "loop_to_duration", lambda audio, _d: audio)
    monkeypatch.setattr(sound_design, "placeholder_audio", lambda *_a, **_k: FakeAudio())

    ctx.write_json(
        "flow_1_master/selection.json",
        {"ordered_segment_ids": ["seg_001"]},
        skip_handoff=True,
    )
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), skip_handoff=True)
    overlays = sound_design.flow1_overlays_from_sdp(ctx, segment_timing={"seg_001": (0, 5000)})
    assert overlays
    assert adjusted_levels == [-29.0]


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


def test_mix_flow2_uses_placement_crossfade_on_join(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pq_mix2")
    from run_fixtures import minimal_flow2_selection, sound_design_plan_with

    seed_flow1_sound_spend_ready(ctx)
    ctx.write_json(
        "flow_2_highlights/selection.json",
        minimal_flow2_selection(
            highlights=[
                {
                    "rank": 1,
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "headline": "Hook",
                    "scores": {
                        "salience": 0.9,
                        "clarity": 0.8,
                        "emotion": 0.7,
                        "quotability": 0.6,
                        "diversity_bonus": 0.1,
                    },
                },
                {
                    "rank": 2,
                    "segment_id": "seg_002",
                    "start_ms": 5000,
                    "end_ms": 10000,
                    "headline": "Second",
                    "scores": {
                        "salience": 0.8,
                        "clarity": 0.8,
                        "emotion": 0.7,
                        "quotability": 0.6,
                        "diversity_bonus": 0.1,
                    },
                },
            ]
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                minimal_manifest("seg_001")["segments"][0],
                minimal_manifest("seg_002")["segments"][0],
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            flow_plans={
                "flow2": {
                    "cues": [
                        {
                            "cue_id": "t1",
                            "asset_id": "bed_01",
                            "placement": "between_clips",
                            "from_clip_rank": 1,
                            "to_clip_rank": 2,
                            "crossfade_ms": 200,
                        }
                    ]
                }
            },
        ),
        skip_handoff=True,
    )
    from interview_mux import sound_design

    crossfades: list[int] = []
    real_append = sound_design._append_mix_clip

    def spy_append(base, clip, crossfade_ms):
        crossfades.append(crossfade_ms)
        return real_append(base, clip, crossfade_ms)

    monkeypatch.setattr(sound_design, "_append_mix_clip", spy_append)
    monkeypatch.setattr(sound_design, "load_audio", lambda _p: sound_design.AudioSegment.silent(duration=1000))
    monkeypatch.setattr(sound_design, "enforce_mix_completeness", lambda *_a, **_k: None)
    monkeypatch.setattr(sound_design, "maybe_check_mix_intelligibility", lambda *_a, **_k: None)
    from interview_mux import placement_qa

    monkeypatch.setattr(placement_qa, "maybe_run_placement_qa", lambda *_a, **_k: None)
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    ctx.path("ingest", "normalized.wav").write_bytes(MINIMAL_WAV_BYTES)

    sound_design.mix_flow2(ctx)
    assert 200 in crossfades
