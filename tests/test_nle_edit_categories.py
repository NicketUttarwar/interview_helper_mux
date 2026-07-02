"""Golden tests: NLE edit category → rerun scope routing."""

from __future__ import annotations

from interview_mux.nle_state import nle_edit_categories


def test_trim_only_without_structural():
    nle = {"segment_overrides": {"seg_a": {"start_ms": 100, "end_ms": 9000}}}
    cats = nle_edit_categories(nle)
    assert cats["has_any"] is True
    assert cats["trim_only"] is True
    assert cats["structural"] is False


def test_structural_on_reorder():
    nle = {"sequence_order": ["seg_b", "seg_a"]}
    cats = nle_edit_categories(nle)
    assert cats["structural"] is True
    assert cats["trim_only"] is False


def test_structural_on_exclude():
    nle = {"segment_overrides": {"seg_a": {"excluded": True}}}
    cats = nle_edit_categories(nle)
    assert cats["structural"] is True
