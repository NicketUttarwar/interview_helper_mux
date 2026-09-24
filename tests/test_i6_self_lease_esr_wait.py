"""i6: incomplete-after-conductor must not ESR-wait on self-lease."""

from __future__ import annotations

import os

os.environ["MUX_FORENSICS"] = "0"

from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def test_i6_self_lease_vo_synthesize_does_not_esr_wait(tmp_path, monkeypatch) -> None:
    """exec_13183: running vo_synthesize + incomplete on vo_synthesize → no wait."""
    from interview_mux.execution_status import should_wait_incomplete_after_conductor

    ctx = isolated_run_ctx(tmp_path, "exec_i6_self_lease")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _ctx: (True, "vo_synthesize"),
    )
    wait = should_wait_incomplete_after_conductor(ctx, pin="vo_synthesize")
    assert wait is None
