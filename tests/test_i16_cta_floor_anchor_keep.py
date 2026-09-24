"""i16: CTA omit must not drop natives that hosted VO floor still targets.

exec_13177 residual: CTA prune removed floor-line targets → topup skipped
``tid not in live`` → hosted_vo_floor_unmet after a "successful" omit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.media_ip_cta import (
    floor_anchor_keep_ids,
    restore_floor_anchor_natives,
    run_cta_prune,
)
from interview_mux.run_context import RunContext
from interview_mux.stages.analysis_extended import commit_layup_cta_selection
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i16_cta_floor")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    monkeypatch.setattr(
        "interview_mux.media_ip_cta.enabled",
        lambda _ctx: True,
    )
    return run


def _seed(ctx: RunContext) -> None:
    segs = []
    ordered = []
    t = 0
    for sid, text in [
        ("seg_a", "Subscribe for more cancer science updates."),
        ("seg_b", "Please follow us on social media."),
        ("seg_c", "Thanks for listening — leave a review."),
        ("seg_d", "Useful clinical insight about trial design."),
    ]:
        segs.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_1",
                "speaker_role": "interviewee",
                "type": "interviewee_answer",
                "topic_tags": ["origin"],
                "text": text,
                "start_ms": t,
                "end_ms": t + 4000,
            }
        )
        ordered.append(sid)
        t += 5000
    ctx.write_json("segments/manifest.json", {"segments": segs}, skip_handoff=True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ordered, "excluded_segment_ids": []},
        skip_handoff=True,
    )
    lines = [
        minimal_gap_line(
            line_id="vo_floor_a",
            text="What led you into oncology?",
            delivery="synthesize",
            targets_segment_id="seg_a",
        ),
        minimal_gap_line(
            line_id="vo_floor_b",
            text="How does the trial design work?",
            delivery="synthesize",
            targets_segment_id="seg_b",
        ),
        minimal_gap_line(
            line_id="vo_floor_c",
            text="What should patients know next?",
            delivery="synthesize",
            targets_segment_id="seg_c",
        ),
    ]
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(*lines),
        skip_handoff=True,
    )


def test_floor_anchor_keep_ids_when_proposed_drops_targets(ctx: RunContext) -> None:
    _seed(ctx)
    keep = floor_anchor_keep_ids(ctx, ["seg_d"])
    assert keep == {"seg_a", "seg_b", "seg_c"}


def test_restore_floor_anchors_after_cta_drop(ctx: RunContext) -> None:
    _seed(ctx)
    before = ["seg_a", "seg_b", "seg_c", "seg_d"]
    after = {
        "ordered_segment_ids": ["seg_d"],
        "excluded_segment_ids": [
            {"segment_id": "seg_a", "reason": "hard_omit_sponsor_or_cta"},
            {"segment_id": "seg_b", "reason": "hard_omit_sponsor_or_cta"},
            {"segment_id": "seg_c", "reason": "hard_omit_sponsor_or_cta"},
        ],
        "exclude_rationales": {
            "seg_a": "hard_omit_sponsor_or_cta",
            "seg_b": "hard_omit_sponsor_or_cta",
            "seg_c": "hard_omit_sponsor_or_cta",
        },
    }
    restored = restore_floor_anchor_natives(ctx, before, after)
    ordered = restored["ordered_segment_ids"]
    assert "seg_a" in ordered and "seg_b" in ordered and "seg_c" in ordered
    excl_ids = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in (restored.get("excluded_segment_ids") or [])
    }
    assert not {"seg_a", "seg_b", "seg_c"} & excl_ids


def test_run_cta_prune_keeps_floor_anchors(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(ctx)
    monkeypatch.setattr(
        "interview_mux.homunculus.values.should_hard_omit_cta",
        lambda text: "subscribe" in text.casefold()
        or "follow us" in text.casefold()
        or "leave a review" in text.casefold(),
    )
    # Prefer-drop path adds judgments for CTA text; force via judgments.
    judgments = [
        {"segment_id": "seg_a", "clearly_media_ip_pitch": True, "action": "omit"},
        {"segment_id": "seg_b", "clearly_media_ip_pitch": True, "action": "omit"},
        {"segment_id": "seg_c", "clearly_media_ip_pitch": True, "action": "omit"},
    ]
    sel = ctx.read_json("master/selection.json")
    out = run_cta_prune(ctx, sel, judgments=judgments, notes=["i16"])
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    assert "seg_a" in ordered
    assert "seg_b" in ordered
    assert "seg_c" in ordered


def test_commit_layup_cta_selection_restores_floor_anchors(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(ctx)
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        lambda _ctx: False,
    )
    prev = ctx.read_json("master/selection.json")
    pruned = {
        "ordered_segment_ids": ["seg_d"],
        "excluded_segment_ids": [
            {"segment_id": "seg_a", "reason": "cta"},
            {"segment_id": "seg_b", "reason": "cta"},
            {"segment_id": "seg_c", "reason": "cta"},
        ],
    }
    # Restore brings anchors back → order matches previous → commit is a no-op
    # (None), which is the correct outcome (CTA cannot starve the floor).
    landed = commit_layup_cta_selection(ctx, prev, pruned)
    assert landed is None
    # Dropping only a non-anchor CTA sibling still commits.
    pruned2 = {
        "ordered_segment_ids": ["seg_a", "seg_b", "seg_c"],
        "excluded_segment_ids": [{"segment_id": "seg_d", "reason": "cta"}],
    }
    # seg_d is not a floor target — but we need a CTA-looking drop of a
    # non-anchor. Use an extra native that is not a floor target.
    prev2 = {
        "ordered_segment_ids": ["seg_a", "seg_b", "seg_c", "seg_d"],
        "excluded_segment_ids": [],
    }
    landed2 = commit_layup_cta_selection(ctx, prev2, pruned2)
    assert landed2 is not None
    assert "seg_d" not in [
        str(s) for s in (landed2.get("ordered_segment_ids") or []) if s
    ]
    assert {"seg_a", "seg_b", "seg_c"}.issubset(
        {str(s) for s in (landed2.get("ordered_segment_ids") or []) if s}
    )
