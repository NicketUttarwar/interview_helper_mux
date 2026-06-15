"""Flow 2 scenario crossfade overrides from sonic_context."""

from __future__ import annotations

from interview_mux import sound_design
from run_fixtures import (
    MINIMAL_WAV_BYTES,
    isolated_run_ctx,
    minimal_flow2_selection,
    minimal_manifest,
    seed_flow1_sound_spend_ready,
    seed_from_sonic_fixture,
    sound_design_plan_with,
)


def test_mix_flow2_uses_sonic_context_crossfade_override(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "flow2_cf")
    seed_flow1_sound_spend_ready(ctx)
    doc = seed_from_sonic_fixture(ctx, "media_profile", seed_base=False)
    doc["mix_policy"] = {**(doc.get("mix_policy") or {}), "crossfade_ms_flow2": 80}
    ctx.write_json("understanding/sonic_context.json", doc, skip_handoff=True)
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
        sound_design_plan_with(flow_plans={"flow2": {"cues": []}}),
        skip_handoff=True,
    )
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
    assert 80 in crossfades


def test_compute_mix_policy_crossfade_per_bucket(tmp_path, monkeypatch):
    from interview_mux.sonic_context import compute_mix_policy
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "mix_policy_cf")
    media = compute_mix_policy(ctx, "media_profile")
    fireside = compute_mix_policy(ctx, "fireside")
    assert media["crossfade_ms_flow2"] == 80
    assert fireside["crossfade_ms_flow2"] == 180
