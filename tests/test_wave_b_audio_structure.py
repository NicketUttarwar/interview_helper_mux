"""Wave B — H-SEG-02 pause ladder + H-ORC-01 interview spine scenario tests."""

from __future__ import annotations

from interview_mux.boundary_observability import (
    ladder_guidance_for_pace,
    observe_boundary_detection_input,
)
from interview_mux.context_volley import _compact_interview_spine, _shape_stage_input
from interview_mux.interview_spine.boundaries import build_boundary_events, _pause_ladder_events
from interview_mux.interview_spine.constants import PAUSE_LADDER_MS
from interview_mux.interview_spine.windows import build_windows, _pace_window_sec
from interview_mux.stage_enrichment import pause_ladder_hints, pause_ladder_hints_from_words
from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_speakers


def _reflective_fireside_words(*, duration_ms: int = 600_000) -> list[dict]:
    """Synthetic calm speech: mix of short gaps and occasional 1.3s reflective pauses."""
    words: list[dict] = []
    t = 0
    for i in range(200):
        words.append({"text": f"w{i}", "start_ms": t, "end_ms": t + 180, "speaker_id": "spk_0"})
        pause = 1300 if i % 5 == 0 else 250
        t += 180 + pause
        if t >= duration_ms:
            break
    return words


def _one_on_one_words(*, duration_ms: int = 600_000) -> list[dict]:
    words: list[dict] = []
    t = 0
    for i in range(120):
        words.append({"text": f"w{i}", "start_ms": t, "end_ms": t + 250, "speaker_id": "spk_0"})
        t += 250 + 900
        if t >= duration_ms:
            break
    return words


def _panel_words() -> list[dict]:
    words: list[dict] = []
    t = 0
    speakers = ["spk_host", "spk_a", "spk_b", "spk_a"]
    for block in range(20):
        spk = speakers[block % len(speakers)]
        for _ in range(8):
            words.append({"text": "word", "start_ms": t, "end_ms": t + 200, "speaker_id": spk})
            t += 400
        t += 1200
    return words


def _technical_dense_words() -> list[dict]:
    words: list[dict] = []
    t = 0
    for _ in range(300):
        words.append({"text": "term", "start_ms": t, "end_ms": t + 120, "speaker_id": "spk_0"})
        t += 120 + 150
    return words


