"""Pipeline execution order must match GUI stage metadata (web/stages.py)."""

from __future__ import annotations

import interview_mux.pipeline as pipeline
from interview_mux.web.stages import EXECUTABLE_ORDER


def test_executable_order_matches_pipeline() -> None:
    pairs = [
        ("analysis", pipeline.ANALYSIS_ORDER),
        ("flow1", pipeline.FLOW1_ORDER),
        ("flow2", pipeline.FLOW2_ORDER),
        ("flow3", pipeline.FLOW3_ORDER),
    ]
    for name, pipe_order in pairs:
        web_order = EXECUTABLE_ORDER[name]
        assert list(pipe_order) == list(web_order), (
            f"{name}: pipeline vs GUI mismatch {set(pipe_order) ^ set(web_order)}"
        )


def test_stage_by_id_covers_pipeline_stages() -> None:
    from interview_mux.web.stages import STAGE_BY_ID

    for order in (
        pipeline.ANALYSIS_ORDER,
        pipeline.FLOW1_ORDER,
        pipeline.FLOW2_ORDER,
        pipeline.FLOW3_ORDER,
    ):
        for stage_id in order:
            assert stage_id in STAGE_BY_ID, f"missing GUI metadata for {stage_id}"
