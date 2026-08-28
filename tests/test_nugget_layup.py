"""Unit tests for the Nugget Layup System (no live LLM)."""

from __future__ import annotations

import json

import pytest

from interview_mux.artifact_repairs import repair_gap_report
from interview_mux.loud_fail import LoudStageFailure
from interview_mux.nugget_layup import (
    CORPUS_REL,
    GAP_REL,
    PLAN_REL,
    aired_nugget_ids,
    attach_selection_order_lock,
    assert_layup_fresh_vs_selection,
    build_corpus_mine_input,
    build_layup_compose_input,
    canned_air_violations,
    coverage_exempt_target_ids,
    dedupe_gap_report_nugget_claims,
    evaluate_layup_qc,
    evaluate_nugget_air_coverage,
    recover_open_high_salience_nuggets,
    recover_open_must_keep_talking_points,
    gap_has_layup_before,
    heal_layup_analysis_fields,
    is_justified_skip_row,
    layup_freshness_errors,
    layup_line_from_row,
    lint_gap_report_layup_authority,
    materialize_over_skipped_layups,
    nugget_layup_cfg,
    prepare_layup_plan_for_persist,
    publish_layup_plan_to_gap_report,
    repair_or_skip_spoken_copy_layups,
    restore_layup_lines,
    stamp_typed_skip,
    stamp_valueless_skips,
    strip_model_order_lock,
    waive_nuggets_for_skipped_vo_lines,
)
from interview_mux.prompt_validation import (
    STAGE_ARTIFACT_DISK_PATHS,
    STAGE_ARTIFACT_SCHEMAS,
    validate_nugget_corpus,
    validate_nugget_layup_plan,
)
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ALL_LLM_STAGES, DELIVERY_ORDER

# Construction analysis every non-skip lay-up row must carry.
_ANALYSIS = {
    "target_beat": "The exit negotiation",
    "listener_need_entering_T": "The prior clip ended before the buyer appeared",
    "forward_unlock": "Why the snack pivot decided the price",
}


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
    # Orientation owns the opening handoff into seg_011 — do not also publish a
    # before-VO layup on that same first target (opening-adjacency contract).
    assert len(layups) == 1
    assert layups[0]["targets_segment_id"] == "seg_028"
    assert not any(ln.get("targets_segment_id") == "seg_011" for ln in layups)
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
                **_ANALYSIS,
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


def test_recover_open_must_keep_already_on_native_tape():
    ctx = RunContext("exec_nugget_layup_recover_must", create=True)
    ctx.write_json(
        "understanding/talking_points.json",
        {
            "strategy_summary": "Founder journey",
            "through_line": "Growth",
            "talking_points": [
                {
                    "talking_point_id": "tp_001",
                    "title": "Bootstrap origin",
                    "importance": "must_keep",
                    "why_it_matters": "Origin",
                    "evidence_quotes": ["bootstrapped from nothing"],
                }
            ],
            "hard_excludes": [],
            "warnings": [],
        },
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_011"]},
        skip_handoff=True,
    )
    from run_fixtures import minimal_manifest, minimal_manifest_segment

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_011",
                text="We bootstrapped from nothing and kept the first store alive.",
            )
        ),
        skip_handoff=True,
    )
    plan = {
        "ordered_segment_ids": ["seg_011"],
        "layups": [
            {
                "target_segment_id": "seg_011",
                "text": "What happened when Rabo wanted out of the deal?",
                "nugget_ids": [],
                "talking_point_ids": [],
                "skip": False,
                "forward_cue_ok": True,
                **_ANALYSIS,
            }
        ],
        "discharged_talking_point_ids": [],
        "open_talking_point_ids": [],
        "discharged_nugget_ids": [],
        "open_high_salience_nugget_ids": [],
    }
    recovered, notes = recover_open_must_keep_talking_points(ctx, plan)
    assert any(str(n).startswith("already_on_tape:tp_001") for n in notes)
    qc = evaluate_layup_qc(ctx, recovered, {"nuggets": []})
    assert qc["open_must_keep_talking_point_ids"] == []
    assert qc["ok"] is True


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


def test_layup_line_removes_repeated_question_sentence():
    line = layup_line_from_row(
        {
            "target_segment_id": "seg_1",
            "text": (
                "The company reached a decision. "
                "Why did the founder sell? Why did the founder sell?"
            ),
        }
    )
    assert line is not None
    assert line["text"] == (
        "The company reached a decision. Why did the founder sell?"
    )


