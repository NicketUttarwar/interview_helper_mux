"""Pre-ranking fuse harden: G1–G6 + H1–H6 policies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from interview_mux.artifact_ownership import write_permitted
from interview_mux.delivery_guardrails import (
    MUST_PRECEDE,
    clamp_resume_through_order,
    earliest_incomplete_must_precede,
)
from interview_mux.delivery_invariants import (
    PRE_RANKING_SEED_CHAIN,
    seed_order_heal_action,
)
from interview_mux.homunculus.agenda import stage_outputs_present
from interview_mux.run_context import RunContext
from interview_mux.segment_fuse import (
    FUSE_ROUNDS_PRE_RANKING_PATH,
    connector_fuse_cfg_for_pass,
    ensure_connector_fuse_enabled_for_full_auto,
    fuse_writer_stage,
    select_pending_seam_packets,
)
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.stages.low_conf_fuse_stages import junction_fuse_evidence
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "pre_rank_harden")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_g1_pre_ranking_index_write_permitted_with_mutation(ctx: RunContext) -> None:
    ok, reason = write_permitted(
        ctx,
        "transcripts/index.json",
        "connector_fuse_pass_pre_ranking",
        role="producer",
        verb="persist",
        mutation_class="segment_id_remap",
    )
    assert ok, reason


def test_h1_pre_ranking_tier_is_standard() -> None:
    conf = connector_fuse_cfg_for_pass("pre_ranking")
    assert conf.get("llm_tier") == "standard"
    assert conf.get("prefer_fuse_when_hint_and_uncertain") is False
    analysis = connector_fuse_cfg_for_pass("post_sanitize")
    assert analysis.get("llm_tier") == "economy"


def test_g3_settled_pair_skipped_unless_hash_or_chapter(ctx: RunContext) -> None:
    ctx.write_json(
        "analysis/connector_fuse_audit.json",
        {
            "version": 1,
            "stay_independent": [
                {
                    "pair_id": "seg_a__seg_b",
                    "seam_hash": "hash1",
                    "decision": "stay_independent",
                }
            ],
            "applied_fuses": [],
            "passes": [],
        },
        skip_handoff=True,
    )
    same = {
        "pair_id": "seg_a__seg_b",
        "seam_hash": "hash1",
        "earlier_segment_id": "seg_a",
        "later_segment_id": "seg_b",
        "earlier_end_ms": 1000,
        "later_start_ms": 1100,
    }
    pending, reopened, skipped = select_pending_seam_packets(
        ctx, [same], pass_id="pre_ranking", force_readjudicate=False
    )
    assert pending == []
    assert skipped == 1
    assert reopened == []

    changed = dict(same, seam_hash="hash2")
    pending2, reopened2, skipped2 = select_pending_seam_packets(
        ctx, [changed], pass_id="pre_ranking", force_readjudicate=False
    )
    assert len(pending2) == 1
    assert skipped2 == 0
    assert reopened2 and reopened2[0]["reason"] == "seam_hash_changed"


def test_g4_h6_incompleteness_missing_manifest_and_wrong_pass(ctx: RunContext) -> None:
    assert stage_artifact_incompleteness(ctx, "connector_fuse_pass_pre_ranking")
    ctx.write_json(
        FUSE_ROUNDS_PRE_RANKING_PATH,
        {"pass_id": "post_sanitize", "total_applied": 0},
        skip_handoff=True,
    )
    assert stage_artifact_incompleteness(ctx, "connector_fuse_pass_pre_ranking")
    ctx.write_json(
        FUSE_ROUNDS_PRE_RANKING_PATH,
        {"pass_id": "pre_ranking", "skip_reason": "missing_manifest", "total_applied": 0},
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, "connector_fuse_pass_pre_ranking")
    assert reason and "missing" in reason.lower()
    assert stage_outputs_present(ctx, "connector_fuse_pass_pre_ranking") is False
    ctx.write_json(
        FUSE_ROUNDS_PRE_RANKING_PATH,
        {"pass_id": "pre_ranking", "skip_reason": "disabled", "total_applied": 0},
        skip_handoff=True,
    )
    assert stage_artifact_incompleteness(ctx, "connector_fuse_pass_pre_ranking") is None


def test_h6_c_full_auto_forces_enabled(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.segment_fuse.connector_fuse_cfg",
        lambda _cfg=None: {"enabled": False},
    )
    ctx.write_json(
        "run_meta.json",
        {"full_auto": True, "run_mode": "full-auto"},
        skip_handoff=True,
    )
    assert ensure_connector_fuse_enabled_for_full_auto(ctx) is True


def test_h4_junction_evidence_false_without_residuals(ctx: RunContext) -> None:
    assert junction_fuse_evidence(ctx) is False
    ctx.write_json(
        "operator/delivery_residuals.json",
        {
            "residuals": [
                {
                    "kind": "fuse_oscillation",
                    "severity": "critical",
                    "stage": "connector_fuse_pass_pre_ranking",
                    "detail": {"pass_id": "pre_ranking"},
                }
            ]
        },
        skip_handoff=True,
    )
    assert junction_fuse_evidence(ctx) is True


def test_g6_must_precede_and_seed_clamp(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    assert "narrative_arc_plan" in MUST_PRECEDE["connector_fuse_pass_pre_ranking"]
    assert PRE_RANKING_SEED_CHAIN[0] == "narrative_arc_plan"

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.producer_ready",
        lambda c, s: s != "narrative_arc_plan",
    )
    pin = clamp_resume_through_order(ctx, "selection_order_sanitize")
    assert pin == "narrative_arc_plan"
    hole = earliest_incomplete_must_precede(ctx, "connector_fuse_pass_pre_ranking")
    assert hole == "narrative_arc_plan"
    _action, resume = seed_order_heal_action(
        ctx,
        "narrative_arc_plan",
        message=(
            "seed order: complete narrative_arc_plan before running "
            "connector_fuse_pass_pre_ranking"
        ),
    )
    assert resume == "narrative_arc_plan"


def test_g5_writer_stage_pre_ranking() -> None:
    assert fuse_writer_stage("pre_ranking") == "connector_fuse_pass_pre_ranking"


def test_g1_rewrite_index_passes_mutation(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux import asset_transcripts as at

    writes: list[dict[str, Any]] = []

    def _capture_write(rel: str, data: Any, **kwargs: Any) -> None:
        writes.append({"rel": rel, **kwargs})
        path = ctx.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        path.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(ctx, "write_json", _capture_write)
    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id",
        lambda: "connector_fuse_pass_pre_ranking",
    )
    at.rewrite_index(ctx)
    assert writes
    hit = next(w for w in writes if w["rel"] == at.INDEX_REL)
    assert hit.get("mutation_class") == "segment_id_remap"
    assert hit.get("stage_key") == "connector_fuse_pass_pre_ranking"
