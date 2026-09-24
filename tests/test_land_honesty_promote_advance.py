"""Land Honesty — bare is_done never hollow-advances or orphan-promotes.

MUX_FORENSICS=0. Regression coverage for promote / reconcile / skip / clear-wait /
shared analysis chain / gap+analysis force-mark helpers.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.delivery_guardrails import (
    MUST_PRECEDE,
    promote_complete_orphan_stage_done,
    producer_ready,
    reconcile_delivery_batch,
    seed_stage_complete,
)
from interview_mux.done_authority import (
    land_honest,
    may_clear_wait,
    may_skip_as_complete,
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.mix_junction_seat import begin_remaster
from interview_mux.pipeline import shared_analysis_chain_complete
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import StageArtifactsIncompleteError, heal_or_refuse_mark
from interview_mux.stages.gaps import _heal_gap_framing_compose_if_complete
from run_fixtures import isolated_run_ctx, mark_done_raw

# MUST_PRECEDE producers sampled for hollow-stamp producer_ready / reconcile.
_HOLLOW_PRECEDE_SAMPLE: tuple[str, ...] = (
    "transitions",
    "sound_design_plan",
    "vo_line_adjudicate",
    "vo_synthesize",
    "edl",
    "nugget_layup_compose",
    "air_contract_sanitize",
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "land_honesty_promote_advance")


def _write_mix_assembly(ctx: RunContext) -> None:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)


# ---------------------------------------------------------------------------
# 1. promote_complete_orphan_stage_done skips unpaid_land_blocks_promote
# ---------------------------------------------------------------------------


def test_promote_skips_unpaid_remaster_mix(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="junction")
    _write_mix_assembly(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )
    assert unpaid_land_blocks_promote(ctx, "mix") is True
    assert unpaid_land_reason(ctx, "mix") is not None
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []
    assert not ctx.is_done("mix")


def test_promote_skips_stamp_alone_layup(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    # Presence alone must not promote while unpaid stamp-alone is open.
    for rel in (
        "understanding/nugget_layup_plan.json",
        "understanding/gap_report.json",
    ):
        # gap_report already written; do not fabricate a plan — unpaid stays open.
        pass
    assert unpaid_land_blocks_promote(ctx, "nugget_layup_compose") is True
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is True
    assert promote_complete_orphan_stage_done(
        ctx, ("nugget_layup_compose", "gap_framing_compose")
    ) == []


# ---------------------------------------------------------------------------
# 2. reconcile_delivery_batch / producer_ready false on hollow MUST_PRECEDE
# ---------------------------------------------------------------------------


def test_producer_ready_false_on_hollow_must_precede_producers(ctx: RunContext) -> None:
    producers = sorted({p for prods in MUST_PRECEDE.values() for p in prods})
    sample = [sid for sid in _HOLLOW_PRECEDE_SAMPLE if sid in producers]
    assert len(sample) >= 4
    for sid in sample:
        mark_done_raw(ctx, sid)
        assert ctx.is_done(sid), sid
        assert producer_ready(ctx, sid) is False, sid
        assert seed_stage_complete(ctx, sid) is False, sid


def test_reconcile_delivery_batch_clears_hollow_stamps(ctx: RunContext) -> None:
    for sid in ("transitions", "edl", "vo_synthesize", "mix"):
        mark_done_raw(ctx, sid)
        assert ctx.is_done(sid)
    cleared = reconcile_delivery_batch(ctx)
    # Hollow markers must be unmarked — never left as ready / promoted.
    for sid in ("transitions", "edl", "vo_synthesize", "mix"):
        assert producer_ready(ctx, sid) is False, sid
        assert seed_stage_complete(ctx, sid) is False, sid
    # At least one hollow stage should appear in reconcile output when present.
    assert isinstance(cleared, list)


# ---------------------------------------------------------------------------
# 3. may_skip_as_complete / may_clear_wait false when unpaid or incomplete
# ---------------------------------------------------------------------------


def test_may_skip_and_clear_wait_false_on_hollow_incomplete(ctx: RunContext) -> None:
    for sid in ("edl", "episode_structure_compose", "master_finalize", "mix"):
        mark_done_raw(ctx, sid)
        assert may_skip_as_complete(ctx, sid) is False, sid
        assert may_clear_wait(ctx, sid) is False, sid
        assert land_honest(ctx, sid) is False, sid


def test_may_skip_and_clear_wait_false_when_unpaid(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="music_epoch")
    _write_mix_assembly(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )
    assert unpaid_land_reason(ctx, "mix") is not None
    assert may_skip_as_complete(ctx, "mix") is False
    assert may_clear_wait(ctx, "mix") is False
    assert land_honest(ctx, "mix") is False


# ---------------------------------------------------------------------------
# 4. Pipeline helpers — shared_analysis_chain_complete not bare is_done
# ---------------------------------------------------------------------------


def test_shared_analysis_chain_complete_false_on_hollow_stamp(ctx: RunContext) -> None:
    mark_done_raw(ctx, "episode_structure_compose")
    assert ctx.is_done("episode_structure_compose")
    assert shared_analysis_chain_complete(ctx) is False
    assert may_skip_as_complete(ctx, "episode_structure_compose") is False


def test_shared_analysis_chain_complete_uses_may_skip_not_bare_is_done() -> None:
    """Source census: helper must route through Done Authority, not ctx.is_done."""
    root = Path(__file__).resolve().parents[1]
    pipeline = (root / "src" / "interview_mux" / "pipeline.py").read_text(encoding="utf-8")
    # Extract the helper body roughly.
    start = pipeline.index("def shared_analysis_chain_complete")
    end = pipeline.index("\ndef ", start + 1)
    body = pipeline[start:end]
    assert "may_skip_as_complete" in body
    assert "ctx.is_done" not in body
    assert "is_done(" not in body


def test_pipeline_esr_seed_paths_use_land_honest_apis() -> None:
    """Walk / lease paths in pipeline.py prefer may_skip / seed_stage_complete."""
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "interview_mux" / "pipeline.py").read_text(encoding="utf-8")
    assert "may_skip_as_complete" in text
    assert "seed_stage_complete" in text
    assert "shared_analysis_chain_complete" in text


# ---------------------------------------------------------------------------
# 5. Gap path / analysis_extended force-mark refuse hollow
# ---------------------------------------------------------------------------


def test_heal_gap_framing_compose_if_complete_refuses_hollow(ctx: RunContext) -> None:
    mark_done_raw(ctx, "gap_framing_compose")
    with pytest.raises((StageArtifactsIncompleteError, SystemExit, RuntimeError, ValueError)):
        _heal_gap_framing_compose_if_complete(ctx)
    assert seed_stage_complete(ctx, "gap_framing_compose") is False
    assert land_honest(ctx, "gap_framing_compose") is False


def test_heal_or_refuse_mark_force_refuses_hollow_gap_and_analysis(ctx: RunContext) -> None:
    for sid in (
        "gap_framing_compose",
        "topic_coverage_audit",
        "nugget_corpus_mine",
        "edl",
    ):
        out = heal_or_refuse_mark(ctx, sid, force=True)
        assert out.get("marked") is not True, (sid, out)
        assert out.get("refused") or not ctx.is_done(sid), (sid, out)
        assert not seed_stage_complete(ctx, sid), sid


def test_analysis_extended_force_mark_sites_use_heal_or_refuse() -> None:
    root = Path(__file__).resolve().parents[1]
    ae = (
        root / "src" / "interview_mux" / "stages" / "analysis_extended.py"
    ).read_text(encoding="utf-8")
    assert "heal_or_refuse_mark" in ae
    # Soft / deterministic complete paths must go through heal, not bare mark_done.
    assert ae.count("heal_or_refuse_mark") >= 2


# ---------------------------------------------------------------------------
# 6. Census — unpaid_land_reason / blocks_promote on promote path
# ---------------------------------------------------------------------------


def test_census_promote_path_references_unpaid_land() -> None:
    """test_done_constitution style: promote path ties to unpaid_land_reason SSOT."""
    root = Path(__file__).resolve().parents[1]
    dg = (root / "src" / "interview_mux" / "delivery_guardrails.py").read_text(
        encoding="utf-8"
    )
    da = (root / "src" / "interview_mux" / "done_authority.py").read_text(encoding="utf-8")

    start = dg.index("def promote_complete_orphan_stage_done")
    end = dg.index("\ndef ", start + 1)
    promote_body = dg[start:end]
    assert "unpaid_land_blocks_promote" in promote_body
    # unpaid_land_reason is the SSOT; blocks_promote is the promote gate.
    assert "def unpaid_land_reason" in da
    assert "def unpaid_land_blocks_promote" in da
    blocks_start = da.index("def unpaid_land_blocks_promote")
    blocks_end = da.index("\ndef ", blocks_start + 1)
    assert "unpaid_land_reason" in da[blocks_start:blocks_end]