def test_thin_target_beat_only_layup_is_skipped_and_not_published():
    ctx = RunContext("exec_nugget_layup_unhealable", create=True)
    _seed_air_order(
        ctx,
        ["seg_003", "seg_004"],
        {
            "seg_003": "Earlier setup for the diagnostic comparison.",
            "seg_004": (
                "Mohan contrasts invasive tissue biopsy with a blood-based liquid biopsy."
            ),
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_003", "seg_004"],
        "layups": [
            {
                "target_segment_id": "seg_003",
                "line_id": "vo_layup_seg_003",
                "text": "",
                "skip": True,
                "skip_reason_code": "opening_orientation_owns_target",
            },
            {
                "target_segment_id": "seg_004",
                "line_id": "vo_layup_seg_004",
                "text": (
                    "Mohan contrasts invasive tissue biopsy with a blood-based liquid biopsy."
                ),
                "target_beat": (
                    "Mohan contrasts invasive tissue biopsy with a blood-based liquid biopsy."
                ),
                "listener_need_entering_T": "The diagnostic comparison needs context.",
                "forward_unlock": "",
                "skip": False,
            },
            {
                "target_segment_id": "seg_004",
                "line_id": "vo_layup_seg_004_skip",
                "text": "",
                "skip": True,
            },
        ],
    }
    fixed, notes = repair_or_skip_spoken_copy_layups(ctx, plan)
    row = next(r for r in fixed["layups"] if r.get("target_segment_id") == "seg_004")
    if row.get("skip"):
        assert row["skip_reason_code"] == "spoken_copy_unhealable"
        assert any(note["action"] == "skip_unhealable_spoken_copy_layup" for note in notes)
    else:
        # Deterministic last-sentence repair is also acceptable when the cue
        # no longer restates the next native.
        assert row.get("spoken_copy_recovered") is True
        assert any(note["action"] == "repair_spoken_copy_layup" for note in notes)
        assert "?" in str(row.get("text") or "")
        assert row["text"] != row.get("target_beat")
    ctx.write_json(PLAN_REL, fixed)
    report = publish_layup_plan_to_gap_report(ctx, fixed)
    if row.get("skip"):
        assert not any(
            line.get("line_id") == "vo_layup_seg_004"
            for line in report.get("interviewer_lines") or []
        )


def test_cfg_defaults():
    cfg = nugget_layup_cfg({})
    assert cfg["enabled"] is True
    assert cfg["min_layup_coverage"] == 0.70
    assert cfg["min_nugget_air_coverage"] == 0.85
    assert cfg["authoritative_gap_report"] is True
    assert cfg["block_on_open_high_salience"] is True


def test_evaluate_nugget_air_coverage_body_intro_waived():
    corpus = {
        "nuggets": [
            {"nugget_id": "nug_a", "salience": "high", "in_selection": False},
            {"nugget_id": "nug_b", "salience": "high", "in_selection": False},
            {"nugget_id": "nug_c", "salience": "high", "in_selection": False},
            {"nugget_id": "nug_d", "salience": "high", "in_selection": False},
            {"nugget_id": "nug_native", "salience": "high", "already_aired_in_selection": True},
        ]
    }
    body_plan = {
        "layups": [
            {
                "target_segment_id": "seg_011",
                "text": "Setup for the snack pivot.",
                "nugget_ids": ["nug_a", "nug_b", "nug_c"],
                "skip": False,
            }
        ],
        "waived_nugget_ids": [{"nugget_id": "nug_d", "reason": "operator_waive"}],
    }
    soft = evaluate_nugget_air_coverage(body_plan, ["nug_d"], None, corpus, hard=False)
    # 3 body + 1 intro on eligible {a,b,c} = 100% (nug_d waived from eligible)
    assert soft["eligible_nugget_count"] == 3
    assert soft["aired_nugget_count"] == 3
    assert soft["nugget_air_coverage"] == 1.0
    assert soft["ok"] is True
    assert not soft["errors"]

    sparse_body = {
        "layups": [
            {
                "target_segment_id": "seg_011",
                "text": "Only one fact lands here.",
                "nugget_ids": ["nug_a"],
                "skip": False,
            }
        ]
    }
    soft_low = evaluate_nugget_air_coverage(sparse_body, [], None, corpus, hard=False)
    assert soft_low["nugget_air_coverage"] == pytest.approx(0.25, rel=1e-3)
    assert soft_low["ok"] is True
    assert any("min_nugget_air_coverage" in w for w in soft_low["warnings"])

    hard_low = evaluate_nugget_air_coverage(sparse_body, [], None, corpus, hard=True)
    assert hard_low["ok"] is False
    assert any("min_nugget_air_coverage" in e for e in hard_low["errors"])

    at_floor = evaluate_nugget_air_coverage(
        {
            "layups": [
                {
                    "target_segment_id": "seg_011",
                    "text": "Two facts in body.",
                    "nugget_ids": ["nug_a", "nug_b"],
                    "skip": False,
                }
            ],
            "waived_nugget_ids": [{"nugget_id": "nug_d"}],
        },
        ["nug_c"],
        None,
        corpus,
        hard=True,
        min_coverage=0.85,
    )
    # eligible {a,b,c}: body 2 + intro 1 = 3/3
    assert at_floor["nugget_air_coverage"] == 1.0
    assert at_floor["ok"] is True


def test_evaluate_nugget_air_coverage_soft_in_qc():
    ctx = RunContext("exec_nugget_air_qc_soft", create=True)
    corpus = {
        "nuggets": [
            {"nugget_id": f"nug_{i}", "salience": "high", "in_selection": False}
            for i in range(1, 6)
        ]
    }
    plan = {
        "ordered_segment_ids": ["seg_011"],
        "layups": [
            {
                "target_segment_id": "seg_011",
                "text": "One recovered fact before the clip.",
                "nugget_ids": ["nug_1"],
                "skip": False,
                "forward_cue_ok": True,
                **_ANALYSIS,
            }
        ],
        "discharged_talking_point_ids": [],
        "open_talking_point_ids": [],
        "discharged_nugget_ids": ["nug_1"],
        "open_high_salience_nugget_ids": [],
    }
    qc = evaluate_layup_qc(ctx, plan, corpus)
    assert qc["nugget_air_coverage"] == pytest.approx(0.2, rel=1e-3)
    assert qc["ok"] is True or not any("nugget_air_coverage" in e for e in (qc.get("errors") or []))
    assert any("min_nugget_air_coverage" in w for w in (qc.get("warnings") or []))


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
                **_ANALYSIS,
            },
            {
                "target_segment_id": "seg_011",
                "text": "Bootstrapped growth to thirty crore set the bar before outside capital. How did five-x change the exit clock?",
                "nugget_ids": ["nug_boot"],
                "talking_point_ids": ["tp_001"],
                "skip": False,
                "forward_cue_ok": True,
                **_ANALYSIS,
            },
            {
                "target_segment_id": "seg_028",
                "text": "Inclusive ESOPs meant shop-floor partners shared the upside. What did the Zydus structure protect?",
                "nugget_ids": ["nug_esop"],
                "talking_point_ids": ["tp_003"],
                "skip": False,
                "forward_cue_ok": True,
                **_ANALYSIS,
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


def _layup_row(target: str, text: str, **extra) -> dict:
    return {
        "target_segment_id": target,
        "line_id": f"vo_layup_{target}",
        "text": text,
        "skip": False,
        "forward_cue_ok": True,
        **_ANALYSIS,
        **extra,
    }


def _seed_air_order(ctx: RunContext, ordered: list[str], texts: dict[str, str]) -> None:
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ordered})
    segments = []
    start = 0
    for sid in ordered:
        segments.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_0",
                "speaker_role": "interviewee",
                "type": "interviewee_answer",
                "topic_tags": [],
                "text": texts.get(sid, f"Native content for {sid}."),
                "start_ms": start,
                "end_ms": start + 9000,
            }
        )
        start += 12_000
    ctx.write_json("segments/manifest.json", {"segments": segments})


def test_stale_or_reordered_plan_fails_closed():
    ctx = RunContext("exec_nugget_layup_stale", create=True)
    _seed_air_order(ctx, ["seg_003", "seg_011"], {})
    plan = {
        "ordered_segment_ids": ["seg_011"],
        "layups": [_layup_row("seg_011", "Recovered ESOP breadth sets up the deal terms.")],
    }
    errors = layup_freshness_errors(ctx, plan)
    assert errors and "ordered_segment_ids" in errors[0]
    with pytest.raises(LoudStageFailure):
        assert_layup_fresh_vs_selection(ctx, plan)

    fresh = {
        "ordered_segment_ids": ["seg_003", "seg_011"],
        "layups": [_layup_row("seg_011", "Recovered ESOP breadth sets up the deal terms.")],
    }
    assert layup_freshness_errors(ctx, fresh) == []
    stale_meta = {**fresh, "_meta": {"stale": True, "stale_reason": "invalidated_by:full_master_ranking"}}
    with pytest.raises(LoudStageFailure):
        assert_layup_fresh_vs_selection(ctx, stale_meta)


def test_extra_dropped_ids_fail_freshness():
    """Dropped bumper/outro children left on the plan must fail closed."""
    ctx = RunContext("exec_nugget_layup_extras", create=True)
    _seed_air_order(ctx, ["seg_002", "seg_005", "seg_009"], {})
    plan = {
        "ordered_segment_ids": [
            "seg_002",
            "seg_005",
            "seg_009",
            "seg_068b",
            "seg_068c",
        ],
        "layups": [_layup_row("seg_005", "The assay sets up the deal terms.")],
    }
    errors = layup_freshness_errors(ctx, plan)
    assert errors
    assert "stale=" in errors[0]
    assert "seg_068b" in errors[0]
    with pytest.raises(LoudStageFailure):
        assert_layup_fresh_vs_selection(ctx, plan)


@pytest.mark.parametrize(
    "llm_lock",
    [
        {"version": 1, "revision": 1, "order_content_hash": "stale"},
        {"version": 1, "order_content_hash": "stale"},
    ],
)
def test_attach_selection_lock_overwrites_llm_authored_lock(llm_lock: dict):
    ctx = RunContext("exec_nugget_layup_llm_lock", create=True)
    ordered = ["seg_003", "seg_011"]
    selection = {
        "ordered_segment_ids": ordered,
        "order_lock": {"version": 1, "revision": 2, "order_content_hash": "current"},
    }
    ctx.write_json("master/selection.json", selection)
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [_layup_row("seg_011", "Recovered ESOP breadth sets up the deal terms.")],
        "order_lock": llm_lock,
    }

    assert layup_freshness_errors(ctx, plan)
    stamped = attach_selection_order_lock(ctx, plan)
    assert stamped["order_lock"] == selection["order_lock"]
    assert layup_freshness_errors(ctx, stamped) == []


def test_attach_selection_lock_restamps_reordered_ids():
    ctx = RunContext("exec_nugget_layup_reorder_stamp", create=True)
    ordered = ["seg_049", "seg_056", "seg_062"]
    _seed_air_order(ctx, ordered, {})
    plan = {
        "ordered_segment_ids": ["seg_049", "seg_062", "seg_056"],
        "layups": [_layup_row("seg_056", "Validation sits before the recurrence close.")],
    }
    assert layup_freshness_errors(ctx, plan)
    stamped = attach_selection_order_lock(ctx, plan)
    assert stamped["ordered_segment_ids"] == ordered
    assert layup_freshness_errors(ctx, stamped) == []


