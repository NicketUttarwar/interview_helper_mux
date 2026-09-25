"""Rank-to-budget hosted VO step-down (keep value, prune to ideal).

MUX_FORENSICS=0.
"""

from __future__ import annotations

import os

import pytest

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.hosted_vo_authority import (
    apply_rank_to_budget_fill,
    rank_to_budget_select,
    score_hosted_vo_line,
    vo_budget_bands,
)
from interview_mux.nugget_layup import _scrub_foreign_before_vo_for_hollow_preserve
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def _line(
    lid: str,
    seg: str,
    *,
    origin: str = "gap_framing_compose",
    severity: str = "medium",
    text: str | None = None,
    nugget_ids: list[str] | None = None,
    required: bool = False,
) -> dict:
    return {
        "line_id": lid,
        "origin": origin,
        "gap_type": origin,
        "targets_segment_id": seg,
        "placement": "before",
        "delivery": "synthesize",
        "text": text or f"Contentful host bridge for {seg} with enough words here.",
        "severity": severity,
        "required": required,
        "nugget_ids": list(nugget_ids or []),
    }


@pytest.fixture
def ctx(tmp_path, monkeypatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "rank_budget")
    init_run_meta_for_test(c)
    c._one_writer_raw = True
    c.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": [f"seg_{i:03d}" for i in range(1, 40)],
            "excluded_segment_ids": [],
        },
        skip_handoff=True,
    )
    c.write_json(
        "understanding/gap_vo_rebudget_after_selection.json",
        {
            "version": 1,
            "vo_line_budget": {"min": 0, "ideal": 4, "max": 4},
            "hosted_floor": 3,
        },
        skip_handoff=True,
    )
    return c


def test_score_prefers_high_severity_and_open_nuggets() -> None:
    low = _line("a", "seg_001", severity="low")
    high = _line(
        "b",
        "seg_002",
        severity="high",
        nugget_ids=["n1"],
        required=True,
        origin="nugget_layup",
    )
    assert score_hosted_vo_line(high, open_nugget_ids={"n1"}) > score_hosted_vo_line(low)


def test_rank_to_budget_keeps_ideal_not_all(ctx: RunContext) -> None:
    pool = [
        _line(f"vo_{i}", f"seg_{i:03d}", severity="low" if i > 4 else "high")
        for i in range(1, 13)
    ]
    kept, pruned, meta = rank_to_budget_select(pool, need=3, ideal=4)
    body = [ln for ln in kept if ln.get("origin") == "nugget_layup"]
    assert len(body) == 4
    assert meta["kept_body"] == 4
    assert len(pruned) == 8
    # Winners adopted into layup authority.
    assert all(
        (ln.get("_meta") or {}).get("rank_to_budget_adopted")
        or ln.get("origin") == "nugget_layup"
        for ln in body
    )


def test_hollow_preserve_ranks_to_ideal_not_mass_scrub(ctx: RunContext) -> None:
    lines = [
        _line(
            f"vo_preface_seg_{i:03d}",
            f"seg_{i:03d}",
            severity="high" if i <= 4 else "low",
            text=f"High value bridge number {i} with enough spoken copy for air.",
        )
        for i in range(1, 20)
    ]
    report = {"interviewer_lines": lines, "nugget_layup_authority": False}
    out = _scrub_foreign_before_vo_for_hollow_preserve(
        report,
        min_active=3,
        ideal=4,
        live_targets={f"seg_{i:03d}" for i in range(1, 40)},
    )
    body = [
        ln
        for ln in (out.get("interviewer_lines") or [])
        if isinstance(ln, dict) and ln.get("placement") == "before"
    ]
    assert 3 <= len(body) <= 4
    assert out.get("nugget_layup_authority") is True
    assert (out.get("_meta") or {}).get("hollow_preserve_rank_to_budget")


def test_fill_adopts_framing_and_clears_prefer_native_skip(ctx: RunContext, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority.need",
        lambda _c: 3,
    )
    keep = [
        _line(
            "vo_layup_seg_037",
            "seg_037",
            origin="nugget_layup",
            severity="high",
            text="Cancer can change over time, so a static test may stop being enough.",
        )
    ]
    pool = [
        _line(
            "vo_context_seg_021",
            "seg_021",
            origin="gap_framing_compose",
            severity="high",
            required=True,
            text="Multi-omics brings together DNA, RNA, and protein measurements clearly.",
        ),
        _line(
            "vo_seed_seg_019",
            "seg_019",
            origin="high_gap_vo_fill_no_key",
            severity="high",
            text="What tension carries into what comes next for the listener here?",
        ),
        _line(
            "vo_seed_seg_014",
            "seg_014",
            origin="high_gap_vo_fill_no_key",
            severity="medium",
            text="What claim should we test as this conversation continues onward?",
        ),
        {
            "line_id": "vo_cta",
            "origin": "cta_hole_cover",
            "targets_segment_id": "seg_002",
            "placement": "before",
            "delivery": "synthesize",
            "text": "Please like and subscribe for more oncology content today.",
            "skip_reason_code": "media_ip_cta_hole",
        },
    ]
    plan = {
        "open_talking_point_ids": [],
        "layups": [
            {
                "target_segment_id": "seg_021",
                "skip": True,
                "skip_reason_code": "listener_already_oriented",
                "text": "",
                "compensating_path": "prior_layup_or_native",
            },
            {
                "target_segment_id": "seg_037",
                "skip": False,
                "text": keep[0]["text"],
                "line_id": "vo_layup_seg_037",
            },
        ],
    }
    filled, meta, plan_out = apply_rank_to_budget_fill(
        ctx,
        keep_lines=keep,
        pool_lines=pool,
        plan=plan,
        seen_targets={"seg_037"},
    )
    assert meta["active_before"] == 1
    assert meta["active_after"] >= 3
    assert "vo_cta" not in meta.get("adopted_line_ids", [])
    assert any(ln.get("line_id") == "vo_context_seg_021" for ln in filled)
    assert plan_out is not None
    row_021 = next(
        r for r in plan_out["layups"] if r.get("target_segment_id") == "seg_021"
    )
    assert row_021.get("skip") is False
    assert str(row_021.get("text") or "").strip()
    assert (row_021.get("_meta") or {}).get("rank_to_budget_cleared_prefer_native")


def test_vo_budget_bands_reads_rebudget(ctx: RunContext, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.hosted_vo_authority.need", lambda _c: 3)
    need_n, ideal, max_ = vo_budget_bands(ctx)
    assert need_n == 3
    assert ideal == 4
    assert max_ == 4
