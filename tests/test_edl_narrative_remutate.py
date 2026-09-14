"""Typed edl_narrative_audit remutate classifier + plan."""

from __future__ import annotations

from interview_mux.edl_narrative_remutate import (
    REMUTATE_REL,
    classify_edl_narrative_audit,
    classify_edl_narrative_issue,
    plan_edl_narrative_remutate,
)
from run_fixtures import isolated_run_ctx


def test_classify_issue_needles() -> None:
    assert classify_edl_narrative_issue("please rerank selection order") == "rerank"
    assert classify_edl_narrative_issue("missing spoken bridge hinge") == "transitions"
    assert classify_edl_narrative_issue("gap VO orphan on timeline") == "rebase_gap_vo"
    assert classify_edl_narrative_issue("blank segment near-silence") == "drop_blank"
    assert classify_edl_narrative_issue("something novel") == "operator"
    assert (
        classify_edl_narrative_issue(
            "The required opening-orientation line is only a meta-question."
        )
        == "rebase_gap_vo"
    )
    assert (
        classify_edl_narrative_issue(
            "high-severity layup has no rendered VO asset or transition coverage"
        )
        == "rebase_gap_vo"
    )
    assert (
        classify_edl_narrative_issue(
            "The selected timeline defines nine chapters, exceeding the "
            "authoritative maximum of eight, and splits one continuous "
            "narrative-plan body chapter into an unsupported duplicate chapter title."
        )
        == "rerank"
    )
    # Plan/chapter mismatch must classify as align_plan even when "transition" appears.
    assert (
        classify_edl_narrative_issue(
            "The selected chapter sequence reverses the narrative plan's "
            "practical-payoff and adoption-hurdle progression; revise chapter "
            "transitions and align narrative_plan to the selected air order."
        )
        == "align_plan"
    )


def test_plan_sticky_exhausted_does_not_climb(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_narr_sticky")
    audit = {
        "verdict": "fail",
        "blocking_issues": [{"issue": "selection order broken — rerank"}],
    }
    for _ in range(3):
        plan_edl_narrative_remutate(ctx, audit)
    stuck = plan_edl_narrative_remutate(ctx, audit)
    assert stuck["exhausted"] is True
    assert stuck["attempt"] == 3
    again = plan_edl_narrative_remutate(ctx, audit)
    assert again["attempt"] == 3
    assert again["exhausted"] is True


def test_metadata_align_under_seat_freeze(tmp_path, monkeypatch) -> None:
    import json

    from interview_mux.edl_narrative_remutate import apply_edl_narrative_host_repair

    ctx = isolated_run_ctx(tmp_path, "exec_narr_meta_freeze")
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active", lambda _ctx: True
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.request_seat_rewrite",
        lambda *_a, **_k: {"allow": False, "refuse_reason": "opportunity_below_threshold"},
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_034", "seg_030", "seg_033", "seg_035", "seg_036"],
            "chapters": [
                {"title": "Mechanism", "segment_ids": ["seg_034"]},
                {"title": "Adoption", "segment_ids": ["seg_030", "seg_033", "seg_035"]},
                {"title": "Trials", "segment_ids": ["seg_036"]},
            ],
            "excluded_segment_ids": [],
        },
        skip_handoff=True,
    )
    plan_path = ctx.path("master", "narrative_plan.json")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(
            {
                "arc_summary": "Test plan vs selection mismatch.",
                "chapters": [
                    {
                        "chapter_id": "ch_04",
                        "title": "Mechanism",
                        "suggested_open_segment_id": "seg_034",
                        "segment_ids": ["seg_034", "seg_035"],
                    },
                    {
                        "chapter_id": "ch_05",
                        "title": "Trials",
                        "suggested_open_segment_id": "seg_036",
                        "segment_ids": ["seg_036"],
                    },
                    {
                        "chapter_id": "ch_06",
                        "title": "Adoption",
                        "suggested_open_segment_id": "seg_030",
                        "segment_ids": ["seg_030", "seg_033"],
                    },
                ],
                "ordering_constraints": [],
            }
        ),
        encoding="utf-8",
    )
    applied = apply_edl_narrative_host_repair(ctx)
    assert "seat_freeze_blocked_host_repair" in applied["notes"]
    # Selection chapter repair (and nested plan align) runs under freeze.
    assert "align_selection_chapters" in applied["notes"] or "align_narrative_plan" in applied["notes"]
    assert applied.get("host_fixed") is True
    plan = ctx.read_json("master/narrative_plan.json")
    ch_ids = [
        tuple(ch.get("segment_ids") or [])
        for ch in (plan.get("chapters") or [])
        if isinstance(ch, dict)
    ]
    assert any("seg_035" in ids for ids in ch_ids)


