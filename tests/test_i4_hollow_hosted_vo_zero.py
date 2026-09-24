"""i4: hosted G-Framing Yes must not aspirational-continue at zero synth seats.

Also: Gap VO ``no synthesize lines`` resume pins layup/compose — never edl_narrative_audit.
"""

from __future__ import annotations

import json

from interview_mux.gap_fill_eligibility import synthetic_vo_incompleteness
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


def test_i4_synthetic_vo_incompleteness_refuses_aspirational_at_zero(
    tmp_path, monkeypatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_i4_zero")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    monkeypatch.setattr(
        "interview_mux.floor_progress.hosted_vo_aspirational",
        lambda _ctx=None: True,
    )
    _write(ctx, "understanding/gap_report.json", {"interviewer_lines": []})
    reason = synthetic_vo_incompleteness(ctx, "nugget_layup_compose")
    assert reason is not None
    assert "have 0" in reason or "has 0" in reason
    assert "nugget_layup_compose" in reason


def test_i4_no_synthesize_lines_pin_is_layup_not_edl(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_i4_pin")
    init_run_meta_for_test(ctx)
    # Avoid music/phase-A walk — pin must short-circuit on hint alone.
    pin = canonical_resume_pin(
        ctx,
        FAIL_CLASS_DELIVERY_BLOCKED,
        hint="Gap VO gate: no synthesize lines armed — compose or rewrite record→synth first.",
    )
    # HG-5: plan on disk → nugget_layup_compose; else analysis-era gap_framing_compose.
    assert pin in {"nugget_layup_compose", "gap_framing_compose"}
    assert pin != "edl_narrative_audit"


def test_i4_force_orientation_when_hosted_zero_despite_omit(
    tmp_path, monkeypatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_i4_orient")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.count_active_gap_vo_lines",
        lambda _ctx: 0,
    )
    monkeypatch.setattr(
        "interview_mux.opening_orientation.native_open_already_orients",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.opening_orientation._fallback_orientation_text",
        lambda _ctx: ("Welcome — today we sit with our guest.", "test"),
    )
    # Durable omit that used to short-circuit remint.
    gap = {
        "interviewer_lines": [],
        "opening_orientation": {
            "omitted": True,
            "omit_reason": "native_open_self_orients",
            "required": False,
            "target_segment_id": "seg_001",
        },
    }
    out, actions = ensure_episode_orientation(
        ctx, gap, ["seg_001", "seg_002"]
    )
    lines = out.get("interviewer_lines") or []
    assert any(
        isinstance(ln, dict) and str(ln.get("text") or "").strip() for ln in lines
    ), actions
    assert not (out.get("opening_orientation") or {}).get("omitted")
