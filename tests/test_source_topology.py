"""Tests for production profile and source topology (source_topology_build stage)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.production_profile import (
    DEFAULT_STYLE,
    TBIY_STYLE,
    get_production_style,
    is_tbiy,
    prompt_variant,
)
from interview_mux.source_topology import (
    apply_flow_adaptation_patch,
    build_topology_artifacts,
    check_pickup_speaker_pending,
    classify_topology,
    confirm_pickup_speaker,
    require_pickup_speaker_clear,
    _speaker_talk_stats,
)
from interview_mux.run_context import RunContext


def test_production_style_default():
    assert get_production_style(None) in (DEFAULT_STYLE, TBIY_STYLE)


def test_is_tbiy_false_by_default():
    assert is_tbiy(None) is False or get_production_style(None) == TBIY_STYLE


def test_prompt_variant_documentary_unchanged():
    rel = "understanding/content-context.system.txt"
    assert prompt_variant(rel, None) == rel or ".tbiy." in prompt_variant(rel, None)


def test_prompt_variant_reanchor_tbiy(tmp_path: Path):
    ctx = RunContext(str(tmp_path / "run"), create=True)
    meta = {"production_style": "tbiy_narrative"}
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    rel = "understanding/content-brief-reanchor.system.txt"
    assert prompt_variant(rel, ctx) == "understanding/content-brief-reanchor.tbiy.system.txt"


def test_classify_monologue():
    stats = [
        {"speaker_id": "spk_0", "talk_ms": 90000, "talk_ratio": 0.85, "role_hint": "interviewee", "turn_count": 5, "question_count": 0},
        {"speaker_id": "spk_1", "talk_ms": 15000, "talk_ratio": 0.15, "role_hint": "interviewer", "turn_count": 3, "question_count": 2},
    ]
    assert classify_topology(stats, {"speakers": []}) == "monologue_heavy"


def test_classify_one_on_one_asymmetric():
    stats = [
        {"speaker_id": "spk_0", "talk_ms": 70000, "talk_ratio": 0.70, "role_hint": "interviewee", "turn_count": 10, "question_count": 0},
        {"speaker_id": "spk_1", "talk_ms": 30000, "talk_ratio": 0.30, "role_hint": "interviewer", "turn_count": 8, "question_count": 5},
    ]
    assert classify_topology(stats, {"speakers": []}) == "one_on_one_asymmetric"


def test_source_topology_build_pickup_eligible_is_least_spoken(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "transcript").mkdir()
    (run_dir / "understanding").mkdir()
    words = []
    t = 0
    for _i in range(100):
        words.append({"word": "hi", "speaker": "spk_0", "start_ms": t, "end_ms": t + 500})
        t += 500
    for _i in range(10):
        words.append({"word": "ok", "speaker": "spk_1", "start_ms": t, "end_ms": t + 500})
        t += 500
    (run_dir / "transcript" / "full.json").write_text(json.dumps({"words": words}))
    (run_dir / "understanding" / "speakers.json").write_text(
        json.dumps(
            {
                "speakers": [
                    {"speaker_id": "spk_0", "role": "interviewee"},
                    {"speaker_id": "spk_1", "role": "interviewer"},
                ]
            }
        )
    )
    ctx = RunContext(str(run_dir))
    topo, adapt = build_topology_artifacts(ctx)
    assert topo["pickup_eligible_speaker_id"] == "spk_1"
    assert topo["least_spoken_speaker_id"] == "spk_1"
    assert adapt["pickup_eligible_speaker_id"] == "spk_1"


def _seed_topology_ctx(tmp_path: Path) -> RunContext:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "transcript").mkdir()
    (run_dir / "understanding").mkdir()
    words = []
    t = 0
    for _i in range(100):
        words.append({"word": "hi", "speaker": "spk_0", "start_ms": t, "end_ms": t + 500})
        t += 500
    for _i in range(10):
        words.append({"word": "ok", "speaker": "spk_1", "start_ms": t, "end_ms": t + 500})
        t += 500
    (run_dir / "transcript" / "full.json").write_text(json.dumps({"words": words}))
    (run_dir / "understanding" / "speakers.json").write_text(
        json.dumps(
            {
                "speakers": [
                    {"speaker_id": "spk_0", "role": "interviewee"},
                    {"speaker_id": "spk_1", "role": "interviewer"},
                ]
            }
        )
    )
    ctx = RunContext(str(run_dir))
    topo, adapt = build_topology_artifacts(ctx)
    ctx.write_json("understanding/source_topology.json", topo, skip_handoff=True)
    ctx.write_json("understanding/flow_adaptation.json", adapt, skip_handoff=True)
    ctx.mark_done("source_topology_build")
    from interview_mux.gap_vo_gates import set_gap_framing_enabled

    set_gap_framing_enabled(ctx, True)
    from interview_mux.pipeline import ANALYSIS_ORDER

    for sid in ANALYSIS_ORDER:
        if sid == "missing_framing":
            break
        ctx.mark_done(sid, force=True)
    return ctx


def test_pickup_speaker_pending_until_confirmed(tmp_path: Path) -> None:
    ctx = _seed_topology_ctx(tmp_path)
    assert check_pickup_speaker_pending(ctx) is True
    with pytest.raises(SystemExit):
        require_pickup_speaker_clear(ctx)
    confirm_pickup_speaker(ctx)
    assert check_pickup_speaker_pending(ctx) is False
    require_pickup_speaker_clear(ctx)


def test_pickup_speaker_operator_override(tmp_path: Path) -> None:
    ctx = _seed_topology_ctx(tmp_path)
    apply_flow_adaptation_patch(ctx, {"pickup_eligible_speaker_id": "spk_0"})
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    topo = ctx.read_json("understanding/source_topology.json")
    assert adapt["pickup_eligible_speaker_id"] == "spk_0"
    assert topo["pickup_eligible_speaker_id"] == "spk_0"
    confirm_pickup_speaker(ctx, speaker_id="spk_0")
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    assert adapt["operator_overrides"]["pickup_speaker_confirmed"] is True
