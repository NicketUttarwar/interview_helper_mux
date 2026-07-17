from __future__ import annotations

from interview_mux.adaptation_loop_guard import AdaptationLoopGuard, adaptation_loop_cfg
from interview_mux.attempt_budget import max_primary_attempts
from interview_mux.interview_duration_policy import (
    duration_tier,
    max_per_segment_shard_calls,
    primary_attempt_cap,
    transcript_duration_ms,
)
from run_fixtures import isolated_run_ctx, patch_merged_config


def _ctx_with_duration(tmp_path, run_id: str, duration_ms: int):
    ctx = isolated_run_ctx(tmp_path, run_id)
    ctx.write_json(
        "transcript/full.json",
        {"duration_ms": duration_ms, "words": []},
        skip_handoff=True,
    )
    return ctx


def test_duration_tiers() -> None:
    assert duration_tier(14 * 60_000) == "short"
    assert duration_tier(15 * 60_000) == "medium"
    assert duration_tier(59 * 60_000) == "medium"
    assert duration_tier(60 * 60_000) == "long"


def test_primary_attempt_cap_short(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"max_primary_attempts_per_stage": 8}}},
    )
    ctx = _ctx_with_duration(tmp_path, "short", 10 * 60_000)
    assert primary_attempt_cap(ctx) == 8


def test_primary_attempt_cap_medium_45min(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "duration_policy": {
                    "primary_attempts_base": 6,
                    "primary_attempts_per_30min_above_short": 1,
                    "primary_attempts_cap": 16,
                },
                "flow_hardening": {"max_primary_attempts_per_stage": 6},
            }
        },
    )
    ctx = _ctx_with_duration(tmp_path, "med", 45 * 60_000)
    # 30 min above 15 min → +1 block → 7
    assert primary_attempt_cap(ctx) == 7


def test_primary_attempt_cap_four_hours(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "duration_policy": {
                    "primary_attempts_base": 6,
                    "primary_attempts_per_30min_above_short": 1,
                    "primary_attempts_cap": 16,
                },
                "flow_hardening": {"max_primary_attempts_per_stage": 6},
            }
        },
    )
    ctx = _ctx_with_duration(tmp_path, "long", 4 * 60 * 60_000)
    # (240-15)/30 = 7.5 → 7 blocks → 13
    assert primary_attempt_cap(ctx) == 13


def test_primary_attempt_cap_unknown_duration_uses_static_floor(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"max_primary_attempts_per_stage": 8}}},
    )
    ctx = isolated_run_ctx(tmp_path, "no_transcript")
    assert primary_attempt_cap(ctx) == 8


def test_shard_calls_scales_at_two_hours(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {})
    short_ctx = _ctx_with_duration(tmp_path, "sh", 60 * 60_000)
    long_ctx = _ctx_with_duration(tmp_path, "lg", 3 * 60 * 60_000)
    assert max_per_segment_shard_calls(short_ctx) == 24
    assert max_per_segment_shard_calls(long_ctx) == 48


def test_adaptation_guard_loads_duration_scaled_shard_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {})
    ctx = _ctx_with_duration(tmp_path, "very_long", 3 * 60 * 60_000)
    guard = AdaptationLoopGuard.load(ctx, "content_context")
    assert guard.cfg["max_per_segment_shard_calls"] == 48
    assert adaptation_loop_cfg(ctx=ctx)["max_per_segment_shard_calls"] == 48


def test_transcript_duration_ms_zero_without_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "empty")
    assert transcript_duration_ms(ctx) == 0


def test_transcript_duration_ms_from_words_when_duration_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "words_only")
    ctx.write_json(
        "transcript/full.json",
        {"words": [{"start_ms": 0, "end_ms": 890575, "text": "x"}]},
        skip_handoff=True,
    )
    assert transcript_duration_ms(ctx) == 890575
