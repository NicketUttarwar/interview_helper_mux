"""Land Honesty remutate unpaid-land matrix (edl_narrative_remutate).

MUX_FORENSICS=0. Covers active/exhausted remutate unpaid, from_stage pin
advisory filtering, orphan-promote skip, and land_honest vs hollow mark_done.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.delivery_guardrails import promote_complete_orphan_stage_done
from interview_mux.delivery_invariants import (
    REMUTATE_PLAN_RELS,
    active_remutate_stages,
)
from interview_mux.done_authority import (
    land_honest,
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw

_EDL_NARRATIVE_REMUTATE = "mastering/edl_narrative_remutate.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_land_honesty_remutate_matrix")


def _write_raw_json(ctx: RunContext, rel: str, doc: dict) -> Path:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _active_edl_narrative_plan(
    *,
    from_stage: str = "mix",
    from_stages: list[str] | None = None,
    attempt: int = 1,
    max_attempts: int = 3,
    exhausted: bool = False,
) -> dict:
    """Fixture shape matching ``_remutate_plan_active`` / ``REMUTATE_PLAN_RELS``."""
    assert _EDL_NARRATIVE_REMUTATE in REMUTATE_PLAN_RELS
    return {
        "version": 1,
        "from_stage": from_stage,
        "from_stages": from_stages
        if from_stages is not None
        else [from_stage, "junction_snip_qa"],
        "attempt": attempt,
        "max_attempts": max_attempts,
        "exhausted": exhausted,
    }


def test_active_edl_narrative_remutate_unpaid_blocks_mix_promote(ctx: RunContext) -> None:
    """Active (not exhausted) plan with from_stage=mix → remutate unpaid on mix."""
    _write_raw_json(
        ctx,
        _EDL_NARRATIVE_REMUTATE,
        _active_edl_narrative_plan(
            from_stage="mix",
            from_stages=["mix", "junction_snip_qa"],
            exhausted=False,
        ),
    )

    assert "mix" in active_remutate_stages(ctx)
    reason = unpaid_land_reason(ctx, "mix")
    assert reason is not None
    assert "remutate" in reason
    assert unpaid_land_blocks_promote(ctx, "mix") is True


def test_exhausted_remutate_clears_mix_unpaid(ctx: RunContext) -> None:
    """Exhausted remutate plan → mix not active; remutate unpaid clears."""
    _write_raw_json(
        ctx,
        _EDL_NARRATIVE_REMUTATE,
        _active_edl_narrative_plan(
            from_stage="mix",
            from_stages=["mix"],
            attempt=9,
            max_attempts=3,
            exhausted=True,
        ),
    )

    assert "mix" not in active_remutate_stages(ctx)
    reason = unpaid_land_reason(ctx, "mix")
    assert reason is None or "remutate" not in reason


def test_pin_at_junction_snip_qa_earlier_advisory_not_unpaid(ctx: RunContext) -> None:
    """Pin at junction_snip_qa: earlier advisory stages before pin are NOT unpaid."""
    _write_raw_json(
        ctx,
        _EDL_NARRATIVE_REMUTATE,
        _active_edl_narrative_plan(
            from_stage="junction_snip_qa",
            from_stages=[
                "air_script_seams",
                "edl",
                "mix",
                "junction_snip_qa",
            ],
            exhausted=False,
        ),
    )

    active = active_remutate_stages(ctx)
    assert "junction_snip_qa" in active
    # Per active_remutate_stages contract: stages before pin are advisory only.
    assert "air_script_seams" not in active
    assert "edl" not in active
    assert "mix" not in active

    for sid in ("air_script_seams", "edl", "mix"):
        reason = unpaid_land_reason(ctx, sid)
        assert reason is None or "remutate" not in reason

    reason_j = unpaid_land_reason(ctx, "junction_snip_qa")
    assert reason_j is not None
    assert "remutate" in reason_j


def test_promote_complete_orphan_skips_remutate_active_stages(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """promote_complete_orphan_stage_done skips remutate-active stages."""
    _write_raw_json(
        ctx,
        _EDL_NARRATIVE_REMUTATE,
        _active_edl_narrative_plan(
            from_stage="mix",
            from_stages=["mix", "junction_snip_qa"],
            exhausted=False,
        ),
    )
    assert "mix" in active_remutate_stages(ctx)

    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, sid: sid == "mix",
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _c, sid: None,
    )

    promoted = promote_complete_orphan_stage_done(ctx, ("mix",))
    assert "mix" not in promoted
    assert promoted == []
    assert not ctx.is_done("mix")


def test_land_honest_false_while_remutate_active_despite_mark_done_raw(
    ctx: RunContext,
) -> None:
    """land_honest False while remutate active even if mark_done_raw stamped."""
    _write_raw_json(
        ctx,
        _EDL_NARRATIVE_REMUTATE,
        _active_edl_narrative_plan(
            from_stage="mix",
            from_stages=["mix"],
            exhausted=False,
        ),
    )
    mark_done_raw(ctx, "mix")
    assert ctx.is_done("mix")

    reason = unpaid_land_reason(ctx, "mix")
    assert reason is not None
    assert "remutate" in reason
    assert land_honest(ctx, "mix") is False
