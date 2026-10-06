"""Rank-to-budget adopt under hosted VO floor (need=3, non-blocking)."""

from __future__ import annotations

import os

import pytest

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.floor_progress import PLAYABILITY_BLOCKERS, floor_miss_blocks_progress
from interview_mux.hosted_vo_authority import floor_snapshot, may_aspirational_proceed
from interview_mux.nugget_layup import (
    GAP_DRAFT_REL,
    GAP_REL,
    PLAN_REL,
    _framing_floor_topup,
    publish_layup_plan_to_gap_report,
    raise_hosted_vo_floor_unsatisfiable,
)
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def _line(
    lid: str,
    seg: str,
    *,
    origin: str = "gap_framing_compose",
    text: str | None = None,
) -> dict:
    return {
        "line_id": lid,
        "origin": origin,
        "gap_type": "extracted_context",
        "targets_segment_id": seg,
        "placement": "before",
        "delivery": "synthesize",
        "text": text or f"Host context for {seg} with enough words to score.",
        "severity": "high",
        "required": True,
    }


def _selection(ctx: RunContext, segs: list[str], *, order_hash: str = "hash_abc") -> None:
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": segs,
            "excluded_segment_ids": [],
            "order_content_hash": order_hash,
        },
        skip_handoff=True,
    )


@pytest.fixture
def ctx(tmp_path, monkeypatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "rank_adopt")
    init_run_meta_for_test(c)
    c._one_writer_raw = True
    segs = ["seg_001", "seg_002", "seg_003", "seg_004"]
    _selection(c, segs)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _c: 3,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.assert_layup_fresh_vs_selection",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.apply_clone_voice_adjacency_skips",
        lambda _c, plan: (plan, []),
    )
    return c


def test_hollow_zero_not_playability_blocker() -> None:
    assert "hosted_vo_hollow_zero" not in PLAYABILITY_BLOCKERS
    assert floor_miss_blocks_progress(None, "hosted_vo_hollow_zero") is False
    assert floor_miss_blocks_progress(None, "hosted_vo_floor") is False


def test_raise_unsatisfiable_never_loud(ctx: RunContext) -> None:
    raise_hosted_vo_floor_unsatisfiable(ctx, need=3, active=0, eligible_nuggets=0)
    raise_hosted_vo_floor_unsatisfiable(ctx, need=3, active=1, eligible_nuggets=0)
    meta = ctx.read_json("run_meta.json")
    assert meta.get("floor_aspirational_proceeded") is True or meta.get(
        "floor_advisories"
    )


def test_floor_snapshot_hollow_aspirational(ctx: RunContext, monkeypatch) -> None:
    ctx.write_json(GAP_REL, {"interviewer_lines": []}, skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _c: True,
    )
    snap = floor_snapshot(ctx, persist=True)
    assert snap.identity.status == "HOLLOW_ZERO"
    assert snap.escalation_should_block is False
    assert may_aspirational_proceed(ctx) is True


def test_framing_floor_topup_adopts_from_prior(ctx: RunContext) -> None:
    prior = [
        _line("vo_a", "seg_001"),
        _line("vo_b", "seg_002"),
        _line("vo_c", "seg_003"),
    ]
    candidate = [
        {
            **_line("vo_layup_seg_004", "seg_004", origin="nugget_layup"),
            "text": "Layup only for seg_004 with enough spoken words here.",
        }
    ]
    filled, notes, _plan = _framing_floor_topup(
        ctx,
        candidate_lines=candidate,
        prior_lines=prior,
        seen_targets={"seg_004"},
        need=3,
        plan={"layups": []},
    )
    active = sum(
        1
        for ln in filled
        if isinstance(ln, dict)
        and not ln.get("skipped_optional")
        and str(ln.get("text") or "").strip()
    )
    assert active >= 3
    assert any(str(ln.get("origin")) == "nugget_layup" for ln in filled)
    assert notes


