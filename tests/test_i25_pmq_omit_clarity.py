"""i25: PMQ omit lock rebuild under freeze + live pack conflicts only."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.omit_ledger import (
    OMIT_LEDGER_REL,
    air_contract_errors,
    heal_omit_ledger_air_contract,
)
from interview_mux.order_hash import bump_order_lock
from interview_mux.run_context import RunContext
from interview_mux.seam_autopsy import _pack_conflicts
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i25_pmq_omit_clarity")
    run.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "seat_freeze": {"mode": "hard", "active": True},
        },
        skip_handoff=True,
    )
    return run


def test_i25_pack_conflicts_ignore_applied_leftovers() -> None:
    sel = {
        "ordered_segment_ids": ["seg_010", "seg_012", "seg_014"],
        "_meta": {
            "repairs": [
                {
                    "action": "insert_leftovers_before_finale_span",
                    "count": 3,
                    "ids": ["seg_010", "seg_012", "seg_014"],
                },
                {
                    "action": "insert_leftovers_before_finale_span",
                    "count": 2,
                    "ids": ["seg_067g", "seg_067h"],
                },
            ]
        },
    }
    conflicts = _pack_conflicts(sel)
    assert len(conflicts) == 1
    assert conflicts[0]["ids"] == ["seg_067g", "seg_067h"]
    assert conflicts[0]["count"] == 2


def test_i25_omit_order_lock_rebuild_under_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.gate_seat_mutation",
        lambda *_a, **_k: False,
    )

    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_002", "seg_005"], "version": 1},
        source="i25",
    )
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    # Stale omit ledger lock (older revision / different hash).
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
    import json

    dest.write_text(json.dumps(stale), encoding="utf-8")

    assert "omit_ledger_order_lock_stale" in air_contract_errors(ctx)
    out = heal_omit_ledger_air_contract(ctx)
    assert out.get("healed") is True
    assert "rebuilt_stale_order_lock" in (out.get("notes") or [])
    assert "omit_ledger_order_lock_stale" not in air_contract_errors(ctx)
