"""G3 orphan promote unpaid land gate.

MUX_FORENSICS=0. Focused on promote_complete_orphan_stage_done refusing
stamp-through while remaster / layup stamp-alone / shared-path / remutate
obligations remain unpaid, plus a positive unpaid-clears vs thin-incompleteness
split.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.delivery_guardrails import (
    promote_complete_orphan_stage_done,
    seed_stage_complete,
)
from interview_mux.done_authority import (
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.mix_junction_seat import begin_remaster, clear_remaster
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_g3_promote_gate")


def _write_assembly(ctx: RunContext) -> Path:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    return path


def _write_raw_json(ctx: RunContext, rel: str, doc: dict) -> Path:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _mock_outputs_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )


def test_remaster_in_flight_promote_does_not_seed_complete_mix(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With remaster owed, orphan promote must not leave mix seed-complete."""
    begin_remaster(ctx, owner="junction")
    _write_assembly(ctx)
    _mock_outputs_present(monkeypatch)

    assert unpaid_land_reason(ctx, "mix") is not None
    assert unpaid_land_blocks_promote(ctx, "mix") is True
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []
    assert not ctx.is_done("mix")
    assert seed_stage_complete(ctx, "mix") is False


def test_layup_authority_without_plan_blocks_gap_framing_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Layup authority without plan: promote must not seed-complete gap_framing."""
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    _write_raw_json(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [{"id": "il_1", "text": "hi"}],
            "nugget_layup_authority": True,
            "_meta": {"producer_stage": "gap_framing_compose"},
        },
    )
    assert not ctx.artifact_exists("understanding/nugget_layup_plan.json")
    _mock_outputs_present(monkeypatch)

    reason = unpaid_land_reason(ctx, "gap_framing_compose")
    assert reason is not None
    assert "stamp-alone" in reason
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is True
    assert (
        promote_complete_orphan_stage_done(ctx, ("gap_framing_compose",)) == []
    )
    assert not ctx.is_done("gap_framing_compose")
    assert seed_stage_complete(ctx, "gap_framing_compose") is False


def test_shared_path_mismatch_skips_selection_order_sanitize(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wrong producer_stage on shared primary → promote skips sanitize stage."""
    _write_raw_json(
        ctx,
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "_meta": {"producer_stage": "full_master_ranking"},
        },
    )
    _mock_outputs_present(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _c, sid: None if sid == "selection_order_sanitize" else "other",
    )

    reason = unpaid_land_reason(ctx, "selection_order_sanitize")
    assert reason is not None
    assert "shared-path" in reason
    assert unpaid_land_blocks_promote(ctx, "selection_order_sanitize") is True
    promoted = promote_complete_orphan_stage_done(
        ctx, ("selection_order_sanitize",)
    )
    assert "selection_order_sanitize" not in promoted
    assert not ctx.is_done("selection_order_sanitize")


def test_active_remutate_target_not_promoted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Active remutate targeting a stage keeps that stage out of promote."""
    _write_raw_json(
        ctx,
        "mastering/listen_delight_remutate.json",
        {
            "attempt": 1,
            "max_attempts": 3,
            "from_stage": "edl",
            "from_stages": ["edl"],
            "exhausted": False,
        },
    )
    _write_raw_json(
        ctx,
        "master/edl.json",
        {"clips": [{"segment_id": "seg_001"}]},
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, sid: sid == "edl",
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _c, sid: None,
    )

    assert unpaid_land_reason(ctx, "edl") is not None
    assert "remutate" in (unpaid_land_reason(ctx, "edl") or "")
    promoted = promote_complete_orphan_stage_done(ctx, ("edl",))
    assert "edl" not in promoted
    assert not ctx.is_done("edl")


def test_positive_unpaid_clears_but_thin_incompleteness_still_blocks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After clear_remaster unpaid is gone; thin incompleteness may still refuse."""
    begin_remaster(ctx, owner="junction")
    assert unpaid_land_reason(ctx, "mix") is not None

    clear_remaster(ctx)
    _write_assembly(ctx)
    _mock_outputs_present(monkeypatch)

    # Separate axes: unpaid obligation paid vs artifact completeness.
    assert unpaid_land_reason(ctx, "mix") is None
    assert unpaid_land_blocks_promote(ctx, "mix") is False
    incomplete = stage_artifact_incompleteness(ctx, "mix")
    assert incomplete is not None

    promoted = promote_complete_orphan_stage_done(ctx, ("mix",))
    assert "mix" not in promoted
    assert not ctx.is_done("mix")
    assert seed_stage_complete(ctx, "mix") is False
