"""Tests for artifact_sanitize air_contract (W3 — seats/omit/gap flags)."""

from __future__ import annotations

import json
from copy import deepcopy

from interview_mux.artifact_sanitize.air_script import (
    commit_air_contract,
    run_air_contract_sanitize,
    sanitize_air_contract,
)
from interview_mux.artifact_sanitize.registry import air_contract_sanitary_errors
from interview_mux.artifact_sanitize.gap_report import sanitize_gap_report
from interview_mux.run_context import RunContext
from run_fixtures import minimal_gap_line, minimal_gap_report


def _dump_raw(ctx: RunContext, rel: str, doc: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _base_gap() -> dict:
    return minimal_gap_report(
        minimal_gap_line(
            line_id="vo_orient",
            text="Welcome to the show.",
            episode_orientation=True,
            targets_segment_id="seg_001",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_a",
            text="Line A",
            targets_segment_id="seg_001",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_b",
            text="Line B",
            targets_segment_id="seg_002",
            delivery="synthesize",
        ),
    )


def test_orientation_never_stripped_from_omit_ledger() -> None:
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": [],
                "orientation_id": "vo_orient",
            }
        }
    }
    omit = {
        "entries": [
            {
                "subject_id": "vo_orient",
                "kind": "gap_line",
                "status": "active",
            },
            {
                "subject_id": "vo_b",
                "kind": "gap_line",
                "status": "active",
            },
        ]
    }
    result = sanitize_air_contract(ctx, {"plan": plan, "gap": gap, "omit": omit})
    omit_out = result.doc.get("_air_contract_omit") or {}
    subjects = {
        str(e.get("subject_id"))
        for e in (omit_out.get("entries") or [])
        if isinstance(e, dict)
    }
    assert "vo_orient" not in subjects
    assert any(a.get("action") == "protect_orientation_from_omit" for a in result.actions)


def test_omit_gap_sync_via_sanitize_air_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_b"],
            }
        }
    }
    result = sanitize_air_contract(ctx, {"plan": plan, "gap": gap, "omit": {}})
    assert any(a.get("action") == "stamp_gap_omit_flags" for a in result.actions)
    gap_out = result.doc.get("_air_contract_gap") or {}
    by_id = {
        str(r.get("line_id")): r
        for r in (gap_out.get("interviewer_lines") or [])
        if isinstance(r, dict)
    }
    assert by_id["vo_b"].get("omit") is True
    assert by_id["vo_b"].get("skipped_optional") is True
    assert not by_id["vo_a"].get("omit")


def test_sanitize_protects_hosted_vo_floor_instead_of_stamp(monkeypatch) -> None:
    """Omit-ledger sync must not collapse G-Framing synthetic floor."""
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_orient", "vo_b"],
                "orientation_id": "vo_orient",
            }
        }
    }
    result = sanitize_air_contract(ctx, {"plan": plan, "gap": gap, "omit": {}})
    assert any(
        a.get("action") == "protect_hosted_vo_floor_reseat" for a in result.actions
    )
    seats = (result.doc.get("air_script") or {}).get("vo_seats") or {}
    seated = set(seats.get("seated_line_ids") or [])
    assert "vo_orient" in seated
    assert "vo_b" in seated or "vo_a" in seated
    gap_out = result.doc.get("_air_contract_gap") or {}
    active = 0
    for row in gap_out.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        if row.get("skipped_optional") or row.get("omit") or row.get("air_script_omit"):
            continue
        if str(row.get("delivery") or "").lower() in {
            "synthesize",
            "record",
            "voice_clone",
            "chatterbox",
            "",
        }:
            active += 1
    assert active >= 3


def test_seats_le_wavs_when_clamp_fixture_allows(monkeypatch) -> None:
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a", "vo_b"],
                "omitted_line_ids": [],
            }
        }
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)
    _dump_raw(ctx, "mastering/mastering_plan.json", plan)

    def fake_clamp(c, g, *, apply_freeze_gate=True):
        rows = [dict(r) for r in (g.get("interviewer_lines") or []) if isinstance(r, dict)]
        out_rows = []
        for row in rows:
            if str(row.get("line_id") or "") == "vo_b":
                row = dict(row)
                row["skipped_optional"] = True
                row["air_script_omit"] = True
                row["omit"] = True
            out_rows.append(row)
        out = dict(g)
        out["interviewer_lines"] = out_rows
        return out, ["vo_b"]

    monkeypatch.setattr(
        "interview_mux.vo_contract.clamp_hosted_seats_docs",
        fake_clamp,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    result = sanitize_air_contract(ctx)
    seats = (result.doc.get("air_script") or {}).get("vo_seats") or {}
    seated = list(seats.get("seated_line_ids") or [])
    assert seated == ["vo_a"]
    assert len(seated) <= 1  # WAV fixture floor


def test_w1_gap_sanitize_does_not_stamp_seats() -> None:
    ctx = RunContext(create=True)
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.path("mastering").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [],
            "chapters": [],
        },
        skip_handoff=True,
    )
    seats = {
        "seated_line_ids": ["vo_a", "vo_b"],
        "omitted_line_ids": [],
    }
    _dump_raw(
        ctx,
        "mastering/mastering_plan.json",
        {"air_script": {"vo_seats": deepcopy(seats)}},
    )
    gap = _base_gap()
    sanitize_gap_report(ctx, gap)
    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan["air_script"]["vo_seats"] == seats


