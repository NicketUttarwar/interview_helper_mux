"""Tests for talking-points-first deterministic coverage + narrative."""

from __future__ import annotations

from interview_mux.talking_points_authority import (
    coverage_from_talking_points,
    narrative_from_talking_points,
)


def test_coverage_from_talking_points_scores_must_keeps():
    tp = {
        "strategy_summary": "Test",
        "through_line": "Line",
        "talking_points": [
            {
                "talking_point_id": "tp_1",
                "title": "Must A",
                "importance": "must_keep",
                "why_it_matters": "x",
            },
            {
                "talking_point_id": "tp_2",
                "title": "Must B",
                "importance": "must_keep",
                "why_it_matters": "y",
            },
            {
                "talking_point_id": "tp_3",
                "title": "Optional",
                "importance": "optional",
                "why_it_matters": "z",
            },
        ],
    }
    mat = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "segment_id": "seg_001",
                "start_ms": 0,
                "end_ms": 3000,
            }
        ]
    }
    cov = coverage_from_talking_points(tp, mat)
    assert cov["coverage_score"] == 0.5
    assert any(m["topic"] == "Must A" and m["covered"] for m in cov["topic_mappings"])
    assert any(m["topic"] == "Must B" and not m["covered"] for m in cov["topic_mappings"])
    assert any(m["item"] == "Must B" for m in cov["missing_coverage"])


def test_narrative_from_talking_points_builds_chapters():
    tp = {
        "strategy_summary": "Story",
        "through_line": "Through",
        "talking_points": [
            {
                "talking_point_id": "tp_1",
                "title": "Open",
                "importance": "must_keep",
                "why_it_matters": "x",
            },
            {
                "talking_point_id": "tp_2",
                "title": "Payoff",
                "importance": "should_keep",
                "why_it_matters": "y",
            },
        ],
    }
    mat = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "segment_id": "seg_001",
                "start_ms": 100,
                "end_ms": 2000,
            },
            {
                "cut_id": "c2",
                "talking_point_id": "tp_2",
                "segment_id": "seg_002",
                "start_ms": 5000,
                "end_ms": 8000,
            },
        ]
    }
    plan = narrative_from_talking_points(
        tp,
        mat,
        mastering_plan={"narrative_mode": "guide_summary", "ordered_segment_ids": ["seg_001", "seg_002"]},
    )
    assert len(plan["chapters"]) == 2
    assert plan["chapters"][0]["suggested_open_segment_id"] == "seg_001"
    assert plan["ordering_constraints"]
    assert "guide_summary" in plan["arc_summary"]


def test_manifest_from_ideal_cuts_types_by_speaker_role(tmp_path):
    from interview_mux.run_context import RunContext
    from interview_mux.talking_points_authority import manifest_from_ideal_cuts
    from run_fixtures import isolated_run_ctx, patch_executions_root
    import pytest

    # Use a simple fake ctx via isolated fixture pattern
    monkeypatch = pytest.MonkeyPatch()
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_class_det")
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9, "evidence": ["q"]},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9, "evidence": ["a"]},
            ]
        },
        skip_handoff=True,
    )
    boundaries = {
        "boundaries": [
            {"segment_id": "seg_001", "start_ms": 0, "end_ms": 3000, "speaker_id": "spk_1"},
            {"segment_id": "seg_002", "start_ms": 4000, "end_ms": 7000, "speaker_id": "spk_0"},
        ]
    }
    tp = {
        "talking_points": [
            {
                "talking_point_id": "tp_1",
                "title": "Claim",
                "importance": "must_keep",
                "why_it_matters": "x",
            }
        ]
    }
    mat = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "segment_id": "seg_001",
                "priority": "must_keep",
                "speaker_id": "spk_1",
                "start_ms": 0,
                "end_ms": 3000,
            }
        ]
    }
    man = manifest_from_ideal_cuts(ctx, boundaries=boundaries, talking_points=tp, materialized=mat)
    by_id = {s["segment_id"]: s for s in man["segments"]}
    assert by_id["seg_001"]["type"] == "interviewee_answer"
    assert by_id["seg_001"]["speaker_role"] == "interviewee"
    assert by_id["seg_002"]["type"] in {"interviewer_question", "interviewer_reaction"}
    monkeypatch.undo()