def test_stale_draft_ignored(ctx: RunContext) -> None:
    ctx.write_json(
        GAP_DRAFT_REL,
        {
            "interviewer_lines": [
                _line("vo_old", "seg_001"),
                _line("vo_old2", "seg_002"),
                _line("vo_old3", "seg_003"),
            ],
            "_meta": {"selection_order_content_hash": "stale_other"},
        },
        skip_handoff=True,
    )
    filled, notes, _ = _framing_floor_topup(
        ctx,
        candidate_lines=[],
        prior_lines=[],
        seen_targets=set(),
        need=3,
        plan={"layups": []},
    )
    assert "stale_draft_ignored" in notes
    count = sum(
        1 for ln in filled if isinstance(ln, dict) and str(ln.get("text") or "").strip()
    )
    assert count == 0


def test_publish_adopts_draft_under_floor(ctx: RunContext) -> None:
    draft_lines = [
        _line("vo_preface", "seg_001"),
        _line("vo_ctx_2", "seg_002"),
        _line("vo_ctx_3", "seg_003"),
        _line("vo_ctx_4", "seg_004"),
    ]
    ctx.write_json(
        GAP_DRAFT_REL,
        {
            "interviewer_lines": draft_lines,
            "_meta": {"selection_order_content_hash": "hash_abc"},
        },
        skip_handoff=True,
    )
    ctx.write_json(
        GAP_REL,
        {
            "interviewer_lines": [
                {
                    **_line("vo_layup_seg_002", "seg_002", origin="nugget_layup"),
                    "text": "Single layup line with enough words for synthesis path.",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_004"],
            "layups": [
                {
                    "target_segment_id": "seg_002",
                    "line_id": "vo_layup_seg_002",
                    "skip": False,
                    "text": "Single layup line with enough words for synthesis path.",
                },
                {
                    "target_segment_id": "seg_003",
                    "skip": True,
                    "skip_reason_code": "listener_already_oriented",
                    "text": "",
                },
            ],
        },
        skip_handoff=True,
    )
    report = publish_layup_plan_to_gap_report(ctx)
    active = sum(
        1
        for ln in (report.get("interviewer_lines") or [])
        if isinstance(ln, dict)
        and not ln.get("skipped_optional")
        and str(ln.get("text") or "").strip()
        and str(ln.get("delivery") or "synthesize")
        in {"", "synthesize", "chatterbox", "record", "mlx_audio"}
    )
    assert active >= 3
    meta = (report.get("_meta") or {}).get("rank_to_budget_adopt") or {}
    assert meta.get("order_content_hash") == "hash_abc"


def test_publish_thrash_guard_skips_second_adopt(ctx: RunContext) -> None:
    thin = [
        {
            **_line("vo_only", "seg_001", origin="nugget_layup"),
            "text": "Only one active hosted line with enough words present.",
        }
    ]
    ctx.write_json(
        GAP_REL,
        {
            "interviewer_lines": thin,
            "_meta": {
                "rank_to_budget_adopt": {
                    "order_content_hash": "hash_abc",
                    "active_after": 1,
                    "need": 3,
                }
            },
        },
        skip_handoff=True,
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_004"],
            "layups": [
                {
                    "target_segment_id": "seg_001",
                    "line_id": "vo_only",
                    "skip": False,
                    "text": "Only one active hosted line with enough words present.",
                }
            ],
        },
        skip_handoff=True,
    )
    report = publish_layup_plan_to_gap_report(ctx)
    adopt = (report.get("_meta") or {}).get("rank_to_budget_adopt") or {}
    assert adopt.get("skipped") == "already_adopted_this_selection"


def test_cta_not_adopted(ctx: RunContext) -> None:
    prior = [
        {
            **_line("vo_cta", "seg_001"),
            "skip_reason_code": "media_ip_cta_hole",
            "text": "Sponsor CTA copy that must never return to air.",
        },
        _line("vo_ok", "seg_002"),
    ]
    filled, _, _ = _framing_floor_topup(
        ctx,
        candidate_lines=[],
        prior_lines=prior,
        seen_targets=set(),
        need=3,
        plan={"layups": []},
    )
    ids = {str(ln.get("line_id")) for ln in filled if isinstance(ln, dict)}
    assert "vo_cta" not in ids
