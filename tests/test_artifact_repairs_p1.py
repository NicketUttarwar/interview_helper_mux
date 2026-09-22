from __future__ import annotations

import pytest

from interview_mux.artifact_repairs import (
    reconcile_ordered_vs_excluded,
    repair_coverage_audit,
    repair_edl_audit,
    repair_gap_report,
    repair_master_selection,
    repair_narrative_plan,
)
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def test_reconcile_ordered_vs_excluded_keeps_air_order() -> None:
    out = reconcile_ordered_vs_excluded(
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [
                {"segment_id": "seg_001", "reason": "covered_by_framing_vo"},
                "seg_099",
            ],
        }
    )
    assert out["ordered_segment_ids"] == ["seg_001", "seg_002"]
    assert [x["segment_id"] if isinstance(x, dict) else x for x in out["excluded_segment_ids"]] == [
        "seg_099"
    ]


def test_reconcile_ordered_vs_excluded_editorial_drops_from_air() -> None:
    out = reconcile_ordered_vs_excluded(
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [
                {
                    "segment_id": "seg_001",
                    "reason": "direct_listener_sponsor_promotion; sponsor message",
                },
            ],
            "exclude_rationales": {
                "seg_001": "direct_listener_sponsor_promotion; sponsor message",
            },
        }
    )
    assert out["ordered_segment_ids"] == ["seg_002"]
    assert any(
        (isinstance(x, dict) and x.get("segment_id") == "seg_001")
        for x in out["excluded_segment_ids"]
    )


def test_reconcile_prunes_stale_rationales_on_air_order_ids() -> None:
    from interview_mux.artifact_repairs import prune_stale_exclude_rationales

    out = reconcile_ordered_vs_excluded(
        {
            "ordered_segment_ids": ["seg_005", "seg_006", "seg_008"],
            "excluded_segment_ids": [
                {"segment_id": "seg_001", "reason": "media_ip_cta"},
            ],
            "exclude_rationales": {
                "seg_001": "media_ip_cta",
                "seg_005": "excluded_from_master",
                "seg_006": "excluded_from_master",
                "seg_007": "duplicate: leftover",
            },
        }
    )
    assert out["ordered_segment_ids"] == ["seg_005", "seg_006", "seg_008"]
    assert set(out["exclude_rationales"]) == {"seg_001"}
    assert "seg_005" not in out["exclude_rationales"]
    pruned, notes = prune_stale_exclude_rationales(out)
    assert pruned["exclude_rationales"] == out["exclude_rationales"]
    assert not notes
    out = reconcile_ordered_vs_excluded(
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [
                {
                    "segment_id": "seg_001",
                    "reason": "direct_listener_sponsor_promotion; sponsor message",
                },
            ],
            "exclude_rationales": {
                "seg_001": "direct_listener_sponsor_promotion; sponsor message",
            },
        }
    )
    assert out["ordered_segment_ids"] == ["seg_002"]
    assert any(
        (isinstance(x, dict) and x.get("segment_id") == "seg_001")
        for x in out["excluded_segment_ids"]
    )


def test_normalize_only_prunes_stale_air_order_rationales() -> None:
    """amplify=False must still clear exclude_rationales that contradict air order."""
    from interview_mux.artifact_repairs import repair_master_selection
    from interview_mux.run_context import RunContext

    ctx = RunContext(create=True)
    doc = {
        "ordered_segment_ids": ["seg_002", "seg_010"],
        "excluded_segment_ids": [
            {"segment_id": "seg_099", "reason": "excluded_from_master"},
        ],
        "exclude_rationales": {
            "seg_002": "finale_tail_leftover",
            "seg_010": "finale_tail_leftover",
            "seg_099": "excluded_from_master",
        },
        "chapters": [],
    }
    fixed, notes = repair_master_selection(ctx, doc, amplify=False)
    assert fixed["ordered_segment_ids"] == ["seg_002", "seg_010"]
    assert "seg_002" not in (fixed.get("exclude_rationales") or {})
    assert "seg_010" not in (fixed.get("exclude_rationales") or {})
    assert "seg_099" in (fixed.get("exclude_rationales") or {})
    assert any(n.get("action") == "prune_stale_exclude_rationales" for n in notes)
    assert any(n.get("action") == "normalize_selection_only" for n in notes)


