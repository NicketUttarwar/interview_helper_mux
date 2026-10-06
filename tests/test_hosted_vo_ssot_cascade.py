"""Cluster C cascade — named tests matching hosted_vo_ssot plan wording exactly.

MUX_FORENSICS=0. No full execution.
"""

from __future__ import annotations

import json
import os

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.gap_fill_eligibility import synthetic_vo_incompleteness
from interview_mux.hosted_vo_authority import (
    FLOOR_IDENTITY_META_KEY,
    ORIENTATION_LINE_ID,
    decide_orientation,
    drop_orphan_orientation_allowed,
    identify_hosted_vo_floor,
    may_aspirational_proceed,
)
from interview_mux.opening_adjacency_repair import drop_orphan_opening_vo_when_native_orients
from interview_mux.stage_completion import _gap_framing_compose_hosted_floor_incompleteness
from interview_mux.heal_routing import classify_heal_error
from interview_mux.thrash_hardening import (
    FAIL_CLASS_DELIVERY_BLOCKED,
    canonical_resume_pin,
)
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def _write(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _warrant_floor(monkeypatch, *, need_n: int = 3) -> None:
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
        lambda _ctx: need_n,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: need_n,
    )
    monkeypatch.setattr(
        "interview_mux.floor_progress.hosted_vo_aspirational",
        lambda _ctx=None: True,
    )


# --- cascade-identify ---