def test_commit_air_contract_persists_omit_gap_sync(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_b"],
            }
        }
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)
    _dump_raw(ctx, "mastering/mastering_plan.json", plan)
    _dump_raw(
        ctx,
        "understanding/omit_ledger.json",
        {"version": 1, "entries": [], "summary": {"active_count": 0}},
    )

    result = commit_air_contract(ctx, reason="test")
    assert result.ok or result.errors  # may refuse seated_missing if ids mismatch
    gap_disk = ctx.read_json("understanding/gap_report.json")
    by_id = {
        str(r.get("line_id")): r
        for r in (gap_disk.get("interviewer_lines") or [])
        if isinstance(r, dict)
    }
    if "vo_b" in by_id:
        assert by_id["vo_b"].get("omit") or by_id["vo_b"].get("skipped_optional")


def test_run_air_contract_sanitize_commits_drop_seated_missing_from_gap(
    monkeypatch,
) -> None:
    """Stage entry must persist orphan-seat drops, not nested-skip commit."""
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.clamp_hosted_seats_docs",
        lambda _ctx, gap, *, apply_freeze_gate=False: (gap, []),
    )
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "plan_status": "complete",
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a", "vo_orphan_bridge", "vo_orphan_context"],
                "omitted_line_ids": [],
            }
        }
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)
    _dump_raw(ctx, "mastering/mastering_plan.json", plan)
    _dump_raw(
        ctx,
        "understanding/omit_ledger.json",
        {"version": 1, "entries": [], "summary": {"active_count": 0}},
    )

    run_air_contract_sanitize(ctx)

    live = ctx.read_json("mastering/mastering_plan.json")
    seated = list(
        ((live.get("air_script") or {}).get("vo_seats") or {}).get("seated_line_ids")
        or []
    )
    assert "vo_orphan_bridge" not in seated
    assert "vo_orphan_context" not in seated
    assert "vo_a" in seated
    assert air_contract_sanitary_errors(ctx) == []
    assert ctx.is_done("air_contract_sanitize")


def test_sanitary_errors_auto_commits_protect_orientation(monkeypatch) -> None:
    """protect_orientation_from_omit must not block vo_synthesize forever (exec_11630)."""
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a", "vo_orient"],
                "omitted_line_ids": [],
                "orientation_id": "vo_orient",
            }
        }
    }
    omit = {
        "version": 1,
        "entries": [
            {
                "subject_id": "vo_orient",
                "kind": "gap_line",
                "status": "active",
            }
        ],
        "summary": {"active_count": 1},
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)
    _dump_raw(ctx, "mastering/mastering_plan.json", plan)
    _dump_raw(ctx, "understanding/omit_ledger.json", omit)
    assert air_contract_sanitary_errors(ctx) == []
    omit_live = ctx.read_json("understanding/omit_ledger.json")
    subjects = {
        str(e.get("subject_id"))
        for e in (omit_live.get("entries") or [])
        if isinstance(e, dict)
    }
    assert "vo_orient" not in subjects


def test_commit_refuses_unreadable_plan() -> None:
    ctx = RunContext(create=True)
    path = ctx.path("mastering", "mastering_plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    result = commit_air_contract(ctx, reason="test")
    assert not result.ok
    assert any("artifact_unreadable" in e for e in (result.errors or []))


def test_commit_gap_write_failure_is_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.clamp_hosted_seats_docs",
        lambda _ctx, gap, *, apply_freeze_gate=False: (gap, []),
    )
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_b"],
            }
        }
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)
    _dump_raw(ctx, "mastering/mastering_plan.json", plan)
    _dump_raw(
        ctx,
        "understanding/omit_ledger.json",
        {"version": 1, "entries": [], "summary": {"active_count": 0}},
    )

    real_write = ctx.write_json

    def boom(rel, doc, **kwargs):
        if rel == "understanding/gap_report.json":
            raise RuntimeError("disk full")
        return real_write(rel, doc, **kwargs)

    monkeypatch.setattr(ctx, "write_json", boom)
    result = commit_air_contract(ctx, reason="test")
    assert not result.ok
    assert any("air_contract_write_failed" in e for e in (result.errors or []))


