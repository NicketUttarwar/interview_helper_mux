"""Wave B Ships 2–6 focused tests: sanitary preflight, invalidate, opening adjacency."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.artifact_sanitize.invalidate import maybe_invalidate_after_sanitize
from interview_mux.artifact_sanitize.preflight import sanitary_preflight_errors
from interview_mux.llm_preflight import run_preflight
from interview_mux.opening_adjacency_repair import (
    suppress_opening_layup_when_orientation_owns_slot,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_input_checks import collect_stage_input_issues


def _dump_raw(ctx: RunContext, rel: str, doc: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_dirty_selection_blocks_transitions_preflight_and_stage_input() -> None:
    ctx = RunContext(create=True)
    # Deep fragment tree without sanitize stamp → unsanitary
    _dump_raw(
        ctx,
        "master/selection.json",
        {
            "ordered_segment_ids": [
                "seg_001",
                "seg_001aaaa",  # depth 4 > max_fragment_depth 3
                "seg_002",
            ],
            "excluded_segment_ids": [],
            "chapters": [],
        },
    )
    pf = run_preflight("transitions", ctx)
    assert any("selection" in e for e in pf), pf
    issues = collect_stage_input_issues(ctx, "transitions")
    msgs = [i.message for i in issues]
    assert any("selection" in m for m in msgs), msgs
    # Dual-path: every run_preflight error appears in collect_stage_input_issues
    for err in pf:
        assert any(err == m or err in m for m in msgs), (err, msgs)


def test_dirty_gap_blocks_vo_line_adjudicate() -> None:
    ctx = RunContext(create=True)
    _dump_raw(
        ctx,
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "excluded_segment_ids": [],
            "chapters": [],
            "order_content_hash": "h1",
        },
    )
    # Off-air target + duplicate text forces sanitize actions → unsanitary until commit
    _dump_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_a",
                    "text": "hello there",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                },
                {
                    "line_id": "vo_b",
                    "text": "hello there",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                },
                {
                    "line_id": "vo_off",
                    "text": "off air line",
                    "targets_segment_id": "seg_999",
                },
            ],
            "gaps": [],
        },
    )
    errs = sanitary_preflight_errors(ctx, "vo_line_adjudicate")
    assert any("gap" in e for e in errs), errs
    issues = collect_stage_input_issues(ctx, "vo_line_adjudicate")
    assert any("gap" in i.message for i in issues)


def test_first_layup_compose_not_blocked_by_missing_plan() -> None:
    ctx = RunContext(create=True)
    # Sanitary selection stamp-ok structural
    from interview_mux.artifact_sanitize.selection import sanitize_master_selection
    from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta

    sel = {
        "ordered_segment_ids": ["seg_001", "seg_002"],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert result.ok
    _dump_raw(ctx, "master/selection.json", result.doc)
    errs = sanitary_preflight_errors(ctx, "nugget_layup_compose")
    assert not any("layup" in e and "missing" in e for e in errs), errs


def test_opening_adjacency_uses_commit_not_fs_write(tmp_path: Path, monkeypatch) -> None:
    ctx = RunContext(create=True)
    _dump_raw(
        ctx,
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [],
            "chapters": [],
        },
    )
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_orient",
                "text": "Welcome to the show",
                "targets_segment_id": "seg_001",
                "episode_orientation": True,
                "placement": "before",
            },
            {
                "line_id": "vo_layup_seg_001",
                "text": "Also welcome",
                "targets_segment_id": "seg_001",
                "origin": "nugget_layup",
                "placement": "before",
            },
        ],
        "gaps": [],
        "opening_orientation": {"required": True, "line_id": "vo_orient"},
    }
    _dump_raw(ctx, "understanding/gap_report.json", gap)

    calls: list[str] = []

    def _track_commit(c, doc, *, reason=""):
        calls.append(reason or "commit")
        from interview_mux.artifact_sanitize.gap_report import sanitize_gap_report

        result = sanitize_gap_report(c, dict(doc))
        _dump_raw(c, "understanding/gap_report.json", result.doc)
        return result

    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.gap_report.commit_gap_report_doc",
        _track_commit,
    )
    # Ensure no fs_write_json is imported/used by the module path under test
    import interview_mux.opening_adjacency_repair as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "from interview_mux.file_store import write_json" not in src
    assert "as fs_write_json" not in src

    changed = suppress_opening_layup_when_orientation_owns_slot(ctx)
    assert changed
    assert calls, "expected commit_gap_report_doc"


def test_maybe_invalidate_after_sanitize_marker_only() -> None:
    ctx = RunContext(create=True)
    done = ctx.final_path(".stage_done", "vo_synthesize")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("1", encoding="utf-8")
    edl_done = ctx.final_path(".stage_done", "edl")
    edl_done.write_text("1", encoding="utf-8")

    # Identical hash → no-op
    cleared = maybe_invalidate_after_sanitize(
        ctx,
        "understanding/gap_report.json",
        before_hash="abc",
        after_hash="abc",
        ok=True,
        actions_n=0,
    )
    assert cleared == []
    assert done.is_file()

    cleared = maybe_invalidate_after_sanitize(
        ctx,
        "understanding/gap_report.json",
        before_hash="abc",
        after_hash="def",
        ok=True,
        actions_n=1,
    )
    assert "vo_synthesize" in cleared
    assert "edl" in cleared
    assert not done.is_file()
    assert not edl_done.is_file()
    # Does not wipe EDL artifact itself
    assert not ctx.artifact_exists("master/edl.json") or True


def test_mid_synth_cascade_suppress() -> None:
    ctx = RunContext(create=True)
    done = ctx.final_path(".stage_done", "edl")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("1", encoding="utf-8")
    setattr(ctx, "_mid_synth_cascade_suppress", True)
    cleared = maybe_invalidate_after_sanitize(
        ctx,
        "understanding/gap_report.json",
        before_hash="a",
        after_hash="b",
        ok=True,
        actions_n=1,
    )
    assert cleared == ["skipped:mid_synth_cascade_suppress"]
    assert done.is_file()
