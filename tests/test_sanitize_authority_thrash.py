"""Thrash class matrix: suppress denylist, authority undo, dual-writer guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.operator_gates import should_stamp_needs_operator
from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import (
    is_hard_non_suppress_class,
    note_authority_undo_attempt,
    suppress_allowed,
)


@pytest.mark.parametrize(
    "fail_class",
    [
        "sanitize_refused:selection",
        "selection_unsanitary — resume selection_order_sanitize",
        "gap_unsanitary — resume gap_report_sanitize",
        "authority_undo_thrash:master/selection.json",
        "HARD: incomplete-after-conductor thrash ×3",
        "same_family_over_budget:1",
    ],
)
def test_hard_non_suppress_classes(fail_class: str) -> None:
    assert is_hard_non_suppress_class(fail_class)
    ctx = RunContext(create=True)
    assert suppress_allowed(ctx, fail_class, source="homunculus") is False
    assert suppress_allowed(ctx, fail_class, source="forensics") is False


@pytest.mark.parametrize(
    "reason",
    [
        "sanitize_refused:selection: same_family",
        "selection_unsanitary — resume selection_order_sanitize: same_family_over_budget:1",
        "authority_undo_thrash:master/selection.json: hash_oscillation",
        "HARD: incomplete-after-conductor thrash ×40 pin=selection_order_sanitize",
    ],
)
def test_needs_operator_stamps_sanitary_and_undo(reason: str) -> None:
    meta = {"partial_auto": True, "homunculus_version": "0.1.0"}
    assert should_stamp_needs_operator("selection_order_sanitize", reason, meta=meta)


def test_authority_undo_halts_on_oscillation() -> None:
    ctx = RunContext(create=True)
    rows = []
    for i, (action, h) in enumerate(
        [
            ("sanitize", "aaa"),
            ("repair", "bbb"),
            ("sanitize", "aaa"),
            ("repair", "bbb"),
        ]
    ):
        row = note_authority_undo_attempt(
            ctx,
            artifact="master/selection.json",
            action_class=action,
            content_hash=h,
            halt_after=3,
        )
        rows.append(row)
    assert rows[-1]["halt"] is True
    assert "oscillation" in str(rows[-1].get("reason") or "")


def test_hard_keep_collapse_caps_overlapping_family(tmp_path: Path, monkeypatch) -> None:
    from interview_mux.hard_keep import hard_keep_segment_ids

    ctx = RunContext(create=True)
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    letters = "ghijkl"
    rows = []
    for i, a in enumerate(letters):
        for b in letters:
            rows.append(
                {
                    "segment_id": f"seg_048{a}{b}",
                    "start_ms": 1_000_000 + i * 40,
                    "end_ms": 1_000_000 + i * 40 + 4000,
                }
            )
    (ctx.path("segments") / "boundaries.json").write_text(
        json.dumps({"boundaries": rows}),
        encoding="utf-8",
    )
    story = {r["segment_id"] for r in rows}
    # Seed a banned parent hard-keep so story transfer fires, then collapses.
    (ctx.path("understanding")).mkdir(parents=True, exist_ok=True)
    (ctx.path("understanding") / "ideal_cuts.json").write_text(
        json.dumps({"must_keep_segment_ids": ["seg_048"], "cuts": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "interview_mux.media_ip_cta.admitted_story_segment_ids",
        lambda _ctx: story,
    )
    monkeypatch.setattr(
        "interview_mux.media_ip_cta.never_touch_segment_ids",
        lambda _ctx: {"seg_048"},
    )
    # Parent banned + story transfer → collapse must not return full lattice.
    keeps = hard_keep_segment_ids(ctx)
    fam = [s for s in keeps if s.startswith("seg_048")]
    assert len(fam) <= 8
    assert "seg_048" not in keeps


# Publishability ↔ EDL soft-fail coverage lives in
# tests/test_delivery_thrash_hardening.py::test_post_edl_soft_fail_leaves_live_edl


def test_admit_sanitized_refuses_unsanitary() -> None:
    from interview_mux.artifact_sanitize.admit import admit_sanitized
    from interview_mux.artifact_sanitize.types import SanitizeResult

    ctx = RunContext(create=True)

    def _bad(_c, d):
        return SanitizeResult(doc=d, ok=False, errors=["forced_refuse"])

    with pytest.raises(RuntimeError, match="sanitize_refused"):
        admit_sanitized(
            ctx,
            "understanding/nugget_layup_plan.json",
            {"ordered_segment_ids": []},
            sanitize_fn=_bad,
            refuse_if_unsanitary=True,
        )


def test_gap_commit_records_authority_undo() -> None:
    from interview_mux.artifact_sanitize.gap_report import commit_gap_report_doc

    ctx = RunContext(create=True)
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    doc = {
        "version": 1,
        "interviewer_lines": [],
        "gaps": [],
    }
    commit_gap_report_doc(ctx, doc, reason="test", stage_key="gap_report")
    assert ctx.artifact_exists("understanding/gap_report.json")
    # Second commit with same content hash should not halt; oscillating hashes do.
    commit_gap_report_doc(ctx, doc, reason="test2", stage_key="gap_report")
    assert ctx.artifact_exists("operator/authority_undo.json")


def test_layup_commit_aligns_to_selection_not_amplify() -> None:
    from interview_mux.artifact_sanitize.nugget_layup_plan import sanitize_nugget_layup_plan
    from interview_mux.artifact_sanitize.one_writer import commit_nugget_layup_plan_doc

    ctx = RunContext(create=True)
    ctx._one_writer_raw = True
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_002", "seg_005"],
            "excluded_segment_ids": [],
            "chapters": [],
        },
        skip_handoff=True,
    )
    ctx._one_writer_raw = False
    dirty = {
        "ordered_segment_ids": ["seg_002", "seg_005", "seg_999"],
        "layups": [
            {
                "target_segment_id": "seg_002",
                "segment_id": "seg_002",
                "nugget_ids": [],
            }
        ],
        "status": "ok",
    }
    # Dual-writer proof: sanitize drops off-air ids; commit does not grow selection.
    sanitized = sanitize_nugget_layup_plan(ctx, dirty)
    assert "seg_999" not in (sanitized.doc.get("ordered_segment_ids") or [])
    commit_nugget_layup_plan_doc(ctx, sanitized.doc, stage_key="nugget_layup_compose")
    sel = ctx.read_json("master/selection.json")
    assert "seg_999" not in (sel.get("ordered_segment_ids") or [])
    assert ctx.artifact_exists("understanding/nugget_layup_plan.json")


def test_sdp_commit_via_admit_sanitized() -> None:
    from interview_mux.analysis_memory import default_sound_design_plan
    from interview_mux.artifact_sanitize.one_writer import commit_sound_design_plan_doc

    ctx = RunContext(create=True)
    ctx._one_writer_raw = True
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_002"], "excluded_segment_ids": [], "chapters": []},
        skip_handoff=True,
    )
    ctx._one_writer_raw = False
    plan = default_sound_design_plan()
    commit_sound_design_plan_doc(ctx, plan, stage_key="sound_design_plan")
    assert ctx.artifact_exists("understanding/sound_design_plan.json")
    disk = ctx.read_json("understanding/sound_design_plan.json")
    assert isinstance(disk, dict)
    meta = (disk.get("_meta") or {}).get("sanitize") or {}
    assert meta.get("ok") is True or "sanitize" in (disk.get("_meta") or {})


def test_transitions_commit_via_admit() -> None:
    from interview_mux.artifact_sanitize.one_writer import commit_transitions_doc

    ctx = RunContext(create=True)
    ctx._one_writer_raw = True
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_002", "seg_005"],
            "excluded_segment_ids": [],
            "chapters": [],
        },
        skip_handoff=True,
    )
    ctx._one_writer_raw = False
    commit_transitions_doc(
        ctx,
        {"transitions": []},
        stage_key="transitions",
    )
    assert ctx.artifact_exists("master/transitions.json")


def test_agenda_identical_error_notes_authority_undo() -> None:
    from interview_mux.homunculus.agenda import note_identical_stage_error

    ctx = RunContext(create=True)
    row = None
    for _ in range(4):
        row = note_identical_stage_error(
            ctx, "selection_order_sanitize", "same_family_over_budget:1"
        )
    assert ctx.artifact_exists("operator/authority_undo.json")
    assert isinstance(row, dict)


def test_music_epoch_and_pair_freeze_still_importable() -> None:
    """Matrix rows covered by delivery_thrash_hardening — smoke the hooks exist."""
    from interview_mux.delivery_guardrails import (
        may_rewind_to_vo_synthesize,
        music_epoch_complete,
    )

    ctx = RunContext(create=True)
    assert music_epoch_complete(ctx) in (True, False)
    assert may_rewind_to_vo_synthesize(ctx) in (True, False)
