"""Listenability percentage-band guards and related product hardening."""

from __future__ import annotations

from interview_mux.listenability_guards import (
    air_pad_ms,
    evaluate_listenability,
    hinge_ids,
    listenability_guards_cfg,
    quartile_segment_buckets,
    soft_unique_asset_guidance,
)


def test_listenability_guards_defaults_are_ratios():
    cfg = listenability_guards_cfg()
    assert 0 < cfg["host_vo_coverage_min_ratio"] < cfg["host_vo_coverage_max_ratio"] <= 1
    assert 0 < cfg["bed_coverage_min_ratio"] < cfg["bed_coverage_max_ratio"] <= 1
    assert cfg["intentional_air_min_ratio"] < cfg["intentional_air_max_ratio"]


def test_air_pad_scales_with_clip_and_clamps():
    cfg = listenability_guards_cfg()
    short = air_pad_ms(500, kind="after_vo", cfg=cfg)
    long = air_pad_ms(20_000, kind="after_vo", cfg=cfg)
    assert short >= int(cfg["air_pad_floor_ms"])
    assert long <= int(cfg["air_pad_ceil_ms"])
    assert long >= short


def test_quartile_buckets_cover_all_segments():
    order = [f"seg_{i:03d}" for i in range(1, 13)]
    durs = {s: 1000 for s in order}
    buckets = quartile_segment_buckets(order, durs)
    flat = [s for b in buckets for s in b]
    assert flat == order
    assert len(buckets) == 4


def test_soft_unique_asset_guidance_scales():
    assert soft_unique_asset_guidance(60_000) >= 3
    assert soft_unique_asset_guidance(60 * 60_000) >= soft_unique_asset_guidance(60_000)


def test_evaluate_listenability_skips_when_creative_off(monkeypatch, tmp_path):
    from interview_mux import creative_delivery
    from interview_mux.run_context import RunContext

    monkeypatch.setattr(creative_delivery, "creative_delivery_required", lambda cfg=None: False)
    # Minimal fake ctx
    class _Ctx:
        run_id = "test"
        def artifact_exists(self, *_a, **_k):
            return False
        def read_json(self, *_a, **_k):
            return {}
        def path(self, *parts):
            return tmp_path.joinpath(*parts)
        def write_json(self, *a, **k):
            return None
        def log(self, *a, **k):
            return None

    report = evaluate_listenability(_Ctx(), edl=None, stage="test")
    assert report["verdict"] == "pass"
    assert report.get("skipped")


