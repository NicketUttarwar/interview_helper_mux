"""Stage #45: layup CTA selection commit + ownership heal pin (exec_13177).

Keeps surgical CTA omit, useful siblings on air, soft-freeze commit via End-A
packaging, hard-freeze skip, and hosted floor seat before done.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_ownership import (
    assert_write,
    heal_pin_for,
    row_for_path,
    write_permitted,
    AuthorityDenied,
)
from interview_mux.mix_junction_seat import SHIP_OMIT_PRODUCER_ACTIONS
from interview_mux.run_context import RunContext
from interview_mux.seat_authority import (
    hard_freeze_action_permitted,
    stamp_hard_seat_freeze,
    stamp_soft_seat_freeze,
)
from interview_mux.stages.analysis_extended import (
    _heal_nugget_layup_compose_if_complete,
    commit_layup_cta_selection,
)
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "layup_sel_commit")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _seed_selection_manifest(ctx: RunContext, rows: list[tuple[str, str]]) -> None:
    """Manifest + selection with schema-complete segments for CTA commit tests."""
    segs = []
    ordered = []
    t = 0
    for sid, text in rows:
        segs.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_0",
                "speaker_role": "interviewer",
                "type": "interviewer_question",
                "topic_tags": ["origin"],
                "text": text,
                "start_ms": t,
                "end_ms": t + 4000,
            }
        )
        ordered.append(sid)
        t += 5000
    ctx.write_json(
        "segments/manifest.json", {"segments": segs}, skip_handoff=True
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ordered, "excluded_segment_ids": []},
        skip_handoff=True,
    )


def test_selection_denies_nugget_layup_compose(ctx: RunContext) -> None:
    """S7: layup is not a selection.json producer."""
    row = row_for_path("master/selection.json")
    assert row is not None
    assert "nugget_layup_compose" not in row.producers
    ok, reason = write_permitted(
        ctx, "master/selection.json", "nugget_layup_compose", verb="persist"
    )
    assert ok is False
    assert "not_allow" in reason


def test_selection_deny_suggests_sanitize_not_junction(ctx: RunContext) -> None:
    """Non-producer deny under pre_soft must pin sanitize, not junction (S7)."""
    ok, reason = write_permitted(
        ctx, "master/selection.json", "selection_framing_apply", verb="persist"
    )
    # Paid framing-apply is a selection producer; deny still pins sanitize.
    if ok is False:
        assert "not_allow" in reason
        assert "selection_order_sanitize" in reason
        with pytest.raises(AuthorityDenied) as caught:
            assert_write(ctx, "master/selection.json", "selection_framing_apply")
        assert caught.value.suggested_owner == "selection_order_sanitize"
    else:
        assert_write(ctx, "master/selection.json", "selection_framing_apply")
    assert heal_pin_for("master/selection.json", ctx=ctx) == "selection_order_sanitize"


def test_ship_omit_maps_ranking_sanitize_and_media_ip_cta() -> None:
    assert SHIP_OMIT_PRODUCER_ACTIONS.get("media_ip_cta") == "media_ip_cta"
    assert SHIP_OMIT_PRODUCER_ACTIONS.get("full_master_ranking") == "media_ip_cta"
    assert SHIP_OMIT_PRODUCER_ACTIONS.get("selection_order_sanitize") == "media_ip_cta"
    assert "nugget_layup_compose" not in SHIP_OMIT_PRODUCER_ACTIONS
    assert (
        SHIP_OMIT_PRODUCER_ACTIONS.get("media_ip_cta.heal_on_air_cta_residue")
        == "heal_on_air_cta"
    )
    assert hard_freeze_action_permitted("media_ip_cta", ctx=None) is True


def test_commit_layup_cta_drops_cta_keeps_siblings(ctx: RunContext) -> None:
    _seed_selection_manifest(
        ctx,
        [
            ("seg_003b", "Welcome to today's conversation about cancer science."),
            ("seg_003c", "Our guest brings decades of clinical research."),
            (
                "seg_003ga",
                "Before we begin, stay up by hitting the subscribe button.",
            ),
        ],
    )
    out = commit_layup_cta_selection(
        ctx,
        {
            "ordered_segment_ids": ["seg_003b", "seg_003c", "seg_003ga"],
            "excluded_segment_ids": [],
        },
        {
            "ordered_segment_ids": ["seg_003b", "seg_003c"],
            "excluded_segment_ids": [
                {"segment_id": "seg_003ga", "reason": "media_ip_cta"}
            ],
        },
    )
    assert out is not None
    ordered = ctx.read_json("master/selection.json")["ordered_segment_ids"]
    assert ordered == ["seg_003b", "seg_003c"]
    assert "seg_003ga" not in ordered


def test_soft_freeze_still_commits_cta(ctx: RunContext) -> None:
    _seed_selection_manifest(
        ctx,
        [
            ("seg_001", "Useful interview beat about the guest's work."),
            (
                "seg_cta",
                "Before we begin, hit the subscribe button and leave a comment.",
            ),
        ],
    )
    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    out = commit_layup_cta_selection(
        ctx,
        {"ordered_segment_ids": ["seg_001", "seg_cta"], "excluded_segment_ids": []},
        {
            "ordered_segment_ids": ["seg_001"],
            "excluded_segment_ids": [{"segment_id": "seg_cta", "reason": "media_ip_cta"}],
        },
    )
    assert out is not None
    assert ctx.read_json("master/selection.json")["ordered_segment_ids"] == ["seg_001"]


def test_hard_freeze_skips_cta_commit(ctx: RunContext) -> None:
    _seed_selection_manifest(
        ctx,
        [
            ("seg_001", "Useful interview beat about the guest's work."),
            (
                "seg_cta",
                "Before we begin, hit the subscribe button and leave a comment.",
            ),
        ],
    )
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    out = commit_layup_cta_selection(
        ctx,
        {"ordered_segment_ids": ["seg_001", "seg_cta"], "excluded_segment_ids": []},
        {
            "ordered_segment_ids": ["seg_001"],
            "excluded_segment_ids": [{"segment_id": "seg_cta", "reason": "media_ip_cta"}],
        },
    )
    assert out is None
    assert ctx.read_json("master/selection.json")["ordered_segment_ids"] == [
        "seg_001",
        "seg_cta",
    ]


def test_execute_cta_omit_uses_live_layup_stage_key(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.media_ip_cta import execute_cta_omit_from_needs

    monkeypatch.setattr("interview_mux.media_ip_cta.enabled", lambda _c: True)
    _seed_selection_manifest(
        ctx,
        [
            ("seg_003b", "Welcome to today's conversation about cancer science."),
            (
                "seg_003ga",
                "Before we begin, stay up on the latest episodes by "
                "hitting the subscribe button.",
            ),
        ],
    )
    stage_keys: list[str] = []
    from interview_mux import air_order_boundary as boundary

    real = boundary.commit_selection_mutation

    def _spy(c, sel, **kwargs):  # type: ignore[no-untyped-def]
        stage_keys.append(str(kwargs.get("stage_key") or ""))
        return real(c, sel, **kwargs)

    monkeypatch.setattr(boundary, "commit_selection_mutation", _spy)
    enter_stage_staging("nugget_layup_compose")
    try:
        dropped = execute_cta_omit_from_needs(
            ctx,
            [
                {
                    "type": "rerun_stage",
                    "stage": "selection",
                    "blocking": True,
                    "reason": "Remove seg_003ga subscribe CTA scrap",
                }
            ],
        )
    finally:
        exit_stage_staging()
    assert "seg_003ga" in dropped
    assert "nugget_layup_compose" in stage_keys
    ordered = ctx.read_json("master/selection.json")["ordered_segment_ids"]
    assert "seg_003b" in ordered
    assert "seg_003ga" not in ordered


def test_execute_cta_omit_keeps_reverse_jump_destination(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.media_ip_cta import execute_cta_omit_from_needs

    monkeypatch.setattr("interview_mux.media_ip_cta.enabled", lambda _c: True)
    _seed_selection_manifest(
        ctx,
        [
            (
                "seg_003ga",
                "Before we begin, stay up on the latest by hitting "
                "the subscribe button.",
            ),
            (
                "seg_054",
                "Yeah, and so this is early detection of the tumor changing.",
            ),
        ],
    )
    dropped = execute_cta_omit_from_needs(
        ctx,
        [
            {
                "type": "rerun_stage",
                "stage": "selection",
                "blocking": True,
                "reason": (
                    "Remove seg_003ga (subscribe CTA); reverse jump into seg_054"
                ),
            }
        ],
    )
    assert "seg_003ga" in dropped
    assert "seg_054" not in dropped
    ordered = ctx.read_json("master/selection.json")["ordered_segment_ids"]
    assert "seg_054" in ordered
    assert "seg_003ga" not in ordered


def test_heal_calls_ensure_hosted_floor_before_done(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    def _ensure(_c):  # type: ignore[no-untyped-def]
        called.append("ensure")
        return []

    monkeypatch.setattr(
        "interview_mux.vo_contract.ensure_hosted_framing_vo_seats", _ensure
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.assert_stage_artifacts_complete",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_raise",
        lambda *_a, **_k: None,
    )
    _heal_nugget_layup_compose_if_complete(ctx)
    assert called == ["ensure"]


def test_floor_unmet_blocks_layup_complete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _c: 3,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _c: True,
    )
    # Bypass aspirational proceed so PARTIAL floor stays incompleteness.
    monkeypatch.setattr(
        "interview_mux.hosted_vo_authority.may_aspirational_proceed",
        lambda *_a, **_k: False,
    )
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_only",
            text="Only one hosted framing line about the guest and stakes.",
            targets_segment_id="seg_001",
            delivery="synthesize",
        ),
    )
    gap["nugget_layup_authority"] = True
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "layups": [
                {
                    "target_segment_id": "seg_001",
                    "text": "Only one hosted framing line about the guest and stakes.",
                    "line_id": "vo_only",
                    "target_beat": "clinical arc ahead for listeners",
                    "listener_need_entering": "why this guest matters now",
                    "forward_unlock": "tease the trial result that follows",
                    "nugget_ids": ["nug_1"],
                }
            ],
        },
        skip_handoff=True,
    )
    _seed_selection_manifest(
        ctx,
        [("seg_001", "Useful native about the clinical arc ahead for listeners.")],
    )
    inc = stage_artifact_incompleteness(ctx, "nugget_layup_compose")
    assert inc is not None
    low = inc.lower()
    assert (
        "synthetic" in low
        or "hosted" in low
        or "floor" in low
        or "≥3" in inc
        or ">=3" in inc
        or "3" in inc
    )
