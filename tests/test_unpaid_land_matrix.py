"""Dig #2 — unpaid_land_reason matrix (Cluster A orphan promote / hollow done).

MUX_FORENSICS=0. Every unpaid family must block promote via unpaid_land_blocks_promote.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.delivery_guardrails import promote_complete_orphan_stage_done
from interview_mux.done_authority import (
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.mix_junction_seat import (
    begin_remaster,
    maybe_remaster_after_music_epoch,
    music_epoch_pre_beds_seat,
    note_speech_first_mix,
    remaster_owner,
    speech_first_remaster_owed,
)
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "unpaid_land_matrix")
    init_run_meta_for_test(c)
    return c


def _write_assembly(ctx: RunContext, *, age_sec: float = 120.0) -> Path:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    old = time.time() - age_sec
    os.utime(path, (old, old))
    return path


def test_unpaid_mix_remaster_in_flight(ctx: RunContext) -> None:
    _write_assembly(ctx)
    begin_remaster(ctx, owner="music_epoch")
    why = unpaid_land_reason(ctx, "mix")
    assert why is not None
    assert "remaster owed" in why
    assert unpaid_land_blocks_promote(ctx, "mix")
    assert unpaid_land_blocks_promote(ctx, "junction_snip_qa")


def test_unpaid_mix_music_epoch_pre_beds(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_assembly(ctx, age_sec=180.0)
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    assert maybe_remaster_after_music_epoch(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert music_epoch_pre_beds_seat(ctx) is True
    why = unpaid_land_reason(ctx, "mix")
    assert why is not None
    assert "music_epoch_pre_beds_seat" in why
    assert "junction" in (unpaid_land_reason(ctx, "junction_snip_qa") or "")


def test_unpaid_speech_first_before_owner_stamp(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_assembly(ctx)
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    # Owed without calling maybe_remaster — owner may be empty.
    assert speech_first_remaster_owed(ctx) is True
    why_mix = unpaid_land_reason(ctx, "mix")
    why_j = unpaid_land_reason(ctx, "junction_snip_qa")
    assert why_mix and "speech_first_remaster_owed" in why_mix
    assert why_j and "speech_first_remaster_owed" in why_j


def test_unpaid_layup_stamp_alone(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"nugget_layup_authority": True, "interviewer_lines": []},
    )
    assert not ctx.artifact_exists("understanding/nugget_layup_plan.json")
    why = unpaid_land_reason(ctx, "nugget_layup_compose")
    assert why is not None
    assert "stamp-alone" in why
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose")


def test_unpaid_remutate_active(ctx: RunContext) -> None:
    from interview_mux.delivery_invariants import REMUTATE_PLAN_RELS, active_remutate_stages

    rel = REMUTATE_PLAN_RELS[0]
    ctx.write_json(
        rel,
        {
            "attempt": 1,
            "max_attempts": 3,
            "from_stage": "edl",
            "from_stages": ["edl", "mix", "junction_snip_qa"],
        },
    )
    active = active_remutate_stages(ctx)
    assert active
    sid = next(iter(active))
    why = unpaid_land_reason(ctx, sid)
    assert why is not None
    assert "remutate unpaid" in why


def test_unpaid_shared_path_producer_mismatch(ctx: RunContext) -> None:
    # selection_order_sanitize shares master/selection.json — wrong producer_stage
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    rel = STAGE_ARTIFACT_DISK_PATHS.get("selection_order_sanitize")
    assert rel
    ctx.write_json(
        str(rel),
        {
            "ordered_segment_ids": ["seg_001"],
            "_meta": {"producer_stage": "full_master_ranking"},
        },
    )
    why = unpaid_land_reason(ctx, "selection_order_sanitize")
    assert why is not None
    assert "shared-path" in why
    assert unpaid_land_blocks_promote(ctx, "selection_order_sanitize")


def test_promote_refuses_all_unpaid_mix_cases(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_assembly(ctx, age_sec=180.0)
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )
    maybe_remaster_after_music_epoch(ctx)
    promoted = promote_complete_orphan_stage_done(ctx, ("mix", "junction_snip_qa"))
    assert "mix" not in promoted
    assert "junction_snip_qa" not in promoted