def test_adopt_layup_rewrites_ids_and_embeds():
    from interview_mux.nugget_layup import adopt_layup_plan_to_selection

    ctx = RunContext("exec_nugget_layup_adopt_remap", create=True)
    _seed_air_order(ctx, ["seg_101", "seg_102"], {})
    plan = {
        "ordered_segment_ids": ["seg_001", "seg_002"],
        "layups": [
            _layup_row("seg_001", "Recovered ESOP breadth sets up the deal terms."),
        ],
        "vo_layup_note": "before vo_layup_seg_001",
    }
    ctx.write_json(PLAN_REL, plan)
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []})
    result = adopt_layup_plan_to_selection(
        ctx,
        mapping={"seg_001": "seg_101", "seg_002": "seg_102"},
        persist=True,
        stage="chapter_close_hitch",
    )
    assert result.get("ok")
    live = ctx.read_json(PLAN_REL)
    assert live["ordered_segment_ids"] == ["seg_101", "seg_102"]
    targets = [str(r.get("target_segment_id")) for r in live.get("layups") or []]
    assert "seg_101" in targets
    assert "vo_layup_seg_101" in str(live)
    assert_layup_fresh_vs_selection(ctx, live)


def test_adopt_layup_split_child_skips_and_freshness_passes():
    from interview_mux.nugget_layup import adopt_layup_plan_to_selection

    ctx = RunContext("exec_nugget_layup_adopt_split", create=True)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_050", "seg_051"]})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_050",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "text": "parent first half",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                },
                {
                    "segment_id": "seg_051",
                    "start_ms": 5000,
                    "end_ms": 10000,
                    "text": "parent second half",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                },
            ]
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_050"],
        "layups": [_layup_row("seg_050", "The assay sets up the deal terms.")],
    }
    ctx.write_json(PLAN_REL, plan)
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []})
    result = adopt_layup_plan_to_selection(ctx, persist=True, stage="chapter_close_hitch")
    assert result.get("ok")
    live = ctx.read_json(PLAN_REL)
    assert live["ordered_segment_ids"] == ["seg_050", "seg_051"]
    by_t = {
        str(r.get("target_segment_id")): r
        for r in live.get("layups") or []
        if isinstance(r, dict)
    }
    assert "seg_050" in by_t
    assert "seg_051" in by_t
    child = by_t["seg_051"]
    assert child.get("skip") or child.get("skipped_optional")
    assert child.get("skip_reason_code") == "hitch_split_no_inherit"
    assert_layup_fresh_vs_selection(ctx, live)


def test_stale_plan_without_adopt_still_fails_freshness():
    ctx = RunContext("exec_nugget_layup_stale_no_adopt", create=True)
    _seed_air_order(ctx, ["seg_050", "seg_051"], {})
    stale = {
        "ordered_segment_ids": ["seg_009"],
        "layups": [_layup_row("seg_009", "Wrong native still on the plan.")],
    }
    ctx.write_json(PLAN_REL, stale)
    with pytest.raises(LoudStageFailure):
        assert_layup_fresh_vs_selection(ctx)


def test_recompose_cannot_wipe_layups():
    ctx = RunContext("exec_nugget_layup_authority", create=True)
    ordered = ["seg_011", "seg_028"]
    _seed_air_order(
        ctx,
        ordered,
        {
            "seg_011": "Then the money conversation started and everything about the timeline shifted.",
            "seg_028": "The buyer signed and the pool stayed intact through the transition.",
        },
    )
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [
            _layup_row(
                "seg_011",
                "The company had grown to thirty crore with no outside capital before that call. "
                "What did the investors want in exchange?",
                nugget_ids=["nug_boot"],
            ),
            _layup_row(
                "seg_028",
                "The employee pool reached shop-floor staff, not just senior managers. "
                "What did the buyer promise in writing?",
                nugget_ids=["nug_esop"],
            ),
        ],
    }
    ctx.write_json(PLAN_REL, plan)
    report = publish_layup_plan_to_gap_report(ctx, plan)
    layups = [ln for ln in report["interviewer_lines"] if ln.get("origin") == "nugget_layup"]
    assert len(layups) == 1
    assert layups[0]["targets_segment_id"] == "seg_028"

    # A recompose that rewrites the artifact without the layups.
    wiped = {
        **report,
        "interviewer_lines": [
            ln for ln in report["interviewer_lines"] if ln.get("origin") != "nugget_layup"
        ],
    }
    assert lint_gap_report_layup_authority(ctx, wiped)
    restored, notes = restore_layup_lines(ctx, wiped)
    assert len(notes) == 1
    assert not any(
        ln.get("origin") == "nugget_layup" and ln.get("targets_segment_id") == "seg_011"
        for ln in restored["interviewer_lines"]
    )
    assert gap_has_layup_before(restored, "seg_028")
    assert lint_gap_report_layup_authority(ctx, restored) == []

    # Same protection on the central gap_report write repair path.
    repaired, applied = repair_gap_report(ctx, wiped)
    assert any(a.get("action") == "restore_nugget_layup_line" for a in applied)
    assert gap_has_layup_before(repaired, "seg_028")
    assert not any(
        ln.get("origin") == "nugget_layup" and ln.get("targets_segment_id") == "seg_011"
        for ln in repaired["interviewer_lines"]
    )


def test_duplicate_nugget_across_layups_warns_and_passes_qc():
    ctx = RunContext("exec_nugget_layup_dupe", create=True)
    ordered = ["seg_011", "seg_028"]
    _seed_air_order(ctx, ordered, {})
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [
            _layup_row(
                "seg_011",
                "Bootstrapped growth to thirty crore set the bar before outside capital.",
                nugget_ids=["nug_esop"],
            ),
            _layup_row(
                "seg_028",
                "Inclusive ESOPs meant shop-floor partners shared the upside of the sale.",
                selected_nugget_ids=["nug_esop"],
            ),
        ],
        "discharged_nugget_ids": ["nug_esop"],
    }
    qc = evaluate_layup_qc(ctx, plan, {"nuggets": []})
    assert qc["ok"] is True
    assert qc["duplicate_nugget_ids"] == ["nug_esop"]
    assert not any("duplicate_nugget" in err for err in qc["errors"])
    assert any("duplicate_nugget" in w for w in qc["warnings"])


def test_duplicate_nugget_across_layups_fails_when_uniqueness_required():
    from interview_mux.nugget_layup import evaluate_layup_craft, nugget_layup_cfg

    ctx = RunContext("exec_nugget_layup_dupe_hard", create=True)
    _seed_air_order(ctx, ["seg_011", "seg_028"], {})
    layups = [
        _layup_row(
            "seg_011",
            "Bootstrapped growth to thirty crore set the bar before outside capital.",
            nugget_ids=["nug_esop"],
        ),
        _layup_row(
            "seg_028",
            "Inclusive ESOPs meant shop-floor partners shared the upside of the sale.",
            selected_nugget_ids=["nug_esop"],
        ),
    ]
    cfg = {**nugget_layup_cfg(), "unique_nuggets_across_layups": True}
    craft = evaluate_layup_craft(ctx, layups, cfg=cfg)
    assert craft["duplicate_nugget_ids"] == ["nug_esop"]
    assert any("duplicate_nugget" in err for err in craft["errors"])


def test_compose_packet_carries_excluded_tape_and_air_ledger():
    ctx = RunContext("exec_nugget_layup_packet", create=True)
    ordered = ["seg_003", "seg_028"]
    _seed_air_order(
        ctx,
        ordered,
        {
            "seg_003": "We bootstrapped the company to thirty crore before any outside capital arrived.",
            "seg_028": "The Zydus structure protected employee ownership through the ESOP pool at exit.",
        },
    )
    ctx.write_json(
        CORPUS_REL,
        {
            "nuggets": [
                {
                    "nugget_id": "nug_esop",
                    "text_claim": "Employee ownership through the ESOP pool covered shop-floor staff",
                    "evidence_quote": "everyone had ESOP",
                    "source_segment_ids": ["seg_014"],
                    "in_selection": False,
                    "salience": "high",
                },
                {
                    "nugget_id": "nug_boot",
                    "text_claim": "Bootstrapped to thirty crore before outside capital",
                    "evidence_quote": "we bootstrapped",
                    "source_segment_ids": ["seg_003"],
                    "in_selection": True,
                    "salience": "high",
                },
            ]
        },
    )
    packet = build_layup_compose_input(ctx)
    first, second = packet["natives"]
    assert first["seam_reason"] == "episode_open"
    assert second["prior_segment_id"] == "seg_003"
    assert "bootstrapped" in second["prior_closing_excerpt"].lower()
    # Facts the earlier native speaks itself are spent before later targets.
    assert "nug_boot" in second["already_aired_nugget_ids"]
    ranked_ids = [n["nugget_id"] for n in second["open_nuggets_ranked"]]
    assert "nug_esop" in ranked_ids
    assert "nug_boot" not in ranked_ids
    esop = next(n for n in second["open_nuggets_ranked"] if n["nugget_id"] == "nug_esop")
    assert esop["in_selection"] is False
    assert esop["relevance_to_target"] > 0
    # Slim ranked rows are pointers; claims live in nugget_corpus once.
    assert "text_claim" not in esop
    assert any(
        n.get("nugget_id") == "nug_esop" and n.get("text_claim")
        for n in (packet.get("nugget_corpus") or {}).get("nuggets") or []
    )
    assert "target_beat" in packet["required_analysis_fields"]


