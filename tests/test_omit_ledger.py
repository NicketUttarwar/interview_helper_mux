"""Tests for understanding/omit_ledger.json builders and air contracts."""

from __future__ import annotations

from interview_mux.omit_ledger import (
    OMIT_LEDGER_REL,
    air_contract_errors,
    build_omit_ledger,
    effective_air_contract,
    empty_omit_ledger,
    mint_entry,
    record_gap_line_skip,
    supersede_entry,
    write_omit_ledger,
)
from interview_mux.nugget_layup import PLAN_REL, stamp_typed_skip
from interview_mux.prompt_validation import validate_omit_ledger
from interview_mux.run_context import RunContext


def test_omit_ledger_schema_accepts_empty():
    assert validate_omit_ledger(empty_omit_ledger()) == []


def test_build_omit_ledger_from_layup_skips():
    ctx = RunContext("exec_omit_ledger_build", create=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_a", "seg_b"],
            "excluded_segment_ids": [{"segment_id": "seg_x", "reason": "low_salience"}],
            "order_lock": {"version": 1, "revision": 1, "order_content_hash": "h1"},
        },
        skip_handoff=True,
    )
    plan = {
        "ordered_segment_ids": ["seg_a", "seg_b"],
        "layups": [
            stamp_typed_skip(
                {"target_segment_id": "seg_a", "line_id": "vo_layup_seg_a", "nugget_ids": []},
                reason_code="opening_orientation_owns_target",
            ),
            {
                "target_segment_id": "seg_b",
                "line_id": "vo_layup_seg_b",
                "skip": False,
                "text": "Shop-floor partners shared ESOP upside. What locked the deal?",
                "nugget_ids": ["nug_1"],
            },
        ],
        "waived_nugget_ids": [{"nugget_id": "nug_w", "reason": "redundant"}],
    }
    ctx.write_json(PLAN_REL, plan, skip_handoff=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    ledger = build_omit_ledger(ctx, plan=plan)
    assert validate_omit_ledger(ledger) == []
    kinds = {e["kind"] for e in ledger["entries"] if e.get("active")}
    assert "segment_exclude" in kinds
    assert "layup_skip" in kinds
    assert "nugget_waive" in kinds
    assert ledger["summary"]["active_count"] >= 3
    contract = effective_air_contract(ledger, target_segment_id="seg_a")
    assert contract["status"] == "suppressed"


def test_gap_line_skip_supersedes_and_defers():
    ctx = RunContext("exec_omit_ledger_g1", create=True)
    write_omit_ledger(ctx, empty_omit_ledger())
    ledger = record_gap_line_skip(
        ctx,
        line_id="vo_001",
        target_segment_id="seg_b",
        reason_code="g1_skipped_optional",
    )
    assert ctx.artifact_exists(OMIT_LEDGER_REL)
    assert effective_air_contract(ledger, line_id="vo_001")["status"] == "deferred"
    again = mint_entry(
        kind="gap_line_skip",
        subject_id="vo_001",
        decision="omit",
        reason_code="operator_force_omit",
        owner_stage="g1_vo_pickup",
        operator_override=True,
        seq=2,
    )
    updated = supersede_entry(ledger, subject_id="vo_001", kind="gap_line_skip", replacement=again)
    active = [e for e in updated["entries"] if e.get("active") and e.get("subject_id") == "vo_001"]
    assert len(active) == 1
    assert active[0]["reason_code"] == "operator_force_omit"


def test_air_contract_detects_unresolved_and_reintroduced_gap_line():
    ctx = RunContext("exec_omit_ledger_contract", create=True)
    ledger = empty_omit_ledger()
    entry = mint_entry(
        kind="gap_line_skip",
        subject_id="vo_001",
        target_segment_id="seg_b",
        decision="defer",
        reason_code="g1_skipped_optional",
        owner_stage="g1_vo_pickup",
        compensating_path="operator_skip_optional",
        seq=1,
    )
    ledger["entries"] = [entry]
    ledger["summary"] = {
        "active_count": 1,
        "by_kind": {"gap_line_skip": 1},
        "compensated_count": 1,
        "unresolved_high_salience": 1,
    }
    errors = air_contract_errors(
        ctx,
        ledger=ledger,
        gap_report={
            "interviewer_lines": [
                {"line_id": "vo_001", "targets_segment_id": "seg_b"}
            ]
        },
        edl={"clips": [{"line_id": "vo_001"}]},
    )
    assert "omit_ledger_unresolved_high_salience=1" in errors
    assert "omit_ledger_gap_line_not_skipped:vo_001" in errors
    assert "omit_ledger_gap_line_still_in_edl:vo_001" in errors


def test_reconcile_edl_strips_omitted_layup_vo(tmp_path):
    from interview_mux.omit_ledger import reconcile_edl_with_omit_ledger, write_omit_ledger
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "exec_omit_strip_edl")
    ledger = empty_omit_ledger()
    ledger["entries"] = [
        mint_entry(
            kind="layup_skip",
            subject_id="vo_layup_seg_005",
            target_segment_id="seg_005",
            decision="omit",
            reason_code="spoken_copy_unhealable",
            owner_stage="nugget_layup_compose",
            compensating_path="omit_unsafe_spoken_copy",
            seq=1,
        )
    ]
    ledger["summary"] = {
        "active_count": 1,
        "by_kind": {"layup_skip": 1},
        "compensated_count": 1,
        "unresolved_high_salience": 0,
    }
    write_omit_ledger(ctx, ledger)
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_004", "seg_005"],
            "timeline_duration_ms": 20_000,
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_004",
                    "timeline_start_ms": 0,
                    "duration_ms": 5_000,
                    "source_start_ms": 0,
                    "source_end_ms": 5_000,
                },
                {
                    "type": "vo_pickup",
                    "line_id": "vo_layup_seg_005",
                    "targets_segment_id": "seg_005",
                    "placement": "before",
                    "timeline_start_ms": 5_000,
                    "duration_ms": 8_000,
                    "source_path": "vo_pickup/synthesized/vo_layup_seg_005.wav",
                },
                {
                    "type": "speech",
                    "segment_id": "seg_005",
                    "timeline_start_ms": 13_000,
                    "duration_ms": 7_000,
                    "source_start_ms": 10_000,
                    "source_end_ms": 17_000,
                },
            ],
            "vo_pickup_clip_count": 1,
        },
        skip_handoff=True,
    )
    report = reconcile_edl_with_omit_ledger(ctx)
    assert report["updated"] is True
    assert "vo_layup_seg_005" in report["removed"]
    edl = ctx.read_json("master/edl.json")
    assert all(c.get("line_id") != "vo_layup_seg_005" for c in edl["clips"])
    assert edl["vo_pickup_clip_count"] == 0
    assert air_contract_errors(ctx, ledger=ledger, edl=edl) == []