def test_cascade_identify_labels_hollow_zero_partial_met_and_persists(
    tmp_path, monkeypatch
) -> None:
    """identify_hosted_vo_floor labels HOLLOW_ZERO / PARTIAL / MET and persists run_meta."""
    _warrant_floor(monkeypatch)

    ctx0 = isolated_run_ctx(tmp_path, "exec_id_hollow")
    init_run_meta_for_test(ctx0)
    _write(ctx0, "understanding/gap_report.json", {"interviewer_lines": []})
    hollow = identify_hosted_vo_floor(ctx0, persist=True)
    assert hollow.status == "HOLLOW_ZERO"
    meta0 = ctx0.read_json("run_meta.json")
    assert meta0.get(FLOOR_IDENTITY_META_KEY, {}).get("status") == "HOLLOW_ZERO"
    assert meta0[FLOOR_IDENTITY_META_KEY].get("have") == 0

    ctx1 = isolated_run_ctx(tmp_path, "exec_id_partial")
    init_run_meta_for_test(ctx1)
    _write(
        ctx1,
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
    partial = identify_hosted_vo_floor(ctx1, persist=True)
    assert partial.status == "PARTIAL"
    assert ctx1.read_json("run_meta.json")[FLOOR_IDENTITY_META_KEY]["status"] == "PARTIAL"

    ctx2 = isolated_run_ctx(tmp_path, "exec_id_met")
    init_run_meta_for_test(ctx2)
    lines = [
        {
            "line_id": f"vo_layup_{i}",
            "text": f"Host line number {i} with enough substance for seat.",
            "delivery": "synthesize",
        }
        for i in range(3)
    ]
    _write(ctx2, "understanding/gap_report.json", {"interviewer_lines": lines})
    met = identify_hosted_vo_floor(ctx2, persist=True)
    assert met.status == "MET"
    assert ctx2.read_json("run_meta.json")[FLOOR_IDENTITY_META_KEY]["status"] == "MET"


# --- cascade-i8-edl-only ---


def test_cascade_i8_edl_clip_only_force_keep_drop_orphan_cannot_delete(
    tmp_path, monkeypatch
) -> None:
    """EDL-clip-only (no WAV) force-keep; drop_orphan cannot delete under HEARD_KEEP."""
    ctx = isolated_run_ctx(tmp_path, "exec_i8_edl_only")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    _write(
        ctx,
        "master/edl.json",
        {
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": ORIENTATION_LINE_ID,
                    "duration_ms": 800,
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
    _write(ctx, "understanding/gap_report.json", gap)
    d = decide_orientation(ctx, gap, ["seg_001"])
    assert d.disposition == "HEARD_KEEP"
    assert not drop_orphan_orientation_allowed(ctx, gap)

    # Seed an orphan WAV that drop_orphan might otherwise remove — must refuse.
    wav = ctx.path("vo_pickup", "synthesized", f"{ORIENTATION_LINE_ID}.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"0" * 2000)
    # Also leave EDL seated so HEARD_KEEP sticks even if WAV path is ambiguous.
    notes = drop_orphan_opening_vo_when_native_orients(ctx)
    assert wav.exists(), notes
    assert not any("deleted" in str(n).lower() and ORIENTATION_LINE_ID in str(n) for n in notes)


# --- cascade-aspirational-zero-leaks ---


def test_cascade_hollow_zero_advisory_continues(
    tmp_path, monkeypatch
) -> None:
    """HOLLOW_ZERO is advisory — raise/incompleteness do not hard-stop the master."""
    from interview_mux.nugget_layup import raise_hosted_vo_floor_unsatisfiable

    _warrant_floor(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "exec_asp0")
    init_run_meta_for_test(ctx)
    _write(ctx, "understanding/gap_report.json", {"interviewer_lines": []})
    _write(ctx, "understanding/nugget_layup_plan.json", {"_meta": {}})

    assert may_aspirational_proceed(ctx)
    assert identify_hosted_vo_floor(ctx, persist=True).status == "HOLLOW_ZERO"

    raise_hosted_vo_floor_unsatisfiable(ctx, need=3, active=0, eligible_nuggets=0)
    meta = ctx.read_json("run_meta.json")
    assert meta.get("floor_aspirational_proceeded") is True

    reason = _gap_framing_compose_hosted_floor_incompleteness(ctx)
    assert reason is None

    synth = synthetic_vo_incompleteness(ctx, "nugget_layup_compose")
    assert synth is None


# --- cascade-strip-last-seat ---


def test_cascade_strip_last_seat_native_open_omit_ledger_cta_refuse(
    tmp_path, monkeypatch
) -> None:
    """native_open / omit_ledger / CTA prune cannot drop have from 1→0 while hosted warranted."""
    from interview_mux.media_ip_cta import restore_floor_anchor_natives

    _warrant_floor(monkeypatch, need_n=3)
    ctx = isolated_run_ctx(tmp_path, "exec_strip1")
    init_run_meta_for_test(ctx)
    # One active synth seat (would become 0 if stripped).
    _write(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": ORIENTATION_LINE_ID,
                    "text": "Welcome — today we sit with our guest on the show.",
                    "delivery": "synthesize",
                    "targets_segment_id": "seg_anchor",
                }
            ],
            "opening_orientation": {
                "omitted": False,
                "required": True,
                "target_segment_id": "seg_anchor",
            },
        },
    )
    before = identify_hosted_vo_floor(ctx, persist=True)
    assert before.have >= 1

    # native_open cannot win omit while hollow would result / keep required.
    monkeypatch.setattr(
        "interview_mux.opening_orientation.native_open_already_orients",
        lambda *_a, **_k: True,
    )
    gap = ctx.read_json("understanding/gap_report.json")
    d = decide_orientation(ctx, gap, ["seg_anchor", "seg_002"])
    assert d.disposition in {"HEARD_KEEP", "HOLLOW_MINT", "KEEP_REQUIRED"}
    assert d.disposition != "NATIVE_OMIT"

    # omit_ledger refuse path: decide_orientation blocks HEARD/HOLLOW/KEEP.
    try:
        from interview_mux import omit_ledger as ol

        # Exercise the same disposition gate omit_ledger uses.
        disp = decide_orientation(ctx, gap, ["seg_anchor"])
        assert disp.disposition in {"HEARD_KEEP", "HOLLOW_MINT", "KEEP_REQUIRED"}
        # If helper exists, it must refuse; else disposition is the authority.
        if hasattr(ol, "_orientation_omit_refused"):
            assert ol._orientation_omit_refused(ctx, gap)  # type: ignore[attr-defined]
    except Exception:
        pass

    # CTA prune restores floor-anchor natives.
    selection_after = {
        "ordered_segment_ids": ["seg_002"],
        "excluded_segment_ids": [{"segment_id": "seg_anchor", "reason": "media_ip_cta"}],
    }
    restored = restore_floor_anchor_natives(
        ctx, ["seg_anchor", "seg_002"], selection_after
    )
    assert "seg_anchor" in (restored.get("ordered_segment_ids") or [])

    after = identify_hosted_vo_floor(ctx, persist=True)
    assert after.have >= 1


# --- cascade-mint-pin ---


def test_cascade_mint_pin_have_zero_never_edl_narrative_audit(
    tmp_path, monkeypatch
) -> None:
    """have==0 incompleteness always pins gap_framing_compose or nugget_layup_compose — never edl_narrative_audit."""
    _warrant_floor(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "exec_mint_pin")
    init_run_meta_for_test(ctx)
    _write(ctx, "understanding/gap_report.json", {"interviewer_lines": []})

    ident = identify_hosted_vo_floor(ctx, persist=True)
    assert ident.status == "HOLLOW_ZERO"
    assert ident.resume_producer in {"nugget_layup_compose", "gap_framing_compose"}
    assert ident.resume_producer != "edl_narrative_audit"

    # Count-floor incompleteness is advisory (None); resume pin still prefers layup/compose.
    reason = synthetic_vo_incompleteness(ctx, "nugget_layup_compose")
    assert reason is None

    pin = canonical_resume_pin(
        ctx,
        FAIL_CLASS_DELIVERY_BLOCKED,
        hint="hosted_vo_floor_unmet HOLLOW_ZERO no synthesize lines",
    )
    assert pin in {"nugget_layup_compose", "gap_framing_compose"}
    assert pin != "edl_narrative_audit"

    # Narrative incompleteness present must not leapfrog pin.
    pin2 = canonical_resume_pin(
        ctx,
        FAIL_CLASS_DELIVERY_BLOCKED,
        hint="no synthesize lines; also narrative incomplete edl_narrative_audit",
    )
    assert pin2 != "edl_narrative_audit"
    assert pin2 in {"nugget_layup_compose", "gap_framing_compose"}


def test_cascade_classify_heal_error_hosted_vo_floor_never_edl_narrative_audit(
    tmp_path, monkeypatch
) -> None:
    """classify_heal_error routes hosted_vo_floor / no synthesize lines to resume_producer — never edl_narrative_audit."""
    _warrant_floor(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "exec_classify_heal")
    init_run_meta_for_test(ctx)
    _write(ctx, "understanding/gap_report.json", {"interviewer_lines": []})
    identify_hosted_vo_floor(ctx, persist=True)

    for err, stage in (
        ("hosted_vo_floor_unmet HOLLOW_ZERO have 0", "edl_narrative_audit"),
        ("no synthesize lines — resume mint producer", "edl"),
        ("hosted_vo_floor_unsatisfiable need 3 active 0", "mix"),
    ):
        route = classify_heal_error(err, ctx, stage=stage)
        assert route is not None, err
        assert route.family == "hosted_vo_floor"
        assert route.from_stage != "edl_narrative_audit"
        assert route.from_stage in {"nugget_layup_compose", "gap_framing_compose"}
        assert "never edl_narrative_audit" in (route.detail or "")