def test_merge_layup_plan_parts_preserves_air_order():
    from interview_mux.nugget_layup import merge_layup_plan_parts

    ordered = ["seg_a", "seg_b", "seg_c"]
    merged = merge_layup_plan_parts(
        [
            {
                "layups": [{"target_segment_id": "seg_a", "text": "A"}],
                "discharged_nugget_ids": ["n1"],
            },
            {
                "layups": [
                    {"target_segment_id": "seg_c", "text": "C"},
                    {"target_segment_id": "seg_b", "text": "B"},
                ],
                "discharged_nugget_ids": ["n2"],
                "open_high_salience_nugget_ids": ["n3"],
            },
        ],
        ordered_segment_ids=ordered,
    )
    assert [r["target_segment_id"] for r in merged["layups"]] == ordered
    assert merged["discharged_nugget_ids"] == ["n1", "n2"]
    assert merged["open_high_salience_nugget_ids"] == ["n3"]


def test_canned_hinge_rejected_under_authority():
    ctx = RunContext("exec_nugget_layup_canned", create=True)
    ordered = ["seg_028"]
    _seed_air_order(
        ctx,
        ordered,
        {"seg_028": "The Zydus structure protected the ESOP pool when the deal closed."},
    )
    assert canned_air_violations("What changed after that?")
    assert canned_air_violations("What shifted from there?")
    assert canned_air_violations(
        "Earlier ESOP breadth made employee wealth part of the deal. What changed after that?"
    )
    assert canned_air_violations(
        "Earlier ESOP breadth made employee wealth part of the deal. "
        "Which promise did the buyer have to honour in writing?"
    ) == []

    plan = {
        "ordered_segment_ids": ordered,
        "layups": [
            _layup_row(
                "seg_028",
                "Earlier ESOP breadth made employee wealth part of the deal. What changed after that?",
                nugget_ids=["nug_esop"],
            )
        ],
    }
    qc = evaluate_layup_qc(ctx, plan, {"nuggets": []})
    assert qc["ok"] is False
    assert any("canned_air" in err for err in qc["errors"])
    assert qc["canned_air_lines"][0]["target_segment_id"] == "seg_028"


def test_missing_analysis_fields_rejected():
    ctx = RunContext("exec_nugget_layup_thin", create=True)
    ordered = ["seg_028"]
    _seed_air_order(ctx, ordered, {})
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [
            {
                "target_segment_id": "seg_028",
                "text": "Inclusive ESOPs meant shop-floor partners shared the upside of the sale.",
                "skip": False,
                "forward_cue_ok": True,
            }
        ],
    }
    qc = evaluate_layup_qc(ctx, plan, {"nuggets": []})
    assert qc["ok"] is False
    assert qc["insufficient_analysis_targets"] == ["seg_028"]


def test_heal_layup_analysis_fields_replaces_canned_what_comes_next(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.nugget_layup import (
        evaluate_layup_qc,
        heal_layup_analysis_fields,
    )

    ctx = RunContext("exec_nugget_layup_heal", create=True)
    import interview_mux.nugget_layup as nl

    monkeypatch.setattr(
        nl,
        "_manifest_segments",
        lambda _ctx: [
            {
                "segment_id": "seg_003",
                "text": "Tissue biopsy is invasive and expensive compared with liquid biopsy.",
            }
        ],
    )
    plan = {
        "ordered_segment_ids": ["seg_003"],
        "layups": [
            {
                "target_segment_id": "seg_003",
                "skip": False,
                "text": (
                    "The guest says tissue biopsy is invasive. "
                    "How liquid biopsy seeks tissue-like information from a blood draw. "
                    "What comes next?"
                ),
                "target_beat": "How liquid biopsy seeks tissue-like information from a blood draw",
                "listener_need_entering_T": "",
                "forward_unlock": "",
                "setup_from_nuggets": "The guest says tissue biopsy is invasive.",
                **{k: v for k, v in _ANALYSIS.items() if k == "target_beat"},
            }
        ],
    }
    # Override beat to the liquid-biopsy one used in text.
    plan["layups"][0]["target_beat"] = (
        "How liquid biopsy seeks tissue-like information from a blood draw"
    )
    before = evaluate_layup_qc(ctx, plan)
    assert before["ok"] is False
    assert any("What comes next" in e or "forward_unlock" in e for e in before["errors"])
    fixed, notes = heal_layup_analysis_fields(ctx, plan)
    assert notes
    row = fixed["layups"][0]
    assert str(row.get("forward_unlock") or "").strip()
    assert "What comes next" not in str(row.get("text") or "")
    assert "What comes next" not in str(row.get("forward_unlock") or "")
    assert not canned_air_violations(str(row.get("text") or ""))
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.nugget_layup import (
        evaluate_layup_qc,
        materialize_over_skipped_layups,
    )

    ctx = RunContext("exec_nugget_layup_mat", create=True)
    ordered = [f"seg_{i:03d}" for i in range(1, 11)]
    _seed_air_order(ctx, ordered, {})
    ctx.write_json(
        "understanding/nugget_corpus.json",
        {
            "nuggets": [
                {
                    "nugget_id": f"nug_{i:03d}",
                    "text_claim": (
                        f"Beat {i} showed shop-floor partners shared ESOP upside number {i} "
                        f"when the company sold, reshaping loyalty talk for cohort {i}."
                    ),
                    "evidence_quote": f"everyone had ESOP {i}",
                    "in_selection": True,
                }
                for i in range(1, 11)
            ]
        },
        skip_handoff=True,
    )
    plan = {
        "ordered_segment_ids": ordered,
        "open_talking_point_ids": [],
        "discharged_talking_point_ids": [],
        "layups": [
            {
                "target_segment_id": sid,
                "skip": True,
                "skip_reason_code": "already_covered",
                "text": "",
                "forward_unlock": f"What changed for workers after beat {i}?",
                "target_beat": f"worker outcome {i}",
                "selected_nugget_ids": [f"nug_{i:03d}"],
                "nugget_ids": [f"nug_{i:03d}"],
                "talking_point_ids": [],
                "listener_need_entering_T": "why this moment matters",
                "setup_from_nuggets": "",
            }
            for i, sid in enumerate(ordered, start=1)
        ],
    }
    before = evaluate_layup_qc(ctx, plan)
    assert before["ok"] is False
    assert any("layup_coverage" in e for e in (before.get("errors") or []))
    fixed, notes = materialize_over_skipped_layups(ctx, plan)
    assert any(str(n).startswith("materialized:") for n in notes)
    after = evaluate_layup_qc(ctx, fixed)
    cov = float(after.get("coverage") or after.get("layup_coverage") or 0.0)
    assert cov >= 0.4
    assert not any("layup_coverage" in e for e in (after.get("errors") or []))
    # Overlap may still warn depending on QC strictness; coverage is the fail we heal.
    assert after.get("ok") is True or not any(
        "layup_coverage" in e for e in (after.get("errors") or [])
    )


def test_dedupe_gap_report_nugget_claims_keeps_first_owner():
    report, notes = dedupe_gap_report_nugget_claims(
        {
            "interviewer_lines": [
                {"line_id": "vo_a", "nugget_ids": ["nug_1", "nug_2"]},
                {"line_id": "vo_b", "nugget_ids": ["nug_2", "nug_3"]},
            ]
        }
    )
    assert notes and notes[0]["dropped_nugget_ids"] == ["nug_2"]
    assert report["interviewer_lines"][1]["nugget_ids"] == ["nug_3"]


def test_publish_skips_dense_nuggets_already_claimed_by_later_layups(monkeypatch):
    """Dense package backfill must not stamp nuggets owned by other plan rows."""
    from interview_mux import information_packages as ip
    from interview_mux import nugget_layup as nl

    ctx = RunContext("exec_nugget_dense_claim", create=True)
    # Keep dense target off the opening segment so orientation adjacency does
    # not suppress the row under test.
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_002", "seg_006"],
            "selected_segment_ids": ["seg_001", "seg_002", "seg_006"],
        },
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "information_packages": [
                {
                    "package_id": "info_pkg_1",
                    "before_segment_ids": ["seg_002"],
                    "nugget_ids": ["nug_001", "nug_002"],
                    "detail_budget": "dense",
                }
            ]
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_006"],
        "selection_fingerprint": "test",
        "layups": [
            {
                "target_segment_id": "seg_002",
                "line_id": "vo_layup_seg_002",
                "text": "What blocked the Stevia pivot before the protein bar launch?",
                "nugget_ids": [],
                "forward_cue_ok": True,
                "skip": False,
                **_ANALYSIS,
            },
            {
                "target_segment_id": "seg_006",
                "line_id": "vo_layup_seg_006",
                "text": "How did the Stevia roadblock force the nutrition-bar decision?",
                "nugget_ids": ["nug_001"],
                "forward_cue_ok": True,
                "skip": False,
                **_ANALYSIS,
            },
        ],
        "discharged_talking_point_ids": [],
        "open_talking_point_ids": [],
        "discharged_nugget_ids": ["nug_001"],
        "open_high_salience_nugget_ids": [],
    }
    ctx.write_json(PLAN_REL, plan)
    ctx.write_json(GAP_REL, {"interviewer_lines": []})

    monkeypatch.setattr(ip, "packages_affect_air", lambda: True)
    monkeypatch.setattr(
        ip,
        "dense_targets_from_plan",
        lambda _mp: {
            "seg_002": {
                "package_id": "info_pkg_1",
                "nugget_ids": ["nug_001", "nug_002"],
                "detail_budget": "dense",
            }
        },
    )
    monkeypatch.setattr(nl, "assert_layup_fresh_vs_selection", lambda *_a, **_k: None)

    report = publish_layup_plan_to_gap_report(ctx, plan)
    by_id = {
        str(ln.get("line_id") or ""): ln
        for ln in (report.get("interviewer_lines") or [])
        if isinstance(ln, dict)
    }
    # Explicit plan claim on seg_006 wins; empty dense row only keeps unclaimed nug_002.
    assert "nug_001" not in (by_id["vo_layup_seg_002"].get("nugget_ids") or [])
    assert by_id["vo_layup_seg_006"].get("nugget_ids") == ["nug_001"]
    assert lint_gap_report_layup_authority(ctx, report) == []

