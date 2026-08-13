"""Unit tests for the Nugget Layup System (no live LLM)."""

from __future__ import annotations

import pytest

from interview_mux.artifact_repairs import repair_gap_report
from interview_mux.loud_fail import LoudStageFailure
from interview_mux.nugget_layup import (
    CORPUS_REL,
    GAP_REL,
    PLAN_REL,
    assert_layup_fresh_vs_selection,
    build_corpus_mine_input,
    build_layup_compose_input,
    canned_air_violations,
    dedupe_gap_report_nugget_claims,
    evaluate_layup_qc,
    gap_has_layup_before,
    layup_freshness_errors,
    layup_line_from_row,
    lint_gap_report_layup_authority,
    nugget_layup_cfg,
    publish_layup_plan_to_gap_report,
    restore_layup_lines,
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
    assert len([ln for ln in report["interviewer_lines"] if ln.get("origin") == "nugget_layup"]) == 2

    # A recompose that rewrites the artifact without the layups.
    wiped = {
        **report,
        "interviewer_lines": [
            ln for ln in report["interviewer_lines"] if ln.get("origin") != "nugget_layup"
        ],
    }
    assert lint_gap_report_layup_authority(ctx, wiped)
    restored, notes = restore_layup_lines(ctx, wiped)
    assert len(notes) == 2
    assert gap_has_layup_before(restored, "seg_011")
    assert gap_has_layup_before(restored, "seg_028")
    assert lint_gap_report_layup_authority(ctx, restored) == []

    # Same protection on the central gap_report write repair path.
    repaired, applied = repair_gap_report(ctx, wiped)
    assert any(a.get("action") == "restore_nugget_layup_line" for a in applied)
    assert gap_has_layup_before(repaired, "seg_028")


def test_duplicate_nugget_across_layups_fails_qc():
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
    assert qc["ok"] is False
    assert qc["duplicate_nugget_ids"] == ["nug_esop"]
    assert any("duplicate_nugget" in err for err in qc["errors"])


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


def test_materialize_over_skipped_layups_recovers_coverage(tmp_path, monkeypatch):
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
    assert cov >= 0.9
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
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_002", "seg_006"], "selected_segment_ids": ["seg_002", "seg_006"]},
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
        "ordered_segment_ids": ["seg_002", "seg_006"],
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