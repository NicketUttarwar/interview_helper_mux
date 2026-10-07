"""A hard keep folded into an on-air survivor by a fuse union is satisfied (ISSUES 64)."""

from __future__ import annotations

from interview_mux import edl_overlap_repair as eor


def _ctx(tmp_path, monkeypatch, overrides):
    from interview_mux.run_context import RunContext

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_keep_union", create=True)
    monkeypatch.setattr(
        "interview_mux.nle_state.load_nle", lambda c: {"segment_overrides": overrides}
    )
    return ctx


def test_junction_fuse_counts_as_consumed(tmp_path, monkeypatch) -> None:
    ctx = _ctx(
        tmp_path,
        monkeypatch,
        {
            "seg_060": {"excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll:fuse_noop_recut"},
            "seg_070": {"excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll:omit_noop_recut"},
            "seg_080": {"excluded": True, "exclude_reason": eor.STAGE_KEY},
        },
    )
    got = eor.consumed_segment_ids(ctx)
    assert "seg_060" in got
    assert "seg_080" in got
    assert "seg_070" not in got  # an omit drops audio; it never satisfies a keep


def test_hard_keep_list_drops_union_consumed(tmp_path, monkeypatch) -> None:
    import interview_mux.hard_keep as hk

    ctx = _ctx(
        tmp_path,
        monkeypatch,
        {"seg_060": {"excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll:fuse_x"}},
    )
    monkeypatch.setattr(hk, "_drop_blank_unusable_keeps", lambda c, ids, *a, **k: ids)
    monkeypatch.setattr(hk, "_drop_orphan_keeps_not_in_manifest", lambda c, ids: ids)
    monkeypatch.setattr(hk, "_collapse_overlapping_keeps", lambda c, ids: ids)
    monkeypatch.setattr(
        "interview_mux.stages.audio_probes.authoritative_must_keep_ids",
        lambda c: {"seg_059", "seg_060"},
    )
    assert hk.hard_keep_segment_ids(ctx) >= {"seg_059"}
    assert "seg_060" not in hk.hard_keep_segment_ids(ctx)


def test_retire_covered_by_an_extended_survivor_counts(tmp_path, monkeypatch) -> None:
    """exec_052: seg_059 extended over seg_060, retire stamped without fuse_."""
    ctx = _ctx(
        tmp_path,
        monkeypatch,
        {
            "seg_059": {"start_ms": 3145830, "end_ms": 3163670},
            "seg_060": {"excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll"},
            "seg_090": {"excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll"},
        },
    )
    from run_fixtures import minimal_manifest, minimal_manifest_segment

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_059", start_ms=3145830, end_ms=3148170, text="a"),
            minimal_manifest_segment("seg_060", start_ms=3148170, end_ms=3162250, text="b"),
            minimal_manifest_segment("seg_090", start_ms=3300000, end_ms=3310000, text="c"),
        ),
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_059"]})
    got = eor.consumed_segment_ids(ctx)
    assert "seg_060" in got
    assert "seg_090" not in got


def test_mostly_covered_retire_counts_but_a_sliver_does_not(tmp_path, monkeypatch) -> None:
    """exec_052: seg_024 recut to cover 97 % of seg_025."""
    from run_fixtures import minimal_manifest, minimal_manifest_segment

    ctx = _ctx(
        tmp_path,
        monkeypatch,
        {
            "seg_024": {"start_ms": 1392400, "end_ms": 1416660},
            "seg_025": {"excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll"},
            "seg_027": {"excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll"},
        },
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_024", start_ms=1387420, end_ms=1392000, text="a"),
            minimal_manifest_segment("seg_025", start_ms=1392000, end_ms=1416860, text="b"),
            minimal_manifest_segment("seg_027", start_ms=1416000, end_ms=1450000, text="c"),
        ),
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_024"]})
    got = eor.consumed_segment_ids(ctx)
    assert "seg_025" in got
    assert "seg_027" not in got


def test_carrier_of_a_retired_keep_inherits_the_keep(tmp_path, monkeypatch) -> None:
    """exec_055: seg_059 carried seg_060, then junction omitted seg_059 (ISSUES 73)."""
    import interview_mux.hard_keep as hk
    from run_fixtures import minimal_manifest, minimal_manifest_segment

    ctx = _ctx(
        tmp_path,
        monkeypatch,
        {
            "seg_059": {"start_ms": 3145830, "end_ms": 3163670},
            "seg_060": {"excluded": True, "exclude_reason": "junction_snip_qa:on_a_roll"},
        },
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_058", start_ms=3100000, end_ms=3145830, text="z"),
            minimal_manifest_segment("seg_059", start_ms=3145830, end_ms=3148170, text="a"),
            minimal_manifest_segment("seg_060", start_ms=3148170, end_ms=3162250, text="b"),
        ),
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_058", "seg_059"]})
    monkeypatch.setattr(hk, "_drop_blank_unusable_keeps", lambda c, ids, *a, **k: ids)
    monkeypatch.setattr(hk, "_drop_orphan_keeps_not_in_manifest", lambda c, ids: ids)
    monkeypatch.setattr(hk, "_collapse_overlapping_keeps", lambda c, ids: ids)
    monkeypatch.setattr(
        "interview_mux.stages.audio_probes.authoritative_must_keep_ids",
        lambda c: {"seg_060"},
    )
    keeps = hk.hard_keep_segment_ids(ctx)
    assert "seg_060" not in keeps
    assert "seg_059" in keeps  # omitting it would silently drop seg_060's tape
    assert "seg_058" not in keeps
