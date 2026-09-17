"""D10: gate_decisions.json is written by the deterministic plane and read by the solver.

Brain 0.2.0 skips the conductor, so ``set_gate`` never ran. Resolutions are now
recorded at the Python functions that actually close gates; ``_gate_verdict``
reads them. ``evaluate_stage`` stays read-only — it never persists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import solver
from interview_mux.homunculus.gates import (
    CATEGORIES,
    DECISIONS_REL,
    SOLVER_GATE_CATEGORIES,
    recorded_gate_action,
    set_gate_decision,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw

POSTURE_META: dict[str, dict[str, object]] = {
    solver.MANUAL: {"run_mode": "manual"},
    solver.PARTIAL: {"run_mode": "partially-accelerated", "partial_auto": True},
    solver.FULL_AUTO: {"run_mode": "full-auto", "full_auto": True},
}

G0_UNKNOWN = "gate_auto_accept_pending:transcript_review"
G0_BLOCK = "gate_open:transcript_review"
FRAMING_PAUSE = "gate_may_pause:gap_framing"


def _ctx(tmp_path: Path, name: str, posture: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    meta: dict[str, object] = {
        "homunculus_version": "0.2.0",
        "homunculus_control_plane": "deterministic",
    }
    meta.update(POSTURE_META[posture])
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    return ctx


def _open_g0(ctx: RunContext) -> None:
    dest = ctx.final_path("transcript", "review_queue.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"chunks": [{"chunk_id": "c1"}]}), encoding="utf-8")


def _plant_g0_ready(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transcript_review_build")
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "version": 1,
            "chunks": [
                {
                    "chunk_id": "tr_0001",
                    "rank": 1,
                    "start_ms": 0,
                    "end_ms": 400,
                    "text": "hello",
                    "speaker_id": "spk_0",
                    "confidence": 0.5,
                    "reviewed": False,
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json("transcript/corrections.json", {"corrections": {}}, skip_handoff=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "hello",
            "words": [
                {
                    "text": "hello",
                    "start_ms": 0,
                    "end_ms": 400,
                    "speaker_id": "spk_0",
                    "confidence": 0.5,
                }
            ],
        },
        skip_handoff=True,
    )


def _gate_unknowns(ctx: RunContext, stage: str, posture: str) -> tuple[str, ...]:
    reasons, unknowns, _detail = solver._gate_verdict(ctx, stage, posture)
    _ = reasons
    return tuple(unknowns)


def test_solver_gate_category_mapping_is_the_ssot() -> None:
    assert set(SOLVER_GATE_CATEGORIES) == set(solver.SOLVER_GATES)
    assert set(SOLVER_GATE_CATEGORIES.values()) <= set(CATEGORIES)


def test_set_gate_decision_round_trip_is_read_by_gate_verdict(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "d10_roundtrip", solver.FULL_AUTO)
    _open_g0(ctx)
    assert G0_UNKNOWN in _gate_unknowns(ctx, "speaker_roles", solver.FULL_AUTO)
    set_gate_decision(ctx, "transcript_integrity", "complete")
    assert recorded_gate_action(ctx, "transcript_integrity") == "complete"
    assert ctx.artifact_exists(DECISIONS_REL)
    assert G0_UNKNOWN not in _gate_unknowns(ctx, "speaker_roles", solver.FULL_AUTO)


def test_full_auto_open_g0_without_decision_stays_unknown_not_blocker(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "d10_g0_open", solver.FULL_AUTO)
    _open_g0(ctx)
    verdict = solver.evaluate_stage(ctx, "speaker_roles", posture=solver.FULL_AUTO)
    assert G0_BLOCK not in verdict.reasons
    assert G0_UNKNOWN in verdict.unknowns
    assert verdict.confident is False


def test_full_auto_open_g0_with_complete_clears_the_unknown(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "d10_g0_complete", solver.FULL_AUTO)
    _open_g0(ctx)
    set_gate_decision(ctx, "transcript_integrity", "complete")
    verdict = solver.evaluate_stage(ctx, "speaker_roles", posture=solver.FULL_AUTO)
    assert G0_UNKNOWN not in verdict.unknowns
    assert G0_BLOCK not in verdict.reasons
    assert all(not u.startswith("gate_") for u in verdict.unknowns)


def test_partial_may_pause_clears_when_complete_or_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, "d10_may_pause", solver.PARTIAL)
    real = solver.gate_open

    def _open_framing(c: RunContext, gate_id: str) -> bool | None:
        if gate_id == solver.G_FRAMING:
            return True
        return real(c, gate_id)

    monkeypatch.setattr(solver, "gate_open", _open_framing)
    verdict = solver.evaluate_stage(ctx, "missing_framing", posture=solver.PARTIAL)
    assert FRAMING_PAUSE in verdict.unknowns
    assert "gate_open:gap_framing" not in verdict.reasons

    set_gate_decision(ctx, "framing_consent", "present_operator")
    still = solver.evaluate_stage(ctx, "missing_framing", posture=solver.PARTIAL)
    assert FRAMING_PAUSE in still.unknowns

    set_gate_decision(ctx, "framing_consent", "complete")
    done = solver.evaluate_stage(ctx, "missing_framing", posture=solver.PARTIAL)
    assert FRAMING_PAUSE not in done.unknowns

    set_gate_decision(ctx, "framing_consent", "skip")
    skipped = solver.evaluate_stage(ctx, "missing_framing", posture=solver.PARTIAL)
    assert FRAMING_PAUSE not in skipped.unknowns


def test_mark_transcript_review_complete_writes_complete_row(tmp_path: Path) -> None:
    from interview_mux.stages.transcript_review import mark_transcript_review_complete

    ctx = _ctx(tmp_path, "d10_g0_write", solver.FULL_AUTO)
    _plant_g0_ready(ctx)
    mark_transcript_review_complete(ctx)
    assert recorded_gate_action(ctx, "transcript_integrity") == "complete"


def test_maybe_auto_accept_gap_gate_defaults_writes_framing_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.gap_vo_gates import maybe_auto_accept_gap_gate_defaults
    from interview_mux.v2.config import ANALYSIS_ORDER

    monkeypatch.setenv("INTERVIEW_MUX_AUTO_ACCEPT_GATES", "1")
    ctx = isolated_run_ctx(tmp_path, "d10_framing_write")
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "homunculus_control_plane": "deterministic",
            "run_mode": "full-auto",
            "full_auto": True,
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "least_spoken_speaker_id": "spk_0",
            "pickup_eligible_speaker_id": "spk_0",
            "speaker_stats": [
                {
                    "speaker_id": "spk_0",
                    "talk_ms": 10_000,
                    "talk_ratio": 0.2,
                    "role_hint": "interviewer",
                },
                {
                    "speaker_id": "spk_1",
                    "talk_ms": 40_000,
                    "talk_ratio": 0.8,
                    "role_hint": "guest",
                },
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {"pickup_eligible_speaker_id": "spk_0", "operator_overrides": {}},
        skip_handoff=True,
    )
    idx = ANALYSIS_ORDER.index("missing_framing")
    mark_done_raw(ctx, *ANALYSIS_ORDER[:idx])
    assert maybe_auto_accept_gap_gate_defaults(ctx) is True
    assert recorded_gate_action(ctx, "framing_consent") in {"auto_resolve", "skip"}


def test_transcript_integrity_still_cannot_auto_resolve(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "d10_g0_forbid", solver.FULL_AUTO)
    with pytest.raises(RuntimeError, match="cannot skip or auto-resolve"):
        set_gate_decision(ctx, "transcript_integrity", "auto_resolve")
    with pytest.raises(RuntimeError, match="cannot skip"):
        set_gate_decision(ctx, "transcript_integrity", "skip")
    doc = set_gate_decision(ctx, "transcript_integrity", "complete")
    assert doc["decisions"]["transcript_integrity"]["action"] == "complete"


def test_preclean_recorded_decision_does_not_clear_the_block(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "d10_preclean")
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "run_mode": "full-auto",
            "full_auto": True,
            "audio_preclean": {"enabled": True, "scope": "full_source"},
        },
        skip_handoff=True,
    )
    set_gate_decision(ctx, "source_preclean", "auto_resolve")
    verdict = solver.evaluate_stage(ctx, "audio_preclean")
    assert verdict.admissible is False
    assert verdict.reason == "gate_open:source_preclean"


def test_evaluate_stage_does_not_persist_gate_decisions(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "d10_readonly", solver.FULL_AUTO)
    _open_g0(ctx)
    solver.evaluate_stage(ctx, "speaker_roles", posture=solver.FULL_AUTO)
    solver._gate_verdict(ctx, "speaker_roles", solver.FULL_AUTO)
    assert not ctx.artifact_exists(DECISIONS_REL)
    assert recorded_gate_action(ctx, "transcript_integrity") is None
