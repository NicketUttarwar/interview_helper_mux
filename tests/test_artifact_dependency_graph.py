from __future__ import annotations

from interview_mux.artifact_dependency_graph import (
    _PROPAGATION_SEEDS,
    build_graph,
    downstream_consumers,
    propagation_map,
    transitive_invalidate,
)
from interview_mux.artifact_root_cause import _PROPAGATION_FROM
from interview_mux.stage_contract import all_contract_stage_ids, load_contract


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


def test_topic_coverage_audit_invalidates_match_adg_seeds() -> None:
    """Stage Clinic TCA-B1: contract invalidates == ADG seeds ⊆ propagation_map."""
    expected = set(_PROPAGATION_SEEDS["topic_coverage_audit"])
    contract = load_contract("topic_coverage_audit")
    assert set(contract.propagation) == expected
    assert expected <= set(propagation_map().get("topic_coverage_audit") or ())


def test_transitions_invalidates_match_adg_seeds() -> None:
    """Stage Clinic transitions-B3: contract invalidates == ADG seeds ⊆ propagation_map."""
    expected = set(_PROPAGATION_SEEDS["transitions"])
    contract = load_contract("transitions")
    assert set(contract.propagation) == expected
    assert expected <= set(propagation_map().get("transitions") or ())


def test_master_transcript_invalidates_exclude_episode_meta() -> None:
    """Stage Clinic EMB-B3: transcript rebuild must not invalidate episode_meta."""
    expected = set(_PROPAGATION_SEEDS["master_transcript_build"])
    assert expected == {"podcast_publish"}
    assert "episode_meta_build" not in expected
    contract = load_contract("master_transcript_build")
    assert set(contract.propagation) == expected
    assert expected <= set(propagation_map().get("master_transcript_build") or ())
    assert "episode_meta_build" not in (propagation_map().get("master_transcript_build") or ())