def test_repair_gap_report_drops_orphan_targets(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_gap")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        skip_handoff=True,
    )
    doc = {
        "interviewer_lines": [
            {"line_id": "line_1", "targets_segment_id": "seg_missing", "text": "Why?"},
            {"targets_segment_id": "seg_001", "text": "Follow up"},
        ]
    }
    patched, applied = repair_gap_report(ctx, doc)
    assert len(patched["interviewer_lines"]) == 1
    assert patched["interviewer_lines"][0]["targets_segment_id"] == "seg_001"
    assert applied


def test_repair_narrative_plan_drops_orphan_chapters(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_narr")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        skip_handoff=True,
    )
    doc = {
        "arc_summary": "Test",
        "chapters": [
            {"chapter_id": "ch_1", "title": "A", "segment_ids": ["seg_missing"]},
            {"chapter_id": "ch_2", "title": "B", "segment_ids": ["seg_001"]},
        ],
    }
    patched, applied = repair_narrative_plan(ctx, doc)
    assert len(patched["chapters"]) == 1
    assert patched["chapters"][0]["chapter_id"] == "ch_2"


def test_repair_narrative_plan_infers_segment_ids_from_topic_tags(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_narr_infer")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001"),
            minimal_manifest_segment("seg_012"),
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Test thesis",
            "topics": [
                {
                    "name": "Early product missteps and pivots",
                    "summary": "Regulatory setbacks and failed products.",
                    "segment_ids": ["seg_012"],
                }
            ],
        },
        skip_handoff=True,
    )
    doc = {
        "arc_summary": "Test arc",
        "chapters": [
            {
                "chapter_id": "ch_01",
                "title": "False Starts",
                "topic_tags": ["early_product_missteps_and_pivots"],
                "suggested_open_segment_id": "seg_012",
            }
        ],
        "ordering_constraints": [],
    }
    patched, applied = repair_narrative_plan(ctx, doc)
    assert len(patched["chapters"]) == 1
    assert patched["chapters"][0]["segment_ids"] == ["seg_012"]
    assert any(row.get("action") == "infer_segment_ids" for row in applied)


def test_repair_edl_audit_normalizes_verdict(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_edl")
    patched, applied = repair_edl_audit(ctx, {"verdict": "unknown_status", "issues": []})
    assert patched["verdict"] == "warn"
    assert applied


def test_repair_edl_audit_demotes_premature_vo_nle_placement(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_edl_vo")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_005")),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_005",
                    "targets_segment_id": "seg_005",
                    "severity": "high",
                    "required": True,
                    "delivery": "synthesize",
                    "gap_type": "nugget_layup",
                    "placement": "before",
                    "text": "Stevia roadblock?",
                }
            ]
        },
        skip_handoff=True,
    )
    vo = ctx.final_path("vo_pickup")
    vo.mkdir(parents=True, exist_ok=True)
    (vo / "vo_layup_seg_005.wav").write_bytes(b"RIFF....")
    doc = {
        "verdict": "fail",
        "blocking_issues": [
            {
                "issue": (
                    "Required high-severity setup and continuity lines have no "
                    "evidenced VO-ingest or NLE placement."
                ),
                "evidence": [
                    "gap_report.interviewer_lines[0].line_id=vo_layup_seg_005",
                    "nle_edits={}",
                ],
                "recommended_action": "rerun vo_ingest, then rerun edl",
            }
        ],
        "warnings": [],
    }
    patched, applied = repair_edl_audit(ctx, doc)
    assert patched["verdict"] in ("pass", "warn")
    assert not patched.get("blocking_issues")
    assert any(
        row.get("action") == "demote_premature_vo_nle_placement" for row in applied
    )


