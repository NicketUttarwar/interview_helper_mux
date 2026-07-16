"""Holistic truncation cap-boost rebuild tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from interview_mux.context_volley import truncation_flags_for_volley
from interview_mux.truncation_policy import (
    apply_context_cap_boost,
    context_cap_boost,
    rebuild_volley_clearing_truncation,
)


def test_apply_context_cap_boost_baseline_unchanged():
    assert apply_context_cap_boost(400) == 400


def test_apply_context_cap_boost_multiplies_and_clears_field_floor():
    with context_cap_boost(1, clear_field_truncation=True):
        # 400 * 2.0 = 800, but clear-field floor raises to 8000
        assert apply_context_cap_boost(400, field_clip=True) >= 8000


def test_rebuild_volley_clearing_truncation_raises_caps_until_clean():
    ctx = MagicMock()
    long_text = "x" * 1200
    stage_input = {
        "content_brief": {"thesis": "t", "topics": []},
        "segments": {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "text": long_text,
                }
            ]
        },
        "speakers": {"speakers": []},
    }

    baseline_calls = {"n": 0}

    def fake_prepare(ctx_arg, stage_key, stage_input_arg, **kwargs):
        from interview_mux.context_volley import _char_limit, _clip_text

        baseline_calls["n"] += 1
        text_max = _char_limit("segment_text_max_chars", 400, field_clip=True)
        clipped = _clip_text(long_text, text_max)
        volley = [{"role": "user", "content": clipped}]
        return volley, None

    with patch(
        "interview_mux.local_volley_framer.prepare_volley_for_llm",
        side_effect=fake_prepare,
    ):
        # Simulate initial truncated volley (400-char clip)
        initial = [{"role": "user", "content": long_text[:400] + "\n…[truncated]"}]
        assert "field_truncated" in truncation_flags_for_volley(initial)

        result = rebuild_volley_clearing_truncation(
            ctx,
            "content_brief_reanchor",
            stage_input,
            profile="full",
            task_kind="primary",
            initial_volley=initial,
            initial_flags=["field_truncated"],
        )

    assert result.cleared is True
    assert not result.flags
    assert "…[truncated]" not in result.volley[0]["content"]
    assert result.boost_round >= 1
    assert baseline_calls["n"] >= 1
    assert any(s.startswith("cap_boost_r") for s in result.steps)


def test_slice_stage_input_filters_reanchor_segments():
    from interview_mux.llm_subtasks import _slice_stage_input

    stage_input = {
        "content_brief": {"thesis": "t"},
        "segments": {
            "segments": [
                {"segment_id": "seg_001", "text": "a" * 500},
                {"segment_id": "seg_002", "text": "b" * 500},
            ]
        },
    }
    sliced = _slice_stage_input(
        "content_brief_reanchor",
        stage_input,
        {"label": "seg_002", "segment_ids": ["seg_002"]},
    )
    segs = sliced["segments"]["segments"]
    assert len(segs) == 1
    assert segs[0]["segment_id"] == "seg_002"