def test_remutate_align_plan_skips_timeline_reopen(tmp_path, monkeypatch) -> None:
    import json

    from interview_mux.edl_narrative_remutate import apply_edl_narrative_remutate

    ctx = isolated_run_ctx(tmp_path, "exec_narr_align_plan")
    monkeypatch.setattr(
        "interview_mux.timeline_reopen_meta_gate.decide_timeline_reopen",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not reopen")),
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active", lambda _ctx: True
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.request_seat_rewrite",
        lambda *_a, **_k: {"allow": False},
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "chapters": [{"title": "A", "segment_ids": ["seg_001", "seg_002"]}],
            "excluded_segment_ids": [],
        },
        skip_handoff=True,
    )
    plan_path = ctx.path("master", "narrative_plan.json")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(
            {
                "arc_summary": "Plan with orphan segment.",
                "chapters": [
                    {
                        "chapter_id": "ch1",
                        "title": "A",
                        "suggested_open_segment_id": "seg_001",
                        "segment_ids": ["seg_001"],
                    },
                    {
                        "chapter_id": "ch2",
                        "title": "B",
                        "suggested_open_segment_id": "seg_002",
                        "segment_ids": ["seg_002", "seg_099"],
                    },
                ],
                "ordering_constraints": [],
            }
        ),
        encoding="utf-8",
    )
    out = apply_edl_narrative_remutate(
        ctx, {"actions": ["align_plan"], "from_stages": ["edl_narrative_audit"], "exhausted": False}
    )
    assert out.get("ok") is True
    assert out.get("from_stage") == "edl_narrative_audit"
    notes = out.get("notes") or []
    assert "align_plan_metadata_only" in notes
    assert "align_selection_chapters" in notes or "align_narrative_plan" in notes
    plan = ctx.read_json("master/narrative_plan.json")
    all_ids = {
        str(s)
        for ch in (plan.get("chapters") or [])
        if isinstance(ch, dict)
        for s in (ch.get("segment_ids") or [])
    }
    assert "seg_099" not in all_ids


def test_narrative_audit_blocks_edl(tmp_path) -> None:
    import json

    from interview_mux.edl_narrative_remutate import (
        narrative_audit_blocks_edl,
        resume_after_narrative_audit_fail,
    )

    ctx = isolated_run_ctx(tmp_path, "exec_narr_block_edl")
    assert narrative_audit_blocks_edl(ctx) is False
    audit_path = ctx.path("master", "edl_narrative_audit.json")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "verdict": "fail",
                "blocking_issues": [{"issue": "x"}],
            }
        ),
        encoding="utf-8",
    )
    assert narrative_audit_blocks_edl(ctx) is True
    assert resume_after_narrative_audit_fail("edl") == "edl_narrative_audit"
    assert resume_after_narrative_audit_fail("transitions") == "transitions"


