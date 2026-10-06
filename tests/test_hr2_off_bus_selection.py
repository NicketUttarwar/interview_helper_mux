"""HR-2 / ASC-B3: Pass A air omits leave selection alone; layup CTA uses commit bus.

ASC-B3: Pass A records omits on plan/ledger only — never shrinks selection.
Layup CTA prune still goes through commit_selection_mutation (refuse pins writer).
Do not start a run. F1 restamp-on-read and HR-4 mute-mark stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.air_script import compose_pass_a, run_air_script_compose
from interview_mux.heal_routing import classify_heal_error
from interview_mux.mastering_plan_loader import forced_sparse_plan, write_plan
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    incompleteness_resume_stage,
    parse_resume_stage_from_reason,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from interview_mux.stages.analysis_extended import commit_layup_cta_selection
from interview_mux.thrash_hardening import heal_navigate
from interview_mux.write_staging import write_mirrored_json
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: True)
    run = isolated_run_ctx(tmp_path, "hr2_selection_bus")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _seed_meander(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    ordered = [f"seg_{i:03d}" for i in range(1, 13)]
    segs = []
    t = 0
    for i, sid in enumerate(ordered):
        segs.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_host" if i % 2 == 0 else "spk_guest",
                "speaker_role": "interviewer" if i % 2 == 0 else "interviewee",
                "type": "interviewer_question" if i % 2 == 0 else "interviewee_answer",
                "start_ms": t,
                "end_ms": t + 8_000,
                "text": f"Beat {i} on {sid}",
                "topic_tags": ["origin_story"],
            }
        )
        # One beat a minute: a 96-second tape sat wholly inside the opening
        # window and the opening constitution excluded half of it on write.
        t += 60_000
    ctx.write_json("segments/manifest.json", {"segments": segs}, skip_handoff=True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": list(ordered), "excluded_segment_ids": []},
        skip_handoff=True,
    )
    write_mirrored_json(
        ctx,
        "understanding/talking_points.json",
        {
            "talking_points": [
                {"segment_id": "seg_001", "claim": "c1"},
                {"segment_id": "seg_002", "claim": "c2"},
                {"segment_id": "seg_005", "claim": "c5"},
            ]
        },
    )
    write_plan(ctx, forced_sparse_plan(reason="hr2_air_script"))
    monkeypatch.setattr(
        "interview_mux.air_script.hard_keep_segment_ids",
        lambda _c, **_k: {"seg_003"},
    )
    monkeypatch.setattr(
        "interview_mux.air_script.compile_circumstance_card",
        lambda _c: {
            "tape_character": ["long_meander"],
            "passion_segment_ids": ["seg_010"],
            "g1_skip": False,
            "nle_locked": False,
            "dry_beds": False,
        },
    )
    return ordered


def test_asc_b3_pass_a_omits_leave_selection_unchanged(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ASC-B3: air omits on plan/ledger; selection.json order stays intact."""
    _seed_meander(ctx, monkeypatch)
    writes: list[str] = []
    real_write = ctx.write_json

    def _spy_write(rel: str, data, **kwargs):  # type: ignore[no-untyped-def]
        if rel == "master/selection.json":
            writes.append(rel)
        return real_write(rel, data, **kwargs)

    monkeypatch.setattr(ctx, "write_json", _spy_write)
    commits: list[str] = []
    from interview_mux import air_order_boundary as boundary

    real_commit = boundary.commit_selection_mutation

    def _spy_commit(c, sel, **kwargs):  # type: ignore[no-untyped-def]
        commits.append(str(kwargs.get("producer") or ""))
        return real_commit(c, sel, **kwargs)

    monkeypatch.setattr(boundary, "commit_selection_mutation", _spy_commit)

    before = list(ctx.read_json("master/selection.json")["ordered_segment_ids"])
    plan = compose_pass_a(ctx)
    omitted = {row["subject_id"] for row in (plan["air_script"]["omits"] or [])}
    assert omitted
    after = list(ctx.read_json("master/selection.json")["ordered_segment_ids"])
    assert after == before
    assert commits == []
    assert writes == []
    assert ctx.artifact_exists("understanding/omit_ledger.json")
    ledger = ctx.read_json("understanding/omit_ledger.json")
    entries = ledger.get("entries") if isinstance(ledger, dict) else []
    assert any(
        isinstance(e, dict) and e.get("reason_code") == "pass_a_padding" for e in entries
    )