def test_speech_band_leak_fails_ambient_bed(tmp_path):
    import array
    import wave

    from interview_mux.mmaudio_asset_qa import analyze_asset_wav

    # Square-ish speech-band energy (ZCR proxy lands in 300–3400 Hz).
    rate = 48000
    n = rate * 2
    samples = array.array("h")
    for i in range(n):
        samples.append(15000 if (i // 24) % 2 == 0 else -15000)
    wav = tmp_path / "ambient_quiet_reflection.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())

    row = analyze_asset_wav(
        asset_id="ambient_quiet_reflection",
        path=wav,
        plan_row={"asset_id": "ambient_quiet_reflection", "role": "ambient_bed"},
    )
    assert "speech_band_leak" in (row.get("reasons") or [])
    assert row.get("verdict") == "fail"
    assert row.get("recommended_action") == "regenerate"


def test_question_budget_uncapped_when_zero():
    from interview_mux.delivery_brief import delivery_brief_cfg
    from interview_mux.config import merged_config

    db = delivery_brief_cfg(merged_config())
    # Config migration sets question_budget_max to 0 = uncapped.
    assert int(db.get("question_budget_max", 0)) == 0


def test_gap_fill_cap_uncapped_at_ratio_one():
    from interview_mux.coverage_limits import gap_fill_cap

    assert gap_fill_cap(100, {"analysis": {"coverage_limits": {"gap_fill_max_ratio": 1.0}}}) == 100


def test_top_up_air_inserts_between_speech_joins():
    from interview_mux.listenability_guards import (
        _top_up_intentional_air,
        intentional_air_ratio,
        reindex_edl_timeline,
    )

    edl = {
        "clips": [
            {"type": "speech", "segment_id": "seg_a", "duration_ms": 50_000},
            {"type": "speech", "segment_id": "seg_b", "duration_ms": 50_000},
            {"type": "speech", "segment_id": "seg_c", "duration_ms": 50_000},
            {"type": "vo_pickup", "line_id": "vo_x", "duration_ms": 9_000},
        ]
    }
    assert intentional_air_ratio(edl) == 0.0
    notes = _top_up_intentional_air(edl, min_ratio=0.01)
    assert notes
    # evaluate_listenability treats value + 0.001 >= min as in-band
    assert intentional_air_ratio(edl) + 0.001 >= 0.01
    reindex_edl_timeline(edl)
    assert edl["clips"][1]["type"] == "silence"


def test_reindex_honors_mix_overlap_ms():
    from interview_mux.listenability_guards import reindex_edl_timeline

    edl = {
        "clips": [
            {"type": "silence", "air_kind": "opening_music", "duration_ms": 14_400, "mix_overlap_ms": 0},
            {
                "type": "speech",
                "segment_id": "seg_a",
                "duration_ms": 10_000,
                "source_start_ms": 0,
                "source_end_ms": 10_000,
                "mix_overlap_ms": 100,
            },
            {
                "type": "transition",
                "duration_ms": 5_000,
                "text": "From there, the conversation turns.",
                "mix_overlap_ms": 80,
            },
        ]
    }
    reindex_edl_timeline(edl)
    assert edl["clips"][0]["timeline_start_ms"] == 0
    assert edl["clips"][1]["timeline_start_ms"] == 14_300
    assert edl["clips"][2]["timeline_start_ms"] == 24_220
    assert edl["timeline_duration_ms"] == 29_220


def test_seat_unused_host_vo_skips_clone_adjacent(tmp_path, monkeypatch):
    import array
    import json
    import wave

    from interview_mux.listenability_guards import (
        host_vo_duration_ratio,
        remediate_listenability_edl,
    )

    run = tmp_path / "run"
    (run / "vo_pickup" / "synthesized").mkdir(parents=True)
    (run / "understanding").mkdir()
    wav = run / "vo_pickup" / "synthesized" / "vo_layup_seg_b.wav"
    rate = 16000
    with wave.open(str(wav), "w") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(array.array("h", [0] * (rate * 2)).tobytes())

    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_b",
                "targets_segment_id": "seg_b",
                "voice_speaker_id": "spk_0",
            }
        ]
    }
    (run / "understanding" / "gap_report.json").write_text(json.dumps(gap))

    class _Ctx:
        run_dir = str(run)

        def artifact_exists(self, rel):
            return (run / rel).is_file()

        def read_json(self, rel):
            return json.loads((run / rel).read_text())

        def path(self, *parts):
            return run.joinpath(*parts)

    edl = {
        "clips": [
            {
                "type": "vo_pickup",
                "line_id": "vo_existing",
                "duration_ms": 20_000,
            },
            {
                "type": "speech",
                "segment_id": "seg_guest",
                "speaker_id": "spk_1",
                "duration_ms": 100_000,
            },
            {
                "type": "speech",
                "segment_id": "seg_b",
                "speaker_id": "spk_0",
                "duration_ms": 50_000,
            },
        ]
    }

    def _spk(_ctx, sid):
        return "spk_0" if sid == "seg_b" else "spk_1"

    monkeypatch.setattr(
        "interview_mux.speaker_level_match.speaker_id_for_segment",
        _spk,
    )
    out, notes = remediate_listenability_edl(_Ctx(), edl)
    assert host_vo_duration_ratio(_Ctx(), out) + 0.001 >= 0.04
    # Already in-band from existing VO — do not force clone-adjacent seating.
    assert not any(c.get("line_id") == "vo_layup_seg_b" for c in out["clips"])