def test_repair_master_selection_merges_duplicate_titles_and_clamps(tmp_path) -> None:
    from interview_mux.artifact_repairs import repair_master_selection

    ctx = isolated_run_ctx(tmp_path, "ch_cap")
    ctx.write_json(
        "understanding/delivery_brief.json",
        {
            "version": 1,
            "source_duration_ms": 60_000,
            "target_duration_sec": {"min": 30, "ideal": 45, "max": 60},
            "question_budget": {"min": 0, "ideal": 1, "max": 2},
            "chapter_budget": {"min": 1, "ideal": 4, "max": 8},
            "selection_mode": "coverage_first",
            "sfx_density": {"max_beds": 1, "max_punctuators": 1, "max_foley": 0},
            "ranking_weights": {},
            "rationale": ["fixture"],
            "operator_overrides": {},
            "generated": {"at": "1970-01-01T00:00:00+00:00", "by": "test_fixture"},
        },
        skip_handoff=True,
    )
    # 9 chapters with a duplicate title — same shape as exec_4741.
    ordered = [f"seg_{i:03d}" for i in range(1, 10)]
    chapters = [
        {"title": "A", "segment_ids": ["seg_001"]},
        {"title": "The Needle in the Haystack", "segment_ids": ["seg_002"]},
        {"title": "C", "segment_ids": ["seg_003"]},
        {"title": "D", "segment_ids": ["seg_004"]},
        {"title": "The Needle in the Haystack", "segment_ids": ["seg_005", "seg_006"]},
        {"title": "F", "segment_ids": ["seg_007"]},
        {"title": "G", "segment_ids": ["seg_008"]},
        {"title": "H", "segment_ids": ["seg_009"]},
        {"title": "I", "segment_ids": ["seg_009"]},  # will share — still 9 rows
    ]
    # Make I unique so we have 9 nonempty chapters before merge.
    chapters[-1] = {"title": "I", "segment_ids": ["seg_009"]}
    chapters[7] = {"title": "H", "segment_ids": ["seg_008"]}
    # Need distinct segs for H vs I — expand to 10 segs with 9 chapters
    ordered = [f"seg_{i:03d}" for i in range(1, 11)]
    chapters = [
        {"title": "A", "segment_ids": ["seg_001"]},
        {"title": "The Needle in the Haystack", "segment_ids": ["seg_002"]},
        {"title": "C", "segment_ids": ["seg_003"]},
        {"title": "D", "segment_ids": ["seg_004"]},
        {"title": "The Needle in the Haystack", "segment_ids": ["seg_005", "seg_006"]},
        {"title": "F", "segment_ids": ["seg_007"]},
        {"title": "G", "segment_ids": ["seg_008"]},
        {"title": "H", "segment_ids": ["seg_009"]},
        {"title": "I", "segment_ids": ["seg_010"]},
    ]
    selection = {
        "ordered_segment_ids": ordered,
        "chapters": chapters,
        "excluded_segment_ids": [],
    }
    repaired, actions = repair_master_selection(ctx, selection)
    titles = [str(c.get("title") or "") for c in (repaired.get("chapters") or [])]
    assert titles.count("The Needle in the Haystack") == 1
    assert len(repaired.get("chapters") or []) <= 8
    action_names = {a.get("action") for a in actions if isinstance(a, dict)}
    assert "merge_duplicate_chapter_titles" in action_names


def test_classify_audit_unique_actions() -> None:
    audit = {
        "verdict": "fail",
        "blocking_issues": [
            {"issue": "reorder leftover after finale", "recommended_action": "rerank"},
            {"issue": "missing transition bridge"},
        ],
    }
    assert classify_edl_narrative_audit(audit) == ["rerank", "transitions"]


def test_plan_increments_and_exhausts(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_narr_remutate")
    audit = {
        "verdict": "fail",
        "blocking_issues": [{"issue": "selection order broken — rerank"}],
    }
    p1 = plan_edl_narrative_remutate(ctx, audit)
    assert p1["attempt"] == 1
    assert "rerank" in p1["actions"]
    assert p1["from_stage"] == "full_master_ranking"
    assert not p1["exhausted"]
    assert ctx.artifact_exists(REMUTATE_REL)

    p2 = plan_edl_narrative_remutate(ctx, audit)
    assert p2["attempt"] == 2
    p3 = plan_edl_narrative_remutate(ctx, audit)
    assert p3["attempt"] == 3
    assert p3["exhausted"] is True


def test_host_repair_rewrites_orientation_and_dedupes_transitions(tmp_path, monkeypatch) -> None:
    import json

    from interview_mux.edl_narrative_remutate import apply_edl_narrative_host_repair
    from interview_mux.opening_orientation import orientation_copy_unusable

    ctx = isolated_run_ctx(tmp_path, "exec_narr_host_repair")
    monkeypatch.setattr(
        "interview_mux.transition_vo.resync_spoken_transitions",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.transition_vo.synthesize_spoken_transitions",
        lambda *_a, **_k: [],
    )
    brief = ctx.path("understanding", "content_brief.json")
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(
        json.dumps(
            {
                "thesis": (
                    "An entrepreneur traces how rural farming roots led to a "
                    "healthy-snack business now seeking scale through Zydus Wellness."
                )
            }
        ),
        encoding="utf-8",
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001", "seg_002"]})
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "opening_orientation": {
                "line_id": "vo_preface_episode_orientation",
                "required": True,
                "target_segment_id": "seg_001",
            },
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "gap_type": "missing_setup",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "text": "What should we listen for as that opens?",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "orientation_missions": [
                        "guest_identity",
                        "conversation_topic",
                        "listener_stakes",
                    ],
                }
            ],
        },
    )
    # Keep both adjacent rows so remutate (not write-time sanitize) performs dedupe.
    ctx._one_writer_raw = True
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "type": "transition",
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "What did that first encounter change?",
                },
                {
                    "type": "transition",
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "At university, an unexpected encounter changed that direction.",
                },
            ]
        },
    )
    audit_path = ctx.path("master", "edl_narrative_audit.json")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "verdict": "fail",
                "blocking_issues": [
                    {"issue": "The required opening-orientation line is only a meta-question."}
                ],
            }
        ),
        encoding="utf-8",
    )
    applied = apply_edl_narrative_host_repair(ctx)
    assert "rewrite_episode_orientation_meta_question" in applied["notes"]
    assert "dedupe_transitions_by_adjacency" in applied["notes"]
    assert "discard_stale_layup_pending" not in applied["notes"]
    assert "drop_stale_fail_audit" in applied["notes"]
    assert not audit_path.is_file()
    gap = ctx.read_json("understanding/gap_report.json")
    line = gap["interviewer_lines"][0]
    assert orientation_copy_unusable(line["text"]) is False
    tr = ctx.read_json("master/transitions.json")
    assert len(tr["transitions"]) == 1
    assert not str(tr["transitions"][0]["text"]).endswith("?")


