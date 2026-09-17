"""Tests for artifact_sanitize selection (non-amplifying air-order cleanup)."""

from __future__ import annotations

import json

from interview_mux.artifact_sanitize.config import sanitize_selection_cfg
from interview_mux.artifact_sanitize.selection import (
    _fragment_depth,
    sanitize_master_selection,
)
from interview_mux.operator_gates import should_stamp_needs_operator
from interview_mux.pipeline import canonical_stage_id
from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER


def test_fragment_depth_counts_suffix() -> None:
    assert _fragment_depth("seg_003") == 0
    assert _fragment_depth("seg_003a") == 1
    assert _fragment_depth("seg_003aaaaa") == 5


def test_sanitize_collapses_deep_fragments() -> None:
    ctx = RunContext(create=True)
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    (ctx.path("segments") / "boundaries.json").write_text(
        json.dumps(
            {
                "boundaries": [
                    {"segment_id": "seg_003", "start_ms": 0, "end_ms": 1000},
                    {"segment_id": "seg_003aaaaa", "start_ms": 0, "end_ms": 1000},
                    {"segment_id": "seg_003aaaab", "start_ms": 0, "end_ms": 1000},
                    {"segment_id": "seg_005", "start_ms": 2000, "end_ms": 3000},
                ]
            }
        ),
        encoding="utf-8",
    )
    sel = {
        "ordered_segment_ids": ["seg_003aaaaa", "seg_003aaaab", "seg_005"],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert result.ok
    depths = [_fragment_depth(s) for s in result.doc["ordered_segment_ids"]]
    max_d = int(sanitize_selection_cfg()["max_fragment_depth"])
    assert all(d <= max_d for d in depths)
    assert "seg_005" in result.doc["ordered_segment_ids"]


def test_sanitize_does_not_grow_via_readmit() -> None:
    ctx = RunContext(create=True)
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    (ctx.path("segments") / "boundaries.json").write_text(
        json.dumps(
            {"boundaries": [{"segment_id": "seg_002", "start_ms": 0, "end_ms": 500}]}
        ),
        encoding="utf-8",
    )
    sel = {
        "ordered_segment_ids": ["seg_002"],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    before = len(sel["ordered_segment_ids"])
    result = sanitize_master_selection(ctx, sel)
    assert len(result.doc["ordered_segment_ids"]) <= before
    assert not any(a.get("action") == "readmit_cta_story_children" for a in result.actions)


def test_sanitize_refused_stamps_needs_operator() -> None:
    meta = {"partial_auto": True, "homunculus_version": "0.1.0"}
    assert should_stamp_needs_operator(
        "nugget_layup_compose",
        "selection_unsanitary — resume selection_order_sanitize: fragment_depth_exceeded",
        meta=meta,
    )
    assert should_stamp_needs_operator(
        "selection_order_sanitize",
        "sanitize_refused:selection: ordered empty",
        meta=meta,
    )
    assert should_stamp_needs_operator(
        "refinement_agenda",
        "gap_unsanitary — resume gap_report_sanitize: gap_needs_sanitize",
        meta=meta,
    )
    assert should_stamp_needs_operator(
        "transitions",
        "air_contract_unsanitary — resume air_contract_sanitize: seats_over_wavs",
        meta=meta,
    )
    assert should_stamp_needs_operator(
        "gap_report_sanitize",
        "sanitize_refused:gap_report: empty after floor",
        meta=meta,
    )
    assert not should_stamp_needs_operator(
        "sound_design_plan",
        "seed order: complete nugget_layup_compose before running sound_design_plan",
        meta=meta,
    )


def test_pipeline_alias_selection_maps_to_sanitize() -> None:
    assert canonical_stage_id("selection") == "selection_order_sanitize"


def test_delivery_order_has_sanitize_after_ranking() -> None:
    i = DELIVERY_ORDER.index("full_master_ranking")
    assert DELIVERY_ORDER[i + 1] == "selection_order_sanitize"


def test_max_cta_readmit_defaults_to_zero() -> None:
    assert int(sanitize_selection_cfg()["max_cta_readmit"]) == 0


def _seg048_lattice_boundaries() -> list[dict]:
    """Overlapping NLE letter-grid under seg_048 (exec_9948-class)."""
    rows = []
    letters = "ghijkl"
    base_start = 1_000_000
    for i, a in enumerate(letters):
        for j, b in enumerate(letters):
            sid = f"seg_048{a}{b}"
            # Heavy overlap within family so sanitize collapses spans.
            start = base_start + (i * 50)
            end = start + 5000
            rows.append({"segment_id": sid, "start_ms": start, "end_ms": end})
    rows.append({"segment_id": "seg_002", "start_ms": 0, "end_ms": 500})
    rows.append({"segment_id": "seg_005", "start_ms": 2000, "end_ms": 3000})
    return rows


def test_max_cta_readmit_zero_is_noop(monkeypatch) -> None:
    from interview_mux.artifact_repairs import _readmit_cta_story_children

    ctx = RunContext(create=True)
    applied: list = []
    monkeypatch.setattr(
        "interview_mux.media_ip_cta.admitted_story_segment_ids",
        lambda _ctx: {"seg_048gg", "seg_048hh", "seg_048ii"},
    )
    monkeypatch.setattr(
        "interview_mux.media_ip_cta.never_touch_segment_ids",
        lambda _ctx: set(),
    )
    out = _readmit_cta_story_children(ctx, ["seg_002"], applied)
    assert out == ["seg_002"]
    assert any(a.get("action") == "skip_cta_readmit" for a in applied)


def test_sanitize_then_repair_stays_under_family_budget(monkeypatch) -> None:
    from interview_mux.artifact_repairs import repair_master_selection
    from interview_mux.artifact_sanitize.config import sanitize_selection_cfg
    from interview_mux.artifact_sanitize.selection import (
        _base_family,
        selection_sanitary_errors,
    )

    ctx = RunContext(create=True)
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    boundaries = _seg048_lattice_boundaries()
    (ctx.path("segments") / "boundaries.json").write_text(
        json.dumps({"boundaries": boundaries}),
        encoding="utf-8",
    )
    lattice = [r["segment_id"] for r in boundaries if r["segment_id"].startswith("seg_048")]
    story = set(lattice)
    monkeypatch.setattr(
        "interview_mux.media_ip_cta.admitted_story_segment_ids",
        lambda _ctx: story,
    )
    monkeypatch.setattr(
        "interview_mux.media_ip_cta.never_touch_segment_ids",
        lambda _ctx: set(),
    )
    sel = {
        "ordered_segment_ids": ["seg_002", "seg_005"] + lattice,
        "excluded_segment_ids": [],
        "chapters": [],
    }
    sanitized = sanitize_master_selection(ctx, sel)
    assert sanitized.ok
    max_family = int(sanitize_selection_cfg()["max_same_family_on_air"])
    fam = {}
    for sid in sanitized.doc["ordered_segment_ids"]:
        fam[_base_family(sid)] = fam.get(_base_family(sid), 0) + 1
    assert fam.get("seg_048", 0) <= max_family

    repaired, notes = repair_master_selection(ctx, sanitized.doc, amplify=True)
    assert any(n.get("action") == "skip_cta_readmit" for n in notes) or not any(
        n.get("action") == "readmit_cta_story_children" for n in notes
    )
    fam2 = {}
    for sid in repaired["ordered_segment_ids"]:
        fam2[_base_family(sid)] = fam2.get(_base_family(sid), 0) + 1
    assert fam2.get("seg_048", 0) <= max_family
    assert len(repaired["ordered_segment_ids"]) <= len(sanitized.doc["ordered_segment_ids"]) + 2

    # Commit sanitize-last path leaves sanitary on disk.
    from interview_mux.air_order_boundary import commit_selection_mutation

    commit_selection_mutation(
        ctx,
        sanitized.doc,
        producer="artifact_sanitize.selection",
        stage_key="selection_order_sanitize",
        checkpoint_mode="detect",
        skip_checkpoint=True,
        write_committed=True,
    )
    assert selection_sanitary_errors(ctx) == []
    disk = ctx.read_json("master/selection.json")
    lock = disk.get("order_lock") or {}
    assert "artifact_sanitize" in str(lock.get("created_by") or disk.get("_meta") or "")


def test_stale_sanitize_stamp_is_rejected() -> None:
    from interview_mux.artifact_sanitize.selection import selection_sanitary_errors

    ctx = RunContext(create=True)
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    (ctx.path("segments") / "boundaries.json").write_text(
        json.dumps(
            {
                "boundaries": [
                    {"segment_id": f"seg_048{a}", "start_ms": 1000, "end_ms": 2000}
                    for a in "abcdefghij"
                ]
                + [{"segment_id": "seg_002", "start_ms": 0, "end_ms": 100}]
            }
        ),
        encoding="utf-8",
    )
    bloated = ["seg_002"] + [f"seg_048{a}" for a in "abcdefghij"]
    doc = {
        "ordered_segment_ids": bloated,
        "order_content_hash": "deadbeef",
        "excluded_segment_ids": [],
        "chapters": [],
        "_meta": {
            "sanitize": {
                "ok": True,
                "after_count": 3,
                "hash": "stale-hash-not-matching",
                "source": "artifact_sanitize.selection",
            }
        },
    }
    ctx._one_writer_raw = True
    ctx.write_json("master/selection.json", doc, skip_handoff=True)
    errs = selection_sanitary_errors(ctx)
    assert errs
    assert any(
        "same_family_over_budget" in e or "stamp_stale" in e or "needs_sanitize" in e
        for e in errs
    )


def test_sanitize_prunes_exclude_rationales_on_air_ids() -> None:
    """Air-order ids must not keep exclude_rationales (exec_11630 freeze preserve)."""
    ctx = RunContext(create=True)
    sel = {
        "ordered_segment_ids": ["seg_023", "seg_041"],
        "excluded_segment_ids": [
            {"segment_id": "seg_023", "reason": "media_ip_cta"},
            {"segment_id": "seg_041", "reason": "media_ip_cta"},
            {"segment_id": "seg_099", "reason": "excluded_from_master"},
        ],
        "exclude_rationales": {
            "seg_023": "media_ip_cta",
            "seg_041": "media_ip_cta",
            "seg_099": "excluded_from_master",
        },
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert result.ok
    assert result.doc["ordered_segment_ids"] == ["seg_023", "seg_041"]
    assert "seg_023" not in (result.doc.get("exclude_rationales") or {})
    assert "seg_041" not in (result.doc.get("exclude_rationales") or {})
    assert "seg_099" in (result.doc.get("exclude_rationales") or {})
    assert any(a.get("action") == "prune_stale_exclude_rationales" for a in result.actions)
