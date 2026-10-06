"""Every judge of a proposed selection reads the proposal, not disk (ISSUES 181).

The run this guards (granola 47-minute source, maintainer's exec_024): the
first ranking commit put the LLM's order through finalize, which excluded the
hard keep seg_007 with a typed omit. ``enforce_hard_keeps`` honoured the omit
(it reads the proposal), ``lattice_lint_codes`` did not (it read the keep
list from disk, where ``master/selection.json`` did not exist yet), and the
seal refused every commit with ``hard_keep_missing_from_order:seg_007``.
Nothing downstream could start without a selection, and the run stopped at
40 of 72.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import hard_keep as hk
from interview_mux.selection_constraints import lattice_lint_codes, seal_selection_lattice
from run_fixtures import isolated_run_ctx

_KEEP = "seg_007"


def _put(ctx, rel: str, doc: dict) -> None:
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc), encoding="utf-8")


def _missing_keep_codes(ctx, sel: dict) -> list[str]:
    return [c for c in lattice_lint_codes(ctx, sel) if c.startswith("hard_keep_missing_from_order")]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "keep_vs_proposal")
    segs = [
        {"segment_id": f"seg_{i:03d}", "start_ms": i * 10_000, "end_ms": i * 10_000 + 8_000,
         "text": f"Story sentence number {i} with enough words to be real speech."}
        for i in range(1, 11)
    ]
    _put(c, "segments/manifest.json", {"segments": segs})
    _put(
        c,
        "segments/boundaries.json",
        {"boundaries": [{k: s[k] for k in ("segment_id", "start_ms", "end_ms")} for s in segs]},
    )
    _put(c, "understanding/ideal_cuts.json", {"must_keep_segment_ids": [_KEEP], "cuts": []})
    _put(
        c,
        "master/narrative_plan.json",
        {
            "chapters": [
                {"chapter_id": "ch_open", "segment_ids": ["seg_001", "seg_002", _KEEP]},
                {"chapter_id": "ch_mid", "segment_ids": ["seg_004", "seg_005"]},
                {"chapter_id": "ch_coda", "segment_ids": ["seg_009", "seg_010"]},
            ]
        },
    )
    return c


def test_the_keep_list_drops_a_typed_omit_of_the_proposal_only_when_asked(ctx) -> None:
    proposal = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_004", "seg_009"],
        "excluded_segment_ids": [{"segment_id": _KEEP, "reason": "opening_slot_overflow"}],
    }
    # Disk has no selection yet (first commit): the plain keep list still demands it.
    assert _KEEP in hk.hard_keep_segment_ids(ctx)
    # Judged against the proposal, the constitution's omit beats the keep.
    assert _KEEP not in hk.hard_keep_segment_ids(ctx, selection=proposal)


def test_first_commit_with_an_opening_constitution_omit_seals(ctx) -> None:
    proposal = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_004", "seg_009"],
        "excluded_segment_ids": [{"segment_id": _KEEP, "reason": "opening_slot_overflow"}],
    }
    assert not ctx.artifact_exists("master/selection.json")
    assert _missing_keep_codes(ctx, proposal) == []
    sealed = seal_selection_lattice(ctx, proposal, fail_closed=True)
    assert _KEEP not in sealed["ordered_segment_ids"]
    assert _missing_keep_codes(ctx, sealed) == []


def test_first_commit_whose_finalize_omits_an_early_keep_seals(ctx) -> None:
    """The restore appends an early-chapter keep, the finale rule omits it as
    finale_tail_leftover, and the lint must read that omit from the same document."""
    proposal = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_004", "seg_009"],
        "excluded_segment_ids": [{"segment_id": _KEEP, "reason": "aside"}],
    }
    sealed = seal_selection_lattice(ctx, proposal, fail_closed=True)
    reasons = {
        str(r.get("segment_id")): str(r.get("reason") or "")
        for r in sealed["excluded_segment_ids"]
        if isinstance(r, dict)
    }
    if _KEEP in sealed["ordered_segment_ids"]:
        # The restore placed it: nothing to omit, nothing to refuse.
        assert _KEEP not in reasons
    else:
        assert reasons.get(_KEEP) == "finale_tail_leftover"
    assert _missing_keep_codes(ctx, sealed) == []


def test_the_committed_file_does_not_override_the_proposal(ctx) -> None:
    _put(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", _KEEP, "seg_009"], "excluded_segment_ids": []},
    )
    proposal = {
        "ordered_segment_ids": ["seg_001", "seg_009"],
        "excluded_segment_ids": [{"segment_id": _KEEP, "reason": "opening_skipped_duplicate"}],
    }
    assert _KEEP in hk.hard_keep_segment_ids(ctx)
    assert _missing_keep_codes(ctx, proposal) == []
    # And the other way round: the file's omit does not excuse a proposal that
    # merely forgot the keep.
    _put(
        ctx,
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_009"],
            "excluded_segment_ids": [{"segment_id": _KEEP, "reason": "opening_skipped_duplicate"}],
        },
    )
    forgot = {"ordered_segment_ids": ["seg_001", "seg_009"], "excluded_segment_ids": []}
    assert _missing_keep_codes(ctx, forgot) == [f"hard_keep_missing_from_order:{_KEEP}"]


def test_a_keep_excluded_as_an_editorial_aside_is_still_restored(ctx) -> None:
    _put(
        ctx,
        "master/narrative_plan.json",
        {
            "chapters": [
                {"chapter_id": "ch_open", "segment_ids": ["seg_001", "seg_002"]},
                {"chapter_id": "ch_coda", "segment_ids": [_KEEP, "seg_009"]},
            ]
        },
    )
    proposal = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_009"],
        "excluded_segment_ids": [{"segment_id": _KEEP, "reason": "aside"}],
    }
    assert _KEEP in hk.hard_keep_segment_ids(ctx, selection=proposal)
    sealed = seal_selection_lattice(ctx, proposal, fail_closed=True)
    assert _KEEP in sealed["ordered_segment_ids"]
    assert _missing_keep_codes(ctx, sealed) == []


def test_the_ranking_injector_does_not_readmit_a_typed_omit(ctx) -> None:
    from interview_mux.framing_coverage_guard import inject_ranking_lattice_keeps

    proposal = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_004", "seg_009"],
        "excluded_segment_ids": [{"segment_id": _KEEP, "reason": "late_intro_reset"}],
    }
    out = inject_ranking_lattice_keeps(ctx, proposal)
    assert _KEEP not in out["ordered_segment_ids"]
    assert any(
        isinstance(r, dict) and r.get("segment_id") == _KEEP for r in out["excluded_segment_ids"]
    )
    # A plain editorial exclude is still injected back, in tape order.
    aside = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_009"],
        "excluded_segment_ids": [{"segment_id": _KEEP, "reason": "aside"}],
    }
    out = inject_ranking_lattice_keeps(ctx, aside)
    order = out["ordered_segment_ids"]
    assert _KEEP in order
    assert order.index("seg_002") < order.index(_KEEP) < order.index("seg_009")


def test_the_deterministic_ranking_lint_reads_the_proposal(ctx) -> None:
    from interview_mux.deterministic_lint import _lint_full_master_ranking

    proposal = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_004", "seg_009"],
        "excluded_segment_ids": [
            {"segment_id": _KEEP, "reason": "opening_slot_overflow"},
            *[
                {"segment_id": f"seg_{i:03d}", "reason": "aside"}
                for i in (3, 5, 6, 8, 10)
            ],
        ],
    }
    errors = _lint_full_master_ranking(proposal, ctx)
    assert not [e for e in errors if f"hard-keep segment {_KEEP}" in e]
    forgot = dict(proposal, excluded_segment_ids=[r for r in proposal["excluded_segment_ids"] if r["segment_id"] != _KEEP])
    errors = _lint_full_master_ranking(forgot, ctx)
    assert [e for e in errors if f"hard-keep segment {_KEEP}" in e]