def test_host_repair_seeds_seated_but_missing_layup(tmp_path) -> None:
    import json

    from interview_mux.edl_narrative_remutate import apply_edl_narrative_host_repair

    ctx = isolated_run_ctx(tmp_path, "exec_narr_seated_layup")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_035", "seg_036"]})
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []}, skip_handoff=True)
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_036",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "missing_setup",
                    "listener_confusion": "how a live cell is actually used",
                    "recommended_framing": "question",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json("master/transitions.json", {"transitions": []}, skip_handoff=True)
    audit_path = ctx.path("master", "edl_narrative_audit.json")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "verdict": "fail",
                "blocking_issues": [
                    {
                        "issue": (
                            "The high-severity actionable-single-cell layup for seg_036 "
                            "is seated but missing, and no transition covers the actual "
                            "selected adjacency from seg_035 to seg_036."
                        )
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    applied = apply_edl_narrative_host_repair(ctx)
    assert "seed_missing_seated_layup" in applied["notes"]
    assert "ensure_adjacency_transition" in applied["notes"]
    assert applied["from_stage"] == "sound_design_vo_finalize"
    gap = ctx.read_json("understanding/gap_report.json")
    targets = [
        str(ln.get("targets_segment_id"))
        for ln in (gap.get("interviewer_lines") or [])
        if isinstance(ln, dict)
    ]
    assert "seg_036" in targets
    tr = ctx.read_json("master/transitions.json")
    pairs = {
        (r.get("after_segment_id"), r.get("before_segment_id"))
        for r in (tr.get("transitions") or [])
        if isinstance(r, dict)
    }
    assert ("seg_035", "seg_036") in pairs
    hinge = next(
        str(r.get("text") or "")
        for r in (tr.get("transitions") or [])
        if isinstance(r, dict)
        and r.get("after_segment_id") == "seg_035"
        and r.get("before_segment_id") == "seg_036"
    )
    assert "next beat" not in hinge.lower()


def test_compact_vo_coverage_marks_omitted_and_rendered(tmp_path) -> None:
    import json

    from interview_mux.mastering_plan_loader import forced_sparse_plan, write_plan
    from interview_mux.stages.edl_narrative_audit import compact_vo_coverage

    ctx = isolated_run_ctx(tmp_path, "exec_vo_cov")
    write_plan(ctx, forced_sparse_plan(reason="vo_cov"))
    plan = ctx.read_json("mastering/mastering_plan.json")
    plan["air_script"] = {
        "version": 1,
        "pass": "pass_b",
        "beats": [],
        "vo_seats": {
            "seated_line_ids": ["vo_preface_episode_orientation"],
            "omitted_line_ids": ["vo_layup_seg_016"],
            "orientation_id": "vo_preface_episode_orientation",
        },
    }
    write_plan(ctx, plan)
    gap_path = ctx.path("understanding", "gap_report.json")
    gap_path.parent.mkdir(parents=True, exist_ok=True)
    gap_path.write_text(
        json.dumps(
            {
                "interviewer_lines": [
                    {
                        "line_id": "vo_preface_episode_orientation",
                        "text": "In this conversation, an entrepreneur traces a path to scale.",
                        "required": True,
                    },
                    {
                        "line_id": "vo_layup_seg_016",
                        "text": "The Zydus transaction closed yesterday.",
                        "required": True,
                        "severity": "high",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    pickup = ctx.final_path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)
    (pickup / "vo_preface_episode_orientation.wav").write_bytes(b"RIFF")
    rows = {r["line_id"]: r for r in compact_vo_coverage(ctx)}
    assert rows["vo_layup_seg_016"]["coverage"] == "omitted"
    assert rows["vo_preface_episode_orientation"]["coverage"] in {"rendered", "wav_stale", "missing"}
