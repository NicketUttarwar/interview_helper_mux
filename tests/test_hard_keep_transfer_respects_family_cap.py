"""The transferred keep list cannot demand a child the family cap took off air (ISSUES 132).

The run this guards (one-hour source, exec_102): a CTA parent (seg_002, a
hard keep) was split into twelve children, ten of them admitted story. The
family cap aired eight (a to h) and excluded i and j. An overlap union then
folded h into g. The keep transfer recomputed its own eight from the whole
story set, g and h collapsed to one, the eighth slot moved to seg_002i, and
junction's remaster was refused: hard_keep_missing_from_order:seg_002i.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import hard_keep as hk
from run_fixtures import isolated_run_ctx

KIDS = [f"seg_002{c}" for c in "abcdefghij"]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "keep_cap")

    def _put(rel: str, doc: dict) -> None:
        dest = c.final_path(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(doc), encoding="utf-8")

    segs = [{"segment_id": "seg_002", "start_ms": 0, "end_ms": 10000, "text": "parent"}]
    for i, sid in enumerate(KIDS):
        start, end = i * 1000, (i + 1) * 1000
        if sid == "seg_002g":
            end = 8000  # the union folded h into g
        segs.append({"segment_id": sid, "start_ms": start, "end_ms": end, "text": f"story sentence number {i} here."})
    _put("segments/manifest.json", {"segments": segs})
    _put("understanding/ideal_cuts.json", {"must_keep_segment_ids": ["seg_002"], "cuts": []})
    _put(
        "master/selection.json",
        {
            "ordered_segment_ids": KIDS[:8],
            "excluded_segment_ids": [
                {"segment_id": "seg_002", "reason": "media_ip_cta"},
                {"segment_id": "seg_002i", "reason": "cap_same_family_on_air"},
                {"segment_id": "seg_002j", "reason": "cap_same_family_on_air"},
            ],
        },
    )
    monkeypatch.setattr("interview_mux.media_ip_cta.admitted_story_segment_ids", lambda _c: set(KIDS))
    monkeypatch.setattr("interview_mux.media_ip_cta.never_touch_segment_ids", lambda _c: {"seg_002"})
    monkeypatch.setattr("interview_mux.media_ip_cta.selection_cta_exclude_ids", lambda _c: {"seg_002"})
    monkeypatch.setattr("interview_mux.media_ip_cta.ranking_cta_omit_ids", lambda _c: set())
    return c


def test_the_lattice_drops_are_read_from_the_selection(ctx) -> None:
    assert hk.lattice_dropped_ids(ctx) == {"seg_002i", "seg_002j"}


def test_a_capped_child_is_not_a_transferred_keep(ctx) -> None:
    keeps = hk.hard_keep_segment_ids(ctx)
    assert "seg_002i" not in keeps and "seg_002j" not in keeps
    # Every keep the transfer names is on air: nothing is demanded that the cap excluded.
    on_air = set(KIDS[:8])
    assert {k for k in keeps if k.startswith("seg_002")} <= on_air
    assert "seg_002a" in keeps


def test_the_committed_selection_passes_the_lattice_lint(ctx) -> None:
    from interview_mux.selection_constraints import lattice_lint_codes

    sel = ctx.read_json("master/selection.json")
    assert not [c for c in lattice_lint_codes(ctx, sel) if c.startswith("hard_keep_missing_from_order")]


def test_a_child_excluded_for_another_reason_is_still_a_keep(ctx) -> None:
    """Only the lattice's own rulings are honoured; a wrongful drop is still refused."""
    sel = ctx.read_json("master/selection.json")
    sel["ordered_segment_ids"] = [s for s in KIDS[:8] if s != "seg_002c"]
    sel["excluded_segment_ids"].append({"segment_id": "seg_002c", "reason": "editorial_trim"})
    ctx.final_path("master", "selection.json").write_text(json.dumps(sel), encoding="utf-8")
    assert "seg_002c" in hk.hard_keep_segment_ids(ctx)


def test_without_a_selection_every_story_child_is_offered(ctx) -> None:
    ctx.final_path("master", "selection.json").unlink()
    assert hk.lattice_dropped_ids(ctx) == set()
    keeps = hk.hard_keep_segment_ids(ctx)
    assert len({k for k in keeps if k.startswith("seg_002")}) >= 8
