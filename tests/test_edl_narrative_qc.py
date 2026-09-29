from __future__ import annotations

import pytest

from interview_mux.edl_narrative_qc import validate_flow1_edl_narrative
from interview_mux.gates import check_edl_narrative_qc
from interview_mux.operator_quality import qc_summary
from interview_mux.run_context import RunContext
from run_fixtures import (
    minimal_gap_line,
    minimal_gap_report,
    minimal_manifest,
    minimal_manifest_segment,
    write_fixture_json,
)


def _write_story_artifacts(ctx: RunContext) -> None:
    # Plant exact validator fixtures past one-writer sanitize/repair (which would
    # rewrite selection/gaps/transitions under music-only + blank-drop rules).
    prev = getattr(ctx, "_one_writer_raw", False)
    ctx._one_writer_raw = True
    try:
        ctx.write_json(
            "segments/manifest.json",
            minimal_manifest(
                minimal_manifest_segment(
                    "seg_a",
                    text="Guest opens with the founding story of the company and early team.",
                    start_ms=0,
                    end_ms=9000,
                ),
                minimal_manifest_segment(
                    "seg_b",
                    text="Host asks how the breakthrough changed the product roadmap for everyone.",
                    start_ms=9000,
                    end_ms=18000,
                ),
                minimal_manifest_segment(
                    "seg_c",
                    text="Guest explains the launch moment that changed the team forever after.",
                    start_ms=18000,
                    end_ms=27000,
                ),
            ),
        )
        ctx.write_json(
            "master/selection.json",
            {
                "ordered_segment_ids": ["seg_a", "seg_b", "seg_c"],
                "chapters": [
                    {"title": "Setup", "segment_ids": ["seg_a", "seg_b"]},
                    {"title": "Payoff", "segment_ids": ["seg_c"]},
                ],
                "excluded_segment_ids": [{"segment_id": "seg_x", "reason": "aside"}],
            },
        )
        ctx.write_json(
            "master/coverage_audit.json",
            {
                "coverage_score": 1.0,
                "topic_mappings": [
                    {"topic": "Origins", "covered": True, "segment_ids": ["seg_a"]},
                    {"topic": "Breakthrough", "covered": True, "segment_ids": ["seg_c"]},
                ],
                "claim_mappings": [
                    {"claim": "The launch changed the team", "covered": True, "segment_ids": ["seg_c"]}
                ],
                "missing_coverage": [],
            },
        )
        ctx.write_json(
            "master/narrative_plan.json",
            {
                "arc_summary": "Setup before payoff.",
                "chapters": [
                    {"chapter_id": "ch_01", "title": "Setup", "suggested_open_segment_id": "seg_a"},
                    {"chapter_id": "ch_02", "title": "Payoff", "suggested_open_segment_id": "seg_c"},
                ],
                "ordering_constraints": [
                    {"before_segment_id": "seg_a", "after_segment_id": "seg_c", "reason": "setup before payoff"}
                ],
            },
        )
        ctx.write_json(
            "master/transitions.json",
            {
                "transitions": [
                    {
                        "after_segment_id": "seg_b",
                        "before_segment_id": "seg_c",
                        "text": "That set up the turning point.",
                        "type": "chapter",
                    }
                ]
            },
        )
        write_fixture_json(
            ctx,
            "understanding/gap_report.json",
            minimal_gap_report(
                minimal_gap_line(
                    line_id="line_001",
                    targets_segment_id="seg_b",
                    placement="before",
                    delivery="record",
                )
            ),
            stage_key="gap_framing_compose",
        )
        ctx.write_json(
            "master/edl_narrative_audit.json",
            {
                "verdict": "pass",
                "blocking_issues": [],
                "warnings": [],
                "recommended_actions": [],
                "reasoning_summary": "Pass.",
            },
        )
    finally:
        ctx._one_writer_raw = prev


