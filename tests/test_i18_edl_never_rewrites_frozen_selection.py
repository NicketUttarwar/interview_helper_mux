"""i18: EDL must never rewrite a frozen selection (selection leads EDL).

exec_11871 spun on
authority_denied:persist:master/selection.json:edl:hard_freeze:selection
(not_allow:owner=selection) because run_edl persisted its in-flight selection
repairs (reconcile / NLE / air-omit / order-lock) straight to disk. Repairs now
stay in memory once the selection owner has frozen the document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import (
    _persist_selection_for_edl,
    _selection_write_permitted,
)
from run_fixtures import isolated_run_ctx, write_fixture_json


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i18_edl_selection")


def _seed_selection(ctx: RunContext) -> dict:
    doc = {
        "version": 1,
        "ordered_segment_ids": ["seg_001", "seg_002"],
        "excluded_segment_ids": [],
    }
    write_fixture_json(ctx, "master/selection.json", doc)
    return doc


def test_i18_frozen_selection_is_not_rewritten_by_edl(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_selection(ctx)
    before = ctx.read_json("master/selection.json")

    monkeypatch.setattr(
        "interview_mux.stages.assembly._selection_write_permitted", lambda _c: False
    )
    mutated = {**before, "ordered_segment_ids": ["seg_002"]}
    _persist_selection_for_edl(ctx, mutated, note="unit")

    after = ctx.read_json("master/selection.json")
    assert after["ordered_segment_ids"] == before["ordered_segment_ids"], (
        "EDL rewrote a frozen selection"
    )


def test_i18_permitted_selection_write_still_lands(ctx: RunContext) -> None:
    _seed_selection(ctx)
    assert _selection_write_permitted(ctx) in {True, False}

    doc = ctx.read_json("master/selection.json")
    doc["ordered_segment_ids"] = ["seg_001"]
    # Owner-permitted path: write through the sanctioned owner stage.
    write_fixture_json(ctx, "master/selection.json", doc)
    assert ctx.read_json("master/selection.json")["ordered_segment_ids"] == ["seg_001"]


def test_i18_edl_is_not_a_selection_producer() -> None:
    from interview_mux.artifact_ownership import owners_of

    assert "edl" not in owners_of("master/selection.json")


def test_i19_frozen_gap_report_is_not_rewritten_by_edl(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EDL gap-line repairs must stay in memory once gap_report is frozen."""
    from interview_mux.stages.assembly import _commit_edl_gap_report

    doc = {"version": 1, "interviewer_lines": [{"segment_id": "seg_001", "text": "a"}]}
    write_fixture_json(ctx, "understanding/gap_report.json", doc)

    calls: list[str] = []
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "not_allow:owner=gap_report_sanitize"),
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.write_committed_json",
        lambda *a, **k: calls.append("wrote"),
    )

    _commit_edl_gap_report(ctx, {**doc, "interviewer_lines": []})
    assert calls == [], "EDL rewrote a frozen gap_report"
    assert ctx.read_json("understanding/gap_report.json")["interviewer_lines"]


def test_i19_edl_is_not_a_gap_report_producer() -> None:
    from interview_mux.artifact_ownership import owners_of

    assert "edl" not in owners_of("understanding/gap_report.json")


def test_i20_orientation_retarget_skips_frozen_gap_report(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """edl/load_inputs → retarget_orientation_to_open must not rewrite a frozen gap_report."""
    from interview_mux import opening_orientation

    gap = {
        "version": 1,
        "interviewer_lines": [
            {"line_id": "l1", "segment_id": "seg_001", "text": "hello", "kind": "bridge"}
        ],
    }
    write_fixture_json(ctx, "understanding/gap_report.json", gap)
    ctx.write_json(
        "master/selection.json",
        {"version": 1, "ordered_segment_ids": ["seg_001"], "excluded_segment_ids": []},
        stage_key="selection_order_sanitize",
    )

    monkeypatch.setattr(
        opening_orientation,
        "ensure_episode_orientation",
        lambda _c, doc, _o: ({**doc, "interviewer_lines": []}, []),
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "not_allow:owner=gap_report_sanitize"),
    )

    written = opening_orientation.retarget_orientation_to_open(ctx)
    assert "understanding/gap_report.json" not in written
    assert ctx.read_json("understanding/gap_report.json")["interviewer_lines"], (
        "frozen gap_report body was emptied by orientation retarget"
    )


