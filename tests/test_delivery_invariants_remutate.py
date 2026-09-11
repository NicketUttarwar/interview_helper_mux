
"""Remutate clear-set must honor from_stage pin."""

from __future__ import annotations

from pathlib import Path

from interview_mux.delivery_invariants import active_remutate_stages
from run_fixtures import isolated_run_ctx


def test_active_remutate_stages_honors_from_stage_pin(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "remutate_pin")
    ctx.write_json(
        "mastering/listen_delight_remutate.json",
        {
            "version": 1,
            "attempt": 1,
            "max_attempts": 3,
            "from_stage": "junction_snip_qa",
            "from_stages": [
                "air_script_seams",
                "edl",
                "mix",
                "junction_snip_qa",
                "listen_delight_audit",
            ],
            "exhausted": False,
        },
        skip_handoff=True,
    )
    active = active_remutate_stages(ctx)
    assert "junction_snip_qa" in active
    assert "air_script_seams" not in active
    assert "edl" not in active