def _good_edl() -> dict:
    return {
        "version": 1,
        "ordered_segment_ids": ["seg_a", "seg_b", "seg_c"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "timeline_start_ms": 0,
                "duration_ms": 1000,
            },
            {
                "type": "vo_pickup",
                "line_id": "line_001",
                "targets_segment_id": "seg_b",
                "placement": "before",
                "timeline_start_ms": 1000,
                "duration_ms": 0,
            },
            {
                "type": "speech",
                "segment_id": "seg_b",
                "source_start_ms": 1000,
                "source_end_ms": 2000,
                "timeline_start_ms": 1000,
                "duration_ms": 1000,
            },
            {
                "type": "transition",
                "after_segment_id": "seg_b",
                "before_segment_id": "seg_c",
                "text": "That set up the turning point.",
                "transition_type": "chapter",
                "timeline_start_ms": 2000,
                "duration_ms": 0,
            },
            {
                "type": "speech",
                "segment_id": "seg_c",
                "source_start_ms": 2000,
                "source_end_ms": 3000,
                "timeline_start_ms": 2000,
                "duration_ms": 1000,
            },
        ],
        "gap_placements": [
            {"line_id": "line_001", "targets_segment_id": "seg_b", "placement": "before", "timeline_start_ms": 1000}
        ],
        "timeline_duration_ms": 3000,
        "warnings": {"missing_vo_files": ["line_001"], "gap_targets_not_in_selection": []},
    }


def test_validate_flow1_edl_narrative_passes() -> None:
    ctx = RunContext("run_edl_narrative_ok", create=True)
    _write_story_artifacts(ctx)
    assert validate_flow1_edl_narrative(ctx, _good_edl()) == []


def test_validate_flow1_edl_narrative_catches_coverage_loss() -> None:
    ctx = RunContext("run_edl_narrative_coverage_loss", create=True)
    _write_story_artifacts(ctx)
    edl = _good_edl()
    edl["ordered_segment_ids"] = ["seg_a", "seg_b"]
    edl["clips"] = [c for c in edl["clips"] if c.get("segment_id") != "seg_c"]
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("covered topic" in e and "Breakthrough" in e for e in errors)


def test_validate_flow1_edl_narrative_catches_ordering_constraint() -> None:
    ctx = RunContext("run_edl_narrative_ordering", create=True)
    _write_story_artifacts(ctx)
    edl = _good_edl()
    edl["ordered_segment_ids"] = ["seg_c", "seg_a", "seg_b"]
    for idx, sid in enumerate(["seg_c", "seg_a", "seg_b"]):
        speech = [c for c in edl["clips"] if c.get("type") == "speech"][idx]
        speech["segment_id"] = sid
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("ordering constraint violated" in e for e in errors)


def test_check_edl_narrative_qc_records_summary(monkeypatch) -> None:
    ctx = RunContext("run_edl_narrative_summary", create=True)
    _write_story_artifacts(ctx)
    monkeypatch.setattr(
        "interview_mux.gates.merged_config",
        lambda: {"edl_narrative_qc": {"strict": True}},
    )
    check_edl_narrative_qc(ctx, stage="edl", edl=_good_edl())
    summary = qc_summary(ctx.read_json("run_meta.json"), "edl_narrative_qc")
    assert summary is not None
    assert summary["passed"] is True
    assert summary["at_stage"] == "edl"


def test_check_edl_narrative_qc_strict_raises(monkeypatch) -> None:
    ctx = RunContext("run_edl_narrative_strict", create=True)
    _write_story_artifacts(ctx)
    monkeypatch.setattr(
        "interview_mux.gates.merged_config",
        lambda: {"edl_narrative_qc": {"strict": True}},
    )
    edl = _good_edl()
    edl["clips"] = [c for c in edl["clips"] if c.get("segment_id") != "seg_c"]
    with pytest.raises(SystemExit, match="edl_narrative_qc strict"):
        check_edl_narrative_qc(ctx, stage="edl", edl=edl)


def test_validate_synthesize_gap_with_missing_vo_warning() -> None:
    ctx = RunContext("run_edl_synth_warn", create=True)
    _write_story_artifacts(ctx)
    report = ctx.read_json("understanding/gap_report.json")
    report["interviewer_lines"][0]["delivery"] = "synthesize"
    write_fixture_json(
        ctx, "understanding/gap_report.json", report, stage_key="gap_framing_compose"
    )
    edl = _good_edl()
    edl["warnings"]["missing_vo_files"] = ["line_001"]
    assert validate_flow1_edl_narrative(ctx, edl) == []


def test_validate_framing_before_impact_missing_vo() -> None:
    ctx = RunContext("run_edl_framing_impact", create=True)
    _write_story_artifacts(ctx)
    ctx.write_json(
        "understanding/gap_framing_plan.json",
        {
            "succinct_master_intent": True,
            "acts": [
                {
                    "act_id": "act_1",
                    "impact_blocks": [
                        {
                            "framing_line_ids": ["line_001"],
                            "source_segment_ids": ["seg_b"],
                        }
                    ],
                }
            ],
        },
    )
    edl = _good_edl()
    edl["clips"] = [c for c in edl["clips"] if c.get("type") != "vo_pickup"]
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("preceding framing VO" in e for e in errors)


