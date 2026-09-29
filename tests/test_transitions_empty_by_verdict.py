"""An empty transitions list the model chose is complete, not partial.

The contract allows it (transitions min_rows 0), but _gaps_transitions accepts
an empty list only through empty_ok, and nothing stamped it. On a real
6-minute run the model returned [] with status complete and the rationale
"No additional spoken bridges are needed across the locked order"; the stage
was refused as partial and the run stopped at 52 of 72.
"""

from __future__ import annotations

from interview_mux.artifact_completeness import _gaps_transitions


def test_empty_without_verdict_is_still_a_gap() -> None:
    assert _gaps_transitions({"transitions": []}) == ["transitions"]


def test_empty_by_model_verdict_is_complete() -> None:
    doc = {"transitions": [], "empty_ok": True, "empty_reason": "model_returned_no_transitions"}
    assert _gaps_transitions(doc) == []


def test_rows_present_is_complete() -> None:
    assert _gaps_transitions({"transitions": [{"after_segment_id": "a", "before_segment_id": "b"}]}) == []
