"""End-A: hard seat freeze mutation constitution (MUX_FORENSICS=0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.artifact_sanitize.air_script import (
    air_contract_sanitary_errors,
    sanitize_air_contract,
)
from interview_mux.omit_ledger import (
    OMIT_LEDGER_REL,
    air_contract_errors,
    heal_omit_ledger_air_contract,
    revive_required_opening_orientation,
)
from interview_mux.order_hash import bump_order_lock
from interview_mux.run_context import RunContext
from interview_mux.seat_authority import (
    HARD_FREEZE_ALLOWLIST_ACTIONS,
    HARD_FREEZE_FORBIDDEN_ACTIONS,
    hard_freeze_action_permitted,
    hard_freeze_blocks_action,
    seat_mutation_allowed,
    stamp_hard_seat_freeze,
)
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "enda_hard_freeze")
    run.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "delivery_epoch": {},
        },
        skip_handoff=True,
    )
    return run


def _stamp_hard(ctx: RunContext) -> None:
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")


def test_enda_allowlist_membership() -> None:
    assert hard_freeze_action_permitted("omit_ledger_revive_orientation")
    assert hard_freeze_action_permitted("drop_seated_missing_from_gap")
    assert hard_freeze_action_permitted("stamp_pair_freeze")
    assert not hard_freeze_action_permitted("protect_hosted_vo_floor_reseat")
    assert "protect_hosted_vo_floor_reseat" in HARD_FREEZE_FORBIDDEN_ACTIONS
    assert "omit_ledger_revive_orientation" in HARD_FREEZE_ALLOWLIST_ACTIONS


def test_enda_seat_mutation_allowlist_bypasses_meta_gate(ctx: RunContext) -> None:
    _stamp_hard(ctx)
    allowed, why = seat_mutation_allowed(
        ctx, reason="omit_ledger_revive_orientation", require_meta_gate=True
    )
    assert allowed is True
    assert why == "end_a_allowlist"
    blocked, why2 = seat_mutation_allowed(
        ctx, reason="invent_new_seats", require_meta_gate=True
    )
    assert blocked is False
    assert why2 == "frozen_needs_meta_gate"


def test_enda_refuse_floor_reseat_under_hard_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    _stamp_hard(ctx)
    assert hard_freeze_blocks_action(ctx, "protect_hosted_vo_floor_reseat")

    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_orient",
            text="Welcome.",
            episode_orientation=True,
            targets_segment_id="seg_001",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_a",
            text="A",
            targets_segment_id="seg_001",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_b",
            text="B",
            targets_segment_id="seg_002",
            delivery="synthesize",
        ),
    )
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_b"],
                "orientation_id": "vo_orient",
            }
        }
    }
    omit = {"entries": []}
    before_seated = list(plan["air_script"]["vo_seats"]["seated_line_ids"])
    result = sanitize_air_contract(ctx, {"plan": plan, "gap": gap, "omit": omit})
    assert any(
        a.get("action") == "protect_hosted_vo_floor_reseat_refused_hard_freeze"
        for a in result.actions
    )
    assert not any(
        a.get("action") == "protect_hosted_vo_floor_reseat" for a in result.actions
    )
    seats = (result.doc.get("air_script") or {}).get("vo_seats") or {}
    assert list(seats.get("seated_line_ids") or []) == before_seated


def test_enda_auto_commit_skips_refuse_notes(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse-hard-freeze notes must not emit needs_sanitize forever."""
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.config.block_consumers_on_unsanitary",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.reentry.stamp_matches",
        lambda _doc: False,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.air_script.sanitize_air_contract",
        lambda _ctx, docs=None: type(
            "R",
            (),
            {
                "ok": True,
                "actions": [
                    {
                        "action": "protect_hosted_vo_floor_reseat_refused_hard_freeze",
                        "ids": ["vo_x"],
                    }
                ],
                "errors": [],
            },
        )(),
    )
    ctx.write_json("mastering/mastering_plan.json", {"air_script": {"vo_seats": {}}})
    _stamp_hard(ctx)
    assert air_contract_sanitary_errors(ctx) == []