def test_repair_edl_audit_demotes_stale_meta_question(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_edl_stale")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "episode_orientation": True,
                    "line_category": "episode_preface",
                    "text": (
                        "In this conversation, an entrepreneur traces how rural "
                        "farming roots led to a healthy-snack business. Let's hear "
                        "how that opening beat lands."
                    ),
                    "delivery": "synthesize",
                    "gap_type": "missing_setup",
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "type": "transition",
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "At university, an unexpected encounter changed that direction.",
                }
            ]
        },
        skip_handoff=True,
    )
    doc = {
        "verdict": "fail",
        "blocking_issues": [
            {
                "issue": (
                    "The required opening-orientation line does not supply the guest "
                    "identity; it is only a meta-question."
                ),
                "evidence": ["gap_report.interviewer_lines[line_id=vo_preface_episode_orientation].text"],
            },
            {
                "issue": "Two different transition lines occupy identical selected-order adjacencies.",
                "evidence": ["transitions.transitions[0] and transitions.transitions[2]"],
            },
        ],
        "warnings": [],
    }
    patched, applied = repair_edl_audit(ctx, doc)
    assert patched["verdict"] in ("pass", "warn")
    assert not patched.get("blocking_issues")
    assert any(row.get("action") == "demote_stale_audit_vs_disk" for row in applied)


def test_repair_edl_audit_demotes_stale_duplicate_vo_transition(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After framing dedupe drops the transition, LLM duplicate-bridge fails demote."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_dup_bridge")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_023", "seg_025", "seg_026"], "chapters": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_025",
                    "text": "What changed when the lab report reached the clinic?",
                    "delivery": "synthesize",
                    "placement": "before",
                    "prior_segment_id": "seg_023",
                    "targets_segment_id": "seg_025",
                    "required": True,
                    "gap_type": "missing_setup",
                }
            ]
        },
        skip_handoff=True,
    )
    # Transition for 023→025 already removed; only an unrelated pair remains.
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "type": "transition",
                    "after_segment_id": "seg_025",
                    "before_segment_id": "seg_026",
                    "text": "From evolving tests to the report clinicians receive.",
                }
            ]
        },
        skip_handoff=True,
    )
    doc = {
        "verdict": "fail",
        "blocking_issues": [
            {
                "issue": (
                    "Two spoken bridges are scheduled for the same selected adjacency: "
                    "the transition after seg_023/before seg_025 and required rendered "
                    "VO vo_layup_seg_025, which is also placed before seg_025 after "
                    "seg_023. This creates duplicate framing at the Chapter 3-to-4 "
                    "handoff."
                ),
                "evidence": [
                    "selection.ordered_segment_ids: seg_023 → seg_025",
                    "transitions.transitions[after_segment_id=seg_023,before_segment_id=seg_025]",
                    "gap_report.interviewer_lines[line_id=vo_layup_seg_025,"
                    "prior_segment_id=seg_023,targets_segment_id=seg_025]",
                    "vo_coverage[line_id=vo_layup_seg_025,coverage=rendered]",
                ],
                "recommended_action": (
                    "rerun transitions and remove or consolidate the seg_023 → "
                    "seg_025 transition; retain the rendered required VO layup."
                ),
            }
        ],
        "warnings": [],
    }
    patched, applied = repair_edl_audit(ctx, doc)
    assert patched["verdict"] in ("pass", "warn")
    assert not patched.get("blocking_issues")
    assert any(row.get("action") == "demote_stale_audit_vs_disk" for row in applied)


def test_repair_coverage_audit_drops_unknown_topics(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_cov")
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "Test thesis", "topics": [{"name": "Origin Story", "summary": "x"}]},
        skip_handoff=True,
    )
    doc = {"missing_coverage": [{"topic": "Unknown Topic", "reason": "gap"}]}
    patched, applied = repair_coverage_audit(ctx, doc)
    # Unknown topics dropped; brief topics may be auto-documented as uncovered.
    assert not any(
        str(row.get("topic") or "") == "Unknown Topic"
        for row in (patched.get("missing_coverage") or [])
        if isinstance(row, dict)
    )
    assert applied
    assert any(
        str(row.get("topic") or "") == "Origin Story"
        for row in (patched.get("missing_coverage") or [])
        if isinstance(row, dict)
    )


