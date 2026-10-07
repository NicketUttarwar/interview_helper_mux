"""One authority decides whether a segment may come off air (ISSUES 74)."""

from __future__ import annotations

import inspect

import pytest

from interview_mux import removal_authority as ra


def _raw(ctx, rel: str, doc: dict) -> None:
    """Fixture state written past the sanitize bus (the states under test are
    exactly the ones the bus refuses)."""
    import json

    path = ctx.final_path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _ctx(tmp_path, monkeypatch, nle_overrides):
    from run_fixtures import minimal_manifest, minimal_manifest_segment
    from interview_mux.run_context import RunContext

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_removal_authority", create=True)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_058", start_ms=3100000, end_ms=3145830, text="z"),
            minimal_manifest_segment("seg_059", start_ms=3145830, end_ms=3148170, text="a"),
            minimal_manifest_segment("seg_060", start_ms=3148170, end_ms=3162250, text="b"),
            minimal_manifest_segment("seg_061", start_ms=3162250, end_ms=3200000, text="c"),
        ),
    )
    _raw(ctx, "segments/nle_edits.json", {"segment_overrides": nle_overrides})
    import interview_mux.hard_keep as hk

    monkeypatch.setattr(hk, "_drop_blank_unusable_keeps", lambda c, ids, *a, **k: ids)
    monkeypatch.setattr(hk, "_drop_orphan_keeps_not_in_manifest", lambda c, ids: ids)
    monkeypatch.setattr(hk, "_collapse_overlapping_keeps", lambda c, ids: ids)
    monkeypatch.setattr(
        "interview_mux.stages.audio_probes.authoritative_must_keep_ids",
        lambda c: {"seg_060"},
    )
    return ctx


# exec_055: seg_059 recut over seg_060, seg_060 retired under it.
CARRIED = {
    "seg_059": {"start_ms": 3145830, "end_ms": 3163670},
    "seg_060": {"excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll"},
}


def test_selection_write_cannot_drop_the_carrier(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, CARRIED)
    _raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_058", "seg_059", "seg_061"]})
    prev = ctx.read_json("master/selection.json")
    proposed = {
        "ordered_segment_ids": ["seg_058", "seg_061"],
        "excluded_segment_ids": [{"segment_id": "seg_059", "reason": "junction_snip_qa:on_a_roll"}],
    }
    out = ra.refuse_selection_removals(ctx, prev, proposed, producer="junction_snip_qa")
    assert out["ordered_segment_ids"] == ["seg_058", "seg_059", "seg_061"]
    assert out["excluded_segment_ids"] == []


def test_selection_write_may_drop_a_free_segment(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, CARRIED)
    _raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_058", "seg_059", "seg_061"]})
    prev = ctx.read_json("master/selection.json")
    proposed = {"ordered_segment_ids": ["seg_059", "seg_061"]}
    out = ra.refuse_selection_removals(ctx, prev, proposed, producer="junction_snip_qa")
    assert out["ordered_segment_ids"] == ["seg_059", "seg_061"]


def test_selection_write_cannot_drop_a_bare_keep(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, {})
    _raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_058", "seg_060", "seg_061"]})
    prev = ctx.read_json("master/selection.json")
    out = ra.refuse_selection_removals(
        ctx, prev, {"ordered_segment_ids": ["seg_058", "seg_061"]}, producer="full_master_ranking"
    )
    assert out["ordered_segment_ids"] == ["seg_058", "seg_060", "seg_061"]


def test_nle_exclude_of_the_carrier_is_refused(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, CARRIED)
    _raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_058", "seg_059", "seg_061"]})
    proposed = {
        "segment_overrides": {
            **CARRIED,
            "seg_059": {**CARRIED["seg_059"], "excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll"},
        }
    }
    out = ra.refuse_nle_excludes(ctx, proposed, producer="junction_snip_qa")
    row = out["segment_overrides"]["seg_059"]
    assert "excluded" not in row
    assert row["removal_refused"] == "hard_keep"
    # The retire of seg_060 under its carrier is still a legal write.
    assert out["segment_overrides"]["seg_060"]["excluded"] is True


def test_nle_retire_under_a_carrier_is_allowed(tmp_path, monkeypatch) -> None:
    """Entry 64: the keep's tape airs under seg_059, so excluding seg_060 passes."""
    ctx = _ctx(tmp_path, monkeypatch, {})
    _raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_058", "seg_059", "seg_061"]})
    out = ra.refuse_nle_excludes(ctx, {"segment_overrides": dict(CARRIED)}, producer="junction_snip_qa")
    assert out["segment_overrides"]["seg_060"]["excluded"] is True


def test_nle_exclude_of_a_bare_keep_is_refused(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, {})
    _raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_058", "seg_060", "seg_061"]})
    out = ra.refuse_nle_excludes(
        ctx,
        {"segment_overrides": {"seg_060": {"excluded": True, "exclude_reason": "x"}}},
        producer="edl_overlap_repair",
    )
    assert "excluded" not in out["segment_overrides"]["seg_060"]


def test_split_parent_exclude_is_not_a_removal(tmp_path, monkeypatch) -> None:
    """A split marks the parent excluded and airs its children; not a drop."""
    ctx = _ctx(tmp_path, monkeypatch, {})
    _raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_060a", "seg_060b"]})
    data = {"segment_overrides": {"seg_060": {"excluded": True, "split_into": ["seg_060a", "seg_060b"]}}}
    assert ra.refuse_nle_excludes(ctx, data, producer="nle_save") is data


@pytest.mark.parametrize(
    "module, fn_name",
    [
        ("interview_mux.air_order_boundary", "commit_selection_mutation"),
        ("interview_mux.nle_state", "save_nle"),
        ("interview_mux.edl_overlap_repair", "_update_nle"),
    ],
)
def test_every_off_air_write_consults_the_authority(module, fn_name) -> None:
    """Guard: the two ways off air (order drop, NLE exclude) both ask here."""
    import importlib

    fn = getattr(importlib.import_module(module), fn_name)
    assert "removal_authority" in inspect.getsource(fn)
