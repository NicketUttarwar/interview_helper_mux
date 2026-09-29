"""action_oscillation must mean one writer reverted another, not two no-op rewrites.

On a real 6-minute run the gap report ledger read compose, layup, compose with
one identical hash for all three. Nothing had been undone, but the branch only
compared the first and third hashes, so the run halted at 51 of 72 with
authority_undo_thrash and nothing to repair.
"""

from __future__ import annotations

import pytest

from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import note_authority_undo_attempt


@pytest.fixture
def ctx() -> RunContext:
    rid = "exec_903_20260101T000000Z"
    c = RunContext(rid, create=True)
    c.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return c


def _note(ctx, action, h):
    return note_authority_undo_attempt(
        ctx, artifact="understanding/gap_report.json", action_class=action, content_hash=h
    )


def test_alternating_keys_with_identical_content_is_not_thrash(ctx) -> None:
    _note(ctx, "gap_framing_compose", "same")
    _note(ctx, "nugget_layup_compose", "same")
    row = _note(ctx, "gap_framing_compose", "same")
    assert not row.get("halt"), row


def test_a_real_revert_is_still_thrash(ctx) -> None:
    _note(ctx, "gap_framing_compose", "x")
    _note(ctx, "nugget_layup_compose", "y")
    row = _note(ctx, "gap_framing_compose", "x")
    assert row.get("halt"), row
    assert "oscillation" in str(row.get("reason")), row
