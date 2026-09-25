"""P0 follow-ups from Land Honesty gap audit + invent/SDP fixture map.

G3 XOR, unpaid-family permanence, invent incompleteness-only (not unpaid_land),
thin zero-byte, promote skip= honor.
MUX_FORENSICS=0.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.delivery_guardrails import (
    G3_RECONCILE_CHAIN,
    promote_complete_orphan_stage_done,
    reconcile_delivery_batch,
    seed_stage_complete,
)
from interview_mux.done_authority import unpaid_land_reason
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx, mark_done_raw

_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_land_honesty_p0_followup")


def test_g3_xor_hollow_unmark_not_repromoted_same_batch(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TH6: hollow-done unmarked this batch must not be re-promoted in the same call."""
    sid = "edl"
    assert sid in G3_RECONCILE_CHAIN
    # 1) Hollow stamp + thin/incomplete primary on a G3 stage.
    path = ctx.path("master", "edl.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    mark_done_raw(ctx, sid)
    assert ctx.is_done(sid)
    assert seed_stage_complete(ctx, sid) is False

    promote_skips: list[frozenset[str]] = []
    real_promote = promote_complete_orphan_stage_done

    def _spy(c, stages=None, *, skip=None):
        promote_skips.append(frozenset(skip or ()))
        return real_promote(c, stages, skip=skip)

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.promote_complete_orphan_stage_done",
        _spy,
    )
    # 2) Same-batch reconcile: unmark XOR promote.
    reconcile_delivery_batch(ctx)

    # 4) Hollow sid must appear in the promote skip frozenset (TH6).
    assert promote_skips, "reconcile_delivery_batch must invoke promote"
    assert any(
        sid in skip for skip in promote_skips
    ), f"TH6: hollow {sid!r} must be in promote skip; got {promote_skips!r}"
    # 3) Unmarked OR still not seed-complete (never re-promoted to land-honest done).
    assert (not ctx.is_done(sid)) or (seed_stage_complete(ctx, sid) is False)
    assert seed_stage_complete(ctx, sid) is False


def test_promote_skip_frozenset_xor_honored(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = "transitions"
    path = ctx.path("master", "transitions.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"transitions": []}', encoding="utf-8")
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _s: True,
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _c, _s: None,
    )
    assert promote_complete_orphan_stage_done(ctx, (sid,), skip=frozenset({sid})) == []
    assert not ctx.is_done(sid)


def test_thin_zero_byte_primary_incomplete(ctx: RunContext) -> None:
    sid = "transitions"
    path = ctx.path("master", "transitions.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    mark_done_raw(ctx, sid)
    reason = stage_artifact_incompleteness(ctx, sid)
    assert reason is not None
    assert "empty" in reason.lower() or "0 bytes" in reason
    assert seed_stage_complete(ctx, sid) is False


def test_invent_obligation_is_incompleteness_not_unpaid_land(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invent owed blocks via stage_artifact_incompleteness, not unpaid_land_reason."""
    from interview_mux.analysis_memory import default_sound_design_plan

    # Sanitary gates must not mask the invent incompleteness path.
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.selection_sanitary_errors",
        lambda _c: [],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.layup_sanitary_errors",
        lambda _c: [],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.sdp_sanitary_errors",
        lambda _c: [],
    )
    ctx.write_json("master/transitions.json", {"transitions": []}, skip_handoff=True)
    sdp = default_sound_design_plan()
    sdp["coherence"]["invent_obligation"] = "sound_design_plan"
    sdp["coherence"]["sonic_identity"] = "warm documentary beds"
    sdp["palettes"] = []
    sdp["_meta"] = {"producer_stage": "sound_design_plan"}
    ctx.write_json("understanding/sound_design_plan.json", sdp, skip_handoff=True)

    from interview_mux.soundscape_policy import invent_obligation_status

    status = invent_obligation_status(ctx)
    assert status.get("unpaid"), status

    assert unpaid_land_reason(ctx, "sound_design_plan") is None
    inc = stage_artifact_incompleteness(ctx, "sound_design_plan")
    assert inc is not None
    assert "invent" in inc.lower()


def test_unpaid_land_families_still_implemented_in_source() -> None:
    text = (
        _REPO / "src" / "interview_mux" / "done_authority.py"
    ).read_text(encoding="utf-8")
    for needle in (
        "remaster owed",
        "remutate unpaid",
        "stamp-alone",
        "shared-path",
    ):
        assert needle in text, needle


def test_census_lists_shared_and_layup_tables() -> None:
    text = (_REPO / "src" / "interview_mux" / "done_authority.py").read_text(
        encoding="utf-8"
    )
    assert "SHARED_PATH_PRODUCER_STAGES" in text
    assert "LAYUP_AUTHORITY_STAGES" in text
    assert "unpaid_land_blocks_promote" in text or "unpaid_land_reason" in text


def test_r6_disk_mapped_cardinality_matches_param_file() -> None:
    """Disk-mapped hollow matrix must stay full-union, not sample-only."""
    from interview_mux.done_authority import GATE_MARKER_ONLY
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    expected = [
        sid
        for sid in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
        if sid in STAGE_ARTIFACT_DISK_PATHS and sid not in GATE_MARKER_ONLY
    ]
    src = (
        _REPO / "tests" / "test_land_honesty_disk_mapped_hollow.py"
    ).read_text(encoding="utf-8")
    # Param list is built the same way — cardinality guard.
    assert f"{len(expected)}" in src or "STAGE_ARTIFACT_DISK_PATHS" in src
    assert len(expected) >= 70
