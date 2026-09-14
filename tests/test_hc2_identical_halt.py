"""HC-2: identical ×3 halt honesty (MUX_FORENSICS=0).

New halt at ×3 still waits when producer files are fresh (1B).
Stamped halt:true is not waived by a later mtime (3A).
Driver stop consults is_halted, not local n≥3 (2A).
Do not start a run. HC-1 later_done stay open.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from interview_mux.identical_failures import (
    fail_key_signature,
    is_fail_key_halted,
    is_halted,
    upsert_fail_key,
)
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_driver as driver  # noqa: E402

_FAIL_KEY = "edl_qc:overlapping source range"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("hc2_halt", create=True)
    run.write_json("run_meta.json", {"homunculus_version": "0.1.0"}, skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _ctx: (False, ""),
    )
    monkeypatch.setattr(driver, "RUN_ID", run.run_id)
    monkeypatch.setattr(driver, "log", lambda *_a, **_k: None)
    driver._IDENTICAL_STAGE_FAILURES.clear()
    return run


def _plant_edl(ctx: RunContext, *, age_s: float = 0.0) -> Path:
    dest = ctx.run_dir / "master" / "edl.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('{"clips":[]}\n', encoding="utf-8")
    if age_s:
        old = time.time() - age_s
        os.utime(dest, (old, old))
    return dest


def test_hc2_fresh_mtime_does_not_stamp_halt(ctx: RunContext) -> None:
    _plant_edl(ctx, age_s=0.0)
    row = upsert_fail_key(
        ctx,
        _FAIL_KEY,
        3,
        failed_stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume_attempted="edl",
    )
    assert row["count"] == 3
    assert row["halt"] is False
    assert row.get("esr_softened") is True
    assert is_halted(ctx, row["signature"]) is False
    assert is_fail_key_halted(ctx, _FAIL_KEY) is False


def test_hc2_stale_files_stamp_halt(ctx: RunContext) -> None:
    _plant_edl(ctx, age_s=10_000)
    row = upsert_fail_key(
        ctx,
        _FAIL_KEY,
        3,
        failed_stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume_attempted="edl",
    )
    assert row["halt"] is True
    assert is_halted(ctx, row["signature"]) is True
    assert is_fail_key_halted(ctx, _FAIL_KEY) is True


def test_hc2_stamped_halt_survives_fresh_mtime(ctx: RunContext) -> None:
    _plant_edl(ctx, age_s=10_000)
    row = upsert_fail_key(
        ctx,
        _FAIL_KEY,
        3,
        failed_stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume_attempted="edl",
    )
    assert row["halt"] is True
    _plant_edl(ctx, age_s=0.0)
    assert is_halted(ctx, row["signature"]) is True
    again = upsert_fail_key(
        ctx,
        _FAIL_KEY,
        4,
        failed_stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume_attempted="edl",
    )
    assert again["halt"] is True
    assert is_fail_key_halted(ctx, _FAIL_KEY) is True


def test_hc2_count_three_without_stamp_is_not_halted_when_fresh(
    ctx: RunContext,
) -> None:
    """Local n≥3 is not a stop while ESR softened the stamp (1B + 2A)."""
    _plant_edl(ctx, age_s=0.0)
    sig = fail_key_signature(_FAIL_KEY)
    upsert_fail_key(
        ctx,
        _FAIL_KEY,
        3,
        failed_stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume_attempted="edl",
    )
    assert is_halted(ctx, sig) is False
    assert driver.identical_should_stop(
        _FAIL_KEY,
        stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume="edl",
    ) is False


def test_hc2_driver_stop_follows_stamped_halt(ctx: RunContext) -> None:
    _plant_edl(ctx, age_s=10_000)
    driver.bump_identical(
        _FAIL_KEY,
        stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume="edl",
    )
    driver.bump_identical(
        _FAIL_KEY,
        stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume="edl",
    )
    n = driver.bump_identical(
        _FAIL_KEY,
        stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume="edl",
    )
    assert n == 3
    assert driver.identical_should_stop(
        _FAIL_KEY,
        stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume="edl",
    ) is True
    _plant_edl(ctx, age_s=0.0)
    assert driver.identical_should_stop(
        _FAIL_KEY,
        stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume="edl",
    ) is True


def test_hc2_driver_n_three_fresh_does_not_stop(ctx: RunContext) -> None:
    _plant_edl(ctx, age_s=0.0)
    for _ in range(3):
        driver.bump_identical(
            _FAIL_KEY,
            stage="edl",
            producer="master/edl.json",
            reason="overlapping source range",
            resume="edl",
        )
    assert driver.identical_should_stop(
        _FAIL_KEY,
        stage="edl",
        producer="master/edl.json",
        reason="overlapping source range",
        resume="edl",
    ) is False


def test_hc2_batch_fill_rewrite_does_not_soften_halt(ctx: RunContext) -> None:
    dest = ctx.run_dir / "understanding" / "gap_evaluations.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('{"evaluations":[]}\n', encoding="utf-8")
    row = upsert_fail_key(
        ctx,
        "missing_framing:batch_fill",
        3,
        failed_stage="missing_framing",
        producer="understanding/gap_evaluations.json",
        reason="missing_framing batch_fill — resume missing_framing: LLM must score 2",
        resume_attempted="missing_framing",
        predicate_token="predicate_unchanged",
    )
    assert row["count"] == 3
    assert row["halt"] is True
    assert row.get("esr_softened") is not True
    assert is_fail_key_halted(ctx, "missing_framing:batch_fill") is True
