"""Tests for production_profile module (production_style / tbiy_narrative)."""

from __future__ import annotations

from interview_mux.production_profile import get_profile, mix_rules, sfx_caps, is_tbiy


def test_get_profile_has_style_key():
    p = get_profile(None)
    assert "production_style" in p


def test_mix_rules_returns_dict():
    assert isinstance(mix_rules(None), dict)


def test_sfx_caps_returns_ints():
    caps = sfx_caps(None)
    assert "max_assets_flow1" in caps
    assert isinstance(caps["max_assets_flow1"], int)