def test_repair_coverage_binds_claims_to_selected_air(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_cov_bind")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            {
                **minimal_manifest_segment("seg_010"),
                "text": (
                    "Mohan says ctDNA is the subset of cell-free DNA released "
                    "when tumour cells die, and liquid biopsy must distinguish it."
                ),
            },
            {
                **minimal_manifest_segment("seg_044"),
                "text": (
                    "OncoInsight uses two 10 ml blood tubes for a 1080-gene "
                    "ctDNA panel and CTC capture."
                ),
            },
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_010", "seg_044"], "chapters": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Cell biopsy",
            "topics": [
                {
                    "name": "OncoInsight assay and integrated reporting",
                    "summary": "Assay reporting",
                }
            ],
            "key_claims": [
                {
                    "claim": (
                        "Mohan says ctDNA is the subset of cell-free DNA released "
                        "when tumour cells die."
                    ),
                    "evidence_segment_ids": [],
                }
            ],
        },
        skip_handoff=True,
    )
    patched, applied = repair_coverage_audit(
        ctx,
        {
            "topic_mappings": [
                {
                    "topic": "OncoInsight Assay and Integrated Reporting",
                    "segment_ids": [],
                    "covered": False,
                }
            ],
            "claim_mappings": [
                {
                    "claim": (
                        "Mohan says ctDNA is the subset of cell-free DNA released "
                        "when tumour cells die."
                    ),
                    "segment_ids": [],
                    "covered": False,
                }
            ],
            "missing_coverage": [],
            "coverage_score": 0.0,
        },
    )
    claims = patched.get("claim_mappings") or []
    assert claims and claims[0].get("covered") is True
    assert "seg_010" in (claims[0].get("segment_ids") or [])
    topics = patched.get("topic_mappings") or []
    assert any(
        isinstance(row, dict)
        and row.get("covered")
        and "seg_044" in (row.get("segment_ids") or [])
        for row in topics
    )
    assert patched.get("coverage_score", 0) > 0
    assert any(
        isinstance(row, dict) and row.get("action") == "bind_coverage_to_selection"
        for row in applied
    )


def test_repair_master_selection_sorts_backward_closing_chapter(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_back_jump")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_010", start_ms=10_000, end_ms=20_000),
            minimal_manifest_segment("seg_056", start_ms=100_000, end_ms=110_000),
            minimal_manifest_segment("seg_062", start_ms=200_000, end_ms=210_000),
        ),
        skip_handoff=True,
    )
    patched, applied = repair_master_selection(
        ctx,
        {
            "ordered_segment_ids": ["seg_010", "seg_062", "seg_056"],
            "chapters": [
                {"title": "Open", "segment_ids": ["seg_010"]},
                {
                    "title": "Validation, access and the recurrence-monitoring ambition",
                    "segment_ids": ["seg_062", "seg_056"],
                },
            ],
        },
    )
    assert patched["ordered_segment_ids"] == ["seg_010", "seg_056", "seg_062"]
    assert patched["chapters"][-1]["segment_ids"] == ["seg_056", "seg_062"]
    assert any(
        isinstance(row, dict)
        and row.get("action") == "sort_chapter_air_order_by_source_time"
        for row in applied
    )


def test_repair_master_selection_coerces_null_cut_ms(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_cta_cut")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        skip_handoff=True,
    )
    patched, applied = repair_master_selection(
        ctx,
        {
            "ordered_segment_ids": ["seg_001"],
            "media_ip_cta": [
                {
                    "segment_id": "seg_001",
                    "clearly_media_ip_pitch": True,
                    "cut_ms": None,
                },
                {
                    "segment_id": "seg_001",
                    "clearly_media_ip_pitch": True,
                    "cut_ms": 1200,
                },
            ],
        },
    )
    assert "cut_ms" not in patched["media_ip_cta"][0]
    assert patched["media_ip_cta"][1]["cut_ms"] == [1200]
    assert any(row.get("path") == "media_ip_cta.cut_ms" for row in applied)


