"""Disk-mapped hollow marker matrix — Land Honesty XC-HOLLOW.

Parametrize every ANALYSIS_ORDER + DELIVERY_ORDER stage that declares a
``STAGE_ARTIFACT_DISK_PATHS`` primary and is not ``GATE_MARKER_ONLY``:
marker-alone must never look land-honest / skippable / promotable-as-complete.

Also documents GATE_MARKER_ONLY: marker-without-primary is allowed for
``assert_may_mark_done`` / ``primary_disk_present``, but seed/land honesty still
requires the gate seed path (outputs present) — marker alone is not land_honest.

MUX_FORENSICS=0.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.artifact_ownership import assert_may_mark_done
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.done_authority import (
    GATE_MARKER_ONLY,
    land_honest,
    may_skip_as_complete,
    primary_disk_present,
    unpaid_land_blocks_promote,
)
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw

_DISK_MAPPED_HOLLOW_STAGES: list[str] = [
    sid
    for sid in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    if sid in STAGE_ARTIFACT_DISK_PATHS and sid not in GATE_MARKER_ONLY
]

_GATE_MARKER_ONLY_STAGES: list[str] = sorted(GATE_MARKER_ONLY)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_land_honesty_disk_mapped_hollow")


def test_disk_mapped_hollow_param_set_nonempty() -> None:
    assert _DISK_MAPPED_HOLLOW_STAGES, (
        "expected ANALYSIS+DELIVERY ∩ STAGE_ARTIFACT_DISK_PATHS − GATE_MARKER_ONLY"
    )
    # Gates are operator sign-offs outside disk-mapped live-order producers.
    for sid in GATE_MARKER_ONLY:
        assert sid not in _DISK_MAPPED_HOLLOW_STAGES
        assert sid not in STAGE_ARTIFACT_DISK_PATHS or sid not in (
            set(ANALYSIS_ORDER) | set(DELIVERY_ORDER)
        )


@pytest.mark.parametrize("sid", _DISK_MAPPED_HOLLOW_STAGES)
def test_disk_mapped_hollow_marker_not_land_honest(ctx: RunContext, sid: str) -> None:
    """mark_done_raw alone (no primary) must not count as complete land."""
    assert sid in STAGE_ARTIFACT_DISK_PATHS
    assert not ctx.artifact_exists(str(STAGE_ARTIFACT_DISK_PATHS[sid]))

    mark_done_raw(ctx, sid)
    assert ctx.is_done(sid)

    assert land_honest(ctx, sid) is False
    # Hollow cannot promote as complete: unpaid land blocks, and/or seed incomplete.
    assert unpaid_land_blocks_promote(ctx, sid) or seed_stage_complete(ctx, sid) is False
    assert may_skip_as_complete(ctx, sid) is False


@pytest.mark.parametrize("sid", _GATE_MARKER_ONLY_STAGES)
def test_gate_marker_only_allows_marker_without_primary(
    ctx: RunContext, sid: str
) -> None:
    """GATE_MARKER_ONLY: intentional marker-without-primary for assert_may_mark_done.

    Contract today: ``primary_disk_present`` is True (exempt), and
    ``assert_may_mark_done`` does not raise — but without the gate seed path
    (outputs), ``land_honest`` / ``seed_stage_complete`` / ``may_skip_as_complete``
    remain False. Marker alone is never a land-honest complete.
    """
    mark_done_raw(ctx, sid)
    assert ctx.is_done(sid)

    assert primary_disk_present(ctx, sid) is True
    assert_may_mark_done(ctx, sid)  # must not raise

    assert land_honest(ctx, sid) is False
    assert seed_stage_complete(ctx, sid) is False
    assert may_skip_as_complete(ctx, sid) is False
    # No unpaid-land family applies to bare gate markers.
    assert unpaid_land_blocks_promote(ctx, sid) is False