def test_seat_unused_host_vo_before_other_speaker(tmp_path, monkeypatch):
    import array
    import json
    import wave

    from interview_mux.listenability_guards import (
        host_vo_duration_ratio,
        remediate_listenability_edl,
    )

    run = tmp_path / "run"
    (run / "vo_pickup" / "synthesized").mkdir(parents=True)
    (run / "understanding").mkdir()
    wav = run / "vo_pickup" / "synthesized" / "vo_layup_seg_b.wav"
    rate = 16000
    n = rate * 5
    with wave.open(str(wav), "w") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(array.array("h", [0] * n).tobytes())

    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_b",
                "targets_segment_id": "seg_b",
                "voice_speaker_id": "spk_0",
            }
        ]
    }
    (run / "understanding" / "gap_report.json").write_text(json.dumps(gap))

    class _Ctx:
        run_dir = str(run)

        def artifact_exists(self, rel):
            return (run / rel).is_file()

        def read_json(self, rel):
            return json.loads((run / rel).read_text())

        def path(self, *parts):
            return run.joinpath(*parts)

    edl = {
        "clips": [
            {"type": "speech", "segment_id": "seg_b", "duration_ms": 80_000},
        ]
    }
    monkeypatch.setattr(
        "interview_mux.speaker_level_match.speaker_id_for_segment",
        lambda _ctx, sid: "spk_1",
    )
    out, notes = remediate_listenability_edl(_Ctx(), edl)
    assert any(n.startswith("seat_host_vo:vo_layup_seg_b") for n in notes)
    assert any(c.get("line_id") == "vo_layup_seg_b" for c in out["clips"])
    assert host_vo_duration_ratio(_Ctx(), out) > 0.04


def _write_silent_wav(path, *, seconds: int = 5) -> None:
    import array
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 16000
    with wave.open(str(path), "w") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(array.array("h", [0] * (rate * seconds)).tobytes())


def test_seat_unused_host_vo_skips_skipped_optional(tmp_path, monkeypatch):
    import json

    from interview_mux.listenability_guards import remediate_listenability_edl

    run = tmp_path / "run"
    wav = run / "vo_pickup" / "synthesized" / "vo_layup_seg_b.wav"
    _write_silent_wav(wav)
    (run / "understanding").mkdir(parents=True)
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_b",
                "targets_segment_id": "seg_b",
                "voice_speaker_id": "spk_0",
                "skipped_optional": True,
                "delivery": "synthesize",
            }
        ]
    }
    (run / "understanding" / "gap_report.json").write_text(json.dumps(gap))

    class _Ctx:
        run_dir = str(run)

        def artifact_exists(self, rel):
            return (run / rel).is_file()

        def read_json(self, rel):
            return json.loads((run / rel).read_text())

        def path(self, *parts):
            return run.joinpath(*parts)

    edl = {"clips": [{"type": "speech", "segment_id": "seg_b", "duration_ms": 80_000}]}
    monkeypatch.setattr(
        "interview_mux.speaker_level_match.speaker_id_for_segment",
        lambda _ctx, sid: "spk_1",
    )
    out, notes = remediate_listenability_edl(_Ctx(), edl)
    assert any("skip_skipped_optional:vo_layup_seg_b" in n for n in notes)
    assert not any(c.get("line_id") == "vo_layup_seg_b" for c in out["clips"])


def test_seat_unused_host_vo_skips_adjacent_transition(tmp_path, monkeypatch):
    import json

    from interview_mux.listenability_guards import remediate_listenability_edl

    run = tmp_path / "run"
    wav = run / "vo_pickup" / "synthesized" / "vo_layup_seg_b.wav"
    _write_silent_wav(wav)
    (run / "understanding").mkdir(parents=True)
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_b",
                "targets_segment_id": "seg_b",
                "voice_speaker_id": "spk_0",
                "delivery": "synthesize",
            }
        ]
    }
    (run / "understanding" / "gap_report.json").write_text(json.dumps(gap))

    class _Ctx:
        run_dir = str(run)

        def artifact_exists(self, rel):
            return (run / rel).is_file()

        def read_json(self, rel):
            return json.loads((run / rel).read_text())

        def path(self, *parts):
            return run.joinpath(*parts)

    edl = {
        "clips": [
            {"type": "speech", "segment_id": "seg_a", "duration_ms": 80_000},
            {
                "type": "transition",
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "duration_ms": 500,
            },
            {"type": "speech", "segment_id": "seg_b", "duration_ms": 80_000},
        ]
    }
    monkeypatch.setattr(
        "interview_mux.speaker_level_match.speaker_id_for_segment",
        lambda _ctx, sid: "spk_1",
    )
    out, notes = remediate_listenability_edl(_Ctx(), edl)
    assert any("skip_adjacent_synthetic:vo_layup_seg_b" in n for n in notes)
    assert not any(c.get("line_id") == "vo_layup_seg_b" for c in out["clips"])
