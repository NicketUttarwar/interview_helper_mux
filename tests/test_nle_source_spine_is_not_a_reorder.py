"""The manifest spine a split mirrors into the NLE is not an operator reorder (ISSUES 130).

The run this guards (one-hour source, exec_102): 68 manifest segments, 60 on
air. A CTA split seeded ``sequence_order`` from the whole manifest. The
length heuristic (1.25 times the on-air count) did not recognise it, so it
was applied as an operator order, and edl refused with "NLE operator edits
not committed on disk selection" three times, the second wind included.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.nle_state import apply_nle_to_selection, is_source_spine
from interview_mux.stages import assembly as asm
from run_fixtures import isolated_run_ctx


def _by_id(n: int) -> dict[str, dict]:
    return {f"seg_{i:03d}": {"segment_id": f"seg_{i:03d}", "start_ms": i * 1000, "end_ms": i * 1000 + 900} for i in range(n)}


def test_a_chronological_full_cover_order_is_the_spine() -> None:
    by_id = _by_id(68)
    spine = sorted(by_id)  # all 68, source order
    ranked = [f"seg_{i:03d}" for i in (5, 2, 9, 1, 30, 12, 40, 7)] + [f"seg_{i:03d}" for i in range(41, 60)]
    out = apply_nle_to_selection(
        {"ordered_segment_ids": list(ranked)}, {"sequence_order": spine, "segment_overrides": {}}, segments_by_id=by_id
    )
    # 68 against 27 on air would also trip the length test; the ratio that broke is below.
    assert out["ordered_segment_ids"] == ranked


def test_the_ratio_that_broke_the_length_heuristic() -> None:
    by_id = _by_id(68)
    spine = sorted(by_id)
    on_air = [s for s in spine if s not in {f"seg_{i:03d}" for i in (3, 11, 19, 27, 35, 43, 51, 66)}]
    ranked = list(reversed(on_air))  # 60 ids, not in source order
    assert len(spine) < int(len(ranked) * 1.25)
    out = apply_nle_to_selection(
        {"ordered_segment_ids": list(ranked)}, {"sequence_order": spine, "segment_overrides": {}}, segments_by_id=by_id
    )
    assert out["ordered_segment_ids"] == ranked
    assert out["nle_merge"]["operator_moved_ids"] == []


def test_an_operator_reorder_is_still_honoured() -> None:
    by_id = _by_id(6)
    ranked = [f"seg_{i:03d}" for i in (0, 1, 2, 3, 4, 5)]
    operator = [f"seg_{i:03d}" for i in (3, 0, 1, 2, 4, 5)]  # full cover, not source order
    out = apply_nle_to_selection(
        {"ordered_segment_ids": list(ranked)}, {"sequence_order": operator, "segment_overrides": {}}, segments_by_id=by_id
    )
    assert out["ordered_segment_ids"] == operator


def test_a_subset_in_source_order_is_not_called_a_spine() -> None:
    by_id = _by_id(6)
    ranked = [f"seg_{i:03d}" for i in (5, 4, 3, 2, 1, 0)]
    out = apply_nle_to_selection(
        {"ordered_segment_ids": list(ranked)},
        {"sequence_order": ["seg_001", "seg_004"], "segment_overrides": {}},
        segments_by_id=by_id,
    )
    assert out["nle_merge"]["operator_moved_ids"] == ["seg_001", "seg_004"]


def test_unknown_start_times_make_no_claim() -> None:
    assert is_source_spine(["a", "b"], {"a": {"start_ms": 0}}) is False
    assert is_source_spine(["a", "b"], None) is False
    assert is_source_spine(["a", "b"], {"a": {"start_ms": 0}, "b": {"start_ms": 5}}) is True


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    for key in ("MUX_RUN_MODE", "MUX_FULL_AUTO", "MUX_AUTOMATION_DRIVER"):
        monkeypatch.delenv(key, raising=False)
    return isolated_run_ctx(tmp_path, "nle_order")


def test_an_engine_driven_run_builds_from_the_selection_when_only_the_order_differs(ctx) -> None:
    ctx.write_json("run_meta.json", {"run_mode": "partially-accelerated"}, skip_handoff=True)
    assert asm._selection_stands_over_nle_order(ctx, ["a", "b", "c"], ["b", "a", "c"]) is True


def test_a_manual_run_keeps_the_refusal(ctx) -> None:
    ctx.write_json("run_meta.json", {"run_mode": "manual"}, skip_handoff=True)
    assert asm._selection_stands_over_nle_order(ctx, ["a", "b", "c"], ["b", "a", "c"]) is False


def test_different_segments_still_refuse(ctx) -> None:
    ctx.write_json("run_meta.json", {"run_mode": "partially-accelerated"}, skip_handoff=True)
    assert asm._selection_stands_over_nle_order(ctx, ["a", "b", "c"], ["a", "b", "d"]) is False
    assert asm._selection_stands_over_nle_order(ctx, ["a", "b", "c"], ["a", "b"]) is False
