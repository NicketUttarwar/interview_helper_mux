"""SOS harden: hard-keep safety, starts/overlap, freeze stamp, pin routing."""

from __future__ import annotations

import json

from interview_mux.artifact_sanitize.config import sanitize_selection_cfg
from interview_mux.artifact_sanitize.selection import (
    sanitize_master_selection,
    selection_sanitary_errors,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    incompleteness_resume_stage,
    producer_pin_for_token,
)


def _boundaries(ctx: RunContext, rows: list[dict]) -> None:
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    (ctx.path("segments") / "boundaries.json").write_text(
        json.dumps({"boundaries": rows}),
        encoding="utf-8",
    )


def test_hard_keep_deep_fragment_refuses_not_drop(monkeypatch) -> None:
    ctx = RunContext(create=True)
    deep = "seg_003aaaaa"
    _boundaries(
        ctx,
        [
            {"segment_id": "seg_003", "start_ms": 0, "end_ms": 1000},
            {"segment_id": deep, "start_ms": 0, "end_ms": 1000},
            {"segment_id": "seg_005", "start_ms": 2000, "end_ms": 3000},
        ],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.selection._hard_keep_ids",
        lambda _ctx, *_a, **_k: {deep},
    )
    sel = {
        "ordered_segment_ids": [deep, "seg_005"],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert deep in result.doc["ordered_segment_ids"]
    assert not result.ok
    assert any("hard_keep_exceeds_fragment_depth" in e for e in result.errors)


def test_family_budget_prefers_hard_keep_then_drops_others(monkeypatch) -> None:
    ctx = RunContext(create=True)
    max_family = int(sanitize_selection_cfg()["max_same_family_on_air"])
    # Depth-1 letter suffixes so fragment-depth collapse does not shrink first.
    ids = [f"seg_010{chr(ord('a') + i)}" for i in range(max_family + 3)]
    rows = [
        {"segment_id": sid, "start_ms": 1000 + i * 200, "end_ms": 1100 + i * 200}
        for i, sid in enumerate(ids)
    ]
    rows.append({"segment_id": "seg_002", "start_ms": 0, "end_ms": 100})
    _boundaries(ctx, rows)
    keep = ids[0]
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.selection._hard_keep_ids",
        lambda _ctx, *_a, **_k: {keep},
    )
    sel = {
        "ordered_segment_ids": ["seg_002"] + ids,
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert result.ok
    ordered = result.doc["ordered_segment_ids"]
    assert keep in ordered
    fam = [s for s in ordered if s.startswith("seg_010")]
    assert len(fam) <= max_family
    assert any(
        a.get("action") == "cap_same_family_on_air" for a in result.actions
    )


def test_family_all_hard_keeps_over_budget_refuses(monkeypatch) -> None:
    ctx = RunContext(create=True)
    max_family = int(sanitize_selection_cfg()["max_same_family_on_air"])
    ids = [f"seg_011{chr(ord('a') + i)}" for i in range(max_family + 2)]
    rows = [
        {"segment_id": sid, "start_ms": 2000 + i * 300, "end_ms": 2100 + i * 300}
        for i, sid in enumerate(ids)
    ]
    _boundaries(ctx, rows)
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.selection._hard_keep_ids",
        lambda _ctx, *_a, **_k: set(ids),
    )
    sel = {
        "ordered_segment_ids": list(ids),
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert not result.ok
    assert any("hard_keep_same_family_over_budget" in e for e in result.errors)
    for sid in ids:
        assert sid in result.doc["ordered_segment_ids"]


def test_both_hard_keep_span_collision_refuses(monkeypatch) -> None:
    ctx = RunContext(create=True)
    a, b = "seg_020a", "seg_020b"
    _boundaries(
        ctx,
        [
            {"segment_id": a, "start_ms": 0, "end_ms": 5000},
            {"segment_id": b, "start_ms": 10, "end_ms": 5010},
        ],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.selection._hard_keep_ids",
        lambda _ctx, *_a, **_k: {a, b},
    )
    sel = {
        "ordered_segment_ids": [a, b],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert not result.ok
    assert any("hard_keep_span_collision" in e for e in result.errors)
    assert a in result.doc["ordered_segment_ids"]
    assert b in result.doc["ordered_segment_ids"]


def test_exclude_rationale_matches_action() -> None:
    ctx = RunContext(create=True)
    deep = "seg_003aaaaa"
    _boundaries(
        ctx,
        [
            {"segment_id": deep, "start_ms": 0, "end_ms": 1000},
            {"segment_id": "seg_005", "start_ms": 2000, "end_ms": 3000},
        ],
    )
    sel = {
        "ordered_segment_ids": [deep, "seg_005"],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert result.ok
    assert deep not in result.doc["ordered_segment_ids"]
    rat = result.doc.get("exclude_rationales") or {}
    assert rat.get(deep) == "collapse_fragment_depth"
    excl = {
        str(r.get("segment_id") if isinstance(r, dict) else r): (
            r.get("reason") if isinstance(r, dict) else ""
        )
        for r in (result.doc.get("excluded_segment_ids") or [])
    }
    assert excl.get(deep) == "collapse_fragment_depth"


def test_hard_keep_missing_pins_ranking(monkeypatch) -> None:
    ctx = RunContext(create=True)
    _boundaries(
        ctx,
        [{"segment_id": "seg_002", "start_ms": 0, "end_ms": 100}],
    )
    doc = {
        "ordered_segment_ids": ["seg_002"],
        "excluded_segment_ids": [],
        "chapters": [],
        "_meta": {
            "sanitize": {
                "ok": True,
                "hash": "will-mismatch",
                "source": "test",
            }
        },
    }
    # Fresh stamp path with lattice missing keep.
    from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta

    doc = stamp_sanitize_meta(
        doc,
        ok=True,
        source="test",
        content_keys=["ordered_segment_ids", "order_content_hash"],
    )
    ctx._one_writer_raw = True
    ctx.write_json("master/selection.json", doc, skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.hard_keep.hard_keep_segment_ids",
        lambda _ctx, **_k: {"seg_099"},
    )
    errs = selection_sanitary_errors(ctx)
    assert any("hard_keep_missing_from_order" in e for e in errs)
    blob = "; ".join(errs)
    assert producer_pin_for_token(blob, ctx=ctx) == "full_master_ranking"
    assert incompleteness_resume_stage(ctx, "selection_order_sanitize") == (
        "full_master_ranking"
    )


def test_segment_starts_unavailable_refuses_multi_family() -> None:
    ctx = RunContext(create=True)
    # No boundaries → empty starts; two same-family ids.
    sel = {
        "ordered_segment_ids": ["seg_030a", "seg_030b"],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert not result.ok
    assert any("segment_starts_unavailable" in e for e in result.errors)


def test_i2_pending_nle_overrides_supply_letter_family_starts() -> None:
    """Pending nle_edits fill letter-split starts (exec_13183 seg_062la…h)."""
    ctx = RunContext(create=True)
    _boundaries(
        ctx,
        [
            {"segment_id": "seg_062", "start_ms": 0, "end_ms": 8000},
            {"segment_id": "seg_070", "start_ms": 9000, "end_ms": 10000},
        ],
    )
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "nugget_layup_compose"
        / "segments"
        / "nle_edits.json"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(
        json.dumps(
            {
                "segment_overrides": {
                    "seg_062la": {"start_ms": 0, "end_ms": 1000},
                    "seg_062lb": {"start_ms": 1000, "end_ms": 2000},
                }
            }
        ),
        encoding="utf-8",
    )
    sel = {
        "ordered_segment_ids": ["seg_062la", "seg_062lb", "seg_070"],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert not any("segment_starts_unavailable" in e for e in (result.errors or []))
    assert result.ok or "seg_062la" in (result.doc.get("ordered_segment_ids") or [])


def test_i3_letter_kids_inherit_parent_start_when_pending_gone() -> None:
    """Phantom seg_062la… inherit seg_062 span after pending NLE demoted."""
    ctx = RunContext(create=True)
    _boundaries(
        ctx,
        [
            {"segment_id": "seg_062", "start_ms": 100, "end_ms": 900},
            {"segment_id": "seg_070", "start_ms": 1000, "end_ms": 2000},
        ],
    )
    sel = {
        "ordered_segment_ids": [
            "seg_062la",
            "seg_062lb",
            "seg_062lc",
            "seg_070",
        ],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert not any("segment_starts_unavailable" in e for e in (result.errors or []))
    # Overlap collapse may keep a single 062* member; must not refuse.
    ordered = result.doc.get("ordered_segment_ids") or []
    assert "seg_070" in ordered
    assert any(str(x).startswith("seg_062") for x in ordered) or result.ok


def test_single_family_member_ok_without_starts() -> None:
    ctx = RunContext(create=True)
    sel = {
        "ordered_segment_ids": ["seg_031"],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    result = sanitize_master_selection(ctx, sel)
    assert result.ok


def test_chapters_emptied_by_sanitize_refuses() -> None:
    ctx = RunContext(create=True)
    deep = "seg_003aaaaa"
    _boundaries(
        ctx,
        [
            {"segment_id": deep, "start_ms": 0, "end_ms": 500},
            {"segment_id": "seg_040", "start_ms": 1000, "end_ms": 2000},
        ],
    )
    sel = {
        "ordered_segment_ids": [deep, "seg_040"],
        "excluded_segment_ids": [],
        "chapters": [{"title": "only deep", "segment_ids": [deep]}],
    }
    result = sanitize_master_selection(ctx, sel)
    # deep dropped → chapter empty → all chapters gone while order non-empty
    assert "seg_040" in result.doc["ordered_segment_ids"]
    assert result.doc.get("chapters") == []
    assert not result.ok
    assert any("chapters_emptied_by_sanitize" in e for e in result.errors)


def test_integrity_critical_in_sanitary_errors_pins_ranking(monkeypatch) -> None:
    ctx = RunContext(create=True)
    _boundaries(
        ctx,
        [{"segment_id": "seg_002", "start_ms": 0, "end_ms": 100}],
    )
    from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta

    doc = stamp_sanitize_meta(
        {
            "ordered_segment_ids": ["seg_002"],
            "excluded_segment_ids": [],
            "chapters": [],
        },
        ok=True,
        source="test",
        content_keys=["ordered_segment_ids", "order_content_hash"],
    )
    ctx._one_writer_raw = True
    ctx.write_json("master/selection.json", doc, skip_handoff=True)

    def _fake_collect(_ctx, _sel, **_kw):
        return [
            {
                "code": "mid_arc_reverse_jump",
                "severity": "critical",
                "message": "jump",
            }
        ]

    monkeypatch.setattr(
        "interview_mux.air_order_integrity.collect_violations",
        _fake_collect,
    )
    errs = selection_sanitary_errors(ctx)
    assert any("air_order_integrity_critical" in e for e in errs)
    assert producer_pin_for_token("; ".join(errs), ctx=ctx) == "full_master_ranking"


def test_freeze_restore_does_not_false_stamp_ok(monkeypatch) -> None:
    from interview_mux.air_order_boundary import _preserve_frozen_selection_order

    ctx = RunContext(create=True)
    deep = "seg_003aaaaa"
    _boundaries(
        ctx,
        [
            {"segment_id": deep, "start_ms": 0, "end_ms": 1000},
            {"segment_id": "seg_005", "start_ms": 2000, "end_ms": 3000},
        ],
    )
    dirty = {
        "ordered_segment_ids": [deep, "seg_005"],
        "excluded_segment_ids": [],
        "chapters": [],
    }
    restored = _preserve_frozen_selection_order(
        {"ordered_segment_ids": ["seg_005"], "excluded_segment_ids": [], "chapters": []},
        previous=dirty,
        prev_ids=[deep, "seg_005"],
        producer="artifact_sanitize.selection",
        stage_key="selection_order_sanitize",
        refuse_reason="meta_gate",
        ctx=ctx,
    )
    stamp = (restored.get("_meta") or {}).get("sanitize") or {}
    assert stamp.get("ok") is not True
    assert stamp.get("freeze_restore_unsanitary") or stamp.get("ok") is False


def test_cosmetic_restamp_requires_unchanged_ids(tmp_path, monkeypatch) -> None:
    from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "sos_restamp_guard")
    _boundaries(
        ctx,
        [
            {"segment_id": "seg_002", "start_ms": 0, "end_ms": 100},
            {"segment_id": "seg_003aaaaa", "start_ms": 0, "end_ms": 100},
        ],
    )
    # Stale stamp + order that needs mutating sanitize (deep fragment).
    doc = {
        "ordered_segment_ids": ["seg_002", "seg_003aaaaa"],
        "order_content_hash": "x",
        "excluded_segment_ids": [],
        "chapters": [],
        "_meta": {
            "sanitize": {
                "ok": True,
                "hash": "stale",
                "source": "test",
            }
        },
    }
    ctx._one_writer_raw = True
    ctx.write_json("master/selection.json", doc, skip_handoff=True)
    writes: list = []

    def _capture(ctx_arg, rel, payload, **kw):
        writes.append((rel, payload))
        path = ctx_arg.final_path(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    monkeypatch.setattr(
        "interview_mux.write_staging.write_committed_json",
        _capture,
    )
    errs = selection_sanitary_errors(ctx)
    assert errs
    assert any("needs_sanitize" in e or "fragment" in e for e in errs)
    assert not writes


def test_shape_tokens_pin_sanitize() -> None:
    assert (
        producer_pin_for_token("segment_starts_unavailable", ctx=None)
        == "selection_order_sanitize"
    )
    assert (
        producer_pin_for_token("chapters_emptied_by_sanitize", ctx=None)
        == "selection_order_sanitize"
    )
    assert (
        producer_pin_for_token(
            "sanitize_refused:selection: hard_keep_span_collision:a,b",
            ctx=None,
        )
        == "full_master_ranking"
    )
    assert (
        producer_pin_for_token(
            "framing:primary impact segment seg_012 excluded — never_exclude_primary_impact",
            ctx=None,
        )
        == "full_master_ranking"
    )


def test_order_shrink_triggers_lifecycle(monkeypatch) -> None:
    from interview_mux.air_order_boundary import commit_selection_mutation

    ctx = RunContext(create=True)
    deep = "seg_003aaaaa"
    _boundaries(
        ctx,
        [
            {"segment_id": deep, "start_ms": 0, "end_ms": 500},
            {"segment_id": "seg_050", "start_ms": 1000, "end_ms": 2000},
        ],
    )
    ctx._one_writer_raw = True
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": [deep, "seg_050"],
            "excluded_segment_ids": [],
            "chapters": [],
        },
        skip_handoff=True,
    )
    called: list = []

    def _on_changed(ctx_arg, **kwargs):
        called.append(kwargs)

    monkeypatch.setattr(
        "interview_mux.air_order_integrity.on_selection_order_changed",
        _on_changed,
    )
    sanitized = sanitize_master_selection(
        ctx,
        {
            "ordered_segment_ids": [deep, "seg_050"],
            "excluded_segment_ids": [],
            "chapters": [],
        },
    )
    assert sanitized.ok
    assert deep not in sanitized.doc["ordered_segment_ids"]
    commit_selection_mutation(
        ctx,
        sanitized.doc,
        producer="artifact_sanitize.selection",
        stage_key="selection_order_sanitize",
        checkpoint_mode="detect",
        skip_checkpoint=True,
        write_committed=True,
    )
    assert called