def test_prepare_persist_strips_llm_lock_before_assert():
    ctx = RunContext("exec_nugget_layup_prep_lock", create=True)
    ordered = ["seg_003", "seg_011"]
    selection = {
        "ordered_segment_ids": ordered,
        "order_lock": {"version": 1, "revision": 2, "order_content_hash": "current"},
    }
    ctx.write_json("master/selection.json", selection)
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [_layup_row("seg_011", "Recovered ESOP breadth sets up the deal terms.")],
        "order_lock": {"version": 1, "revision": 1, "order_content_hash": "invented"},
    }
    assert layup_freshness_errors(ctx, plan)
    prepared = prepare_layup_plan_for_persist(ctx, plan)
    assert prepared["order_lock"] == selection["order_lock"]
    assert layup_freshness_errors(ctx, prepared) == []
    stripped = strip_model_order_lock(plan)
    assert "order_lock" not in stripped


def test_compose_envelope_omits_order_lock():
    from interview_mux.openai_structured_output import compose_envelope_schema

    envelope = compose_envelope_schema("nugget_layup_compose", strict=True)
    props = ((envelope.get("properties") or {}).get("artifacts") or {}).get("properties") or {}
    assert "order_lock" not in props
    assert "order_content_hash" not in props


def test_justified_skip_excluded_from_coverage_denominator():
    ctx = RunContext("exec_nugget_justified_cov", create=True)
    ordered = ["seg_a", "seg_b", "seg_c"]
    _seed_air_order(ctx, ordered, {})
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [
            stamp_typed_skip(
                {
                    "target_segment_id": "seg_a",
                    "line_id": "vo_layup_seg_a",
                    "nugget_ids": [],
                },
                reason_code="opening_orientation_owns_target",
            ),
            stamp_typed_skip(
                {
                    "target_segment_id": "seg_b",
                    "line_id": "vo_layup_seg_b",
                    "nugget_ids": ["nug_x"],
                },
                reason_code="spoken_copy_unhealable",
                evidence_refs=["spoken_copy:restatement"],
            ),
            _layup_row(
                "seg_c",
                "Shop-floor partners shared ESOP upside when the company sold. "
                "What did the buyer lock in writing?",
                nugget_ids=["nug_y"],
            ),
        ],
    }
    assert is_justified_skip_row(plan["layups"][0])
    assert is_justified_skip_row(plan["layups"][1])
    exempt = coverage_exempt_target_ids(ctx, plan)
    assert "seg_a" in exempt and "seg_b" in exempt
    qc = evaluate_layup_qc(ctx, plan, {"nuggets": []})
    assert qc["layup_coverage"] == 1.0
    assert not any("layup_coverage" in e for e in (qc.get("errors") or []))


def test_materialize_preserves_justified_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_nugget_preserve_justified", create=True)
    ordered = [f"seg_{i:03d}" for i in range(1, 6)]
    _seed_air_order(ctx, ordered, {})
    plan = {
        "ordered_segment_ids": ordered,
        "open_talking_point_ids": [],
        "discharged_talking_point_ids": [],
        "layups": [
            stamp_typed_skip(
                {
                    "target_segment_id": ordered[0],
                    "line_id": f"vo_layup_{ordered[0]}",
                    "forward_unlock": "unused",
                    "target_beat": "open",
                    "nugget_ids": [],
                },
                reason_code="opening_orientation_owns_target",
            ),
            stamp_typed_skip(
                {
                    "target_segment_id": ordered[1],
                    "line_id": f"vo_layup_{ordered[1]}",
                    "forward_unlock": "unused",
                    "target_beat": "unsafe",
                    "nugget_ids": [],
                },
                reason_code="spoken_copy_unhealable",
            ),
            *[
                {
                    "target_segment_id": sid,
                    "skip": True,
                    "skip_reason_code": "already_covered",
                    "text": "",
                    "forward_unlock": f"What changed after beat {i}?",
                    "target_beat": f"outcome {i}",
                    "selected_nugget_ids": [],
                    "nugget_ids": [],
                    "talking_point_ids": [],
                    "listener_need_entering_T": "why this moment matters",
                    "setup_from_nuggets": "",
                }
                for i, sid in enumerate(ordered[2:], start=3)
            ],
        ],
    }
    fixed, notes = materialize_over_skipped_layups(ctx, plan)
    by = {r["target_segment_id"]: r for r in fixed["layups"]}
    assert by[ordered[0]].get("skip") is True
    assert by[ordered[1]].get("skip") is True
    assert any("preserve_justified_skip" in str(n) or "preserve_opening" in str(n) for n in notes)
    assert not any(str(n).startswith("materialized:") for n in notes)
    assert any("skip_no_grounded_nugget" in str(n) for n in notes)


