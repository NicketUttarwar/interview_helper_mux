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
