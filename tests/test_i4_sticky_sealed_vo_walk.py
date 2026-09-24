"""exec_13170: remutate must not block VO adjudicate while G1 open."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


def test_delivery_resume_skips_remutate_when_g1_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "i4_remutate_g1")
    driver_path = Path(__file__).resolve().parents[1] / "tools" / "full_auto_driver.py"
    spec = importlib.util.spec_from_file_location("full_auto_driver_i4", driver_path)
    assert spec and spec.loader
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    monkeypatch.setattr(driver, "RUN_ID", ctx.run_id)
    ctx.write_json(
        "mastering/listen_delight_remutate.json",
        {
            "version": 1,
            "attempt": 1,
            "max_attempts": 3,
            "exhausted": False,
            "from_stage": "transitions",
            "from_stages": ["transitions", "edl", "mix"],
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(driver, "_g1_vo_missing", lambda _ctx: ["vo_layup_seg_001"])
    resume = driver.delivery_resume_stage()
    assert resume != "transitions"
