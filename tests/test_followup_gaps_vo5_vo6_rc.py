"""Follow-up gaps: VO5 lease suppress, VO6 freshness stems, RC3/RC11, fingerprint producer skip."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import artifact_usable


def test_vo_synth_lease_suppresses_spoken_cascade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "vo5_lease")
    line0 = {
        "line_id": "vo_a",
        "gap_type": "clarify",
        "targets_segment_id": "seg_001",
        "placement": "before",
        "delivery": "synthesize",
        "text": "What changed next?",
    }
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [line0]},
        skip_handoff=True,
    )
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise RuntimeError("cascade should not run under lease")

    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.maybe_propagate_gap_spoken_text_change",
        _boom,
    )
    setattr(ctx, "_vo_synth_lease", 1)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {**line0, "text": "What changed after that?"},
            ]
        },
        skip_handoff=True,
    )
    assert called["n"] == 0


def test_spoken_cascade_fail_closed_when_consumers_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "vo5_fail_closed")
    line0 = {
        "line_id": "vo_a",
        "gap_type": "clarify",
        "targets_segment_id": "seg_001",
        "placement": "before",
        "delivery": "synthesize",
        "text": "Before.",
    }
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [line0]},
        skip_handoff=True,
    )
    # Hollow-force guard refuses mark_done(edl) without a real EDL — pin is_done.
    monkeypatch.setattr(ctx, "is_done", lambda sid: sid == "edl")

    def _boom(*_a, **_k):
        raise RuntimeError("cascade blew up")

    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.maybe_propagate_gap_spoken_text_change",
        _boom,
    )
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit._SPOKEN_TEXT_CASCADE_STAGES",
        ("edl",),
    )
    with pytest.raises(RuntimeError, match="fail-closed"):
        ctx.write_json(
            "understanding/gap_report.json",
            {"interviewer_lines": [{**line0, "text": "After."}]},
        )


def test_gap_row_stem_requires_fresh_resolve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.vo_contract import _gap_row_has_pickup_stem
    import interview_mux.vo_synthesis_audit as vo_audit

    ctx = isolated_run_ctx(tmp_path, "vo6_stem")
    row = {"line_id": "vo_x", "targets_segment_id": "seg_001", "text": "Hello."}
    pickup = ctx.path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)
    (pickup / "vo_x.wav").write_bytes(b"RIFF" + b"\x00" * 100)

    # Stem helper is existence-only (clamp floor). Resolve/fresh are separate.
    monkeypatch.setattr(
        "interview_mux.stages.assembly.resolve_vo_pickup_path",
        lambda *_a, **_k: None,
    )
    assert _gap_row_has_pickup_stem(ctx, row) is True
    assert vo_audit.line_vo_wav_fresh(ctx, row)[0] is False

    monkeypatch.setattr(
        "interview_mux.stages.assembly.resolve_vo_pickup_path",
        lambda *_a, **_k: pickup / "vo_x.wav",
    )
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.line_vo_wav_fresh",
        lambda *_a, **_k: (False, "qc_pass_false"),
    )
    assert _gap_row_has_pickup_stem(ctx, row) is True
    assert vo_audit.line_vo_wav_fresh(ctx, row)[0] is False

    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.line_vo_wav_fresh",
        lambda *_a, **_k: (True, "ok"),
    )
    assert _gap_row_has_pickup_stem(ctx, row) is True
    assert vo_audit.line_vo_wav_fresh(ctx, row)[0] is True

    (pickup / "vo_x.wav").unlink()
    assert _gap_row_has_pickup_stem(ctx, row) is False


def test_artifact_usable_skips_fingerprint_for_own_producer(
    tmp_path: Path,
) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.artifact_lifecycle import fingerprint_artifact, _record_fingerprint

    ctx = isolated_run_ctx(tmp_path, "fp_own")
    doc = {
        "thesis": "t",
        "topics": [{"topic_id": "t1", "name": "N", "summary": "S", "segment_ids": ["seg_001"]}],
        "ordered_topic_ids": ["t1"],
    }
    fp = fingerprint_artifact(doc, "content_context")
    ctx.write_json("understanding/content_brief.json", fp, skip_handoff=True)
    _record_fingerprint(
        ctx,
        "understanding/content_brief.json",
        str((fp.get("_meta") or {}).get("content_hash") or "old"),
        "content_context",
    )
    # Rewrite body without restamping run_meta fingerprint.
    doc2 = dict(fp)
    doc2["thesis"] = "changed"
    ctx.write_json("understanding/content_brief.json", doc2, skip_handoff=True)
    ok, reason = artifact_usable(
        ctx, "understanding/content_brief.json", consumer="content_brief_reanchor"
    )
    assert ok is True
    assert reason == ""


def test_is_halted_respects_live_cascade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.identical_failures import (
        failure_signature_by_class,
        is_halted,
        record_class_failure,
    )

    ctx = isolated_run_ctx(tmp_path, "rc3_halt")
    # Force a halted row on disk.
    for _ in range(5):
        record_class_failure(ctx, failed_stage="edl", error_class="vo_seated_coverage")
    sig = failure_signature_by_class(failed_stage="edl", error_class="vo_seated_coverage")
    assert is_halted(ctx, sig) is True
    monkeypatch.setattr(
        "interview_mux.execution_contract.failure_in_active_policy_cascade",
        lambda *_a, **_k: True,
    )
    assert is_halted(ctx, sig) is False


def test_automated_markers_include_sanitize_class() -> None:
    """Sanitize refuse / unsanitary is a hard halt (operator stamp), not auto-classified."""
    from interview_mux.operator_gates import (
        is_automated_classified_block,
        is_operator_gate,
        should_stamp_needs_operator,
    )

    reason_sel = "selection_unsanitary — resume selection_order_sanitize: depth"
    reason_gap = "gap_unsanitary — resume gap_report_sanitize: duplicate"
    assert is_automated_classified_block(reason_sel) is False
    assert is_automated_classified_block(reason_gap) is False
    assert is_operator_gate(None, reason_sel) is True
    assert is_operator_gate(None, reason_gap) is True
    meta = {"partial_auto": True, "homunculus_version": "0.1.0"}
    assert should_stamp_needs_operator("nugget_layup_compose", reason_sel, meta=meta) is True
    assert should_stamp_needs_operator("vo_line_adjudicate", reason_gap, meta=meta) is True