def test_validate_duplicate_line_id_is_blocking() -> None:
    ctx = RunContext("run_edl_dup_vo", create=True)
    _write_story_artifacts(ctx)
    report = ctx.read_json("understanding/gap_report.json")
    line = dict(report["interviewer_lines"][0])
    report["interviewer_lines"].append(line)
    # Plant intentional duplicate past one-writer sanitize (which would collapse it).
    write_fixture_json(
        ctx, "understanding/gap_report.json", report, stage_key="gap_framing_compose"
    )
    edl = _good_edl()
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("appears 2x" in e and "line_id" in e for e in errors)


def test_validate_clone_voice_adjacency_allows_only_cut_recovery() -> None:
    ctx = RunContext("run_edl_clone_adjacency", create=True)
    _write_story_artifacts(ctx)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a", speaker_id="spk_guest"),
            minimal_manifest_segment("seg_b", speaker_id="spk_host"),
            minimal_manifest_segment("seg_c", speaker_id="spk_guest"),
        ),
    )
    report = ctx.read_json("understanding/gap_report.json")
    report["interviewer_lines"][0].update(
        {"voice_speaker_id": "spk_host", "origin": "nugget_layup", "nugget_ids": []}
    )
    write_fixture_json(
        ctx, "understanding/gap_report.json", report, stage_key="gap_framing_compose"
    )
    edl = _good_edl()
    edl["clips"][1]["voice_speaker_id"] = "spk_host"

    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("cloned voice" in error for error in errors)

    report["interviewer_lines"][0]["nugget_ids"] = ["cut_fact"]
    write_fixture_json(
        ctx, "understanding/gap_report.json", report, stage_key="gap_framing_compose"
    )
    ctx.write_json(
        "understanding/nugget_corpus.json",
        {
            "nuggets": [
                {
                    "nugget_id": "cut_fact",
                    "source_segment_ids": ["seg_x"],
                    "in_selection": False,
                    "text_claim": "A fact recovered from the cut tape.",
                    "evidence_quote": "The source states the recovered fact.",
                }
            ]
        },
    )
    assert not any("cloned voice" in error for error in validate_flow1_edl_narrative(ctx, edl))


def test_validate_framing_ignores_air_script_omitted_layup() -> None:
    """QC must not require layup VO that air-script seated as native_handoff."""
    ctx = RunContext("run_edl_air_script_omit_framing", create=True)
    _write_story_artifacts(ctx)
    ctx.write_json(
        "understanding/gap_framing_plan.json",
        {
            "succinct_master_intent": True,
            "acts": [
                {
                    "act_id": "act_1",
                    "impact_blocks": [
                        {
                            "framing_line_ids": ["line_001"],
                            "source_segment_ids": ["seg_b"],
                        }
                    ],
                }
            ],
        },
    )
    from interview_mux.mastering_plan_loader import forced_sparse_plan, write_plan

    plan = forced_sparse_plan(reason="air_script_omit_qc")
    plan["air_script"] = {
        "version": 1,
        "pass": "pass_b",
        "beats": [
            {
                "id": "b1",
                "segment_id": "seg_a",
                "montage_move": "vo_then_clip",
                "line_id": "vo_preface_episode_orientation",
                "is_orientation": True,
            },
            {"id": "b2", "segment_id": "seg_b", "montage_move": "native_handoff"},
            {"id": "b3", "segment_id": "seg_c", "montage_move": "native_handoff"},
        ],
        "omits": [],
        "energy_curve": [],
        "cold_open": {"kind": "none"},
        "vo_seats": {
            "seated_line_ids": ["vo_preface_episode_orientation"],
            "omitted_line_ids": ["line_001"],
            "orientation_id": "vo_preface_episode_orientation",
        },
    }
    write_plan(ctx, plan)
    edl = _good_edl()
    edl["clips"] = [c for c in edl["clips"] if c.get("type") != "vo_pickup"]
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert not any("preceding framing VO" in e for e in errors)


