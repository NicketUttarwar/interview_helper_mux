"""Tests for LLM field fabrication (fabricate_enabled main branch)."""

from __future__ import annotations

from interview_mux.field_path_match import path_matches_pattern
from interview_mux.llm_fabricate import fabricate_field_values
from run_fixtures import patch_merged_config


def _null_policy_cfg(**overrides: object) -> dict:
    return {
        "analysis": {
            "llm_null_policy": {
                "enabled": True,
                "fabricate_enabled": True,
                **overrides,
            }
        }
    }


def test_fabricate_field_values_enabled_main_branch(monkeypatch):
    """Regression: fabricate_enabled=True must not raise NameError on path matching."""
    patch_merged_config(monkeypatch, _null_policy_cfg())
    artifacts = {
        "thesis": "Main point",
        "topics": [{"name": "Tech", "summary": "Topic summary"}],
    }
    updated, provenance = fabricate_field_values(
        None,
        "content_context",
        artifacts,
        ["audience"],
    )
    assert updated["audience"] == "General audience"
    assert len(provenance) == 1
    assert provenance[0]["action"] == "fabricate"
    assert provenance[0]["source"] == "deterministic_benign"


def test_fabricate_field_values_skips_never_fabricate_paths(monkeypatch):
    patch_merged_config(monkeypatch, _null_policy_cfg())
    artifacts = {"topics": [{"name": "A", "segment_ids": None}]}
    updated, provenance = fabricate_field_values(
        None,
        "content_context",
        artifacts,
        ["topics[0].segment_ids"],
    )
    assert updated["topics"][0].get("segment_ids") is None
    assert provenance == []


def test_path_matches_pattern_shared_helper():
    assert path_matches_pattern("speakers[0].role", "speakers[].role")
    assert path_matches_pattern("topics[2].name", "topics[].name")
    assert path_matches_pattern("key_claims[0].segment_ids", "key_claims[].segment_ids")
