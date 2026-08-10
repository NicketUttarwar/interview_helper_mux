"""Unit tests for the Nugget Layup System (no live LLM)."""

from __future__ import annotations

from interview_mux.nugget_layup import (
    CORPUS_REL,
    GAP_REL,
    PLAN_REL,
    build_corpus_mine_input,
    build_layup_compose_input,
    evaluate_layup_qc,
    gap_has_layup_before,
    layup_line_from_row,
    nugget_layup_cfg,
    publish_layup_plan_to_gap_report,
)
from interview_mux.prompt_validation import (
    STAGE_ARTIFACT_DISK_PATHS,
    STAGE_ARTIFACT_SCHEMAS,
    validate_nugget_corpus,
    validate_nugget_layup_plan,
)
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ALL_LLM_STAGES, DELIVERY_ORDER


def test_delivery_order_places_layup_after_ranking():
    assert "nugget_corpus_mine" in DELIVERY_ORDER
    assert "nugget_layup_compose" in DELIVERY_ORDER
    assert DELIVERY_ORDER.index("nugget_corpus_mine") > DELIVERY_ORDER.index("full_master_ranking")
    assert DELIVERY_ORDER.index("nugget_layup_compose") > DELIVERY_ORDER.index("nugget_corpus_mine")
    assert "nugget_corpus_mine" in ALL_LLM_STAGES
    assert "nugget_layup_compose" in ALL_LLM_STAGES


def test_schemas_registered():
    assert STAGE_ARTIFACT_SCHEMAS["nugget_corpus_mine"] == "nugget_corpus_artifact.schema.json"
    assert STAGE_ARTIFACT_SCHEMAS["nugget_layup_compose"] == "nugget_layup_plan_artifact.schema.json"
    assert STAGE_ARTIFACT_DISK_PATHS["nugget_corpus_mine"] == CORPUS_REL
    assert STAGE_ARTIFACT_DISK_PATHS["nugget_layup_compose"] == PLAN_REL


def test_validate_corpus_and_plan_schemas():
    corpus = {
        "nuggets": [
            {
                "nugget_id": "nug_001",
                "text_claim": "Snack insight",
                "evidence_quote": "as a snack",
                "in_selection": False,
                "salience": "high",
            }
        ]
    }
    assert validate_nugget_corpus(corpus) == []
    plan = {
        "ordered_segment_ids": ["seg_011"],
        "layups": [
            {
                "target_segment_id": "seg_011",
                "text": "Before the exit, the snack pivot rewrote the market. What changed?",
                "nugget_ids": ["nug_001"],
                "forward_cue_ok": True,
                "skip": False,
            }
        ],
    }
    assert validate_nugget_layup_plan(plan) == []


def test_build_inputs_mark_excluded():
    ctx = RunContext("exec_nugget_layup_inputs", create=True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_011"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_002",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Customers used it as a snack not a supplement.",
                    "start_ms": 0,
                    "end_ms": 5000,
                },
                {
                    "segment_id": "seg_011",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "A 30 crore company became 150.",
                    "start_ms": 8000,
                    "end_ms": 12000,
                },
            ]
        },
    )
    ctx.write_json(
        "understanding/talking_points.json",
        {
            "strategy_summary": "Founder journey",
            "through_line": "Growth to exit",
            "talking_points": [
                {
                    "talking_point_id": "tp_002",
                    "title": "Snack pivot",
                    "importance": "must_keep",
                    "why_it_matters": "Expanded the market",
                    "evidence_quotes": ["as a snack"],
                }
            ],
            "hard_excludes": [],
            "warnings": [],
        },
    )
    packet = build_corpus_mine_input(ctx)
    by_id = {r["segment_id"]: r for r in packet["segments"]}
    assert by_id["seg_002"]["in_selection"] is False
    assert by_id["seg_011"]["in_selection"] is True
    assert packet["ordered_segment_ids"] == ["seg_011"]

    ctx.write_json(CORPUS_REL, {"nuggets": []})
    layup_in = build_layup_compose_input(ctx)
    assert layup_in["natives"][0]["segment_id"] == "seg_011"
    assert "30" in layup_in["natives"][0]["text"]