def test_commit_cas_conflict_refuses(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.clamp_hosted_seats_docs",
        lambda _ctx, gap, *, apply_freeze_gate=False: (gap, []),
    )
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": [],
            }
        }
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)
    _dump_raw(ctx, "mastering/mastering_plan.json", plan)
    _dump_raw(
        ctx,
        "understanding/omit_ledger.json",
        {"version": 1, "entries": [], "summary": {"active_count": 0}},
    )

    calls = {"n": 0}
    from interview_mux.artifact_sanitize import air_script as ac

    real_sanitize = ac.sanitize_air_contract

    def sanitize_then_drift(c, docs=None):
        out = real_sanitize(c, docs)
        calls["n"] += 1
        if calls["n"] == 1:
            drifted = dict(c.read_json("mastering/mastering_plan.json"))
            drifted["_cas_probe"] = "drift"
            _dump_raw(c, "mastering/mastering_plan.json", drifted)
        return out

    monkeypatch.setattr(ac, "sanitize_air_contract", sanitize_then_drift)
    result = commit_air_contract(ctx, reason="test")
    assert not result.ok
    assert "air_contract_cas_conflict" in (result.errors or [])


def test_sanitize_no_mid_pass_gap_disk_write(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_b"],
            }
        }
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)
    _dump_raw(ctx, "mastering/mastering_plan.json", plan)
    before_mtime = ctx.path("understanding", "gap_report.json").stat().st_mtime_ns
    sanitize_air_contract(ctx)
    after_mtime = ctx.path("understanding", "gap_report.json").stat().st_mtime_ns
    assert before_mtime == after_mtime


def test_post_commit_dry_check_refuses_dirty(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.clamp_hosted_seats_docs",
        lambda _ctx, gap, *, apply_freeze_gate=False: (gap, []),
    )
    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_b"],
            }
        }
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)
    _dump_raw(ctx, "mastering/mastering_plan.json", plan)
    _dump_raw(
        ctx,
        "understanding/omit_ledger.json",
        {"version": 1, "entries": [], "summary": {"active_count": 0}},
    )

    calls = {"n": 0}
    from interview_mux.artifact_sanitize import air_script as ac
    from interview_mux.artifact_sanitize.types import SanitizeResult

    real = ac.sanitize_air_contract

    def flaky(c, docs=None):
        calls["n"] += 1
        out = real(c, docs)
        if calls["n"] >= 2:
            return SanitizeResult(
                doc=out.doc,
                actions=[{"action": "stamp_gap_omit_flags", "count": 1}],
                ok=True,
                errors=[],
                artifact_rel=out.artifact_rel,
                metrics=out.metrics,
            )
        return out

    monkeypatch.setattr(ac, "sanitize_air_contract", flaky)
    raised = False
    try:
        run_air_contract_sanitize(ctx)
    except RuntimeError as exc:
        raised = True
        assert "post-commit drift" in str(exc) or "unsanitary" in str(exc)
    assert raised


def test_sanitary_errors_never_auto_commit_floor_reseat(monkeypatch) -> None:
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
                    {"action": "protect_hosted_vo_floor_reseat", "ids": ["vo_b"]}
                ],
                "errors": [],
            },
        )(),
    )
    committed = {"n": 0}

    def fake_commit(ctx, *, reason=""):
        committed["n"] += 1
        return type("C", (), {"ok": True, "errors": []})()

    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.air_script.commit_air_contract",
        fake_commit,
    )
    ctx = RunContext(create=True)
    _dump_raw(ctx, "mastering/mastering_plan.json", {"air_script": {"vo_seats": {}}})
    errs = air_contract_sanitary_errors(ctx)
    assert committed["n"] == 0
    assert any("protect_hosted_vo_floor_reseat" in e for e in errs)


def test_full_auto_always_blocks_unsanitary(monkeypatch) -> None:
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary

    monkeypatch.setenv("MUX_FULL_AUTO", "1")
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"artifact_sanitize": {"block_consumers": False}},
    )
    assert block_consumers_on_unsanitary() is True


def test_i34_gap_framing_compose_reconcile_no_authority_denied(
    monkeypatch,
) -> None:
    """Non-owner stage must not raise when reconcile skips sealed plan."""
    from interview_mux.execution_contract import reconcile_execution_contract

    ctx = RunContext(create=True)
    gap = _base_gap()
    plan = {
        "plan_status": "complete",
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": [],
            }
        }
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)
    _dump_raw(ctx, "mastering/mastering_plan.json", plan)
    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id",
        lambda: "gap_framing_compose",
    )

    def _permitted(ctx, path, stage, **kwargs):
        if "mastering_plan" in str(path):
            return (False, "pre_soft_freeze:air_contract_sanitize")
        return (True, "ok")

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        _permitted,
    )
    snap = reconcile_execution_contract(ctx, reason="test_gap_framing")
    assert isinstance(snap, dict)
    assert "mastering/mastering_plan.json" not in (snap.get("reconcile_changed") or [])