def test_enda_protect_orientation_and_revive_under_hard_freeze(
    ctx: RunContext,
) -> None:
    _stamp_hard(ctx)

    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_orient",
            text="Welcome to the show.",
            episode_orientation=True,
            targets_segment_id="seg_001",
            delivery="synthesize",
            skipped_optional=True,
            air_script_omit=True,
        ),
    )
    gap["opening_orientation"] = {
        "required": True,
        "line_id": "vo_orient",
    }
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)

    omit = {
        "version": 1,
        "entries": [
            {
                "subject_id": "vo_orient",
                "kind": "gap_line_skip",
                "status": "active",
            }
        ],
        "summary": {
            "active_count": 1,
            "by_kind": {},
            "unresolved_high_salience": 0,
            "compensated_count": 0,
        },
    }
    dest = ctx.final_path(*OMIT_LEDGER_REL.split("/", 1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(omit), encoding="utf-8")

    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_orient"],
                "omitted_line_ids": [],
                "orientation_id": "vo_orient",
            }
        }
    }
    result = sanitize_air_contract(
        ctx,
        {
            "plan": plan,
            "gap": ctx.read_json("understanding/gap_report.json"),
            "omit": json.loads(dest.read_text(encoding="utf-8")),
        },
    )
    assert any(
        a.get("action") == "protect_orientation_from_omit" for a in result.actions
    )

    out = revive_required_opening_orientation(ctx)
    assert out.get("changed") is True
    assert not any("seat_freeze_blocked" in str(n) for n in (out.get("notes") or []))
    gap2 = ctx.read_json("understanding/gap_report.json")
    orient = next(
        r
        for r in (gap2.get("interviewer_lines") or [])
        if isinstance(r, dict) and r.get("line_id") == "vo_orient"
    )
    assert not orient.get("skipped_optional")
    assert not orient.get("air_script_omit")


def test_enda_omit_order_lock_rebuild_under_hard_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.seat_authority.gate_seat_mutation",
        lambda *_a, **_k: False,
    )
    _stamp_hard(ctx)
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_002", "seg_005"], "version": 1},
        source="enda",
    )
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    stale = {
        "version": 1,
        "order_content_hash": "deadbeefdeadbeef",
        "order_lock": {
            "version": 1,
            "revision": 1,
            "authority": "master/selection.json",
            "ordered_segment_ids": ["seg_002"],
            "order_content_hash": "deadbeefdeadbeef",
            "created_by": "test",
        },
        "entries": [],
        "summary": {
            "active_count": 0,
            "by_kind": {},
            "unresolved_high_salience": 0,
            "compensated_count": 0,
        },
    }
    dest = ctx.final_path(*OMIT_LEDGER_REL.split("/", 1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(stale), encoding="utf-8")
    assert "omit_ledger_order_lock_stale" in air_contract_errors(ctx)
    out = heal_omit_ledger_air_contract(ctx)
    assert out.get("healed") is True
    assert "rebuilt_stale_order_lock" in (out.get("notes") or [])
    assert "omit_ledger_order_lock_stale" not in air_contract_errors(ctx)


def test_enda_transitions_strip_actions_allowlisted() -> None:
    for action in ("stamp_pair_freeze", "trim_pair_freeze", "framing_dedupe"):
        assert hard_freeze_action_permitted(action)


def test_enda_blank_drop_survives_freeze_order_preserve(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.air_order_boundary import _drop_blank_segments_under_freeze

    _stamp_hard(ctx)
    assert hard_freeze_action_permitted("drop_blank_segments_under_freeze")

    monkeypatch.setattr(
        "interview_mux.artifact_repairs._segment_is_blank_or_unusable",
        lambda _ctx, sid: str(sid) == "seg_blank",
    )
    sel = {
        "ordered_segment_ids": ["seg_blank", "seg_real"],
        "excluded_segment_ids": [],
        "chapters": [{"segment_ids": ["seg_blank", "seg_real"]}],
    }
    out = _drop_blank_segments_under_freeze(ctx, sel)
    assert "seg_blank" not in (out.get("ordered_segment_ids") or [])
    assert "seg_real" in (out.get("ordered_segment_ids") or [])
    excl_ids = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in (out.get("excluded_segment_ids") or [])
    }
    assert "seg_blank" in excl_ids
