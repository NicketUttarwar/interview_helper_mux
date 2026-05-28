from __future__ import annotations

from interview_mux.model_registry import next_tier, resolve_model


def test_resolve_model_primary_uses_stage_tier():
    resolved = resolve_model("missing_framing", "primary")
    assert resolved.tier in {"flagship", "explicit"}
    assert resolved.model_id


def test_resolve_model_arbiter_always_economy():
    resolved = resolve_model("missing_framing", "arbiter")
    assert resolved.tier == "economy"


def test_next_tier_caps_at_flagship():
    assert next_tier("economy") == "standard"
    assert next_tier("standard") == "flagship"
    assert next_tier("flagship") == "flagship"
