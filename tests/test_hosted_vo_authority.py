"""Cluster C — hosted_vo_authority disposition + floor identity matrix."""

from __future__ import annotations

import json
import os

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.hosted_vo_authority import (
    FLOOR_IDENTITY_META_KEY,
    ORIENTATION_LINE_ID,
    assert_books_agree,
    decide_orientation,
    floor_snapshot,
    identify_hosted_vo_floor,
    may_aspirational_proceed,
    reconcile_escalations,
)
from interview_mux.opening_orientation import ensure_episode_orientation
from interview_mux.thrash_hardening import (
    FAIL_CLASS_DELIVERY_BLOCKED,
    canonical_resume_pin,
)
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def _write(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_identify_hollow_zero_persists(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_id")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_waived",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_warranted",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority.need",
        lambda _ctx: 3,
    )
    _write(ctx, "understanding/gap_report.json", {"interviewer_lines": []})
    ident = identify_hosted_vo_floor(ctx, persist=True)
    assert ident.status == "HOLLOW_ZERO"
    meta = ctx.read_json("run_meta.json")
    assert meta.get(FLOOR_IDENTITY_META_KEY, {}).get("status") == "HOLLOW_ZERO"
    assert not may_aspirational_proceed(ctx)


def test_may_aspirational_only_partial(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_partial")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_waived",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_warranted",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority.need",
        lambda _ctx: 3,
    )
    _write(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_1",
                    "text": "Host asks a substantive follow-up about the guest.",
                    "delivery": "synthesize",
                }
            ]
        },
    )
    ident = identify_hosted_vo_floor(ctx, persist=True)
    assert ident.status == "PARTIAL"
    assert may_aspirational_proceed(ctx)


