from __future__ import annotations

from interview_mux.artifact_dependency_graph import (
    build_graph,
    downstream_consumers,
    propagation_map,
    transitive_invalidate,
)
from interview_mux.artifact_root_cause import _PROPAGATION_FROM
from interview_mux.stage_contract import all_contract_stage_ids


def test_build_graph_has_produces_edges():
    edges = build_graph()
    kinds = {e.kind for e in edges}
    assert "produces" in kinds
    assert "invalidates" in kinds


def test_transitive_invalidate_includes_pipeline_downstream():
    stale = transitive_invalidate("boundary_detection")
    assert "segment_classification" in stale


def test_propagation_map_matches_root_cause():
    pmap = propagation_map()
    for stage, targets in _PROPAGATION_FROM.items():
        for t in targets:
            assert t in pmap.get(stage, ())


def test_downstream_consumers_non_empty_for_content_context():
    consumers = downstream_consumers("content_context")
    assert consumers


def test_contracts_loaded():
    assert len(all_contract_stage_ids()) >= 40
