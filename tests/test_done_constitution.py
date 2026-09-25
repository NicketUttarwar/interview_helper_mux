"""Heal Clinic hollow_pass B+ — Done Constitution.

MUX_FORENSICS=0: R1–R8 matrix for Partial + Full-auto.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import MUST_PRECEDE, producer_ready, seed_stage_complete
from interview_mux.delivery_invariants import apply_seed_order_heal
from interview_mux.done_authority import (
    GATE_MARKER_ONLY,
    RAW_STAMP_ALLOW,
    honest_restamp,
    may_post_master_backfill,
    may_skip_as_complete,
    primary_disk_present,
    raw_stamp_session,
    try_mark_done,
)
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "done_constitution_b_plus")


def test_exception_tables_populated() -> None:
    assert "transcript_review" in GATE_MARKER_ONLY
    assert "heal_or_refuse_mark" in RAW_STAMP_ALLOW
    assert "post_master_backfill" in RAW_STAMP_ALLOW
    assert "test_fixture" in RAW_STAMP_ALLOW


def test_r1_honest_restamp_refuses_hollow(ctx) -> None:
    # No primary for layup → restamp must not leave seed-complete.
    assert honest_restamp(ctx, "nugget_layup_compose") is False
    assert seed_stage_complete(ctx, "nugget_layup_compose") is False


def test_r1_apply_seed_order_heal_no_bare_touch(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.delivery_invariants.live_producer_authority",
        lambda _c, _p: True,
    )
    apply_seed_order_heal(ctx, "nugget_layup_compose", message="seed_order")
    # Must not become seed-complete via Path.touch
    assert seed_stage_complete(ctx, "nugget_layup_compose") is False


def test_r2_raw_stamp_session_rejects_unknown_reason(ctx) -> None:
    with pytest.raises(RuntimeError, match="RAW_STAMP_ALLOW"):
        with raw_stamp_session(ctx, "sneaky_unlisted"):
            pass


def test_r3_backfill_refuses_without_outputs(ctx) -> None:
    assert may_post_master_backfill(ctx, "transitions") is False


def test_r4_producer_ready_hollow_marker_not_ready(ctx) -> None:
    mark_done_raw(ctx, "transitions")
    assert producer_ready(ctx, "transitions") is False


def test_r4_must_precede_producers_marker_only(ctx) -> None:
    producers = sorted({p for prods in MUST_PRECEDE.values() for p in prods})
    for sid in producers[:12]:
        mark_done_raw(ctx, sid)
        assert producer_ready(ctx, sid) is False or sid in GATE_MARKER_ONLY


def test_r5_may_skip_requires_seed_complete(ctx) -> None:
    mark_done_raw(ctx, "edl")
    assert may_skip_as_complete(ctx, "edl") is False


def test_r6_disk_mapped_hollow_mark_not_seed_complete(ctx) -> None:
    # Sample of ANALYSIS + DELIVERY stages with disk paths
    sample = []
    for sid in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER):
        if sid in STAGE_ARTIFACT_DISK_PATHS and sid not in GATE_MARKER_ONLY:
            sample.append(sid)
        if len(sample) >= 15:
            break
    assert sample
    for sid in sample:
        mark_done_raw(ctx, sid)
        assert seed_stage_complete(ctx, sid) is False


def test_r8_partial_full_auto_parity(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    mark_done_raw(ctx, "vo_line_adjudicate")
    monkeypatch.setenv("MUX_PARTIAL", "1")
    a = producer_ready(ctx, "vo_line_adjudicate")
    sa = seed_stage_complete(ctx, "vo_line_adjudicate")
    monkeypatch.setenv("MUX_PARTIAL", "0")
    monkeypatch.setenv("MUX_FULL_AUTO", "1")
    b = producer_ready(ctx, "vo_line_adjudicate")
    sb = seed_stage_complete(ctx, "vo_line_adjudicate")
    assert a == b
    assert sa == sb


def test_gate_marker_only_primary_exempt() -> None:
    assert primary_disk_present  # import smoke
    assert "transcript_review" in GATE_MARKER_ONLY


def test_census_pack_and_modules_mention_apis() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src" / "interview_mux"
    assert "honest_restamp" in (src / "delivery_invariants.py").read_text(encoding="utf-8")
    assert "may_skip_as_complete" in (src / "pipeline.py").read_text(encoding="utf-8")
    assert "raw_stamp_session" in (src / "stage_completion.py").read_text(encoding="utf-8")
    assert "may_post_master_backfill" in (src / "homunculus" / "agenda.py").read_text(
        encoding="utf-8"
    )
    assert "unpaid_land_reason" in (src / "done_authority.py").read_text(encoding="utf-8")
    assert "unpaid_land_blocks_promote" in (src / "delivery_guardrails.py").read_text(
        encoding="utf-8"
    )


def test_try_mark_done_false_on_hollow_guarded(ctx) -> None:
    assert try_mark_done(ctx, "master_finalize") is False
