"""HU-4: source_topology_build cannot heal-complete from topology.json alone.

Done requires topology.json and flow_adaptation.json. Speaker sample WAVs stay
skip-only. Do not start a run. HU-1 SAP / HU-3 speaker_roles stay closed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import (
    pending_analysis_for_delivery,
    skip_stage,
    stage_outputs_present,
)
from interview_mux.run_context import RunContext
from interview_mux.source_topology import ensure_source_topology
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    parse_resume_stage_from_reason,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_STAGE = "source_topology_build"
_TOPO = "understanding/source_topology.json"
_ADAPT = "understanding/flow_adaptation.json"


def _topo_doc() -> dict:
    return {
        "topology_class": "one_on_one_asymmetric",
        "speaker_stats": [{"speaker_id": "spk_0"}],
    }


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hu4_topo")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hu4_topology_alone_is_incomplete(ctx: RunContext) -> None:
    ctx.write_json(_TOPO, _topo_doc(), skip_handoff=True)
    mark_done_raw(ctx, _STAGE)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "flow_adaptation" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert stage_outputs_present(ctx, _STAGE) is False
    assert seed_stage_complete(ctx, _STAGE) is False
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)
    pending = pending_analysis_for_delivery(ctx)
    assert _STAGE in pending
    assert not ctx.is_done(_STAGE)


def test_hu4_ensure_does_not_mark_topology_alone(ctx: RunContext) -> None:
    ctx.write_json(_TOPO, _topo_doc(), skip_handoff=True)
    topo = ensure_source_topology(ctx)
    assert topo.get("speaker_stats")
    assert not ctx.is_done(_STAGE)
    assert not ctx.artifact_exists(_ADAPT)


def test_hu4_both_json_complete_without_sample_wavs(ctx: RunContext) -> None:
    ctx.write_json(_TOPO, _topo_doc(), skip_handoff=True)
    ctx.write_json(_ADAPT, {"topology_class": "one_on_one_asymmetric"}, skip_handoff=True)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    assert stage_outputs_present(ctx, _STAGE) is True
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("marked") is True
    assert ctx.is_done(_STAGE)
    assert seed_stage_complete(ctx, _STAGE) is True
    pending = pending_analysis_for_delivery(ctx)
    assert _STAGE not in pending
    with pytest.raises(RuntimeError, match="speaker sample"):
        skip_stage(ctx, _STAGE, reason="missing samples")
    assert ctx.is_done(_STAGE)


def test_hu4_ensure_rebuilds_missing_flow_adaptation(ctx: RunContext) -> None:
    ctx.write_json(_TOPO, _topo_doc(), skip_handoff=True)
    words = [
        {"word": "hi", "speaker": "spk_0", "start_ms": i * 500, "end_ms": i * 500 + 400}
        for i in range(20)
    ] + [
        {"word": "ok", "speaker": "spk_1", "start_ms": 10000 + i * 500, "end_ms": 10400 + i * 500}
        for i in range(8)
    ]
    ctx.write_json("transcript/full.json", {"words": words}, skip_handoff=True)
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9},
            ]
        },
        skip_handoff=True,
    )
    topo = ensure_source_topology(ctx)
    assert ctx.artifact_exists(_ADAPT)
    assert ctx.is_done(_STAGE)
    assert topo.get("speaker_stats")
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