def test_repair_gap_report_coerces_null_nugget_ids_and_gap_type(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_gap_nulls")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        skip_handoff=True,
    )
    patched, applied = repair_gap_report(
        ctx,
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "text": (
                        "Bootstrapped growth to thirty crore set the bar before outside capital."
                    ),
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "origin": "nugget_layup",
                    "nugget_ids": None,
                    "recovery_of_talking_point_ids": None,
                }
            ]
        },
    )
    line = patched["interviewer_lines"][0]
    assert line["nugget_ids"] == []
    assert line["recovery_of_talking_point_ids"] == []
    assert line["gap_type"] == "nugget_layup"
    assert any(row.get("action") == "null_to_empty_array" for row in applied)
    assert any(row.get("action") == "default_gap_type" for row in applied)


def test_repair_gap_report_coerces_null_line_category_origin_and_oo(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_gap_cat_nulls")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        skip_handoff=True,
    )
    patched, applied = repair_gap_report(
        ctx,
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "gap_type": "missing_setup",
                    "text": (
                        "Bootstrapped growth to thirty crore set the bar before outside capital."
                    ),
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "line_category": None,
                    "origin": None,
                }
            ],
            "opening_orientation": {
                "sequence": None,
                "target_segment_id": None,
                "omit_reason": None,
                "required": None,
                "omitted": None,
            },
        },
    )
    line = patched["interviewer_lines"][0]
    assert isinstance(line["line_category"], str) and line["line_category"]
    assert line["origin"] == ""
    oo = patched["opening_orientation"]
    assert oo["sequence"] == ""
    assert oo["target_segment_id"] == ""
    assert oo["omit_reason"] == ""
    assert oo["required"] is False
    assert oo["omitted"] is False
    assert any(row.get("action") == "default_line_category" for row in applied)


def test_repair_gap_evaluations_coerces_explicit_null_leaves(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.artifact_repairs import repair_gap_evaluations

    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_eval_nulls")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        skip_handoff=True,
    )
    patched, applied = repair_gap_evaluations(
        ctx,
        {
            "evaluations": [
                {
                    "segment_id": "seg_001",
                    "self_explanatory": None,
                    "gap_type": "missing_setup",
                    "severity": "high",
                    "listener_confusion": None,
                    "recommended_framing": None,
                    "duplicate_claim_cluster": None,
                    "candidate_for_summary": None,
                }
            ]
        },
    )
    row = patched["evaluations"][0]
    assert row["listener_confusion"] == ""
    assert row["recommended_framing"] == "none"
    assert row["duplicate_claim_cluster"] == ""
    assert row["self_explanatory"] is True
    assert row["candidate_for_summary"] is False
    assert any(row.get("action") == "null_to_empty_string" for row in applied)


def test_repair_gap_report_restamps_air_contract_omits(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EDL courtesy repair must not leave omitted seats without skip flags."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_gap_restamp_omit")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_022",
                text="What if I found a CTC and the doctor is saying so what?",
            ),
            minimal_manifest_segment(
                "seg_026",
                text="Traditional circulating tumor cell CTC enumeration alone.",
            ),
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_008"],
                    "omitted_line_ids": ["vo_layup_seg_022", "vo_layup_seg_026"],
                }
            }
        },
        skip_handoff=True,
    )
    patched, applied = repair_gap_report(
        ctx,
        {
            "nugget_layup_authority": True,
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_008",
                    "text": "Hosted layup still on air with a forward cue into the next beat.",
                    "targets_segment_id": "seg_022",
                    "placement": "before",
                    "delivery": "synthesize",
                    "origin": "nugget_layup",
                    "gap_type": "nugget_layup",
                },
                {
                    "line_id": "vo_layup_seg_022",
                    "text": "Before sequencing, captured tumour cells can be assessed carefully.",
                    "targets_segment_id": "seg_022",
                    "placement": "before",
                    "delivery": "synthesize",
                    "origin": "nugget_layup",
                    "gap_type": "nugget_layup",
                    "required": True,
                },
                {
                    "line_id": "vo_layup_seg_026",
                    "text": "Circulating tumour cells can also travel in clusters sometimes.",
                    "targets_segment_id": "seg_026",
                    "placement": "before",
                    "delivery": "synthesize",
                    "origin": "nugget_layup",
                    "gap_type": "nugget_layup",
                },
            ],
        },
    )
    by_id = {
        str(r.get("line_id")): r
        for r in (patched.get("interviewer_lines") or [])
        if isinstance(r, dict)
    }
    assert by_id["vo_layup_seg_022"].get("skipped_optional") is True
    assert by_id["vo_layup_seg_022"].get("air_script_omit") is True
    assert by_id["vo_layup_seg_026"].get("skipped_optional") is True
    assert by_id["vo_layup_seg_026"].get("air_script_omit") is True
    assert any(a.get("action") == "restamp_air_contract_omit" for a in applied)


