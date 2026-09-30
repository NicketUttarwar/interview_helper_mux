"""The orientation guard writes the gap report under its current owner's key (ISSUES 95)."""

from __future__ import annotations

import json

import pytest
from run_fixtures import isolated_run_ctx

from interview_mux import refinement_passes as rp


class _Stop(Exception):
    pass


def _seed(ctx, *, layup_authority: bool) -> None:
    gap = ctx.final_path("understanding", "gap_report.json")
    gap.parent.mkdir(parents=True, exist_ok=True)
    doc = {"version": 1, "interviewer_lines": []}
    if layup_authority:
        doc["nugget_layup_authority"] = True
    gap.write_text(json.dumps(doc), encoding="utf-8")
    sel = ctx.final_path("master", "selection.json")
    sel.parent.mkdir(parents=True, exist_ok=True)
    sel.write_text(json.dumps({"ordered_segment_ids": ["seg_001", "seg_002"]}), encoding="utf-8")


@pytest.mark.parametrize(
    "layup_authority, expected_key",
    [(True, "nugget_layup_compose"), (False, "gap_framing_compose")],
)
def test_guard_write_carries_the_owner_key(tmp_path, monkeypatch, layup_authority, expected_key) -> None:
    ctx = isolated_run_ctx(tmp_path, f"exec_orientation_{expected_key}")
    _seed(ctx, layup_authority=layup_authority)
    monkeypatch.setattr(
        "interview_mux.opening_orientation.ensure_episode_orientation",
        lambda _c, report, _ordered, **_k: ({**report, "opening_orientation": {"x": 1}}, [{"action": "mint"}]),
    )
    seen: list[tuple[str, str | None]] = []

    def _write(rel, doc, **kw):
        seen.append((rel, kw.get("stage_key")))
        raise _Stop()

    monkeypatch.setattr(ctx, "write_json", _write)
    with pytest.raises(_Stop):
        rp.after_gap_recompose_or_skip(ctx)
    assert seen == [("understanding/gap_report.json", expected_key)]
