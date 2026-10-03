"""Sponsor-outro scraps of a closing CTA parent never stay on air (ISSUES 147, exec_010).

seg_038 (sponsor read + credits) closed the tape. The recut excluded seg_038a-f as
media_ip_cta and admitted g-k as story: "The Life Sciences DNA.", "I'm Daniel
Levine. Thanks for joining us.", corrupt fragments. nugget_layup_compose refused
them as post-roll on every attempt; its selection need ("post-roll/end-credit or
corrupt fragments") was not read as an outro, so it stayed blocking.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import media_ip_cta as m
from run_fixtures import isolated_run_ctx

TAIL = {
    "seg_038g": (3532000, 3534000, "The Life Sciences DNA."),
    "seg_038h": (3534000, 3538000, "I'm Daniel Levine. Thanks for joining us."),
    "seg_038i": (3538000, 3564000, "You most of the time, Michael."),
    "seg_038j": (3564000, 3565000, "You are listening to your follow -up."),
    "seg_038k": (3565000, 3567460, "-up. You are listening to us bone and cut -edge"),
}


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, closes_tape: bool = True):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "exec_outro_tail")
    shift = 0 if closes_tape else -600_000
    segs = [{"segment_id": "seg_037", "start_ms": 3400000 + shift, "end_ms": 3503000 + shift, "text": "That is where we close."}]
    segs += [
        {"segment_id": sid, "start_ms": a + shift, "end_ms": b + shift, "text": t}
        for sid, (a, b, t) in TAIL.items()
    ]
    if not closes_tape:
        segs.append({"segment_id": "seg_039", "start_ms": 3000000, "end_ms": 3567460, "text": "More interview after the break."})
    sel = {
        "ordered_segment_ids": ["seg_037", *TAIL] + ([] if closes_tape else ["seg_039"]),
        "excluded_segment_ids": [
            {"segment_id": "seg_038", "reason": "media_ip_cta"},
            *[{"segment_id": f"seg_038{x}", "reason": "media_ip_cta"} for x in "abcdef"],
        ],
    }
    for rel, doc in (("segments/manifest.json", {"segments": segs}), ("master/selection.json", sel)):
        dest = c.final_path(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(m, "admitted_story_segment_ids", lambda _c: set(TAIL))
    monkeypatch.setattr(m, "never_touch_segment_ids", lambda _c: {"seg_038"})
    return c, sel


def test_closing_outro_tail_is_scrap_even_when_admitted_as_story(tmp_path, monkeypatch) -> None:
    ctx, sel = _ctx(tmp_path, monkeypatch)
    assert sorted(m.on_air_orphaned_cta_scrap_ids(ctx, sel)) == sorted(TAIL)


def test_a_cta_parent_mid_tape_keeps_its_story_children(tmp_path, monkeypatch) -> None:
    ctx, sel = _ctx(tmp_path, monkeypatch, closes_tape=False)
    picked = set(m.on_air_orphaned_cta_scrap_ids(ctx, sel))
    assert "seg_038i" not in picked and "seg_038g" not in picked


def test_layup_outro_need_is_executed_not_blocking() -> None:
    need = {
        "type": "rerun_stage",
        "stage": "selection",
        "reason": (
            "Remove seg_038g, seg_038h, seg_038i, seg_038j and seg_038k from the locked air "
            "order. They are post-roll/end-credit or corrupt fragments after the coherent "
            "close in seg_037, and cannot be made narrative-safe with VO."
        ),
    }
    assert m.is_selection_cta_omit_need(need)
    assert not m.is_editorial_exclude_reason("ranking_budget")


def test_undecodable_text_is_a_scrap() -> None:
    assert m.looks_like_orphaned_cta_scrap("You are listening to usHS� bone and cut")


def test_the_parent_keep_is_not_transferred_onto_the_outro_tail(tmp_path, monkeypatch) -> None:
    """exec_011: seg_032 was a must-keep CTA parent; its keep moved onto g-k and
    removal_authority refused the outro omit on every pass (ISSUES 148)."""
    from interview_mux import hard_keep as hk

    ctx, _sel = _ctx(tmp_path, monkeypatch)
    dest = ctx.final_path("understanding", "ideal_cuts.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"must_keep_segment_ids": ["seg_038"], "cuts": []}), encoding="utf-8")
    monkeypatch.setattr(m, "selection_cta_exclude_ids", lambda _c: {"seg_038"})
    monkeypatch.setattr(m, "ranking_cta_omit_ids", lambda _c: set())
    keeps = hk.hard_keep_segment_ids(ctx)
    assert not set(TAIL) & keeps
