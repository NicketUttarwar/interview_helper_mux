"""Regression locks for full_master_ranking hardening (Waves 1–4)."""

from __future__ import annotations

import pytest

from interview_mux.artifact_ownership import (
    FREEZE_WRITE_POLICY,
    owners_of,
    write_permitted,
)
from interview_mux.bridge_completeness import mint_needs_spoken_glue_placeholders
from interview_mux.homunculus.values import should_hard_omit_cta
from interview_mux.open_shape_repair import (
    build_deterministic_ranking_fallback,
    preserve_ranking_membership,
    protect_open_window_order,
)
from run_fixtures import (
    isolated_run_ctx,
    minimal_manifest,
    minimal_manifest_segment,
    minimal_narrative_plan,
)


def test_full_master_ranking_owns_manifest_cta_child() -> None:
    owners = owners_of("segments/manifest.json")
    assert "full_master_ranking" in owners
    assert owners[-1] == "segment_classification"
    assert any(
        p.stage == "full_master_ranking" and p.mutation_class == "cta_child_materialize"
        for p in FREEZE_WRITE_POLICY
    )


def test_ranking_cta_manifest_write_permitted(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fmr_manifest")
    ok, reason = write_permitted(
        ctx,
        "segments/manifest.json",
        "full_master_ranking",
        role="producer",
        mutation_class="cta_child_materialize",
    )
    assert ok, reason


def test_stageinfo_declares_ranking_membership_outputs() -> None:
    from interview_mux.web.stages import DELIVERY_STAGES

    info = next(s for s in DELIVERY_STAGES if s.id == "full_master_ranking")
    outs = set(info.artifacts)
    assert "master/selection.json" in outs
    assert "master/rank_candidates.json" in outs
    assert "master/story_health.json" in outs
    # FMR S6: bridges / SDP owned by selection_order_sanitize
    assert "understanding/reorder_bridges.json" not in outs
    assert "understanding/speaker_delivery_plan.json" not in outs


def test_stageinfo_sanitize_declares_ranking_side_outputs() -> None:
    from interview_mux.web.stages import DELIVERY_STAGES

    info = next(s for s in DELIVERY_STAGES if s.id == "selection_order_sanitize")
    outs = set(info.artifacts)
    assert "master/selection.json" in outs
    assert "understanding/reorder_bridges.json" in outs
    assert "understanding/speaker_delivery_plan.json" in outs


def test_deterministic_ranking_fallback_from_chapters(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fmr_fallback")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001"),
            minimal_manifest_segment("seg_002", start_ms=1000, end_ms=2000),
            minimal_manifest_segment("seg_003", start_ms=2000, end_ms=3000),
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "master/narrative_plan.json",
        minimal_narrative_plan(
            chapters=[
                {
                    "chapter_id": "ch1",
                    "title": "A",
                    "segment_ids": ["seg_002", "seg_001"],
                    "suggested_open_segment_id": "seg_002",
                },
                {
                    "chapter_id": "ch2",
                    "title": "B",
                    "segment_ids": ["seg_003"],
                    "suggested_open_segment_id": "seg_003",
                },
            ]
        ),
        skip_handoff=True,
    )
    arts = build_deterministic_ranking_fallback(ctx)
    assert arts is not None
    assert arts["ordered_segment_ids"] == ["seg_002", "seg_001", "seg_003"]
    assert "narrative_chapters" in arts["order_bind_reason"]


def test_preserve_ranking_membership_keeps_tail() -> None:
    out = preserve_ranking_membership(
        ["a", "b", "c", "d"],
        ["b", "a"],
        manifest_ids={"a", "b", "c", "d"},
    )
    assert out == ["b", "a", "c", "d"]


def test_protect_open_window_order_freezes_head() -> None:
    protected = protect_open_window_order(
        ["open1", "open2", "open3", "body"],
        ["body", "open1", "x"],
        open_slots=3,
    )
    assert protected[:3] == ["open1", "open2", "open3"]
    assert "body" in protected