def test_compose_packet_exposes_handoff_and_opening():
    ctx = RunContext("exec_nugget_compose_enrich", create=True)
    ordered = ["seg_003", "seg_011"]
    _seed_air_order(
        ctx,
        ordered,
        {
            "seg_003": "We started with a gym-buyer story.",
            "seg_011": "Then demand nearly broke the supply chain.",
        },
    )
    # Bypass schema — only handoff fields are read by compose packet builder.
    path = ctx.path("understanding/gap_evaluations.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        __import__("json").dumps(
            {
                "evaluations": [
                    {
                        "segment_id": "seg_011",
                        "listener_confusion": "Scale sounds unearned without the snack pivot",
                        "recommended_framing": "question",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    ctx.write_json(CORPUS_REL, {"nuggets": []}, skip_handoff=True)
    packet = build_layup_compose_input(ctx)
    assert "seg_003" in packet["opening_owned_segment_ids"]
    native = next(n for n in packet["natives"] if n["segment_id"] == "seg_011")
    assert native.get("handoff_need")
    assert native.get("opening_owner") is False
    assert packet.get("order_lock_note")


def test_authority_lint_matches_qc_exempt_math():
    ctx = RunContext("exec_nugget_lint_align", create=True)
    ordered = ["seg_a", "seg_b"]
    _seed_air_order(ctx, ordered, {"seg_a": "Open beat.", "seg_b": "Close beat about ESOP pools."})
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [
            stamp_typed_skip(
                {"target_segment_id": "seg_a", "line_id": "vo_a", "nugget_ids": []},
                reason_code="opening_orientation_owns_target",
            ),
            _layup_row(
                "seg_b",
                "Shop-floor partners shared ESOP upside when the company sold. "
                "What did the buyer lock in writing?",
            ),
        ],
    }
    ctx.write_json(PLAN_REL, plan)
    report = publish_layup_plan_to_gap_report(ctx, plan)
    qc = evaluate_layup_qc(ctx, plan)
    lint = lint_gap_report_layup_authority(ctx, report)
    assert qc["ok"] or not any("layup_coverage" in e for e in (qc.get("errors") or []))
    assert not any("layup coverage" in e for e in lint)


def test_exec_1822_planner_leak_skips_unhealable_layup():
    """Analysis field pasted into air (episode intended scope) must omit, not air."""
    ctx = RunContext("exec_nugget_planner_leak", create=True)
    _seed_air_order(
        ctx,
        ["seg_002", "seg_003"],
        {
            "seg_002": "Welcome Mohan — what should we cover today?",
            "seg_003": "Tissue biopsy is invasive; liquid biopsy uses a blood draw.",
        },
    )
    need = (
        "The native continuation states the episode's intended scope and welcomes the guest."
    )
    plan = {
        "ordered_segment_ids": ["seg_002", "seg_003"],
        "layups": [
            {
                "target_segment_id": "seg_003",
                "line_id": "vo_layup_seg_003",
                "text": (
                    "The guest says tissue biopsy is invasive. "
                    f"{need} What should we listen for next?"
                ),
                "target_beat": "Liquid biopsy from a blood draw",
                "listener_need_entering_T": need,
                "forward_unlock": "What should we listen for next?",
                "setup_from_nuggets": "",
                "nugget_ids": [],
                "skip": False,
            },
        ],
    }
    fixed, notes = repair_or_skip_spoken_copy_layups(ctx, plan)
    row = next(r for r in fixed["layups"] if r.get("line_id") == "vo_layup_seg_003")
    assert row.get("skip") is True
    assert row.get("skip_reason_code") == "spoken_copy_unhealable"
    assert any("analysis_leak" in str(v) or "planner" in str(v) for v in (row.get("spoken_copy_violations") or []))
    assert any(n.get("action") == "skip_unhealable_spoken_copy_layup" for n in notes)


def test_sparse_coverage_floor_allows_many_typed_skips():
    """Default 40% floor: mostly typed skips still pass QC when a few air."""
    ctx = RunContext("exec_nugget_sparse_floor", create=True)
    ordered = [f"seg_{i:03d}" for i in range(1, 6)]
    texts = {sid: f"Native beat {sid} with enough words for a handoff." for sid in ordered}
    _seed_air_order(ctx, ordered, texts)
    air_texts = [
        (
            "Protein-aware buyers rewrote the addressable market before scale. "
            "What nearly broke the supply chain?"
        ),
        (
            "Shop-floor partners shared ESOP upside when the company sold. "
            "What did the buyer lock in writing?"
        ),
    ]
    layups = []
    air_i = 0
    for i, sid in enumerate(ordered):
        if i in (0, 2):
            layups.append(_layup_row(sid, air_texts[air_i], nugget_ids=[f"nug_{air_i}"]))
            air_i += 1
        else:
            layups.append(
                stamp_typed_skip(
                    {
                        "target_segment_id": sid,
                        "line_id": f"vo_layup_{sid}",
                        "nugget_ids": [],
                    },
                    reason_code="self_explanatory_native",
                )
            )
    plan = {"ordered_segment_ids": ordered, "layups": layups}
    qc = evaluate_layup_qc(ctx, plan)
    assert float(qc.get("layup_coverage") or 0) >= 0.4
    assert not any("layup_coverage" in e for e in (qc.get("errors") or []))


def test_clear_native_handoff_skips_framing_without_nuggets():
    ctx = RunContext("exec_nugget_clear_handoff", create=True)
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.95},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.95},
            ]
        },
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_a",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewer",
                    "type": "interviewer_question",
                    "topic_tags": [],
                    "text": "Mohan, why does liquid biopsy matter for trial design?",
                    "start_ms": 0,
                    "end_ms": 4000,
                },
                {
                    "segment_id": "seg_b",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Because tissue biopsy is invasive and slow for real-time profiling.",
                    "start_ms": 4000,
                    "end_ms": 12000,
                },
            ]
        },
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_a", "seg_b"]})
    ctx.write_json(CORPUS_REL, {"nuggets": []}, skip_handoff=True)
    plan = {
        "ordered_segment_ids": ["seg_a", "seg_b"],
        "layups": [
            {
                "target_segment_id": "seg_b",
                "line_id": "vo_layup_seg_b",
                "text": "Before the answer, remember profiling speed matters. What changed?",
                "target_beat": "Real-time profiling",
                "listener_need_entering_T": "Need a bridge into profiling",
                "forward_unlock": "What changed for trial design?",
                "setup_from_nuggets": "",
                "nugget_ids": [],
                "skip": False,
            }
        ],
    }
    from interview_mux.nugget_layup import apply_clear_native_handoff_skips

    fixed, notes = apply_clear_native_handoff_skips(ctx, plan)
    row = fixed["layups"][0]
    assert row.get("skip") is True
    assert row.get("skip_reason_code") == "native_self_orients"
    assert any(n.get("action") == "skip_clear_native_handoff" for n in notes)


def test_sparse_omit_stamps_valueless_skips_without_materialize(monkeypatch):
    """Balanced sparse_omit: stamp holes so coverage passes; never force-air."""
    ctx = RunContext("exec_nugget_sparse_omit_stamp", create=True)
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {
            "topology_class": "one_on_one_balanced",
            "recovery_policy": {"vo_posture": "sparse_omit"},
        },
    )
    ordered = ["seg_a", "seg_b", "seg_c"]
    _seed_air_order(ctx, ordered, {})
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [
            {
                "target_segment_id": "seg_a",
                "line_id": "vo_layup_seg_a",
                "skip": True,
                "text": "",
                "nugget_ids": [],
                "listener_need_entering_T": "Paste this analysis into spoken copy.",
            },
            {
                "target_segment_id": "seg_b",
                "line_id": "vo_layup_seg_b",
                "skip": True,
                "text": "",
                "nugget_ids": [],
            },
            _layup_row(
                "seg_c",
                "Shop-floor partners shared ESOP upside when the company sold. "
                "What did the buyer lock in writing?",
                nugget_ids=["nug_y"],
            ),
        ],
    }

    def _boom(*_a, **_k):
        raise AssertionError("materialize_over_skipped_layups must not run under sparse_omit")

    monkeypatch.setattr(
        "interview_mux.nugget_layup.materialize_over_skipped_layups", _boom
    )
    stamped, notes = stamp_valueless_skips(ctx, plan)
    assert notes
    assert all(is_justified_skip_row(r) for r in stamped["layups"] if r.get("skip"))
    for row in stamped["layups"]:
        if row.get("skip"):
            assert "Paste this analysis" not in str(row.get("text") or "")
    qc = evaluate_layup_qc(ctx, stamped)
    assert qc.get("ok") is True or not any(
        "layup_coverage" in str(e) for e in (qc.get("errors") or [])
    )


