from __future__ import annotations

import json

import pytest

from interview_mux import local_volley_framer as local_volley_framer_mod
from interview_mux.context_volley import apply_local_framing_to_volley
from interview_mux.local_volley_framer import (
    LocalFramingResult,
    must_escalate_to_openai,
    parse_framer_response,
    prepare_volley_for_llm,
)
from interview_mux.model_registry import stage_severity
from run_fixtures import isolated_run_ctx


def test_parse_framer_response_caps_turns():
    raw = json.dumps(
        {
            "escalate": False,
            "confidence": 0.9,
            "reason": "ok",
            "volley_turns": [
                {"role": "assistant", "content": "a"},
                {"role": "user", "content": "b"},
                {"role": "assistant", "content": "c"},
            ],
        }
    )
    parsed = parse_framer_response(raw, max_turns=2)
    assert len(parsed["volley_turns"]) == 2
    assert parsed["confidence"] == 0.9


def test_parse_framer_response_invalid_json_escalates_on_error():
    with pytest.raises(ValueError):
        parse_framer_response("not json", max_turns=2)


def test_must_escalate_high_severity():
    force, reason = must_escalate_to_openai(
        "missing_framing",
        severity="high",
        truncation_flags=[],
        operator_verified=False,
    )
    assert force is True
    assert reason == "high_severity_stage"


def test_must_escalate_low_confidence():
    force, _ = must_escalate_to_openai(
        "speaker_roles",
        severity="low",
        truncation_flags=[],
        operator_verified=False,
        parsed={"confidence": 0.2, "volley_turns": [{"role": "assistant", "content": "x"}]},
    )
    assert force is True


def test_apply_local_framing_replaces_middle():
    base = [
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "long prior"},
        {"role": "user", "content": "profile"},
        {"role": "user", "content": "evidence"},
    ]
    framed = [{"role": "assistant", "content": "compressed"}]
    out = apply_local_framing_to_volley(base, framed)
    assert out == [
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "compressed"},
        {"role": "user", "content": "evidence"},
    ]


def test_prepare_volley_skips_when_disabled(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "local_off")
    volley, framing = prepare_volley_for_llm(
        ctx,
        "speaker_roles",
        {"transcript": {"text": "hi"}},
        profile="full",
        task_kind="primary",
        cfg={"local_llm": {"enabled": False}},
    )
    assert framing is None  # explicit opt-out overrides default-on
    assert volley
    assert volley[0]["role"] == "user"


def test_prepare_volley_uses_local_and_openai_fallback(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "local_on")
    monkeypatch.setattr(local_volley_framer_mod, "mlx_available", lambda: True)

    def fake_frame(*_args, **_kwargs):
        return LocalFramingResult(
            escalate=True,
            confidence=0.95,
            reason="high_severity_stage",
            volley_turns=[{"role": "assistant", "content": "compressed priors"}],
            used_local=True,
            model_id="test-model",
            latency_ms=10,
            tokens_approx=50,
            volley_turn_count=1,
        )

    monkeypatch.setattr(local_volley_framer_mod, "frame_volley_with_local", fake_frame)
    volley, framing = prepare_volley_for_llm(
        ctx,
        "missing_framing",
        {"segments": {"segments": []}},
        profile="full",
        task_kind="primary",
        cfg={"local_llm": {"enabled": True}},
    )
    assert framing is not None
    assert framing.used_local is True
    assert framing.escalate is True
    assert any("compressed priors" in m.get("content", "") for m in volley)


def test_stage_severity_tiers():
    assert stage_severity("speaker_roles") == "low"
    assert stage_severity("boundary_detection") == "medium"
    assert stage_severity("missing_framing") == "high"


def test_prepare_volley_falls_back_when_mlx_missing(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "local_fail")
    monkeypatch.setattr(local_volley_framer_mod, "mlx_available", lambda: False)
    volley, framing = prepare_volley_for_llm(
        ctx,
        "content_context",
        {"transcript": {"text": "hello world"}},
        profile="full",
        task_kind="primary",
        cfg={"local_llm": {"enabled": True}},
    )
    assert framing is not None
    assert framing.escalate is True
    assert framing.fallback == "mlx_unavailable"
    assert volley[0]["role"] == "user"