def test_run_classification_det_path_runs_post_hooks(tmp_path, monkeypatch) -> None:
    """SC-B4: deterministic early-return still runs topic bootstrap + seed refresh."""
    from interview_mux.stages.segmentation import run_classification
    from run_fixtures import isolated_run_ctx, patch_executions_root

    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_sc_b4_det")
    det_manifest = {
        "segments": [
            {
                "segment_id": "seg_001",
                "start_ms": 0,
                "end_ms": 3000,
                "type": "interviewee_answer",
                "speaker_id": "spk_1",
                "text": "hello world",
            }
        ]
    }
    monkeypatch.setattr(
        "interview_mux.talking_points_authority.try_deterministic_classification",
        lambda _c: det_manifest,
    )
    monkeypatch.setattr(
        "interview_mux.boundary_enrich.restamp_run_span_speakers",
        lambda _c: None,
    )
    llm_calls: list[str] = []

    def _boom(*_a, **_k):
        llm_calls.append("llm")
        raise AssertionError("LLM must not run on det path")

    monkeypatch.setattr(
        "interview_mux.stages.analysis_stage.run_analysis_llm_stage",
        _boom,
    )
    monkeypatch.setattr(
        "interview_mux.llm_simple.run_llm_stage_simple",
        _boom,
    )
    hooks = {"topic": 0, "seed": 0, "specialists": 0}

    def _topic(_c):
        hooks["topic"] += 1
        return 0

    def _seed(_c):
        hooks["seed"] += 1
        return {"ordered_segment_ids": ["seg_001"]}

    def _specialists(_c, _stage, _payload):
        hooks["specialists"] += 1
        return []

    monkeypatch.setattr(
        "interview_mux.topic_tag_bootstrap.bootstrap_manifest_topic_tags",
        _topic,
    )
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.refresh_selection_seed_from_boundaries",
        _seed,
    )
    monkeypatch.setattr(
        "interview_mux.stages.segmentation.maybe_run_post_stage_specialists",
        _specialists,
    )
    monkeypatch.setattr(
        "interview_mux.segmentation_input_resolver.build_classification_payload",
        lambda _c: {"ok": True},
    )
    monkeypatch.setattr(
        "interview_mux.asset_transcripts.sync_speech_sidecars",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_writes.write_validated_artifact",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.stages.segmentation.heal_or_refuse_mark",
        lambda *_a, **_k: None,
    )

    run_classification(ctx)
    assert llm_calls == []
    assert hooks["topic"] == 1
    assert hooks["seed"] == 1
    assert hooks["specialists"] == 1


def test_talking_points_compose_requires_content_brief(tmp_path, monkeypatch) -> None:
    """TPC-B1: hard content_brief — refuse before LLM when brief missing."""
    import pytest
    from interview_mux.run_context import RunContext
    from interview_mux.stages.understanding import run_talking_points_compose

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    llm_calls: list[str] = []

    def _boom(*_a, **_k):
        llm_calls.append("llm")
        raise AssertionError("LLM must not run without content_brief")

    monkeypatch.setattr(
        "interview_mux.stages.understanding.run_analysis_llm_stage",
        _boom,
    )
    monkeypatch.setattr(
        "interview_mux.llm_simple.run_llm_stage_simple",
        _boom,
    )
    ctx = RunContext(str(tmp_path / "tpc_no_brief"), create=True)
    ctx.write_json(
        "transcript/full.json",
        {"text": "hello enough transcript text here", "words": []},
        skip_handoff=True,
    )
    with pytest.raises(RuntimeError, match="content_brief required"):
        run_talking_points_compose(ctx)
    assert llm_calls == []
    assert not ctx.is_done("talking_points_compose")


def test_talking_points_compose_disabled_stub_without_brief(tmp_path, monkeypatch) -> None:
    """Disabled ideal_cuts path still stubs without requiring content_brief."""
    from interview_mux.run_context import RunContext
    from interview_mux.stages.understanding import run_talking_points_compose

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.ideal_cuts_cfg",
        lambda: {"enable": False},
    )
    ctx = RunContext(str(tmp_path / "tpc_disabled"), create=True)
    run_talking_points_compose(ctx)
    assert ctx.is_done("talking_points_compose")
    doc = ctx.read_json("understanding/talking_points.json")
    assert doc["talking_points"][0]["talking_point_id"] == "tp_disabled"


def test_content_context_requires_source_topology(tmp_path, monkeypatch) -> None:
    """CC-B1: hard topology — refuse before LLM when source_topology missing."""
    import pytest
    from interview_mux.run_context import RunContext
    from interview_mux.stages.understanding import run_content_context

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    llm_calls: list[str] = []

    def _boom(*_a, **_k):
        llm_calls.append("llm")
        raise AssertionError("LLM must not run without source_topology")

    monkeypatch.setattr(
        "interview_mux.stages.understanding.run_analysis_llm_stage",
        _boom,
    )
    monkeypatch.setattr(
        "interview_mux.llm_simple.run_llm_stage_simple",
        _boom,
    )
    ctx = RunContext(str(tmp_path / "cc_no_topo"), create=True)
    ctx.write_json(
        "transcript/full.json",
        {"text": "hello enough transcript text here for content context", "words": []},
        skip_handoff=True,
    )
    with pytest.raises(RuntimeError, match="source_topology required"):
        run_content_context(ctx)
    assert llm_calls == []
    assert not ctx.is_done("content_context")