def test_publish_restamps_stale_opening_skip_when_native_self_orients(tmp_path):
    """Opening layup stamped for orientation must become native-self-orient skip."""
    from interview_mux.omit_ledger import OMIT_LEDGER_REL
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "exec_layup_native_open_restamp")
    ordered = ["seg_010", "seg_011"]
    brief_path = ctx.path("understanding", "content_brief.json")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        json.dumps({"guest_name": "Mohan", "thesis": "Liquid biopsy changes trials."}),
        encoding="utf-8",
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ordered}, skip_handoff=True)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_010",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewer",
                    "type": "interviewer_question",
                    "topic_tags": [],
                    "text": (
                        "Welcome Mohan — today we talk about liquid biopsy, "
                        "trial design, and why a blood draw changes diagnostics."
                    ),
                    "start_ms": 0,
                    "end_ms": 8000,
                },
                {
                    "segment_id": "seg_011",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Tissue biopsy is invasive and expensive.",
                    "start_ms": 8000,
                    "end_ms": 14000,
                },
            ]
        },
        skip_handoff=True,
    )
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [
            stamp_typed_skip(
                {
                    "target_segment_id": "seg_010",
                    "line_id": "vo_layup_seg_010",
                    "nugget_ids": ["nug_001"],
                    **_ANALYSIS,
                },
                reason_code="opening_orientation_owns_target",
            ),
            {
                "target_segment_id": "seg_011",
                "line_id": "vo_layup_seg_011",
                "text": (
                    "Tissue sampling is the old default. What makes a blood draw "
                    "the better diagnostic path?"
                ),
                "nugget_ids": ["nug_002"],
                "origin": "nugget_layup",
                **_ANALYSIS,
            },
        ],
    }
    ctx.write_json(PLAN_REL, plan, skip_handoff=True)
    ctx.write_json(GAP_REL, {"interviewer_lines": []}, skip_handoff=True)
    from interview_mux.opening_orientation import native_open_already_orients

    assert native_open_already_orients(ctx, ordered, target_segment_id="seg_010")
    report = publish_layup_plan_to_gap_report(ctx, plan)
    persisted = ctx.read_json(PLAN_REL)
    opening = next(r for r in persisted["layups"] if r.get("target_segment_id") == "seg_010")
    assert opening.get("skip") is True
    assert opening.get("skip_reason_code") == "episode_open_native_self_orients"
    meta = report.get("opening_orientation") or {}
    assert meta.get("omitted") is True
    ledger = ctx.read_json(OMIT_LEDGER_REL) if ctx.artifact_exists(OMIT_LEDGER_REL) else {}
    layup_entries = [
        e
        for e in (ledger.get("entries") or [])
        if e.get("active") and e.get("subject_id") == "vo_layup_seg_010"
    ]
    assert layup_entries
    assert layup_entries[0].get("decision") == "omit"
    assert layup_entries[0].get("replacement_ref") in (None, "")


def test_qc_open_high_salience_fails_and_skip_does_not_discharge():
    ctx = RunContext("exec_nugget_open_high", create=True)
    _seed_air_order(
        ctx,
        ["seg_012"],
        {"seg_012": "Guest explains circulating tumour cells in blood."},
    )
    plan = {
        "ordered_segment_ids": ["seg_012"],
        "layups": [
            stamp_typed_skip(
                {
                    "target_segment_id": "seg_012",
                    "line_id": "vo_layup_seg_012",
                    "nugget_ids": ["nug_004"],
                    **_ANALYSIS,
                },
                reason_code="no_eligible_unspent_nugget",
            )
        ],
        "discharged_nugget_ids": ["nug_004"],
        "open_high_salience_nugget_ids": [],
    }
    corpus = {
        "nuggets": [
            {
                "nugget_id": "nug_004",
                "text_claim": "CTCs occur at roughly one in a billion blood cells.",
                "evidence_quote": "one in a billion",
                "in_selection": False,
                "salience": "high",
                "already_aired_in_selection": False,
            },
            {
                "nugget_id": "nug_005",
                "text_claim": "Price-performance improved a thousandfold.",
                "evidence_quote": "thousandfold",
                "in_selection": False,
                "salience": "high",
                "already_aired_in_selection": False,
            },
        ]
    }
    qc = evaluate_layup_qc(ctx, plan, corpus)
    assert qc["ok"] is False
    assert "nug_004" in qc["open_high_salience_nugget_ids"]
    assert "nug_005" in qc["open_high_salience_nugget_ids"]
    assert any("open_high_salience_nuggets" in e for e in (qc.get("errors") or []))
    assert "nug_004" not in aired_nugget_ids(plan)


def test_recover_open_high_salience_unskips_skipped_nugget():
    ctx = RunContext("exec_nugget_recover_high", create=True)
    _seed_air_order(
        ctx,
        ["seg_002", "seg_012"],
        {
            "seg_002": "Welcome, today we talk about diagnostics.",
            "seg_012": "Guest explains circulating tumour cells in blood.",
        },
    )
    corpus = {
        "nuggets": [
            {
                "nugget_id": "nug_004",
                "text_claim": "CTCs occur at roughly one in a billion blood cells.",
                "evidence_quote": "one in a billion",
                "in_selection": False,
                "salience": "high",
                "already_aired_in_selection": False,
                "source_segment_ids": ["seg_cut"],
            }
        ]
    }
    ctx.write_json(CORPUS_REL, corpus)
    plan = {
        "ordered_segment_ids": ["seg_002", "seg_012"],
        "layups": [
            stamp_typed_skip(
                {
                    "target_segment_id": "seg_002",
                    "line_id": "vo_layup_seg_002",
                    **_ANALYSIS,
                },
                reason_code="opening_orientation_owns_target",
            ),
            stamp_typed_skip(
                {
                    "target_segment_id": "seg_012",
                    "line_id": "vo_layup_seg_012",
                    "nugget_ids": ["nug_004"],
                    "value_forgone": ["nug_004"],
                    **_ANALYSIS,
                },
                reason_code="no_eligible_unspent_nugget",
            )
        ],
        "open_high_salience_nugget_ids": ["nug_004"],
        "discharged_nugget_ids": [],
    }
    recovered, notes = recover_open_high_salience_nuggets(ctx, plan)
    row = next(r for r in recovered["layups"] if r.get("target_segment_id") == "seg_012")
    assert any(n.startswith("unskipped:nug_004") for n in notes)
    assert row.get("skip") is not True
    assert "nug_004" in (row.get("nugget_ids") or [])
    assert "one in a billion" in str(row.get("text") or "").lower()
    qc = evaluate_layup_qc(ctx, recovered, corpus)
    assert "nug_004" not in qc["open_high_salience_nugget_ids"]
    assert not any("open_high_salience_nuggets" in e for e in (qc.get("errors") or []))


def _set_host_guest_speakers(ctx: RunContext) -> None:
    man = ctx.read_json("segments/manifest.json")
    segs = man.get("segments") or []
    if segs:
        segs[0]["speaker_id"] = "spk_0"
        segs[0]["speaker_role"] = "interviewer"
        segs[0]["type"] = "interviewer_question"
    for seg in segs[1:]:
        seg["speaker_id"] = "spk_1"
        seg["speaker_role"] = "interviewee"
        seg["type"] = "interviewee_answer"
    ctx.write_json("segments/manifest.json", man)
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.95},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.95},
            ]
        },
    )