def test_mint_needs_spoken_glue_tags_incomplete_pairs() -> None:
    bridges = {
        "pairs": [
            {
                "after_id": "a",
                "before_id": "b",
                "text": "Meanwhile—",
            },
            {"after_id": "c", "before_id": "d"},
        ]
    }
    out = mint_needs_spoken_glue_placeholders(None, bridges)
    assert out["needs_spoken_glue_count"] >= 1
    for pair in out["pairs"]:
        if pair.get("after_id") == "a":
            assert pair.get("needs_spoken_glue") is True
            assert pair.get("complete") is False


def test_should_hard_omit_cta_url_and_promo() -> None:
    assert should_hard_omit_cta("Visit us at https://example.com/course today")
    assert should_hard_omit_cta("Use promo code SAVE20 for our newsletter")
    assert not should_hard_omit_cta(
        "Hospitals subscribe to shared research protocols across regions."
    )


def test_commit_ranking_with_deterministic_fallback(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fmr_commit_fb")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_001",
                start_ms=0,
                end_ms=8000,
                text="We opened with the core claim about the trial outcome.",
            ),
            minimal_manifest_segment(
                "seg_002",
                start_ms=8000,
                end_ms=16000,
                text="Then we walked through the clinical evidence that followed.",
            ),
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "master/narrative_plan.json",
        minimal_narrative_plan(
            chapters=[
                {
                    "chapter_id": "ch1",
                    "title": "Open",
                    "segment_ids": ["seg_001", "seg_002"],
                    "suggested_open_segment_id": "seg_001",
                }
            ]
        ),
        skip_handoff=True,
    )
    from interview_mux.stages.selection import commit_ranking_with_deterministic_fallback

    assert commit_ranking_with_deterministic_fallback(ctx)
    sel = ctx.read_json("master/selection.json")
    assert "seg_001" in sel["ordered_segment_ids"]
    assert ctx.is_done("full_master_ranking")


def test_order_reconcile_and_sdp_co_owned_by_ranking() -> None:
    assert "full_master_ranking" in owners_of("master/order_reconcile.json")
    assert "full_master_ranking" in owners_of("understanding/speaker_delivery_plan.json")


def test_cover_ranking_manifest_membership_excludes_orphans(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fmr_cover")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001"),
            minimal_manifest_segment("seg_002", start_ms=1000, end_ms=2000),
            minimal_manifest_segment("orphan_cta", start_ms=2000, end_ms=3000),
        ),
        skip_handoff=True,
    )
    from interview_mux.open_shape_repair import cover_ranking_manifest_membership

    arts = cover_ranking_manifest_membership(
        ctx,
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [],
        },
    )
    excl_ids = {
        str(r.get("segment_id") or "") if isinstance(r, dict) else str(r)
        for r in (arts.get("excluded_segment_ids") or [])
    }
    assert "orphan_cta" in excl_ids
    assert arts.get("exclude_rationales", {}).get("orphan_cta") == "ranking_membership_cover"
    covered = set(arts["ordered_segment_ids"]) | excl_ids
    man = ctx.read_json("segments/manifest.json")
    manifest_ids = {
        str(s.get("segment_id"))
        for s in man["segments"]
        if isinstance(s, dict) and s.get("segment_id")
    }
    assert manifest_ids <= covered


def test_hard_freeze_skips_cta_child_invent(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fmr_hf_invent")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("parent_a")),
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        lambda _ctx: True,
    )
    from interview_mux.nle_state import materialize_split_children_into_manifest

    inserted = materialize_split_children_into_manifest(
        ctx,
        "parent_a",
        ["child_new_1", "child_new_2"],
        stage_key="full_master_ranking",
        mutation_class="cta_child_materialize",
    )
    assert inserted == []
    man = ctx.read_json("segments/manifest.json")
    ids = {str(s.get("segment_id")) for s in man["segments"]}
    assert "child_new_1" not in ids
    assert "child_new_2" not in ids


