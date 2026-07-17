"""Tests for holistic fabrication fallback."""

from __future__ import annotations

import json

import pytest

from interview_mux.holistic_fabrication import (
    _repair_topic_coverage_deterministic,
    mark_holistic_fabrication_cleared,
    should_accept_holistic_fabrication,
    try_holistic_fabrication,
)
from run_fixtures import isolated_run_ctx, patch_merged_config


def _topic_coverage_brief() -> dict:
    return {
        "thesis": "Test thesis about entrepreneurship.",
        "topics": [
            {
                "name": "Building a healthy business culture",
                "summary": "ESOP and sustainable growth.",
                "segment_ids": ["seg_006"],
            },
            {
                "name": "From rural India to Silicon Valley and back",
                "summary": "Education and return to India.",
                "segment_ids": ["seg_001"],
            },
        ],
        "key_claims": [],
    }


def _manifest() -> dict:
    return {
        "segments": [
            {
                "segment_id": "seg_001",
                "type": "setup",
                "topic_tags": ["from_rural_india_to_silicon_valley_and_back"],
                "text": "deep dive into Indian entrepreneurship material on Vijay",
            },
            {
                "segment_id": "seg_003",
                "type": "interviewee_answer",
                "topic_tags": [],
                "text": "leading up to this acquisition career arc beyond building a successful business",
            },
            {
                "segment_id": "seg_004",
                "type": "interviewee_answer",
                "topic_tags": [],
                "text": "navigating the Indian market health food sector human element",
            },
            {
                "segment_id": "seg_006",
                "type": "interviewee_answer",
                "topic_tags": ["building_a_healthy_business_culture"],
                "text": "healthy business ESOP employee ownership sustainable growth",
            },
        ]
    }


def test_repair_topic_coverage_maps_orphans_and_synthesizes_claims(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "hf_tc_det")
    brief = _topic_coverage_brief()
    manifest = _manifest()
    artifacts = {
        "topic_mappings": [
            {
                "topic": "Building a healthy business culture",
                "segment_ids": ["seg_006"],
                "covered": True,
            },
            {
                "topic": "From rural India to Silicon Valley and back",
                "segment_ids": ["seg_001"],
                "covered": True,
            },
        ],
        "claim_mappings": [],
        "missing_coverage": [],
        "orphan_segment_ids": ["seg_003", "seg_004"],
        "coverage_score": 1.0,
    }
    repaired, upstream, actions = _repair_topic_coverage_deterministic(
        ctx,
        artifacts,
        stage_inputs={"content_brief": brief, "segments": manifest},
    )
    assert "seg_003" not in (repaired.get("orphan_segment_ids") or [])
    assert any("synthesize_key_claims" in a for a in actions)
    assert upstream.get("understanding/content_brief.json", {}).get("key_claims")
    assert len(repaired.get("claim_mappings") or []) >= 2


def test_mark_holistic_clears_envelope_and_overrides_arbiter():
    envelope = {"status": "blocked", "artifacts": {"coverage_score": 0.9}}
    arbiter = {"verdict": "enqueue_investigation", "gaps": ["grounding"]}
    updated = mark_holistic_fabrication_cleared(envelope, arbiter, actions=["test"])
    assert envelope["status"] == "complete"
    assert should_accept_holistic_fabrication(envelope)
    assert updated is not None
    assert updated["verdict"] == "accept"


def test_try_holistic_fabrication_clears_blocked_topic_coverage(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "hf_tc_int")
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "holistic_fabrication": {
                    "enabled": True,
                    "llm_enabled": False,
                    "deterministic_first": True,
                }
            }
        },
    )
    brief_path = ctx.path("understanding", "content_brief.json")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(json.dumps(_topic_coverage_brief()), encoding="utf-8")
    manifest_path = ctx.path("segments", "manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")

    envelope = {
        "status": "blocked",
        "artifacts": {
            "topic_mappings": [
                {
                    "topic": "Building a healthy business culture",
                    "segment_ids": ["seg_006"],
                    "covered": True,
                },
            ],
            "claim_mappings": [],
            "orphan_segment_ids": ["seg_003", "seg_004"],
            "coverage_score": 1.0,
        },
        "memory_updates": {},
        "needs": [],
        "follow_up_investigations": [],
    }
    arbiter = {
        "verdict": "enqueue_investigation",
        "reasoning_summary": "orphan segments",
    }
    result = try_holistic_fabrication(
        ctx,
        "topic_coverage_audit",
        envelope,
        arbiter_result=arbiter,
        lint_errors=["envelope_status_complete: status is not complete"],
    )
    assert result.cleared
    assert result.envelope["status"] == "complete"
    assert should_accept_holistic_fabrication(result.envelope)
    assert ctx.artifact_exists("understanding/content_brief.json")
    brief = ctx.read_json("understanding/content_brief.json")
    assert brief.get("key_claims")
