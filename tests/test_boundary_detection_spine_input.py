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