def test_fmr_s2_inject_ranking_lattice_keeps(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2: playable primary-impact + hard_keeps land in ordered before CTA."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fmr_s2_inject")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001"),
            minimal_manifest_segment("seg_impact", start_ms=1000, end_ms=2000),
            minimal_manifest_segment("seg_keep", start_ms=2000, end_ms=3000),
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_framing_plan.json",
        {
            "acts": [
                {
                    "act_id": "a1",
                    "impact_blocks": [
                        {"source_segment_ids": ["seg_impact"]},
                    ],
                }
            ]
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.hard_keep.hard_keep_segment_ids",
        lambda _ctx: {"seg_keep"},
    )
    from interview_mux.framing_coverage_guard import inject_ranking_lattice_keeps

    out = inject_ranking_lattice_keeps(
        ctx,
        {
            "ordered_segment_ids": ["seg_001"],
            "excluded_segment_ids": [
                {"segment_id": "seg_impact", "reason": "aside"},
                {"segment_id": "seg_keep", "reason": "aside"},
            ],
        },
    )
    ordered = out["ordered_segment_ids"]
    assert "seg_impact" in ordered
    assert "seg_keep" in ordered
    excl = {
        str(r.get("segment_id") or "") if isinstance(r, dict) else str(r)
        for r in (out.get("excluded_segment_ids") or [])
    }
    assert "seg_impact" not in excl
    assert "seg_keep" not in excl


def test_fmr_s2_cta_restore_keeps_primary_impact(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2: CTA prune restore re-admits enforceable primary-impact."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fmr_s2_cta")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001", text="Normal answer about origins."),
            minimal_manifest_segment(
                "seg_impact",
                start_ms=1000,
                end_ms=2000,
                text="The real claim that carries the act.",
            ),
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_framing_plan.json",
        {
            "acts": [
                {
                    "act_id": "a1",
                    "impact_blocks": [{"source_segment_ids": ["seg_impact"]}],
                }
            ]
        },
        skip_handoff=True,
    )
    from interview_mux.framing_coverage_guard import (
        restore_enforceable_primary_impact_natives,
    )

    after = restore_enforceable_primary_impact_natives(
        ctx,
        ["seg_001", "seg_impact"],
        {
            "ordered_segment_ids": ["seg_001"],
            "excluded_segment_ids": [
                {"segment_id": "seg_impact", "reason": "media_ip_cta"}
            ],
        },
    )
    assert "seg_impact" in after["ordered_segment_ids"]


def test_fmr_s5_contract_soft_trimmed_to_build_input() -> None:
    """S5: soft inputs are the attach/persist set; dropped unused rows stay out."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("full_master_ranking")
    assert c is not None
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    outs = {o.path for o in c.outputs}
    assert "understanding/gap_framing_plan.json" in soft
    assert "understanding/ideal_cuts_selection_seed.json" in soft
    assert "mastering/mastering_plan.json" in soft
    assert "understanding/nugget_corpus.json" not in soft
    assert "understanding/nugget_layup_plan.json" not in soft
    assert "transcript/full.json" not in soft
    assert "master/transitions.json" not in soft
    assert "analysis/run_golden_facts.json" not in soft
    assert "master/order_reconcile.json" not in outs
    # FMR S6: bridges / SDP no longer ranking outputs
    assert "understanding/reorder_bridges.json" not in outs
    assert "understanding/speaker_delivery_plan.json" not in outs


def test_fmr_s6_ensure_ranking_side_artifacts(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S6: first consumer writes bridges / story_health after sealed selection."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fmr_s6_sides")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001"),
            minimal_manifest_segment("seg_002", start_ms=1000, end_ms=2000),
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "master/narrative_plan.json",
        minimal_narrative_plan(
            chapters=[
                {
                    "chapter_id": "ch1",
                    "title": "Open",
                    "suggested_open_segment_id": "seg_001",
                    "segment_ids": ["seg_001", "seg_002"],
                }
            ]
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [],
        },
        skip_handoff=True,
    )
    from interview_mux.ranking_side_artifacts import ensure_ranking_side_artifacts

    ensure_ranking_side_artifacts(ctx, stage_key="selection_order_sanitize")
    assert ctx.artifact_exists("understanding/reorder_bridges.json")
    assert ctx.artifact_exists("master/story_health.json")
