"""Cascade: gap_framing_compose S1–S5 simplify (MUX_FORENSICS=0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.artifact_repairs import repair_gap_report
from interview_mux.run_context import RunContext
from interview_mux.stages.gaps import (
    ComposeAuthorityGate,
    _gap_framing_compose_payload,
    compose_authority_gate,
)
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "gfc_s1_s5")


def _write_raw(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_s2_compose_authority_gate_orphan_vs_noop(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.freeze_write_allowed",
        lambda *_a, **_k: True,
    )
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {"nugget_layup_authority": True, "interviewer_lines": []},
    )
    gate = compose_authority_gate(ctx)
    assert gate == ComposeAuthorityGate("clear_orphan_and_run", "orphan_layup_stamp")

    _write_raw(
        ctx,
        "understanding/nugget_layup_plan.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "lines": [{"line_id": "vo_1", "text": "Host."}],
        },
    )
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {"nugget_layup_authority": True, "interviewer_lines": []},
    )
    gate2 = compose_authority_gate(ctx)
    assert gate2.action == "noop_publish"
    assert gate2.why == "layup_authority"


def test_s5_payload_does_not_mint_speaker_delivery_plan(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes: list[str] = []

    def _boom_write(*_a, **_k):
        writes.append("write")
        raise AssertionError("compose must not mint speaker_delivery_plan")

    monkeypatch.setattr(
        "interview_mux.speaker_delivery_plan.write_speaker_delivery_plan",
        _boom_write,
    )
    monkeypatch.setattr(
        "interview_mux.speaker_delivery_plan.build_speaker_delivery_plan",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("compose must not build/mint SDP")
        ),
    )
    _write_raw(ctx, "understanding/content_brief.json", {"thesis": "t", "topics": []})
    _write_raw(ctx, "understanding/gap_evaluations.json", {"evaluations": []})
    _write_raw(ctx, "mastering/mastering_plan.json", {"plan_status": "degraded"})
    payload = _gap_framing_compose_payload(ctx)
    assert not payload.get("speaker_delivery_plan")
    assert writes == []

    _write_raw(
        ctx,
        "understanding/speaker_delivery_plan.json",
        {
            "address_labels": {"spk_1": "Alex"},
            "clone_speaker_id": "spk_1",
            "speaker_count": 2,
        },
    )
    payload2 = _gap_framing_compose_payload(ctx)
    assert payload2.get("address_labels") == {"spk_1": "Alex"}
    assert payload2.get("speaker_delivery_plan", {}).get("clone_speaker_id") == "spk_1"
    assert writes == []


def test_s3_spoken_copy_block_grounded_or_omit_not_loud_fail(ctx: RunContext) -> None:
    _write_raw(
        ctx,
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_010",
                    "type": "speech",
                    "speaker_id": "spk_1",
                    "speaker_role": "guest",
                    "topic_tags": [],
                    "text": "We rebuilt the launch timeline around weeks not months.",
                    "start_ms": 0,
                    "end_ms": 1000,
                }
            ]
        },
    )
    _write_raw(
        ctx,
        "understanding/content_brief.json",
        {"thesis": "launch timing", "topics": ["timing"]},
    )
    doc = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_seg_010",
                "text": "Coming up next in this clip segment chapter.",
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": "seg_010",
                "required": True,
                "line_category": "episode_preface",
                "severity": "high",
            }
        ]
    }
    repaired, actions = repair_gap_report(ctx, doc)
    assert isinstance(repaired.get("interviewer_lines"), list)
    # Must not raise; soft grounded seed or omit-leave-incomplete is enough.
    assert all(
        str(a.get("action") or "") != "spoken_copy_unhealable" for a in actions
    )

def test_s6_stamp_stages_cannot_rewrite_gap_body_text(ctx: RunContext) -> None:
    """Safest S6: sanitize/VO stamp omit/delivery only — body text = compose|layup."""
    from interview_mux.artifact_ownership import (
        AuthorityDenied,
        assert_gap_report_body_sole_writer,
        write_permitted,
    )

    ok, reason = write_permitted(
        ctx,
        "understanding/gap_report.json",
        "gap_report_sanitize",
        role="producer",
        verb="persist",
        fields=("interviewer_lines[].skipped_optional",),
    )
    assert ok is True, reason
    prior = {
        "interviewer_lines": [
            {"line_id": "vo_1", "text": "Original host line.", "targets_segment_id": "seg_001"}
        ]
    }
    new = {
        "interviewer_lines": [
            {"line_id": "vo_1", "text": "Sanitizer rewrote body.", "targets_segment_id": "seg_001"}
        ]
    }
    with pytest.raises(AuthorityDenied):
        assert_gap_report_body_sole_writer(
            ctx, stage_key="gap_report_sanitize", prior=prior, new=new
        )


def test_s9_floor_incompleteness_peeled_under_layup_stamp(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Safest S9: live layup stamp + plan → compose ignores hosted floor."""
    from interview_mux.stage_completion import (
        _gap_framing_compose_hosted_floor_incompleteness,
    )

    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.gap_fill_was_skipped",
        lambda _ctx: False,
    )
    _write_raw(
        ctx,
        "understanding/nugget_layup_plan.json",
        {"ordered_segment_ids": ["seg_001"], "lines": [{"line_id": "vo_1", "text": "Host."}]},
    )
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "nugget_layup_authority": True,
            "interviewer_lines": [],
            "_meta": {"producer": "nugget_layup_compose"},
        },
    )
    assert _gap_framing_compose_hosted_floor_incompleteness(ctx) is None

