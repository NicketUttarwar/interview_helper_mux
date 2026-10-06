"""Framing coverage never excludes a hard-keep segment (ISSUES 55)."""

from __future__ import annotations

import pytest

from interview_mux import refinement_passes as rp


class _Ctx:
    run_id = "exec_framing_hard_keep"

    def __init__(self, sel):
        self.sel = sel
        self.committed = None

    def artifact_exists(self, rel):
        return rel == "master/selection.json"

    def read_json(self, rel):
        return self.committed or self.sel


def test_hard_keep_is_not_excluded_by_framing_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    sel = {"ordered_segment_ids": ["seg_001", "seg_059", "seg_060"], "excluded_segment_ids": []}
    ctx = _Ctx(sel)
    committed: dict = {}

    monkeypatch.setattr(rp, "ensure_gap_report_authoritative", lambda c: None, raising=False)
    monkeypatch.setattr(rp, "decide_pass", lambda c, s: {"status": "activate"}, raising=False)
    monkeypatch.setattr(
        "interview_mux.gap_framing.ranking_exclude_segment_ids", lambda c: ["seg_059", "seg_060"]
    )
    monkeypatch.setattr("interview_mux.hard_keep.hard_keep_segment_ids", lambda c, **_k: {"seg_059"})
    monkeypatch.setattr(
        "interview_mux.framing_coverage_guard.validate_framing_ranking", lambda c, s: []
    )

    def _commit(c, s, **kw):
        committed.update(s)
        c.committed = dict(s)
        raise _Stop()

    class _Stop(Exception):
        pass

    monkeypatch.setattr("interview_mux.air_order_boundary.commit_selection_mutation", _commit)
    with pytest.raises(_Stop):
        rp.run_selection_framing_apply(ctx)
    assert committed["ordered_segment_ids"] == ["seg_001", "seg_059"]
    assert [e["segment_id"] for e in committed["excluded_segment_ids"]] == ["seg_060"]