def test_heal_omit_ledger_stamps_gap_line_and_strips_edl():
    from interview_mux.omit_ledger import heal_omit_ledger_air_contract, write_omit_ledger

    ctx = RunContext("exec_omit_heal_air", create=True)
    ledger = empty_omit_ledger()
    ledger["entries"] = [
        mint_entry(
            kind="gap_line_skip",
            subject_id="vo_001",
            target_segment_id="seg_b",
            decision="omit",
            reason_code="g1_skipped_optional",
            owner_stage="g1_vo_pickup",
            compensating_path="operator_skip_optional",
            seq=1,
        )
    ]
    ledger["summary"] = {
        "active_count": 1,
        "by_kind": {"gap_line_skip": 1},
        "compensated_count": 1,
        "unresolved_high_salience": 0,
    }
    write_omit_ledger(ctx, ledger)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_001",
                    "targets_segment_id": "seg_b",
                    "gap_type": "missing_setup",
                    "text": "What happened after that turn?",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_b"],
            "timeline_duration_ms": 8_000,
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": "vo_001",
                    "targets_segment_id": "seg_b",
                    "placement": "before",
                    "timeline_start_ms": 0,
                    "duration_ms": 8_000,
                    "source_path": "vo_pickup/synthesized/vo_001.wav",
                }
            ],
            "vo_pickup_clip_count": 1,
        },
        skip_handoff=True,
    )
    before = air_contract_errors(ctx)
    assert any("gap_line_not_skipped" in e for e in before)
    report = heal_omit_ledger_air_contract(ctx)
    assert report["healed"] is True
    gap = ctx.read_json("understanding/gap_report.json")
    assert gap["interviewer_lines"][0].get("skipped_optional") is True
    edl = ctx.read_json("master/edl.json")
    assert all(c.get("line_id") != "vo_001" for c in edl.get("clips") or [])
    assert air_contract_errors(ctx) == []
