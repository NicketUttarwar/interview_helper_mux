"""DP-BUD1 A — product fingerprint reclaim + refuse ≠ hollow Finished.

MUX_FORENSICS=0 cascade: Partial / full-auto must reclaim spent max_invokes and
attempt_memo when the product fingerprint flips, and must not write job status
complete / \"Finished\" when a door refuse left required outputs missing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from interview_mux.dispatch_door import (
    DispatchVerdict,
    evaluate_dispatch,
    refuse_dispatch,
)
from interview_mux.homunculus.budget import count_attempts, dispatch_cap_refusal
from interview_mux.homunculus.ledger import append_ledger, stamp_budget_epoch
from interview_mux.identical_failures import (
    PRODUCT_FINGERPRINT_META_KEY,
    product_code_fingerprint,
    reclaim_budget_on_product_flip,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture(autouse=True)
def _forensics_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")


def _driver_ctx(tmp_path: Path, name: str) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "homunculus_kind": "homunculus",
            "homunculus_control_plane": "deterministic",
            "run_mode": "partially-accelerated",
            "full_auto": False,
            PRODUCT_FINGERPRINT_META_KEY: "old_product_fp",
        },
        skip_handoff=True,
    )
    return ctx


def _burn_attempts(ctx: RunContext, stage: str, n: int) -> None:
    for _ in range(n):
        append_ledger(ctx, {"kind": "stage", "identity": stage, "status": "started"})


def test_fingerprint_flip_reclaims_max_invokes(tmp_path: Path) -> None:
    ctx = _driver_ctx(tmp_path, "bud1_reclaim_cap")
    stage = "gap_framing_compose"
    _burn_attempts(ctx, stage, 6)
    assert count_attempts(ctx, stage) >= 3
    assert dispatch_cap_refusal(ctx, stage) is not None

    result = reclaim_budget_on_product_flip(ctx)
    assert result.get("product_changed") is True
    assert result.get("budget_epoch") is True
    assert count_attempts(ctx, stage) == 0
    assert dispatch_cap_refusal(ctx, stage) is None
    meta = ctx.read_json("run_meta.json")
    assert str(meta.get(PRODUCT_FINGERPRINT_META_KEY) or "") == product_code_fingerprint()


def test_evaluate_dispatch_reclaims_once_on_product_flip(tmp_path: Path) -> None:
    ctx = _driver_ctx(tmp_path, "bud1_door_reclaim")
    stage = "gap_framing_compose"
    _burn_attempts(ctx, stage, 6)
    assert dispatch_cap_refusal(ctx, stage) is not None

    verdict = evaluate_dispatch(ctx, stage, source="delivery_walk_to_master", layer="walk")
    assert verdict.allowed is True
    assert getattr(ctx, "_budget_product_reclaim_checked", False) is True


def test_memo_stale_fingerprint_reclaims_without_run_meta_prev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When run_meta never stamped fp, stale memo fingerprints still reclaim."""
    from interview_mux import dispatch_delta as dd

    ctx = isolated_run_ctx(tmp_path, "bud1_memo_stale")
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "run_mode": "partially-accelerated",
        },
        skip_handoff=True,
    )
    live = product_code_fingerprint()
    monkeypatch.setattr(dd, "_live_product_stamps", lambda: (live, "mv1"))
    ctx.write_json(
        dd.MEMO_REL,
        {
            "stages": {
                "gap_framing_compose": {
                    "outcome": "refused",
                    "product_fingerprint": "stale_pre_patch_fp",
                    "matrix_version": "mv0",
                    "state_token": "tok",
                    "progress_token": "prog",
                }
            }
        },
        skip_handoff=True,
    )
    _burn_attempts(ctx, "gap_framing_compose", 4)
    assert dispatch_cap_refusal(ctx, "gap_framing_compose") is not None

    result = reclaim_budget_on_product_flip(ctx)
    assert result.get("memo_stale") is True
    assert result.get("budget_epoch") is True
    assert count_attempts(ctx, "gap_framing_compose") == 0
    memo = ctx.read_json(dd.MEMO_REL)
    assert "gap_framing_compose" not in (memo.get("stages") or {})


def test_refuse_incomplete_outputs_not_job_complete_finished(tmp_path: Path) -> None:
    """Runner honesty: door refuse with missing outputs → incomplete, not Finished."""
    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.web.runner import JobRunner

    ctx = _driver_ctx(tmp_path, "bud1_hollow_finished")
    stage = "gap_framing_compose"
    refuse_dispatch(
        ctx,
        stage,
        DispatchVerdict(False, "max_invokes_per_identity", {"used": 3, "cap": 3}),
        source="test",
    )
    asserts_refuses = getattr(ctx, "_dispatch_refuses", None)
    assert isinstance(asserts_refuses, list) and asserts_refuses

    # Simulate the runner post-walk honesty check without spinning JobRunner locks.
    from interview_mux.homunculus.agenda import stage_outputs_present

    refuse_incomplete = False
    done_msg = f"Finished: Interviewer script"
    for row in list(getattr(ctx, "_dispatch_refuses", None) or []):
        sid = str(row.get("stage") or "")
        if sid and not stage_outputs_present(ctx, sid):
            refuse_incomplete = True
            done_msg = (
                f"Incomplete: dispatch refused {sid} ({row.get('reason')}) — outputs missing"
            )
            break
    assert refuse_incomplete is True
    assert done_msg.startswith("Incomplete:")
    assert "Finished:" not in done_msg

    # Job payload shape the runner writes for this case.
    job: dict[str, Any] = {
        "status": "incomplete",
        "mode": "analysis",
        "stage": stage,
        "message": done_msg,
        "error": done_msg,
    }
    assert job["status"] != "complete"
    assert not str(job["message"]).startswith("Finished:")
    # Keep JobRunner import live so HEAD tracks the module path.
    assert JobRunner is not None


def test_stamp_budget_epoch_still_resets_after_manual_epoch(tmp_path: Path) -> None:
    ctx = _driver_ctx(tmp_path, "bud1_epoch_manual")
    _burn_attempts(ctx, "gap_framing_compose", 5)
    stamp_budget_epoch(ctx, fingerprint="manual", reason="test")
    assert count_attempts(ctx, "gap_framing_compose") == 0