def test_publish_layup_to_gap_report():
    ctx = RunContext("exec_nugget_layup_publish", create=True)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_011", "seg_028"]})
    ctx.write_json(
        GAP_REL,
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "gap_type": "missing_setup",
                    "line_category": "episode_preface",
                    "text": "In this conversation we follow the founder journey.",
                    "targets_segment_id": "seg_011",
                    "placement": "before",
                    "delivery": "synthesize",
                    "episode_orientation": True,
                }
            ]
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_011", "seg_028"],
        "layups": [
            {
                "target_segment_id": "seg_011",
                "line_id": "vo_layup_seg_011",
                "text": "Recall the snack pivot that expanded the market. How did scale change the stakes?",
                "nugget_ids": ["nug_001"],
                "talking_point_ids": ["tp_002"],
                "why_relevant_to_target": "Recovered pivot",
                "forward_cue_ok": True,
                "skip": False,
            },
            {
                "target_segment_id": "seg_028",
                "line_id": "vo_layup_seg_028",
                "text": "Earlier ESOP breadth made employee wealth part of the deal. What did Zydus protect?",
                "nugget_ids": ["nug_esop"],
                "forward_cue_ok": True,
                "skip": False,
            },
        ],
        "discharged_talking_point_ids": ["tp_002"],
        "open_talking_point_ids": [],
        "discharged_nugget_ids": ["nug_001", "nug_esop"],
        "open_high_salience_nugget_ids": [],
    }
    ctx.write_json(PLAN_REL, plan)
    report = publish_layup_plan_to_gap_report(ctx, plan)
    lines = report.get("interviewer_lines") or []
    assert any(ln.get("episode_orientation") for ln in lines)
    layups = [ln for ln in lines if ln.get("origin") == "nugget_layup"]
    assert len(layups) == 2
    assert gap_has_layup_before(report, "seg_011")
    assert gap_has_layup_before(report, "seg_028")
    assert report.get("nugget_layup_authority") is True