def test_seated_vo_missing_skips_plan_omitted_even_without_gap_flags(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.vo_contract import seated_vo_missing_ids

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "vo_omit_no_wav")
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_ok"],
                    "omitted_line_ids": ["vo_omit"],
                }
            }
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_ok",
                    "text": "On air line with enough words for synthesis.",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "required": True,
                },
                {
                    "line_id": "vo_omit",
                    "text": "Should not demand a WAV when plan-omitted.",
                    "targets_segment_id": "seg_002",
                    "placement": "before",
                    "delivery": "synthesize",
                    "required": True,
                },
            ]
        },
        skip_handoff=True,
    )
    missing = seated_vo_missing_ids(ctx)
    assert "vo_omit" not in missing


def test_repair_edl_audit_defaults_evidence_and_recommended_action(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_edl_nulls")
    patched, applied = repair_edl_audit(
        ctx,
        {
            "verdict": "warn",
            "blocking_issues": [{"issue": "something off", "evidence": None}],
            "warnings": [{"issue": "soft note"}],
        },
    )
    assert patched["blocking_issues"][0]["evidence"] == []
    assert patched["blocking_issues"][0]["recommended_action"] == "review"
    assert patched["warnings"][0]["evidence"] == []
    assert patched["warnings"][0]["recommended_action"] == "review"
    assert any(row.get("path") == "evidence" for row in applied)
    assert any(row.get("path") == "recommended_action" for row in applied)


def test_repair_master_selection_keeps_stringified_exclude_objects(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_exclude_str")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001"),
            minimal_manifest_segment("seg_cta"),
        ),
        skip_handoff=True,
    )
    patched, _applied = repair_master_selection(
        ctx,
        {
            "ordered_segment_ids": ["seg_001"],
            "excluded_segment_ids": [
                "{'segment_id': 'seg_cta', 'reason': 'media_ip_cta'}",
            ],
        },
    )
    rows = patched.get("excluded_segment_ids") or []
    assert any(
        isinstance(r, dict) and r.get("segment_id") == "seg_cta" for r in rows
    )


def test_repair_master_selection_prunes_stale_air_order_rationales(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "p1_prune_rat")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_005",
                text="We spent years on the trial design and the endpoints that actually mattered.",
            ),
            minimal_manifest_segment(
                "seg_006",
                text="The later readout changed how we think about treating late-stage disease.",
            ),
            minimal_manifest_segment(
                "seg_cta",
                text="Please subscribe to the show and buy the course this week.",
            ),
        ),
        skip_handoff=True,
    )
    patched, applied = repair_master_selection(
        ctx,
        {
            "ordered_segment_ids": ["seg_005", "seg_006"],
            "excluded_segment_ids": [{"segment_id": "seg_cta", "reason": "media_ip_cta"}],
            "exclude_rationales": {
                "seg_cta": "media_ip_cta",
                "seg_005": "excluded_from_master",
                "seg_006": "excluded_from_master",
            },
        },
    )
    assert "seg_005" in patched["ordered_segment_ids"]
    assert "seg_005" not in patched["exclude_rationales"]
    assert "seg_006" not in patched["exclude_rationales"]
    assert patched["exclude_rationales"].get("seg_cta") == "media_ip_cta"
    assert any(
        row.get("action") in {"prune_stale_exclude_rationales", "reconcile_ordered_vs_excluded"}
        for row in applied
    )