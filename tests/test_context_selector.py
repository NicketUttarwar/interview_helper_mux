from __future__ import annotations

from interview_mux.context_selector import catalog_from_segments, hydrate_segments, select_chunk_ids


def test_catalog_and_select_spreads():
    segs = [
        {"segment_id": f"seg_{i:03d}", "start_ms": i * 5000, "end_ms": (i + 1) * 5000, "text": f"t{i}"}
        for i in range(12)
    ]
    catalog = catalog_from_segments(segs)
    assert len(catalog) == 12
    ids = select_chunk_ids(catalog, cap=4)
    assert len(ids) == 4
    hydrated = hydrate_segments(segs, ids)
    assert len(hydrated) == 4
    assert hydrated[0]["segment_id"] in ids