def test_validate_air_script_native_handoff_does_not_require_transition_clip() -> None:
    """exec_2058: air-script drops native_handoff pairs; QC must not still require the clip."""
    ctx = RunContext("run_edl_air_script_native_handoff_tr", create=True)
    _write_story_artifacts(ctx)
    from interview_mux.mastering_plan_loader import forced_sparse_plan, write_plan

    plan = forced_sparse_plan(reason="native_handoff_transition_qc")
    plan["air_script"] = {
        "version": 1,
        "pass": "pass_b",
        "beats": [
            {"id": "b1", "segment_id": "seg_a", "montage_move": "vo_then_clip"},
            {"id": "b2", "segment_id": "seg_b", "montage_move": "native_handoff"},
            {"id": "b3", "segment_id": "seg_c", "montage_move": "native_handoff"},
        ],
        "omits": [],
        "energy_curve": [],
        "cold_open": {"kind": "none"},
        "vo_seats": {
            "seated_line_ids": [],
            "omitted_line_ids": [],
            "orientation_id": None,
        },
    }
    write_plan(ctx, plan)
    edl = _good_edl()
    edl["clips"] = [c for c in edl["clips"] if c.get("type") != "transition"]
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert not any("missing transition clip" in e for e in errors)


def test_validate_vo_pickup_satisfies_planned_transition() -> None:
    """One host turn per seam: VO on the hinge fulfills transitions.json."""
    ctx = RunContext("run_edl_vo_satisfies_transition", create=True)
    _write_story_artifacts(ctx)
    prev = getattr(ctx, "_one_writer_raw", False)
    ctx._one_writer_raw = True
    try:
        ctx.write_json(
            "master/transitions.json",
            {
                "transitions": [
                    {
                        "after_segment_id": "seg_a",
                        "before_segment_id": "seg_b",
                        "text": "Already covered by the before-VO.",
                        "type": "chapter",
                    }
                ]
            },
        )
    finally:
        ctx._one_writer_raw = prev
    edl = _good_edl()
    edl["clips"] = [c for c in edl["clips"] if c.get("type") != "transition"]
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert not any("missing transition clip" in e for e in errors)


def test_validate_clone_suppressed_transition_not_required() -> None:
    """build_flow1_edl may omit clone-adjacent transitions; QC must not demand them."""
    ctx = RunContext("run_edl_clone_suppressed_transition", create=True)
    _write_story_artifacts(ctx)
    prev = getattr(ctx, "_one_writer_raw", False)
    ctx._one_writer_raw = True
    try:
        ctx.write_json(
            "master/transitions.json",
            {
                "transitions": [
                    {
                        "after_segment_id": "seg_a",
                        "before_segment_id": "seg_b",
                        "text": "Clone-adjacent bridge omitted on purpose.",
                        "type": "bridge",
                        "voice_speaker_id": "spk_1",
                    }
                ]
            },
        )
    finally:
        ctx._one_writer_raw = prev
    edl = _good_edl()
    edl["clips"] = [c for c in edl["clips"] if c.get("type") != "transition"]
    edl.setdefault("warnings", {})["suppressed_clone_adjacency"] = [
        "transition:seg_a->seg_b"
    ]
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert not any("missing transition clip" in e for e in errors)


def test_validate_clone_suppressed_vo_skips_gap_placement() -> None:
    ctx = RunContext("run_edl_clone_suppressed_vo_placement", create=True)
    _write_story_artifacts(ctx)
    report = ctx.read_json("understanding/gap_report.json")
    report["interviewer_lines"][0]["delivery"] = "synthesize"
    report["interviewer_lines"][0]["line_id"] = "vo_layup_seg_010"
    report["interviewer_lines"][0]["targets_segment_id"] = "seg_b"
    write_fixture_json(
        ctx, "understanding/gap_report.json", report, stage_key="gap_framing_compose"
    )
    edl = _good_edl()
    edl["clips"] = [c for c in edl["clips"] if c.get("type") != "vo_pickup"]
    edl["gap_placements"] = []
    edl.setdefault("warnings", {})["suppressed_clone_adjacency"] = ["vo_layup_seg_010"]
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert not any("gap_placements" in e for e in errors)


def test_validate_transition_after_incomplete_thought_fails() -> None:
    ctx = RunContext("run_edl_illegal_hinge_vo", create=True)
    _write_story_artifacts(ctx)
    hanging = "So early prediction of a reoccurrence, if I could do through cell biopsy."
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a", start_ms=0, end_ms=1000, text="Complete setup."),
            minimal_manifest_segment("seg_b", start_ms=1000, end_ms=2000, text=hanging),
            minimal_manifest_segment("seg_c", start_ms=2000, end_ms=3000, text="Complete payoff."),
        ),
    )
    words = []
    t = 1000
    for tok in hanging.split():
        words.append({"text": tok, "start_ms": t, "end_ms": t + 80, "speaker_id": "spk_0"})
        t += 90
    # The tape does finish the thought a moment later, so the EDL could have
    # reached a legal close and the transition must still be refused.
    for tok in "That would change how we treat patients.".split():
        words.append({"text": tok, "start_ms": t, "end_ms": t + 80, "speaker_id": "spk_0"})
        t += 90
    ctx.write_json("transcript/full.json", {"words": words})
    edl = _good_edl()
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("incomplete thought" in e for e in errors)