def test_decide_heard_keep_beats_omit(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_heard")
    init_run_meta_for_test(ctx)
    wav = ctx.path("vo_pickup", "synthesized", f"{ORIENTATION_LINE_ID}.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"0" * 2000)
    gap = {
        "interviewer_lines": [],
        "opening_orientation": {
            "omitted": True,
            "omit_reason": "native_open_self_orients",
            "required": False,
        },
    }
    d = decide_orientation(ctx, gap, ["seg_001"])
    assert d.disposition == "HEARD_KEEP"
    assert d.force_remint


def test_decide_edl_only_heard_keep(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_edl")
    init_run_meta_for_test(ctx)
    _write(
        ctx,
        "master/edl.json",
        {
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": ORIENTATION_LINE_ID,
                    "duration_ms": 500,
                }
            ]
        },
    )
    gap = {
        "interviewer_lines": [],
        "opening_orientation": {
            "omitted": True,
            "required": False,
            "omit_reason": "native_open_self_orients",
        },
    }
    d = decide_orientation(ctx, gap, ["seg_001"])
    assert d.disposition == "HEARD_KEEP"
    assert d.force_remint is True  # gap still omits — remint required


def test_decide_heard_keep_no_remint_when_already_live(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_live")
    init_run_meta_for_test(ctx)
    wav = ctx.path("vo_pickup", "synthesized", f"{ORIENTATION_LINE_ID}.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"0" * 2000)
    gap = {
        "interviewer_lines": [
            {
                "line_id": ORIENTATION_LINE_ID,
                "text": "Welcome — today we sit with our guest on the show.",
                "delivery": "synthesize",
                "episode_orientation": True,
            }
        ],
        "opening_orientation": {
            "omitted": False,
            "required": True,
            "target_segment_id": "seg_001",
        },
    }
    d = decide_orientation(ctx, gap, ["seg_001"])
    assert d.disposition == "HEARD_KEEP"
    assert d.force_remint is False


def test_reconcile_clears_stale_aspirational_when_met(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_stale_asp")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_waived",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_warranted",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority.need",
        lambda _ctx: 3,
    )
    lines = [
        {
            "line_id": f"vo_layup_{i}",
            "text": f"Host line number {i} with enough substance for seat.",
            "delivery": "synthesize",
        }
        for i in range(3)
    ]
    _write(ctx, "understanding/gap_report.json", {"interviewer_lines": lines})
    meta = ctx.read_json("run_meta.json")
    meta["floor_aspirational_proceeded"] = True
    meta["aspirational_proceeded"] = True
    meta["floor_advisories"] = [
        {
            "gate_id": "hosted_vo_floor",
            "detail": {"have": 0, "need": 3, "pool_exhausted": True},
            "at": "2026-01-01T00:00:00+00:00",
        }
    ]
    ctx.write_json("run_meta.json", meta)
    snap = floor_snapshot(ctx, persist=True)
    assert snap.identity.status == "MET"
    reconcile_escalations(ctx, snap)
    meta2 = ctx.read_json("run_meta.json")
    assert not meta2.get("floor_aspirational_proceeded")
    assert not meta2.get("aspirational_proceeded")
    hollow = [
        a
        for a in (meta2.get("floor_advisories") or [])
        if isinstance(a, dict)
        and str(a.get("gate_id") or "") == "hosted_vo_floor"
        and int(((a.get("detail") or {}).get("have") or -1)) == 0
    ]
    assert hollow == []


def test_books_agree_detects_omit_vs_wav(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_books")
    init_run_meta_for_test(ctx)
    wav = ctx.path("vo_pickup", "synthesized", f"{ORIENTATION_LINE_ID}.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"0" * 2000)
    _write(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [],
            "opening_orientation": {
                "omitted": True,
                "required": False,
                "omit_reason": "native_open_self_orients",
            },
        },
    )
    errs = assert_books_agree(ctx)
    assert any("hosted_vo_books_agree" in e for e in errs)


def test_no_synthesize_pin_not_edl_narrative(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_pin")
    init_run_meta_for_test(ctx)
    pin = canonical_resume_pin(
        ctx,
        FAIL_CLASS_DELIVERY_BLOCKED,
        hint="Gap VO gate: no synthesize lines armed — compose first.",
    )
    assert pin in {"nugget_layup_compose", "gap_framing_compose"}
    assert pin != "edl_narrative_audit"


def test_reconcile_clears_escalation_triple(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_esc")
    init_run_meta_for_test(ctx)
    _write(
        ctx,
        "operator/escalations/nugget_layup_compose.json",
        {"status": "open", "reason": "hosted_vo_floor_unsatisfiable", "need": 3, "active": 0},
    )
    _write(
        ctx,
        "understanding/nugget_layup_plan.json",
        {"_meta": {"hosted_vo_floor_unsatisfiable": True}},
    )
    meta = ctx.read_json("run_meta.json")
    meta["hosted_vo_floor_unsatisfiable"] = True
    ctx.write_json("run_meta.json", meta)
    _write(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": ORIENTATION_LINE_ID,
                    "text": "Welcome to today's conversation with our guest.",
                    "delivery": "synthesize",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_waived",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_warranted",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority.need",
        lambda _ctx: 3,
    )
    snap = floor_snapshot(ctx, persist=True)
    assert snap.have >= 1
    reconcile_escalations(ctx, snap)
    esc = ctx.read_json("operator/escalations/nugget_layup_compose.json")
    assert str(esc.get("status") or "").lower() == "cleared"
    meta2 = ctx.read_json("run_meta.json")
    assert not meta2.get("hosted_vo_floor_unsatisfiable")


def test_ensure_force_keep_via_authority(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hvo_ensure")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority._floor_warranted",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.opening_orientation.native_open_already_orients",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.opening_orientation._fallback_orientation_text",
        lambda _ctx: ("Welcome — today we sit with our guest.", "test"),
    )
    gap = {
        "interviewer_lines": [],
        "opening_orientation": {
            "omitted": True,
            "omit_reason": "native_open_self_orients",
            "required": False,
            "target_segment_id": "seg_001",
        },
    }
    out, actions = ensure_episode_orientation(ctx, gap, ["seg_001", "seg_002"])
    lines = out.get("interviewer_lines") or []
    assert any(
        isinstance(ln, dict) and str(ln.get("text") or "").strip() for ln in lines
    ), actions