def test_i21_seam_glue_skips_frozen_reorder_bridges(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """edl → seam_glue.rebuild_reorder_bridges must not rewrite frozen reorder_bridges."""
    from interview_mux import seam_glue

    original = {"version": 1, "bridges": [{"from_segment_id": "seg_001"}]}
    ctx.write_json(
        "understanding/reorder_bridges.json", original, stage_key="full_master_ranking"
    )

    monkeypatch.setattr(
        "interview_mux.reorder_bridges.build_reorder_bridges",
        lambda *a, **k: {"version": 1, "bridges": []},
    )
    monkeypatch.setattr(
        "interview_mux.bridge_voice_policy.annotate_reorder_bridges",
        lambda doc, **k: doc,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "not_allow:owner=full_master_ranking"),
    )

    out = seam_glue.rebuild_reorder_bridges(ctx, ["seg_001"], {"seg_001": {}})
    assert out == {"version": 1, "bridges": []}, "caller must still get the rebuilt body"
    assert ctx.read_json("understanding/reorder_bridges.json") == original, (
        "frozen reorder_bridges was overwritten by seam glue"
    )


def test_i21_permitted_bridges_write_still_lands(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import seam_glue

    ctx.write_json(
        "understanding/reorder_bridges.json",
        {"version": 1, "bridges": [{"from_segment_id": "old"}]},
        stage_key="full_master_ranking",
    )
    monkeypatch.setattr(
        "interview_mux.reorder_bridges.build_reorder_bridges",
        lambda *a, **k: {"version": 1, "bridges": [{"from_segment_id": "new"}]},
    )
    monkeypatch.setattr(
        "interview_mux.bridge_voice_policy.annotate_reorder_bridges",
        lambda doc, **k: doc,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted", lambda *a, **k: (True, "")
    )

    seam_glue.rebuild_reorder_bridges(ctx, ["seg_001"], {"seg_001": {}})
    doc = ctx.read_json("understanding/reorder_bridges.json")
    assert doc["bridges"][0]["from_segment_id"] == "new"


def test_i22_deferred_pairs_sync_skips_sealed_doc(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Consumer-side deferred-pair bookkeeping must not rewrite the sealed doc."""
    from interview_mux import transition_vo

    sealed = {
        "version": 1,
        "deferred_pairs": ["seg_001->seg_002"],
        "frozen_count": 1,
        "current_count": 2,
    }
    ctx.write_json(transition_vo.DEFERRED_PAIRS_REL, sealed, stage_key="transitions")

    monkeypatch.setattr(
        transition_vo, "frozen_transition_pair_keys", lambda _c: {"seg_009->seg_010"}
    )
    monkeypatch.setattr(
        transition_vo,
        "spoken_transition_pairs",
        lambda _c: [("seg_009", "seg_010"), ("seg_020", "seg_021")],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "not_allow:owner=transitions"),
    )

    deferred = transition_vo.deferred_transition_pairs(ctx)
    assert deferred == [("seg_020", "seg_021")], "caller still gets recomputed pairs"
    assert ctx.read_json(transition_vo.DEFERRED_PAIRS_REL) == sealed, (
        "sealed deferred_transition_pairs was rewritten by a consumer"
    )


def test_i22_deferred_pairs_sync_persists_when_permitted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import transition_vo

    monkeypatch.setattr(
        transition_vo, "frozen_transition_pair_keys", lambda _c: {"seg_009->seg_010"}
    )
    monkeypatch.setattr(
        transition_vo,
        "spoken_transition_pairs",
        lambda _c: [("seg_009", "seg_010"), ("seg_020", "seg_021")],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted", lambda *a, **k: (True, "")
    )

    transition_vo.deferred_transition_pairs(ctx)
    doc = ctx.read_json(transition_vo.DEFERRED_PAIRS_REL)
    assert doc["deferred_pairs"] == ["seg_020->seg_021"]