def test_pause_ladder_empty_words_returns_valid_shape(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wb_empty")
    ctx.path("transcript").mkdir(parents=True, exist_ok=True)
    ctx.write_json("transcript/full.json", {"words": []})
    hints = pause_ladder_hints(ctx)
    assert hints["candidates"] == []
    assert hints["thresholds_ms"] == list(PAUSE_LADDER_MS)


def test_pause_ladder_partial_timestamps_skips_pair():
    words = [
        {"start_ms": 0, "end_ms": 100, "text": "a"},
        {"start_ms": None, "end_ms": 200, "text": "b"},
    ]
    hints = pause_ladder_hints_from_words(words)
    assert hints["candidates"][0]["count"] == 0


def test_calm_pace_class_ladder_guidance():
    guidance = ladder_guidance_for_pace("calm")
    assert "400 ms" in guidance
    assert "advisory" in guidance


def test_fireside_400ms_not_more_than_2x_1200ms():
    words = _reflective_fireside_words()
    hints = pause_ladder_hints_from_words(words, pace_class="calm")
    tier400 = next(c for c in hints["candidates"] if c["threshold_ms"] == 400)
    tier1200 = next(c for c in hints["candidates"] if c["threshold_ms"] == 1200)
    assert tier400["count"] <= max(1, tier1200["count"] * 2)


def test_build_windows_calm_uses_12s_policy():
    cfg = {"window_sec_default": 10, "window_sec_dense": 6, "window_sec_calm": 12, "hop_sec": 5}
    assert _pace_window_sec("calm", cfg) == 12.0
    words = _reflective_fireside_words(duration_ms=120_000)
    windows = build_windows(words, pace_class="calm", cfg=cfg)
    assert windows
    assert max(w["end_ms"] - w["start_ms"] for w in windows) <= 12_000 + 500


def test_build_windows_dense_uses_6s_policy():
    cfg = {"window_sec_default": 10, "window_sec_dense": 6, "window_sec_calm": 12, "hop_sec": 5}
    assert _pace_window_sec("dense", cfg) == 6.0
    words = _technical_dense_words()
    windows = build_windows(words, pace_class="dense", cfg=cfg)
    assert windows
    assert max(w["end_ms"] - w["start_ms"] for w in windows) <= 6_000 + 500


def test_technical_deep_dive_prefers_longer_ladder_tiers():
    words = _technical_dense_words()
    hints = pause_ladder_hints_from_words(words, pace_class="dense")
    tier400 = next(c for c in hints["candidates"] if c["threshold_ms"] == 400)
    tier1200 = next(c for c in hints["candidates"] if c["threshold_ms"] == 1200)
    assert tier1200["count"] >= tier400["count"]


def test_panel_ladder_aligns_with_speaker_changes():
    words = _panel_words()
    hints = pause_ladder_hints_from_words(words, pace_class="conversational")
    tier700 = next(c for c in hints["candidates"] if c["threshold_ms"] == 700)
    speaker_changes = []
    for i in range(1, len(words)):
        if words[i].get("speaker_id") != words[i - 1].get("speaker_id"):
            speaker_changes.append(int(words[i]["start_ms"]))
    aligned = sum(
        1 for t in tier700["split_times_ms"] if any(abs(t - sc) <= 2000 for sc in speaker_changes)
    )
    assert aligned >= 1


def test_boundary_events_capped_at_80():
    words = _technical_dense_words()
    windows = build_windows(words, pace_class="dense", cfg={"window_sec_dense": 6, "hop_sec": 5})
    events = build_boundary_events(words=words, windows=windows, wav_path="/nonexistent.wav")
    assert len(events) <= 80


def test_pause_ladder_events_first_hit_per_tier():
    words = [
        {"start_ms": 0, "end_ms": 100, "text": "a"},
        {"start_ms": 900, "end_ms": 1000, "text": "b"},
        {"start_ms": 2000, "end_ms": 2100, "text": "c"},
    ]
    events = _pause_ladder_events(words)
    assert len(events) >= 2
    assert all(e["type"] == "pause_ladder" for e in events)


def test_context_volley_omits_spine_when_missing():
    shaped = _shape_stage_input(
        "boundary_detection",
        {"speakers": {}, "content_brief": {}, "transcript": {"text": "hi"}},
    )
    assert "interview_spine" not in shaped


def test_boundary_volley_includes_pace_class_and_ladder():
    shaped = _shape_stage_input(
        "boundary_detection",
        {
            "speakers": {},
            "content_brief": {},
            "transcript": {"text": "hi"},
            "pause_ladder_hints": pause_ladder_hints_from_words(
                [{"start_ms": 0, "end_ms": 100, "text": "a"}, {"start_ms": 900, "end_ms": 1000, "text": "b"}],
                pace_class="calm",
            ),
            "source_acoustic_profile": {"pacing": {"pace_class": "calm"}},
        },
    )
    assert shaped["pause_ladder_hints"]["pace_class"] == "calm"
    assert shaped["source_acoustic_profile"]["pacing"]["pace_class"] == "calm"


def test_compact_interview_spine_caps_boundary_events():
    spine = {"boundary_events": [{"time_ms": i * 1000, "type": "pause_ladder"} for i in range(100)]}
    compact = _compact_interview_spine(spine, "boundary_detection")
    assert len(compact["top_boundary_events"]) == 40


def test_observe_oversplit_risk_logs(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wb_oversplit")
    payload = {
        "pause_ladder_hints": {
            "candidates": [{"threshold_ms": 400, "count": 60, "split_times_ms": list(range(60))}]
        }
    }
    observe_boundary_detection_input(ctx, payload)
    log_path = ctx.path("gui_log.jsonl")
    assert log_path.is_file()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert any("pause_ladder_oversplit_risk" in line for line in lines)


def test_one_on_one_window_count_baseline_stable():
    words = _one_on_one_words(duration_ms=120_000)
    one_windows = build_windows(words, pace_class="conversational", cfg={"window_sec_default": 10, "hop_sec": 5})
    fireside_words = _reflective_fireside_words(duration_ms=120_000)
    fireside_windows = build_windows(fireside_words, pace_class="calm", cfg={"window_sec_calm": 12, "hop_sec": 5})
    assert len(fireside_windows) <= len(one_windows) * 2


def test_boundary_detection_build_input_includes_pace_and_observability(monkeypatch, tmp_path):
    from interview_mux.stages.segmentation import run_boundaries

    captured: dict = {}

    def fake_run(ctx, stage_key, prompt, build_input, persist, **kwargs):
        captured["payload"] = build_input(ctx)

    monkeypatch.setattr("interview_mux.stages.segmentation.run_analysis_llm_stage", fake_run)

    ctx = isolated_run_ctx(tmp_path, "wb_seg")
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"start_ms": 0, "end_ms": 100, "text": "a"},
                {"start_ms": 900, "end_ms": 1000, "text": "b"},
            ]
        },
    )
    ctx.write_json("understanding/speakers.json", minimal_speakers())
    ctx.write_json("understanding/content_brief.json", minimal_content_brief())
    sap_path = ctx.path("understanding", "source_acoustic_profile.json")
    sap_path.write_text('{"pacing": {"pace_class": "calm"}}', encoding="utf-8")

    monkeypatch.setattr(
        "interview_mux.interview_spine.compact.attach_spine_to_payload",
        lambda ctx, payload, stage_key: None,
    )
    monkeypatch.setattr("interview_mux.interview_spine.config.spine_enabled", lambda *a, **k: False)

    run_boundaries(ctx)
    assert "pause_ladder_hints" in captured["payload"]
    assert captured["payload"]["source_acoustic_profile"]["pacing"]["pace_class"] == "calm"
