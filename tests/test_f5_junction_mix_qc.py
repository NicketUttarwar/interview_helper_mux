"""F5 junction / mix QC: no mix on live hangs; fuse-then-omit noop recut.

Fixture shape from exec_11160 incomplete-cut residuals at pre_mix.
Does not resume that run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error
from interview_mux.junction_snip_qa import (
    apply_junction_repairs,
    refuse_mix_if_live_incomplete_cuts,
    remaster_mix_only,
)
from interview_mux.loud_fail import LoudStageFailure
from interview_mux.publishability_boundary import validate_publishability
from interview_mux.recovery_controller import classify_error_class
from interview_mux.thought_complete_recut import ACTION as THOUGHT_COMPLETE
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging
from run_fixtures import isolated_run_ctx

_FIX = Path(__file__).resolve().parent / "fixtures" / "f5_junction_mix_qc"
_META = json.loads((_FIX / "on_a_roll_hang.json").read_text(encoding="utf-8"))
HANG = str(_META["hang_segment_id"])
NEIGHBOR = str(_META["neighbor_segment_id"])


def _seg(sid: str, start_ms: int, end_ms: int, text: str) -> dict:
    return {
        "segment_id": sid,
        "speaker_id": "spk_0",
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "topic_tags": [],
        "text": text,
        "start_ms": start_ms,
        "end_ms": end_ms,
    }


def _speech(sid: str, start_ms: int, end_ms: int) -> dict:
    return {
        "type": "speech",
        "segment_id": sid,
        "source_start_ms": start_ms,
        "source_end_ms": end_ms,
        "timeline_start_ms": start_ms,
        "duration_ms": max(0, end_ms - start_ms),
    }


def _plant(ctx, *, clips: list[dict], ordered: list[str], segments: list[dict]) -> dict:
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)
    duration = sum(int(c.get("duration_ms") or 0) for c in clips)
    edl = {
        "version": 1,
        "ordered_segment_ids": ordered,
        "clips": clips,
        "timeline_duration_ms": duration,
        "excluded_segment_ids": [],
        "chapters": [],
    }
    for rel, data in (
        ("master/selection.json", {"ordered_segment_ids": ordered}),
        ("master/edl.json", edl),
    ):
        path = ctx.final_path(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return edl


def test_remaster_refuses_live_incomplete_cuts_and_keeps_mix_done_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "f5_remaster_refuse")
    _plant(
        ctx,
        clips=[_speech(HANG, 0, 800)],
        ordered=[HANG],
        segments=[_seg(HANG, 0, 800, "how expensive is it")],
    )
    marker = ctx.final_path(".stage_done", "mix")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("done", encoding="utf-8")
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": HANG}
        ],
    )
    # Residuals are advisory (ISSUES 185): the gate logs instead of refusing,
    # and the mix-done marker is untouched by it.
    assert refuse_mix_if_live_incomplete_cuts(ctx) is None
    assert marker.is_file()
    assert (
        classify_error_class(
            "mix",
            LoudStageFailure(
                "incomplete_cut_unresolved: Mix refused: live incomplete-cut residuals on_a_roll",
                stage="mix",
                reason="incomplete_cut_unresolved",
            ),
        )
        == "incomplete_cut_unresolved"
    )
    route = classify_heal_error(
        "incomplete_cut_unresolved: Mix refused: live incomplete-cut residuals on_a_roll",
        ctx,
        stage="mix",
    )
    assert route is not None
    assert route.from_stage == "junction_snip_qa"
    assert route.from_stage != "mix"


def test_pre_mix_blocks_live_hang_even_when_junction_is_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "f5_premix_live")
    _plant(
        ctx,
        clips=[_speech(HANG, 0, 800)],
        ordered=[HANG],
        segments=[_seg(HANG, 0, 800, "how expensive is it")],
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": HANG}
        ],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.has_critical_residuals",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.critical_residual_view",
        lambda _ctx: type(
            "V",
            (),
            {"count": 1, "kinds": ("on_a_roll",), "sources": ("junction_findings",)},
        )(),
    )
    enter_stage_staging("junction_snip_qa")
    try:
        report = validate_publishability(ctx, checkpoint="pre_mix")
        assert any(v.error_class == "incomplete_cut_unresolved" for v in report.violations)
    finally:
        exit_stage_staging()


def test_noop_thought_complete_fuses_into_neighbor(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "f5_fuse")
    edl = _plant(
        ctx,
        clips=[_speech(HANG, 0, 800), _speech(NEIGHBOR, 900, 4000)],
        ordered=[HANG, NEIGHBOR],
        segments=[
            _seg(HANG, 0, 800, "how expensive is it"),
            _seg(NEIGHBOR, 900, 4000, "The assay price depends on the panel."),
        ],
    )
    finding = {
        "kind": "on_a_roll",
        "severity": "critical",
        "segment_id": HANG,
        "clip_index": 0,
        "action": THOUGHT_COMPLETE,
        "detail": {"end_text": "how expensive is it"},
    }
    new_edl, applied, changed = apply_junction_repairs(ctx, edl, [finding])
    assert changed
    assert any(a.get("status") == "fused_neighbor" for a in applied)
    speech = [
        str(c.get("segment_id") or "")
        for c in (new_edl.get("clips") or [])
        if str(c.get("type") or "") == "speech"
    ]
    assert HANG not in speech
    assert NEIGHBOR in speech


def test_noop_thought_complete_omits_when_no_neighbor(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "f5_omit")
    edl = _plant(
        ctx,
        clips=[_speech(HANG, 0, 800), _speech(NEIGHBOR, 80_000, 90_000)],
        ordered=[HANG, NEIGHBOR],
        segments=[
            _seg(HANG, 0, 800, "how expensive is it"),
            _seg(NEIGHBOR, 80_000, 90_000, "Later we talk about pricing."),
        ],
    )
    finding = {
        "kind": "on_a_roll",
        "severity": "critical",
        "segment_id": HANG,
        "clip_index": 0,
        "action": THOUGHT_COMPLETE,
        "detail": {"end_text": "how expensive is it"},
    }
    new_edl, applied, changed = apply_junction_repairs(ctx, edl, [finding])
    assert changed
    assert any(a.get("status") == "omitted_no_neighbor" for a in applied)
    speech = [
        str(c.get("segment_id") or "")
        for c in (new_edl.get("clips") or [])
        if str(c.get("type") or "") == "speech"
    ]
    assert HANG not in speech
    assert NEIGHBOR in speech
    assert HANG not in [str(s) for s in (new_edl.get("ordered_segment_ids") or [])]
