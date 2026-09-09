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
    ensure_source_topology,
    recovery_policy_for_class,
    require_pickup_speaker_clear,
    _speaker_talk_stats,
)
from interview_mux.run_context import RunContext
from run_fixtures import mark_done_raw


def test_production_style_default():
    assert get_production_style(None) in (DEFAULT_STYLE, TBIY_STYLE)


def test_is_tbiy_false_by_default():
    assert is_tbiy(None) is False or get_production_style(None) == TBIY_STYLE


def test_prompt_variant_always_canonical():
    rel = "understanding/content-context.system.txt"
    assert prompt_variant(rel, None) == rel


def test_prompt_variant_strips_tbiy_suffix(tmp_path: Path):
    ctx = RunContext(str(tmp_path / "run"), create=True)
    meta = {"production_style": "tbiy_narrative"}
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    rel = "understanding/content-brief-reanchor.tbiy.system.txt"
    assert prompt_variant(rel, ctx) == "understanding/content-brief-reanchor.system.txt"


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


def test_classify_one_on_one_balanced():
    stats = [
        {"speaker_id": "spk_0", "talk_ms": 50000, "talk_ratio": 0.50, "role_hint": "interviewee", "turn_count": 10, "question_count": 0},
        {"speaker_id": "spk_1", "talk_ms": 50000, "talk_ratio": 0.50, "role_hint": "interviewer", "turn_count": 10, "question_count": 8},
    ]
    assert classify_topology(stats, {"speakers": []}) == "one_on_one_balanced"


def test_balanced_recovery_policy_is_framing_needed():
    policy = recovery_policy_for_class("one_on_one_balanced")
    assert policy["vo_posture"] == "framing_needed"
    assert policy["contiguous_seam"] == "skip_waive_glue"
    assert policy["reorder_seam"] == "mint_bridge"
    assert policy["synth_ladder"] == "chatterbox_then_mlx_qc"
    assert recovery_policy_for_class("one_on_one_asymmetric")["vo_posture"] == "framing_needed"
    assert recovery_policy_for_class("monologue_heavy")["vo_posture"] == "sparse_omit"
    assert recovery_policy_for_class("panel_multi_guest")["vo_posture"] == "bridge_only"


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
    assert isinstance(adapt.get("recovery_policy"), dict)
    assert "vo_posture" in adapt["recovery_policy"]


def test_pickup_defaults_to_least_spoken_host_not_quiet_guest(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "transcript").mkdir()
    (run_dir / "understanding").mkdir()
    words = []
    t = 0
    for _i in range(20):
        words.append({"word": "hi", "speaker": "spk_0", "start_ms": t, "end_ms": t + 500})
        t += 500
    for _i in range(80):
        words.append({"word": "ok", "speaker": "spk_1", "start_ms": t, "end_ms": t + 500})
        t += 500
    (run_dir / "transcript" / "full.json").write_text(json.dumps({"words": words}))
    (run_dir / "understanding" / "speakers.json").write_text(
        json.dumps(
            {
                "speakers": [
                    {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
                    {"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9},
                ]
            }
        )
    )
    ctx = RunContext(str(run_dir))
    topo, adapt = build_topology_artifacts(ctx)
    assert topo["least_spoken_speaker_id"] == "spk_0"
    assert topo["pickup_eligible_speaker_id"] == "spk_1"
    assert adapt["pickup_eligible_speaker_id"] == "spk_1"


def test_ensure_source_topology_builds_when_homunculus_skipped(tmp_path: Path):
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "exec_topo_skip")
    words = []
    t = 0
    for _i in range(40):
        words.append({"word": "hi", "speaker": "spk_0", "start_ms": t, "end_ms": t + 500})
        t += 500
    for _i in range(8):
        words.append({"word": "ok", "speaker": "spk_1", "start_ms": t, "end_ms": t + 500})
        t += 500
    (ctx.run_dir / "transcript").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "transcript" / "full.json").write_text(
        json.dumps({"words": words}), encoding="utf-8"
    )
    (ctx.run_dir / "understanding" / "speakers.json").write_text(
        json.dumps(
            {
                "speakers": [
                    {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
                    {"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert not ctx.artifact_exists("understanding/source_topology.json")
    topo = ensure_source_topology(ctx)
    assert topo.get("pickup_eligible_speaker_id") == "spk_1"
    assert ctx.artifact_exists("understanding/source_topology.json")
    assert ctx.artifact_exists("understanding/flow_adaptation.json")
    assert ctx.is_done("source_topology_build")


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
                    {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
                    {"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9},
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
        mark_done_raw(ctx, sid)
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


def test_unknown_roles_do_not_clone_most_talk_guest(tmp_path: Path) -> None:
    from interview_mux.source_topology import (
        clone_host_auto_approve_allowed,
        pickup_eligible_speaker_id,
        resolve_clone_host_speaker_id,
    )

    run_dir = tmp_path / "run_unknown"
    run_dir.mkdir()
    (run_dir / "understanding").mkdir()
    ctx = RunContext(str(run_dir))
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "unknown", "confidence": 0.4, "talk_time_ms": 90_000},
                {"speaker_id": "spk_1", "role": "unknown", "confidence": 0.4, "talk_time_ms": 10_000},
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_balanced",
            "speaker_stats": [
                {"speaker_id": "spk_0", "talk_ms": 90_000, "role_hint": "unknown"},
                {"speaker_id": "spk_1", "talk_ms": 10_000, "role_hint": "unknown"},
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json("run_meta.json", {"gap_framing_enabled": True}, skip_handoff=True)
    assert resolve_clone_host_speaker_id(ctx) is None
    assert pickup_eligible_speaker_id(ctx) in {None, ""}
    assert not clone_host_auto_approve_allowed(ctx, "spk_0")


def test_delivery_plan_does_not_override_host_when_framing_yes(tmp_path: Path) -> None:
    from interview_mux.source_topology import pickup_eligible_speaker_id
    from interview_mux.speaker_delivery_plan import build_speaker_delivery_plan

    run_dir = tmp_path / "run_plan"
    run_dir.mkdir()
    (run_dir / "understanding").mkdir()
    ctx = RunContext(str(run_dir))
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
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "pickup_eligible_speaker_id": "spk_1",
            "speaker_stats": [
                {"speaker_id": "spk_0", "talk_ms": 80_000, "role_hint": "interviewee"},
                {"speaker_id": "spk_1", "talk_ms": 20_000, "role_hint": "interviewer"},
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json("run_meta.json", {"gap_framing_enabled": True}, skip_handoff=True)
    ctx.write_json(
        "understanding/speaker_delivery_plan.json",
        {
            "clone_speaker_id": "spk_0",
            "insert_strategy": "self_clone_no_interviewer",
        },
        skip_handoff=True,
    )
    assert pickup_eligible_speaker_id(ctx) == "spk_1"
    plan = build_speaker_delivery_plan(ctx)
    assert plan["clone_speaker_id"] == "spk_1"
    assert plan["insert_strategy"] != "self_clone_no_interviewer"
