"""DP-GAP-PICKUP-CONFIRM A — flow_adaptation writes stamp owning stage_key."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from interview_mux.artifact_ownership import AuthorityDenied
from interview_mux.run_context import RunContext
from interview_mux.source_topology import (
    check_pickup_speaker_pending,
    confirm_pickup_speaker,
    maybe_auto_confirm_pickup_speaker,
)
from interview_mux.web.stages import ANALYSIS_STAGES
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "gap_pickup_confirm")
    run.write_json(
        "run_meta.json",
        {"gap_framing_enabled": True},
        skip_handoff=True,
    )
    run.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_host", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_guest", "role": "interviewee", "confidence": 0.9},
            ]
        },
        skip_handoff=True,
    )
    run.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "pickup_eligible_speaker_id": "spk_host",
            "least_spoken_speaker_id": "spk_host",
            "speaker_stats": [
                {
                    "speaker_id": "spk_host",
                    "role_hint": "interviewer",
                    "talk_ms": 5_000,
                    "talk_ratio": 0.05,
                    "turn_count": 2,
                    "question_count": 1,
                },
                {
                    "speaker_id": "spk_guest",
                    "role_hint": "interviewee",
                    "talk_ms": 95_000,
                    "talk_ratio": 0.95,
                    "turn_count": 10,
                    "question_count": 0,
                },
            ],
        },
        skip_handoff=True,
    )
    run.write_json(
        "understanding/flow_adaptation.json",
        {
            "pickup_eligible_speaker_id": "spk_host",
            "operator_overrides": {
                "gap_framing_enabled": True,
                "pickup_speaker_confirmed": False,
            },
        },
        skip_handoff=True,
    )
    from interview_mux.pipeline import ANALYSIS_ORDER
    from run_fixtures import mark_done_raw

    for sid in ANALYSIS_ORDER:
        if sid == "missing_framing":
            break
        mark_done_raw(run, sid)
    return run


def test_confirm_pickup_under_active_gap_framing_compose(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live exec_13168: active gap_framing_compose must not AuthorityDeny pickup confirm."""
    os.environ["MUX_FORENSICS"] = "0"
    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id",
        lambda: "gap_framing_compose",
    )
    assert check_pickup_speaker_pending(ctx)
    confirm_pickup_speaker(ctx, speaker_id="spk_host")
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    assert adapt["operator_overrides"]["pickup_speaker_confirmed"] is True
    assert not check_pickup_speaker_pending(ctx)


def test_maybe_auto_confirm_under_gap_framing_compose(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    os.environ["MUX_FORENSICS"] = "0"
    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id",
        lambda: "gap_framing_compose",
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.auto_accept_gap_gate_defaults_enabled",
        lambda: True,
    )
    assert maybe_auto_confirm_pickup_speaker(ctx) is True
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    assert adapt["operator_overrides"]["pickup_speaker_confirmed"] is True


def test_bare_active_stage_still_denied_without_stamp(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard: wrong stage_key still fails — proves ALLOW did not widen to compose."""
    os.environ["MUX_FORENSICS"] = "0"
    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id",
        lambda: "gap_framing_compose",
    )
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    with pytest.raises(AuthorityDenied):
        ctx.write_json(
            "understanding/flow_adaptation.json",
            adapt,
            stage_key="gap_framing_compose",
        )


def test_missing_framing_stageinfo_declares_flow_adaptation() -> None:
    os.environ["MUX_FORENSICS"] = "0"
    info = next(s for s in ANALYSIS_STAGES if s.id == "missing_framing")
    assert "understanding/flow_adaptation.json" in info.artifacts
    assert "understanding/flow_adaptation.json" in info.editable
