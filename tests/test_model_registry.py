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


def test_resolve_model_collate_floor_for_high_severity():
    resolved = resolve_model("missing_framing", "collate")
    assert resolved.tier in {"flagship", "explicit", "standard"}
    assert resolved.model_id


def test_flat_stage_override_wins_for_primary():
    resolved = resolve_model("speaker_roles", "primary")
    assert resolved.tier == "explicit"
    assert resolved.model_id == "gpt-4o-mini"
