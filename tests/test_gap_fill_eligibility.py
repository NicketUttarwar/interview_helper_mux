"""Gap-fill eligibility binary gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.conversation_context import build_gap_sensitivity
from interview_mux.gap_fill_eligibility import (
    assess_gap_fill_eligibility,
    gap_fill_was_skipped,
    hosted_framing_requires_synthetic_vo,
    silent_skip_allowed,
    synthetic_vo_incompleteness,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, patch_merged_config


def _write_speakers(run: Path, doc: dict) -> None:
    (run / "understanding").mkdir(parents=True, exist_ok=True)
    (run / "understanding" / "speakers.json").write_text(json.dumps(doc), encoding="utf-8")
    (run / "understanding" / "analysis_state.json").write_text("{}", encoding="utf-8")
    (run / "run_meta.json").write_text("{}", encoding="utf-8")


def test_skip_true_monologue(tmp_path: Path) -> None:
    run = tmp_path / "exec_mono"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
            ],
            "conversation_profile": {"format_class_candidate": "fireside", "dynamics": {}},
        },
    )
    (run / "understanding" / "source_topology.json").write_text(
        json.dumps({"topology_class": "monologue_heavy", "speaker_stats": []}),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    decision = assess_gap_fill_eligibility(ctx)
    assert not decision.eligible
    assert decision.signals.get("skip_signal") in {"true_monologue", "topology_skip_class"}


def test_two_speakers_without_labeled_interviewer_are_eligible(tmp_path: Path) -> None:
    run = tmp_path / "exec_no_frame"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "unknown", "confidence": 0.4},
            ],
            "conversation_profile": {"format_class_candidate": "one_on_one", "dynamics": {}},
        },
    )
    ctx = RunContext(str(run))
    decision = assess_gap_fill_eligibility(ctx)
    assert decision.eligible, decision.reason


def test_eligible_asymmetric_interview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = tmp_path / "exec_asym"
    _write_speakers(
        run,
        {
            "speakers": [
                {
                    "speaker_id": "spk_0",
                    "role": "interviewer",
                    "confidence": 0.9,
                    "question_density": "high",
                },
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ],
            "conversation_profile": {
                "format_class_candidate": "one_on_one",
                "dynamics": {"turn_asymmetry": "high", "question_density": "high"},
            },
            "gap_sensitivity": build_gap_sensitivity("one_on_one"),
        },
    )
    (run / "understanding" / "source_topology.json").write_text(
        json.dumps({"topology_class": "one_on_one_asymmetric", "speaker_stats": []}),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    decision = assess_gap_fill_eligibility(ctx)
    assert decision.eligible


def test_hosted_balanced_interview_with_frame_questions_is_eligible(tmp_path: Path) -> None:
    """one_on_one_balanced + interviewer questions is G-Framing eligible.

    Talk-time ~50/50 and frame confidence 0.64 (just under 0.65) must not skip
    a hosted podcast; sparse-omit is recovery_policy for layups, not a framing skip.
    """
    run = tmp_path / "exec_balanced_host"
    _write_speakers(
        run,
        {
            "speakers": [
                {
                    "speaker_id": "spk_1",
                    "role": "interviewer",
                    "confidence": 0.64,
                    "question_density": "high",
                },
                {
                    "speaker_id": "spk_0",
                    "role": "interviewee",
                    "confidence": 0.67,
                    "question_density": "medium",
                },
            ],
            "conversation_profile": {
                "format_class_candidate": "technical_deep_dive",
                "dynamics": {"turn_asymmetry": "low", "question_density": "high"},
            },
            "gap_sensitivity": build_gap_sensitivity("one_on_one"),
        },
    )
    (run / "understanding" / "source_topology.json").write_text(
        json.dumps({"topology_class": "one_on_one_balanced", "speaker_stats": []}),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    decision = assess_gap_fill_eligibility(ctx)
    assert decision.eligible, decision.reason
    assert decision.signals.get("eligible_signal") in {
        "hosted_one_on_one",
        "multi_speaker_fail_open",
        "hosted_one_on_one_questions",
    }


def test_forced_skip_via_run_meta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = tmp_path / "exec_forced"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.95},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.95},
            ],
        },
    )
    (run / "run_meta.json").write_text(json.dumps({"gap_fill_mode": "skipped"}), encoding="utf-8")
    ctx = RunContext(str(run))
    assert not assess_gap_fill_eligibility(ctx).eligible


def test_gap_fill_was_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "skip_flag")
    assert not gap_fill_was_skipped(ctx)
    ctx.write_json(
        "understanding/gap_fill_skip.json",
        {"status": "skipped", "reason": "test"},
        skip_handoff=True,
    )
    assert gap_fill_was_skipped(ctx)


def test_hosted_1on1_requires_synthetic_vo_lines(tmp_path: Path) -> None:
    run = tmp_path / "exec_vo_floor"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
            ],
        },
    )
    (run / "understanding" / "source_topology.json").write_text(
        json.dumps({"topology_class": "one_on_one_balanced"}),
        encoding="utf-8",
    )
    (run / "run_meta.json").write_text(
        json.dumps({"gap_framing_enabled": True, "gap_fill_mode": "active"}),
        encoding="utf-8",
    )
    (run / "master").mkdir(parents=True, exist_ok=True)
    (run / "master" / "selection.json").write_text(
        json.dumps({"ordered_segment_ids": [f"seg_{i:03d}" for i in range(10)]}),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    assert hosted_framing_requires_synthetic_vo(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    # HOLLOW_ZERO / under-floor is advisory — incompleteness returns None.
    assert synthetic_vo_incompleteness(ctx, "nugget_layup_compose") is None
    assert synthetic_vo_incompleteness(ctx, "g1_vo_pickup") is None
    assert synthetic_vo_incompleteness(ctx, "edl") is None
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": f"vo_{i}",
                    "delivery": "synthesize",
                    "text": "Q?",
                    "gap_type": "missing_question",
                    "targets_segment_id": f"seg_{i:03d}",
                    "placement": "before",
                }
                for i in range(3)
            ]
        },
        skip_handoff=True,
    )
    assert synthetic_vo_incompleteness(ctx, "nugget_layup_compose") is None


def test_silent_skip_only_for_monologue_or_operator(tmp_path: Path) -> None:
    from interview_mux.gap_fill_eligibility import GapFillDecision

    assert silent_skip_allowed(
        GapFillDecision(False, "mono", {"skip_signal": "true_monologue"})
    )
    assert not silent_skip_allowed(
        GapFillDecision(False, "low conf", {"skip_signal": "low_frame_confidence"})
    )
    assert not silent_skip_allowed(GapFillDecision(True, "ok", {}))


def test_compose_not_held_to_min_vo_floor(tmp_path: Path) -> None:
    run = tmp_path / "exec_compose_floor"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
            ]
        },
    )
    (run / "understanding" / "source_topology.json").write_text(
        json.dumps({"topology_class": "one_on_one_balanced"}),
        encoding="utf-8",
    )
    (run / "run_meta.json").write_text(
        json.dumps({"gap_framing_enabled": True, "gap_fill_mode": "active"}),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    assert synthetic_vo_incompleteness(ctx, "gap_framing_compose") is None
    assert synthetic_vo_incompleteness(ctx, "optimal_questions") is None
    # Layup stage under-floor is advisory too (need=3 target, not a ship bar).
    assert synthetic_vo_incompleteness(ctx, "nugget_layup_compose") is None


def test_blank_delivery_does_not_count_toward_vo_floor(tmp_path: Path) -> None:
    from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines

    run = tmp_path / "exec_blank_del"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
            ]
        },
    )
    ctx = RunContext(str(run))
    path = ctx.path("understanding", "gap_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "interviewer_lines": [
                    {
                        "line_id": "vo_blank",
                        "delivery": "",
                        "text": "Why?",
                        "gap_type": "missing_question",
                        "targets_segment_id": "seg_001",
                        "placement": "before",
                    },
                    {
                        "line_id": "vo_ok",
                        "delivery": "synthesize",
                        "text": "Why this?",
                        "gap_type": "missing_question",
                        "targets_segment_id": "seg_002",
                        "placement": "before",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    assert count_active_gap_vo_lines(ctx) == 1


def test_sparse_host_and_panel_not_held_to_min_three(tmp_path: Path) -> None:
    run = tmp_path / "exec_sparse_floor"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9},
            ]
        },
    )
    (run / "run_meta.json").write_text(
        json.dumps({"gap_framing_enabled": True, "gap_fill_mode": "active"}),
        encoding="utf-8",
    )
    (run / "understanding" / "source_topology.json").write_text(
        json.dumps({"topology_class": "multi_idea_sparse_host"}),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    assert not hosted_framing_requires_synthetic_vo(ctx)
    assert synthetic_vo_incompleteness(ctx, "nugget_layup_compose") is None
    (run / "understanding" / "source_topology.json").write_text(
        json.dumps({"topology_class": "panel_multi_guest"}),
        encoding="utf-8",
    )
    assert not hosted_framing_requires_synthetic_vo(ctx)


def test_unclassified_two_speaker_no_min_three_floor(tmp_path: Path) -> None:
    run = tmp_path / "exec_unclass"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "unknown", "confidence": 0.5},
                {"speaker_id": "spk_1", "role": "unknown", "confidence": 0.5},
            ]
        },
    )
    (run / "run_meta.json").write_text(
        json.dumps({"gap_framing_enabled": True}),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    assert assess_gap_fill_eligibility(ctx).eligible
    assert not hosted_framing_requires_synthetic_vo(ctx)


def test_clear_gap_fill_skip_removes_stub_producer(tmp_path: Path) -> None:
    from interview_mux.gap_fill_eligibility import clear_gap_fill_skip

    run = tmp_path / "exec_stub"
    _write_speakers(run, {"speakers": [{"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9}]})
    ctx = RunContext(str(run))
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [],
            "_meta": {"producer": "gap_fill_skip", "producer_stage": "optimal_questions"},
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_fill_skip.json",
        {"status": "skipped", "reason": "test"},
        skip_handoff=True,
    )
    clear_gap_fill_skip(ctx, reason="test_enable")
    assert not ctx.artifact_exists("understanding/gap_report.json")
    assert not gap_fill_was_skipped(ctx)
