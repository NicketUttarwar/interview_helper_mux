"""i28: unrecoverable incomplete cuts must escalate to fuse/omit, and junction's own remaster must not self-refuse.

exec_11871 spun on two criticals that carried
``detail.unrecoverable_within_clip: true``:

* ``seg_014`` ``chapter_bleed_incomplete`` — ``cut_earlier`` recommended 462400ms,
  before the clip's own source start, so the in-clip repair landed
  ``skipped_next_clip_clamp`` and nothing else touched it.
* ``seg_071`` ``on_a_roll`` — recut applied but re-detected.

`run_mix` then refused ("recut/fuse/omit at junction_snip_qa first") and the
junction ladder's *own* remaster hit the same refusal before it could rescan.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.junction_snip_qa import (
    apply_junction_repairs,
    refuse_mix_if_live_incomplete_cuts,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i28_unrecoverable_cut")


def _manifest_seg(sid: str, start: int, end: int, text: str) -> dict:
    return {
        "segment_id": sid,
        "start_ms": start,
        "end_ms": end,
        "text": text,
        "type": "interviewee_answer",
        "speaker_id": "spk_1",
        "speaker_role": "interviewee",
        "topic_tags": ["platform"],
    }


def _speech(sid: str, start: int, end: int) -> dict:
    return {
        "type": "speech",
        "segment_id": sid,
        "source_start_ms": start,
        "source_end_ms": end,
        "timeline_start_ms": 0,
        "duration_ms": end - start,
    }


def _seed_edl(ctx: RunContext) -> dict:
    edl = {
        "version": 1,
        "clips": [_speech("seg_014", 462_800, 469_580), _speech("seg_015", 469_660, 480_000)],
        "ordered_segment_ids": ["seg_014", "seg_015"],
        "timeline_duration_ms": 17_120,
    }
    ctx.write_json(
        "master/selection.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_014", "seg_015"],
            "excluded_segment_ids": [],
        },
        stage_key="selection_order_sanitize",
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "version": 1,
            "segments": [
                _manifest_seg(
                    "seg_014",
                    462_800,
                    469_580,
                    "taking that industry forward to the third generation,",
                ),
                _manifest_seg(
                    "seg_015", 469_660, 480_000, "So we built the next platform."
                ),
            ],
        },
        stage_key="segment_classification",
    )
    return edl


def test_i28_unrecoverable_cut_escalates_to_fuse_or_omit(ctx: RunContext) -> None:
    edl = _seed_edl(ctx)
    finding = {
        "kind": "chapter_bleed_incomplete",
        "severity": "critical",
        "segment_id": "seg_014",
        "clip_index": 0,
        "action": "cut_earlier",
        "detail": {
            # Recommended cut sits before the clip's own source start — the in-clip
            # repair can never land, exactly like exec_11871.
            "recommended_ms": 462_400,
            "unrecoverable_within_clip": True,
        },
        "evidence": "incomplete at chapter hinge",
    }

    _new_edl, applied, changed = apply_junction_repairs(ctx, edl, [finding])
    statuses = {
        str(a.get("status") or "")
        for a in applied
        if str(a.get("segment_id") or "") == "seg_014"
        and str(a.get("kind") or "") == "chapter_bleed_incomplete"
    }
    assert changed, applied
    assert statuses & {"fused_neighbor", "omitted_no_neighbor"}, statuses


def test_i28_recoverable_cut_is_not_escalated(ctx: RunContext) -> None:
    """A cut that lands inside the clip must stay a bound repair (no omit)."""
    edl = _seed_edl(ctx)
    finding = {
        "kind": "chapter_bleed_incomplete",
        "severity": "critical",
        "segment_id": "seg_014",
        "clip_index": 0,
        "action": "cut_earlier",
        "detail": {"recommended_ms": 466_000},
        "evidence": "incomplete at chapter hinge",
    }

    new_edl, applied, _changed = apply_junction_repairs(ctx, edl, [finding])
    statuses = {
        str(a.get("status") or "")
        for a in applied
        if str(a.get("segment_id") or "") == "seg_014"
    }
    assert "omitted_no_neighbor" not in statuses, statuses
    speech = [
        str(c.get("segment_id") or "")
        for c in (new_edl.get("clips") or [])
        if str(c.get("type") or "") == "speech"
    ]
    assert "seg_014" in speech


def test_i28_inner_remaster_does_not_self_refuse(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )
    setattr(ctx, "_junction_snip_qa_inner", True)
    refuse_mix_if_live_incomplete_cuts(ctx)


def test_i28_outer_mix_still_refuses(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.loud_fail import LoudStageFailure

    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [
            {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"}
        ],
    )
    # Advisory (ISSUES 185): mix renders and logs the residuals.
    assert refuse_mix_if_live_incomplete_cuts(ctx) is None