def test_spoken_copy_keeps_nugget_body_and_appends_cue(monkeypatch):
    ctx = RunContext("exec_nugget_heal_body", create=True)
    target = (
        "Mohan walks through how a blood draw finds circulating tumour cells."
    )
    _seed_air_order(
        ctx,
        ["seg_002", "seg_012"],
        {
            "seg_002": "Welcome, today we talk about diagnostics.",
            "seg_012": target,
        },
    )
    _set_host_guest_speakers(ctx)
    monkeypatch.setattr(
        "interview_mux.source_topology.pickup_eligible_speaker_id",
        lambda _ctx: "spk_0",
    )
    ctx.write_json(
        CORPUS_REL,
        {
            "nuggets": [
                {
                    "nugget_id": "nug_004",
                    "text_claim": (
                        "Mohan describes cell biopsy as a blood-based liquid biopsy "
                        "using circulating tumour cells."
                    ),
                    "evidence_quote": "circulating tumour cells",
                    "in_selection": False,
                    "salience": "high",
                }
            ]
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_002", "seg_012"],
        "layups": [
            {
                "target_segment_id": "seg_012",
                "line_id": "vo_layup_seg_012",
                "text": (
                    "Mohan describes cell biopsy as a blood-based liquid biopsy "
                    "using circulating tumour cells."
                ),
                "nugget_ids": ["nug_004"],
                "selected_nugget_ids": ["nug_004"],
                "setup_from_nuggets": (
                    "Mohan describes cell biopsy as a blood-based liquid biopsy "
                    "using circulating tumour cells."
                ),
                "target_beat": "Blood-draw CTC detection",
                "listener_need_entering_T": "The CTC rarity needs a setup.",
                "forward_unlock": "What should we listen for in that explanation?",
                "skip": False,
            }
        ],
    }
    fixed, notes = repair_or_skip_spoken_copy_layups(ctx, plan)
    row = next(r for r in fixed["layups"] if r.get("line_id") == "vo_layup_seg_012")
    text = str(row.get("text") or "")
    assert row.get("skip") is not True
    assert "cell biopsy" in text.lower()
    assert "?" in text
    assert "story in motion" not in text.lower()
    assert any(n.get("action") == "repair_spoken_copy_layup" for n in notes)


def test_spoken_copy_rejects_cue_only_when_nuggets_exist(monkeypatch):
    ctx = RunContext("exec_nugget_heal_no_hinge", create=True)
    _seed_air_order(
        ctx,
        ["seg_002", "seg_012"],
        {
            "seg_002": "Welcome, today we talk about diagnostics.",
            "seg_012": "Guest explains circulating tumour cells in blood.",
        },
    )
    _set_host_guest_speakers(ctx)
    monkeypatch.setattr(
        "interview_mux.source_topology.pickup_eligible_speaker_id",
        lambda _ctx: "spk_0",
    )
    ctx.write_json(
        CORPUS_REL,
        {
            "nuggets": [
                {
                    "nugget_id": "nug_004",
                    "text_claim": "CTCs occur at roughly one in a billion blood cells.",
                    "evidence_quote": "one in a billion",
                    "in_selection": False,
                    "salience": "high",
                }
            ]
        },
    )
    plan = {
        "ordered_segment_ids": ["seg_002", "seg_012"],
        "layups": [
            stamp_typed_skip(
                {
                    "target_segment_id": "seg_002",
                    "line_id": "vo_layup_seg_002",
                    **_ANALYSIS,
                },
                reason_code="opening_orientation_owns_target",
            ),
            {
                "target_segment_id": "seg_012",
                "line_id": "vo_layup_seg_012",
                "text": "What set this part of the story in motion?",
                "nugget_ids": ["nug_004"],
                "selected_nugget_ids": ["nug_004"],
                "setup_from_nuggets": "CTCs occur at roughly one in a billion blood cells.",
                "target_beat": "CTC rarity",
                "listener_need_entering_T": "Need the one-in-a-billion fact.",
                "forward_unlock": "What should we listen for next?",
                "skip": False,
            }
        ],
    }
    fixed, notes = repair_or_skip_spoken_copy_layups(ctx, plan)
    row = next(r for r in fixed["layups"] if r.get("line_id") == "vo_layup_seg_012")
    text = str(row.get("text") or "")
    if row.get("skip"):
        assert row.get("skip_reason_code") == "spoken_copy_unhealable"
        assert any(n.get("action") == "skip_unhealable_spoken_copy_layup" for n in notes)
    else:
        assert "one in a billion" in text.lower()
        assert "story in motion" not in text.lower()
        assert any(n.get("action") == "repair_spoken_copy_layup" for n in notes)


def _enable_gap_framing(ctx: RunContext) -> None:
    from interview_mux.gap_vo_gates import set_gap_framing_enabled, set_gap_vo_delivery

    set_gap_framing_enabled(ctx, True)
    set_gap_vo_delivery(ctx, "chatterbox")
    brief_path = ctx.path("understanding", "content_brief.json")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        json.dumps(
            {
                "thesis": "Diagnostics and circulating tumour cells in blood.",
                "guest_name": "Dr. Chen",
                "topics": [{"name": "diagnostics", "label": "Diagnostics"}],
            }
        ),
        encoding="utf-8",
    )


def test_recover_open_high_salience_routes_to_orientation_when_no_body_target():
    ctx = RunContext("exec_nugget_orient_recovery", create=True)
    _seed_air_order(
        ctx,
        ["seg_002"],
        {"seg_002": "Welcome, today we talk about diagnostics."},
    )
    corpus = {
        "nuggets": [
            {
                "nugget_id": "nug_004",
                "text_claim": "CTCs occur at roughly one in a billion blood cells.",
                "evidence_quote": "one in a billion",
                "in_selection": False,
                "salience": "high",
                "already_aired_in_selection": False,
            }
        ]
    }
    ctx.write_json(CORPUS_REL, corpus)
    plan = {
        "ordered_segment_ids": ["seg_002"],
        "layups": [
            stamp_typed_skip(
                {
                    "target_segment_id": "seg_002",
                    "line_id": "vo_layup_seg_002",
                    **_ANALYSIS,
                },
                reason_code="opening_orientation_owns_target",
            )
        ],
        "open_high_salience_nugget_ids": ["nug_004"],
        "discharged_nugget_ids": [],
    }
    recovered, notes = recover_open_high_salience_nuggets(ctx, plan)
    assert "nug_004" in (recovered.get("orientation_nugget_recovery_ids") or [])
    assert any(n.startswith("orientation_recovery:nug_004") for n in notes)
    assert recovered.get("open_high_salience_nugget_ids") == []
    qc = evaluate_layup_qc(ctx, recovered, corpus)
    assert "nug_004" not in qc["open_high_salience_nugget_ids"]
    assert not any("open_high_salience_nuggets" in e for e in (qc.get("errors") or []))


def test_publish_embeds_orientation_nugget_recovery():
    ctx = RunContext("exec_nugget_orient_publish", create=True)
    _enable_gap_framing(ctx)
    _seed_air_order(
        ctx,
        ["seg_002", "seg_012"],
        {
            "seg_002": "Welcome, today we talk about diagnostics.",
            "seg_012": "Guest explains circulating tumour cells in blood.",
        },
    )
    ctx.write_json(CORPUS_REL, {
        "nuggets": [
            {
                "nugget_id": "nug_004",
                "text_claim": "CTCs occur at roughly one in a billion blood cells.",
                "evidence_quote": "one in a billion",
                "in_selection": False,
                "salience": "high",
            }
        ]
    })
    plan = {
        "ordered_segment_ids": ["seg_002", "seg_012"],
        "layups": [],
        "orientation_nugget_recovery_ids": ["nug_004"],
    }
    ctx.write_json(PLAN_REL, plan)
    report = publish_layup_plan_to_gap_report(ctx, plan)
    orient = next(
        ln for ln in report["interviewer_lines"] if ln.get("episode_orientation")
    )
    assert "one in a billion" in str(orient.get("text") or "").lower()
    assert "nug_004" in (orient.get("nugget_ids") or [])
    assert report.get("orientation_nugget_recovery", {}).get("nugget_ids")


def test_waive_nuggets_for_g1_skipped_vo_lines():
    ctx = RunContext("exec_nugget_g1_waive", create=True)
    _seed_air_order(ctx, ["seg_012"], {"seg_012": "Guest explains CTCs."})
    ctx.write_json(
        GAP_REL,
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_012",
                    "gap_type": "nugget_layup",
                    "placement": "before",
                    "targets_segment_id": "seg_012",
                    "delivery": "synthesize",
                    "nugget_ids": ["nug_004"],
                    "selected_nugget_ids": ["nug_004"],
                    "text": "CTCs occur at roughly one in a billion blood cells.",
                    "skipped_optional": True,
                }
            ]
        },
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_012"],
            "layups": [],
            "open_high_salience_nugget_ids": ["nug_004"],
        },
    )
    waived = waive_nuggets_for_skipped_vo_lines(
        ctx, skipped_line_ids=["vo_layup_seg_012"]
    )
    assert waived == ["nug_004"]
    plan = ctx.read_json(PLAN_REL)
    assert plan["open_high_salience_nugget_ids"] == []
    waived_ids = {x["nugget_id"] for x in plan.get("waived_nugget_ids") or []}
    assert "nug_004" in waived_ids