def test_asc_b3_pass_a_ignores_selection_commit_bus(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ASC-B3: Pass A does not call selection commit — boom on bus is irrelevant."""
    _seed_meander(ctx, monkeypatch)
    before = list(ctx.read_json("master/selection.json")["ordered_segment_ids"])

    def _boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise RuntimeError("sanitize_refused:selection: boom")

    monkeypatch.setattr(
        "interview_mux.air_order_boundary.commit_selection_mutation",
        _boom,
    )
    plan = compose_pass_a(ctx)
    assert plan.get("air_script", {}).get("omits")
    assert ctx.read_json("master/selection.json")["ordered_segment_ids"] == before
    run_air_script_compose(ctx)
    assert ctx.is_done("air_script_compose") or ctx.artifact_exists(
        "mastering/mastering_plan.json"
    )


def test_hr2_pass_a_freeze_noops_without_write_json(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import seat_authority as sa

    _seed_meander(ctx, monkeypatch)
    frozen = list(ctx.read_json("master/selection.json")["ordered_segment_ids"])
    sa.stamp_soft_seat_freeze(ctx, reason="hr2")
    monkeypatch.setattr(
        "interview_mux.seat_authority.request_seat_rewrite",
        lambda *a, **k: {
            "allow": False,
            "refuse_reason": "opportunity_below_threshold",
            "opportunity_score": 0.3,
        },
    )
    writes: list[str] = []
    real_write = ctx.write_json

    def _spy_write(rel: str, data, **kwargs):  # type: ignore[no-untyped-def]
        if rel == "master/selection.json":
            writes.append(rel)
        return real_write(rel, data, **kwargs)

    monkeypatch.setattr(ctx, "write_json", _spy_write)
    compose_pass_a(ctx)
    assert ctx.read_json("master/selection.json")["ordered_segment_ids"] == frozen
    assert writes == []


def test_hr2_layup_cta_commits_not_write_json(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_cta"],
            "excluded_segment_ids": [],
        },
        skip_handoff=True,
    )
    writes: list[str] = []
    real_write = ctx.write_json

    def _spy_write(rel: str, data, **kwargs):  # type: ignore[no-untyped-def]
        if rel == "master/selection.json":
            writes.append(rel)
        return real_write(rel, data, **kwargs)

    monkeypatch.setattr(ctx, "write_json", _spy_write)
    sanitize_calls: list[str] = []
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.selection.run_selection_order_sanitize",
        lambda *_a, **_k: sanitize_calls.append("w1"),
    )
    commits: list[str] = []
    from interview_mux import air_order_boundary as boundary

    real_commit = boundary.commit_selection_mutation

    def _spy_commit(c, sel, **kwargs):  # type: ignore[no-untyped-def]
        commits.append(str(kwargs.get("producer") or ""))
        return real_commit(c, sel, **kwargs)

    monkeypatch.setattr(boundary, "commit_selection_mutation", _spy_commit)
    out = commit_layup_cta_selection(
        ctx,
        {"ordered_segment_ids": ["seg_001", "seg_cta"], "excluded_segment_ids": []},
        {
            "ordered_segment_ids": ["seg_001"],
            "excluded_segment_ids": [{"segment_id": "seg_cta", "reason": "cta"}],
        },
    )
    assert out is not None
    assert commits == ["selection_order_sanitize"]
    assert writes == []
    assert sanitize_calls == []
    assert ctx.read_json("master/selection.json")["ordered_segment_ids"] == ["seg_001"]


def test_hr2_cta_commit_refuse_pins_sanitize_not_w1(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S7: CTA bus commit is sanitize-owned; refuse pins sanitize (not W1 thrash)."""
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_cta"], "excluded_segment_ids": []},
        skip_handoff=True,
    )

    def _boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise RuntimeError("sanitize_refused:selection: boom")

    monkeypatch.setattr(
        "interview_mux.air_order_boundary.commit_selection_mutation",
        _boom,
    )
    with pytest.raises(RuntimeError, match="selection_commit_refused") as caught:
        commit_layup_cta_selection(
            ctx,
            {"ordered_segment_ids": ["seg_001", "seg_cta"]},
            {"ordered_segment_ids": ["seg_001"]},
        )
    reason = str(caught.value)
    assert parse_resume_stage_from_reason(reason) == "selection_order_sanitize"
    assert parse_resume_stage_from_reason(reason) != "nugget_layup_compose"


def test_hr2_unchanged_order_skips_commit(ctx: RunContext) -> None:
    same = {"ordered_segment_ids": ["seg_001"], "excluded_segment_ids": []}
    assert commit_layup_cta_selection(ctx, same, dict(same)) is None
