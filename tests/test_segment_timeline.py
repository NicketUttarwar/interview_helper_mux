from interview_mux.segment_timeline import (
    sort_segments_by_start_ms,
    validate_boundary_rows,
    validate_timeline_monotonic,
)


def test_sort_segments_by_start_ms_tiebreaks_segment_id():
    rows = [
        {"segment_id": "seg_002", "start_ms": 1000, "end_ms": 2000},
        {"segment_id": "seg_001", "start_ms": 1000, "end_ms": 1500},
    ]
    sorted_rows = sort_segments_by_start_ms(rows)
    assert [r["segment_id"] for r in sorted_rows] == ["seg_001", "seg_002"]


def test_validate_timeline_monotonic_detects_overlap():
    rows = [
        {"segment_id": "seg_001", "start_ms": 0, "end_ms": 5000},
        {"segment_id": "seg_002", "start_ms": 4000, "end_ms": 8000},
    ]
    errors = validate_timeline_monotonic(rows, allow_overlap_ms=0)
    assert any("seg_002" in e for e in errors)


def test_validate_boundary_rows_requires_speaker_id():
    rows = [{"segment_id": "seg_001", "start_ms": 0, "end_ms": 1000}]
    errors = validate_boundary_rows(rows, require_speaker_id=True)
    assert any("speaker_id" in e for e in errors)