def test_qc_flags_open_must_keep():
    ctx = RunContext("exec_nugget_layup_qc", create=True)
    ctx.write_json(
        "understanding/talking_points.json",
        {
            "strategy_summary": "Founder journey",
            "through_line": "Growth",
            "talking_points": [
                {
                    "talking_point_id": "tp_001",
                    "title": "Bootstrap",
                    "importance": "must_keep",
                    "why_it_matters": "Origin",
                    "evidence_quotes": ["bootstrapped"],
                },
                {
                    "talking_point_id": "tp_002",
                    "title": "Snack",
                    "importance": "must_keep",
                    "why_it_matters": "Pivot",
                    "evidence_quotes": ["snack"],
                },
            ],
            "hard_excludes": [],
            "warnings": [],
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_011"],
        "layups": [
            {
                "target_segment_id": "seg_011",
                "text": "What happened when Rabo wanted out?",
                "nugget_ids": [],
                "talking_point_ids": [],
                "skip": False,
                "forward_cue_ok": True,
            }
        ],
        "discharged_talking_point_ids": [],
        "open_talking_point_ids": [],
        "discharged_nugget_ids": [],
        "open_high_salience_nugget_ids": [],
    }
    corpus = {
        "nuggets": [
            {
                "nugget_id": "nug_x",
                "text_claim": "x",
                "evidence_quote": "x",
                "in_selection": False,
                "salience": "high",
                "already_aired_in_selection": False,
            }
        ]
    }
    qc = evaluate_layup_qc(ctx, plan, corpus)
    assert qc["ok"] is False
    assert "tp_001" in qc["open_must_keep_talking_point_ids"]
    assert "nug_x" in qc["open_high_salience_nugget_ids"]


def test_qc_ignores_should_keep_and_discharged_open_ids():
    ctx = RunContext("exec_nugget_layup_qc_ledger", create=True)
    ctx.write_json(
        "understanding/talking_points.json",
        {
            "strategy_summary": "Founder journey",
            "through_line": "Growth",
            "talking_points": [
                {
                    "talking_point_id": "tp_001",
                    "title": "Bootstrap",
                    "importance": "must_keep",
                    "why_it_matters": "Origin",
                    "evidence_quotes": ["bootstrapped"],
                },
                {
                    "talking_point_id": "tp_007",
                    "title": "Next chapter",
                    "importance": "should_keep",
                    "why_it_matters": "Nice to have",
                    "evidence_quotes": ["next"],
                },
            ],
            "hard_excludes": [],
            "warnings": [],
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_011"],
        "layups": [
            {
                "target_segment_id": "seg_011",
                "text": "What happened when the snack pivot landed?",
                "nugget_ids": [],
                "talking_point_ids": ["tp_001"],
                "skip": False,
                "forward_cue_ok": True,
            }
        ],
        # LLM noise: should_keep open + must_keep listed as both open and discharged.
        "discharged_talking_point_ids": ["tp_001"],
        "open_talking_point_ids": ["tp_007", "tp_001"],
        "discharged_nugget_ids": [],
        "open_high_salience_nugget_ids": [],
    }
    qc = evaluate_layup_qc(ctx, plan, {"nuggets": []})
    assert qc["ok"] is True
    assert qc["open_must_keep_talking_point_ids"] == []


def test_layup_line_skips():
    assert layup_line_from_row({"target_segment_id": "seg_1", "skip": True}) is None
    assert layup_line_from_row({"target_segment_id": "seg_1", "text": ""}) is None
    line = layup_line_from_row(
        {
            "target_segment_id": "seg_1",
            "text": "Setup for the next beat.",
            "nugget_ids": ["n1"],
            "talking_point_ids": ["tp1"],
        }
    )
    assert line is not None
    assert line["placement"] == "before"
    assert line["delivery"] == "synthesize"
    assert line["origin"] == "nugget_layup"


def test_cfg_defaults():
    cfg = nugget_layup_cfg({})
    assert cfg["enabled"] is True
    assert cfg["min_layup_coverage"] == 0.9
    assert cfg["authoritative_gap_report"] is True


def test_exec_1579_shaped_recovery_mapping():
    """Fixture shaped like exec_1579: excluded early facts assigned before later natives."""
    ctx = RunContext("exec_nugget_layup_1579", create=True)
    ctx.write_json(
        "understanding/talking_points.json",
        {
            "strategy_summary": "Founder journey",
            "through_line": "Growth to exit",
            "talking_points": [
                {
                    "talking_point_id": "tp_001",
                    "title": "Bootstrap",
                    "importance": "must_keep",
                    "why_it_matters": "Origin",
                    "evidence_quotes": ["30 crore"],
                },
                {
                    "talking_point_id": "tp_002",
                    "title": "Snack",
                    "importance": "must_keep",
                    "why_it_matters": "Pivot",
                    "evidence_quotes": ["snack"],
                },
                {
                    "talking_point_id": "tp_003",
                    "title": "ESOP",
                    "importance": "must_keep",
                    "why_it_matters": "Culture",
                    "evidence_quotes": ["ESOP"],
                },
            ],
            "hard_excludes": [],
            "warnings": [],
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_003", "seg_011", "seg_028"],
        "layups": [
            {
                "target_segment_id": "seg_003",
                "text": "Gym buyers were a niche — the snack use case opened the wider market. Listen for that thread.",
                "nugget_ids": ["nug_snack"],
                "talking_point_ids": ["tp_002"],
                "skip": False,
                "forward_cue_ok": True,
            },
            {
                "target_segment_id": "seg_011",
                "text": "Bootstrapped growth to thirty crore set the bar before outside capital. How did five-x change the exit clock?",
                "nugget_ids": ["nug_boot"],
                "talking_point_ids": ["tp_001"],
                "skip": False,
                "forward_cue_ok": True,
            },
            {
                "target_segment_id": "seg_028",
                "text": "Inclusive ESOPs meant shop-floor partners shared the upside. What did the Zydus structure protect?",
                "nugget_ids": ["nug_esop"],
                "talking_point_ids": ["tp_003"],
                "skip": False,
                "forward_cue_ok": True,
            },
        ],
        "discharged_talking_point_ids": ["tp_001", "tp_002", "tp_003"],
        "open_talking_point_ids": [],
        "discharged_nugget_ids": ["nug_snack", "nug_boot", "nug_esop"],
        "open_high_salience_nugget_ids": [],
    }
    qc = evaluate_layup_qc(ctx, plan, {"nuggets": []})
    assert qc["layup_coverage"] == 1.0
    assert qc["ok"] is True
