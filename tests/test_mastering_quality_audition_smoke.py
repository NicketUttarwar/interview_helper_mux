"""Smoke: audition manifests are planned without needing to render audio."""

from __future__ import annotations

from interview_mux.mastering_auditions import (
    build_manifest,
    plan_hash,
    select_audition_candidates,
)
from tests.mastering_quality_corpus import candidates, load_fixture


def test_audition_manifest_covers_opening_hinge_and_dense():
    fixture, _ = load_fixture("business_panel_rich")
    cand = candidates(fixture)[0]
    manifest = build_manifest(cand, fixture["segments"])
    kinds = {w["kind"] for w in manifest["windows"]}
    assert "opening" in kinds
    assert "hinge" in kinds
    assert "dense" in kinds
    assert 0 < manifest["total_duration_ms"] <= 90000
    assert manifest["rendered"] is False
    assert manifest["plan_hash"] == plan_hash(cand)


def test_audition_without_cold_open_still_renders_an_opening():
    fixture, _ = load_fixture("memoir_monologue_noisy")
    manifest = build_manifest(candidates(fixture)[0], fixture["segments"])
    opening = next(w for w in manifest["windows"] if w["kind"] == "opening")
    assert opening["source_refs"]
    assert "body start" in (opening.get("note") or "")


def test_select_audition_candidates_respects_max_and_eligibility():
    fixture, _ = load_fixture("business_panel_rich")
    cands = candidates(fixture)
    selected = select_audition_candidates(
        cands,
        eligible_ids={"cand_2"},
        cfg={"mastering": {"quality_hardening": {"auditions": {"max_auditions": 1}}}},
    )
    assert [c["candidate_id"] for c in selected] == ["cand_2"]


def test_hook_landmine_fixture_plans_an_opening_from_the_hook_segment():
    fixture, _ = load_fixture("technical_1on1_landmined")
    manifest = build_manifest(candidates(fixture)[0], fixture["segments"])
    opening = next(w for w in manifest["windows"] if w["kind"] == "opening")
    assert "seg_3" in opening["source_refs"]
