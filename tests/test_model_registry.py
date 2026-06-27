from __future__ import annotations

from interview_mux.model_registry import (
    DEFAULT_TIER_MODELS,
    next_tier,
    resolve_model,
    supports_custom_temperature,
    temperature_for_chat,
)


def test_resolve_model_primary_uses_stage_tier():
    resolved = resolve_model("missing_framing", "primary")
    assert resolved.tier == "flagship"
    assert resolved.model_id == DEFAULT_TIER_MODELS["flagship"]


def test_resolve_model_arbiter_always_economy():
    resolved = resolve_model("missing_framing", "arbiter")
    assert resolved.tier == "economy"
    assert resolved.model_id == DEFAULT_TIER_MODELS["economy"]


def test_next_tier_caps_at_flagship():
    assert next_tier("economy") == "standard"
    assert next_tier("standard") == "flagship"
    assert next_tier("flagship") == "flagship"


def test_resolve_model_collate_floor_for_high_severity():
    resolved = resolve_model("missing_framing", "collate")
    assert resolved.tier == "flagship"
    assert resolved.model_id


def test_tiers_resolve_to_distinct_models(monkeypatch):
    from interview_mux import model_registry

    def fake_merged_config():
        return {
            "models": {
                "tiers": {
                    "economy": "gpt-4o-mini",
                    "standard": "gpt-4o",
                    "flagship": "o3",
                },
                "stages": {
                    "speaker_roles": {"tier": "economy"},
                    "boundary_detection": {"tier": "standard"},
                    "missing_framing": {"tier": "flagship"},
                },
            },
            "secrets": {},
        }

    monkeypatch.setattr(model_registry, "merged_config", fake_merged_config)
    economy = resolve_model("speaker_roles", "primary")
    standard = resolve_model("boundary_detection", "primary")
    flagship = resolve_model("missing_framing", "primary")
    assert economy.model_id != flagship.model_id
    assert standard.model_id != flagship.model_id


def test_bump_tier_bypasses_flat_stage_override(monkeypatch):
    from interview_mux import model_registry

    def fake_merged_config():
        return {
            "models": {
                "tiers": {
                    "economy": "gpt-4o-mini",
                    "standard": "gpt-4o",
                    "flagship": "o3",
                },
                "stages": {"missing_framing": {"tier": "standard"}},
                "missing_framing": "gpt-4o",
            },
            "secrets": {},
        }

    monkeypatch.setattr(model_registry, "merged_config", fake_merged_config)
    first = resolve_model("missing_framing", "primary")
    assert first.tier == "explicit"
    assert first.model_id == "gpt-4o"

    bumped = resolve_model("missing_framing", "primary", bump_tier=True)
    assert bumped.tier == "flagship"
    assert bumped.model_id == "o3"


def test_reasoning_models_omit_temperature():
    assert supports_custom_temperature("gpt-4o-mini") is True
    assert supports_custom_temperature("gpt-4o") is True
    assert supports_custom_temperature("o3") is False
    assert supports_custom_temperature("o3-mini") is False
    assert supports_custom_temperature("o1-preview") is False
    assert supports_custom_temperature("o4-mini") is False


def test_temperature_for_chat_by_model_and_task():
    assert temperature_for_chat("gpt-4o-mini", "primary") == 0.2
    assert temperature_for_chat("gpt-4o-mini", "arbiter") == 0.0
    assert temperature_for_chat("o3", "primary") is None
    assert temperature_for_chat("o3", "arbiter") is None
