"""The transferred keep list cannot demand a CTA scrap the selection excluded (ISSUES 136).

The run this guards (one-hour source, macOS exec_003): the sponsor outro
seg_035 was split; a to f were excluded as media_ip_cta and the tail
fragments g, h, i (2 s each, "The Life Sciences DNA.", "I'm Daniel Levine.
Thanks for joining", "joining us.") were excluded with an outro / degraded-CTA
reason. Another banned CTA parent was a hard keep, the transfer offered the
whole admitted story set, and every selection commit was refused:
hard_keep_missing_from_order:seg_035g,seg_035h,seg_035i.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import hard_keep as hk
from run_fixtures import isolated_run_ctx

OUTRO_REASON = (
    "seg_035h is retained in the locked order but has an empty, heavily degraded "
    "transcript after the CTA cut; a verified substantive excerpt is required to keep it on air."
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "keep_cta_scrap")

    def _put(rel: str, doc: dict) -> None:
        dest = c.final_path(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(doc), encoding="utf-8")

    segs = [
        {"segment_id": "seg_002", "start_ms": 0, "end_ms": 4000, "text": "parent"},
        {"segment_id": "seg_002a", "start_ms": 0, "end_ms": 2000, "text": "Story sentence one here."},
        {"segment_id": "seg_002b", "start_ms": 2000, "end_ms": 4000, "text": "Story sentence two here."},
        {"segment_id": "seg_035", "start_ms": 90000, "end_ms": 96000, "text": "Thanks again to our sponsor."},
        {"segment_id": "seg_035g", "start_ms": 90000, "end_ms": 92000, "text": "The Life Sciences DNA."},
        {"segment_id": "seg_035h", "start_ms": 92000, "end_ms": 94000, "text": "I'm Daniel Levine. Thanks for joining"},
        {"segment_id": "seg_035i", "start_ms": 94000, "end_ms": 96000, "text": "joining us."},
    ]
    _put("segments/manifest.json", {"segments": segs})
    _put("understanding/ideal_cuts.json", {"must_keep_segment_ids": ["seg_002"], "cuts": []})
    _put(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_002a", "seg_002b"],
            "excluded_segment_ids": [
                {"segment_id": "seg_002", "reason": "media_ip_cta"},
                {"segment_id": "seg_035", "reason": "media_ip_cta"},
                {"segment_id": "seg_035g", "reason": OUTRO_REASON},
                {"segment_id": "seg_035h", "reason": OUTRO_REASON},
                {"segment_id": "seg_035i", "reason": OUTRO_REASON},
            ],
        },
    )
    story = {"seg_002a", "seg_002b", "seg_035g", "seg_035h", "seg_035i"}
    monkeypatch.setattr("interview_mux.media_ip_cta.admitted_story_segment_ids", lambda _c: story)
    monkeypatch.setattr(
        "interview_mux.media_ip_cta.never_touch_segment_ids", lambda _c: {"seg_002", "seg_035"}
    )
    monkeypatch.setattr(
        "interview_mux.media_ip_cta.selection_cta_exclude_ids", lambda _c: {"seg_002", "seg_035"}
    )
    monkeypatch.setattr("interview_mux.media_ip_cta.ranking_cta_omit_ids", lambda _c: set())
    return c


def test_cta_scrap_children_are_not_transferred_keeps(ctx) -> None:
    keeps = hk.hard_keep_segment_ids(ctx)
    assert not {"seg_035g", "seg_035h", "seg_035i"} & keeps
    assert "seg_002a" in keeps


def test_the_committed_selection_passes_the_lattice_lint(ctx) -> None:
    from interview_mux.selection_constraints import lattice_lint_codes

    sel = ctx.read_json("master/selection.json")
    assert not [c for c in lattice_lint_codes(ctx, sel) if c.startswith("hard_keep_missing_from_order")]


def test_a_child_excluded_for_a_non_editorial_reason_is_still_a_keep(ctx) -> None:
    sel = ctx.read_json("master/selection.json")
    for row in sel["excluded_segment_ids"]:
        if row["segment_id"] == "seg_035i":
            row["reason"] = "ranking_budget"
    dest = ctx.final_path("master", "selection.json")
    dest.write_text(json.dumps(sel), encoding="utf-8")
    assert "seg_035i" in hk.hard_keep_segment_ids(ctx)
