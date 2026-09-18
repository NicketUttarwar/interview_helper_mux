from __future__ import annotations

from unittest.mock import MagicMock

from interview_mux.stages.segmentation import run_boundaries


def test_boundary_detection_build_input_includes_spine(monkeypatch):
    captured: dict = {}

    def fake_run(ctx, stage_key, prompt, build_input, persist, **kwargs):
        captured["payload"] = build_input(ctx)

    monkeypatch.setattr(
        "interview_mux.stages.segmentation.run_analysis_llm_stage",
        fake_run,
    )
    ctx = MagicMock()
    ctx.read_json.side_effect = lambda path: {
        "transcript/full.json": {"text": "hi", "words": []},
        "understanding/speakers.json": {"speakers": []},
        "understanding/content_brief.json": {"topics": []},
    }[path]
    ctx.artifact_exists.return_value = False

    monkeypatch.setattr(
        "interview_mux.interview_spine.compact.attach_spine_to_payload",
        lambda ctx, payload, stage_key: payload.update(
            {"interview_spine": {"window_count": 2, "boundary_events": []}}
        ),
    )
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_enabled",
        lambda *a, **k: True,
    )

    run_boundaries(ctx)
    assert "interview_spine" in captured["payload"]
    assert "transcript_quality" not in captured["payload"]


def test_boundary_detection_bind_without_file_falls_through_llm(monkeypatch):
    """BD-B4: ideal-cuts bind stamp but missing boundaries.json → LLM, no crash."""
    llm_calls: list[str] = []

    def fake_run(ctx, stage_key, prompt, build_input, persist, **kwargs):
        llm_calls.append(stage_key)
        build_input(ctx)

    monkeypatch.setattr(
        "interview_mux.stages.segmentation.run_analysis_llm_stage",
        fake_run,
    )
    monkeypatch.setattr(
        "interview_mux.stages.segmentation._assert_boundary_quality",
        lambda ctx: None,
    )
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.bind_boundaries_enabled",
        lambda conf: True,
    )
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.ideal_cuts_cfg",
        lambda: {"skip_boundary_llm_when_bound": True},
    )
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.boundaries_already_from_ideal_cuts",
        lambda ctx: True,
    )

    ctx = MagicMock()
    ctx.is_done.return_value = False
    # Bind path claims ideal-cuts provenance, but the primary is absent.
    ctx.artifact_exists.side_effect = lambda path: False
    ctx.read_json.side_effect = lambda path: {
        "transcript/full.json": {"text": "hi", "words": [], "duration_ms": 60_000},
        "understanding/speakers.json": {"speakers": []},
        "understanding/content_brief.json": {"topics": []},
    }[path]

    monkeypatch.setattr(
        "interview_mux.interview_spine.compact.attach_spine_to_payload",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "interview_mux.stages.segmentation.observe_boundary_detection_input",
        lambda *a, **k: None,
    )

    run_boundaries(ctx)
    assert llm_calls == ["boundary_detection"]


def test_boundary_detection_contract_hard_soft_aligned() -> None:
    """BD-B1/B2/B3: hard transcript+speakers+brief; soft materialize; no OQ."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract("boundary_detection")
    assert contract is not None
    hard = {d.path for d in contract.inputs if d.hard and d.path}
    soft = {d.path for d in contract.inputs if not d.hard and d.path}
    assert hard == {
        "transcript/full.json",
        "understanding/speakers.json",
        "understanding/content_brief.json",
    }
    assert "understanding/ideal_cuts_materialized.json" in soft
    assert "understanding/ideal_cuts_materialized.json" not in hard
    assert "transcript/review_queue.json" not in soft
    assert "analysis/run_golden_facts.json" not in soft
    assert "transcript/protected_zones.json" not in soft
    assert "optimal_questions" not in (contract.propagation or [])