def test_transition_after_unrecoverable_trail_off_is_a_warning() -> None:
    """ISSUES entry 59: the tape never completes the thought within reach."""
    ctx = RunContext("run_edl_trail_off_vo", create=True)
    _write_story_artifacts(ctx)
    hanging = "So early prediction of a reoccurrence, if I could do through cell biopsy."
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a", start_ms=0, end_ms=1000, text="Complete setup."),
            minimal_manifest_segment("seg_b", start_ms=1000, end_ms=2000, text=hanging),
            minimal_manifest_segment("seg_c", start_ms=2000, end_ms=3000, text="Complete payoff."),
        ),
    )
    words = []
    t = 1000
    for tok in hanging.split():
        words.append({"text": tok, "start_ms": t, "end_ms": t + 80, "speaker_id": "spk_0"})
        t += 90
    ctx.write_json("transcript/full.json", {"words": words})
    errors = validate_flow1_edl_narrative(ctx, _good_edl())
    assert not any("incomplete thought" in e for e in errors)


def test_unaired_ordering_constraint_is_skipped(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_edl_unaired_constraint", create=True)
    _write_story_artifacts(ctx)
    plan = ctx.read_json("master/narrative_plan.json")
    plan["ordering_constraints"].append(
        {
            "before_segment_id": "seg_a",
            "after_segment_id": "seg_dropped",
            "reason": "stale_mastering_plan",
        }
    )
    ctx.write_json("master/narrative_plan.json", plan)
    errors = validate_flow1_edl_narrative(ctx, _good_edl())
    assert not any("seg_dropped" in e for e in errors)


def test_validate_rejects_transition_then_layup_before_native() -> None:
    ctx = RunContext("run_edl_double_synth", create=True)
    _write_story_artifacts(ctx)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a"),
            minimal_manifest_segment("seg_b"),
            minimal_manifest_segment("seg_c"),
        ),
    )
    edl = _good_edl()
    # Insert a layup immediately after the existing transition, before seg_c.
    clips = list(edl["clips"])
    trans_idx = next(i for i, c in enumerate(clips) if c.get("type") == "transition")
    clips.insert(
        trans_idx + 1,
        {
            "type": "vo_pickup",
            "line_id": "vo_layup_seg_c",
            "targets_segment_id": "seg_c",
            "placement": "before",
            "timeline_start_ms": 2100,
            "duration_ms": 1000,
        },
    )
    edl["clips"] = clips
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("synthetic inserts adjacent" in e for e in errors)


def test_validate_rejects_mixed_voice_speaker_id() -> None:
    ctx = RunContext("run_edl_mixed_voice", create=True)
    _write_story_artifacts(ctx)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a"),
            minimal_manifest_segment("seg_b"),
            minimal_manifest_segment("seg_c"),
        ),
    )
    edl = _good_edl()
    edl["clips"][1]["voice_speaker_id"] = "spk_0"
    for clip in edl["clips"]:
        if clip.get("type") == "transition":
            clip["voice_speaker_id"] = "spk_1"
    errors = validate_flow1_edl_narrative(ctx, edl)
    assert any("mixed voice_speaker_id" in e for e in errors)


def test_apply_episode_vo_identity_fills_missing_layup_voice() -> None:
    from interview_mux.speaker_delivery_plan import apply_episode_vo_identity_to_edl

    ctx = RunContext("run_edl_stamp_voice", create=True)
    ctx.write_json(
        "understanding/speaker_delivery_plan.json",
        {"clone_speaker_id": "spk_1"},
        skip_handoff=True,
    )
    edl = {
        "clips": [
            {
                "type": "vo_pickup",
                "line_id": "vo_layup_seg_010",
                "targets_segment_id": "seg_b",
                "placement": "before",
            },
            {"type": "speech", "segment_id": "seg_b"},
        ]
    }
    apply_episode_vo_identity_to_edl(ctx, edl)
    assert edl["clips"][0]["voice_speaker_id"] == "spk_1"
    assert "voice_speaker_id" not in edl["clips"][1]

